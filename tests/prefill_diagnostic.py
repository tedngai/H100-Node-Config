#!/usr/bin/env python3
"""Separate, fixed 32K c2 cold scheduling diagnostic, never a no-queue benchmark.

Exactly one round, two requests, no warmup/retry/configuration change. Both live
confirmation flags are required. Initial waiting is observed for at most five
seconds from submission; normal benchmark.py queue checks are not changed.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import threading
import time
import uuid

from benchmark import generate, validate_samples
from common import (Client, DEFAULT_CONTAINER, DEFAULT_URL, check_budget,
                    experiment_lock, label, report_path, require_live, stamp,
                    verify_profile, write_json)
from prompts import build_prompts

CONCURRENCY = 2
PROMPT_TOKENS = 32768
OUTPUT_TOKENS = 512
REQUEST_TIMEOUT = 30
PREFILL_WINDOW = 5.0
POLL_SECONDS = 0.1
REQUIRED_COUNTS = ("num_running_reqs", "num_waiting_reqs",
                   "total_prefill_uncached_tokens", "total_prefill_busy_us")


def snapshot(client, origin):
    started = time.monotonic() - origin
    rows = client.json("/v1/loads").get("loads", [])
    if len(rows) != 1 or rows[0].get("dp_rank") != 0:
        raise ValueError("Diagnostic requires exactly one DP0 load snapshot")
    row = rows[0]
    # Do not retain the raw endpoint response or substitute zero for missing data.
    result = {key: row.get(key) for key in REQUIRED_COUNTS}
    result["num_retracted_reqs"] = (row.get("queues") or {}).get("retracted")
    for key, value in result.items():
        if type(value) is not int or value < 0:
            raise ValueError("Required count unavailable or invalid: " + key)
    timestamp = row.get("timestamp")
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp <= 0:
        raise ValueError("Published snapshot timestamp unavailable or invalid")
    age = time.time() - timestamp
    if not -1 <= age <= 2:
        raise ValueError("Load snapshot stale or clock comparison unreliable")
    result.update({"at": stamp(), "server_timestamp": timestamp,
                   "sample_started_seconds": started,
                   "sample_finished_seconds": time.monotonic() - origin})
    return result


def check_snapshot(row, first_submission=None, *, concurrency=CONCURRENCY,
                   prefill_window=PREFILL_WINDOW):
    if row["num_retracted_reqs"]:
        raise RuntimeError("Retraction observed in diagnostic")
    # Running batch + waiting are distinct counts, not an inference of GPU activity.
    if row["num_running_reqs"] + row["num_waiting_reqs"] > concurrency:
        raise RuntimeError("More reported requests than diagnostic clients")
    if (first_submission is not None and row["num_waiting_reqs"]
            and row["sample_started_seconds"] - first_submission > prefill_window):
        raise RuntimeError("Waiting observed beyond the predeclared prefill window")


def require_idle(row, *, concurrency=CONCURRENCY):
    check_snapshot(row, concurrency=concurrency)
    if row["num_running_reqs"] or row["num_waiting_reqs"]:
        raise RuntimeError("Engine is not idle; no diagnostic requests submitted")


def analyze(samples, requests, *, concurrency=CONCURRENCY):
    if not samples:
        raise ValueError("No load observations; queue classification unavailable")
    unique = []
    for row in samples:
        if unique and row["server_timestamp"] < unique[-1]["server_timestamp"]:
            raise ValueError("Published snapshot time moved backwards")
        if unique and row["server_timestamp"] == unique[-1]["server_timestamp"]:
            if any(row[key] != unique[-1][key] for key in (*REQUIRED_COUNTS, "num_retracted_reqs")):
                raise ValueError("Conflicting values for one published snapshot")
            continue
        if unique and any(row[key] < unique[-1][key] for key in
                          ("total_prefill_uncached_tokens", "total_prefill_busy_us")):
            raise ValueError("Cumulative prefill counter reset; attribution unavailable")
        unique.append(row)
    queued = [row for row in unique if row["num_waiting_reqs"] > 0]
    queued_reads = [row for row in samples if row["num_waiting_reqs"] > 0]
    all_text = (max(row["first_text_seconds"] for row in requests)
                if len(requests) == concurrency
                and all(row.get("first_text_seconds") is not None for row in requests)
                else None)
    # Use client-clock observation intervals. A queue snapshot whose GET overlaps
    # first-text arrival is ambiguous, not confidently classified as prefill-only.
    queued_before_text = (all_text is not None and bool(queued)
                          and all(row["sample_finished_seconds"] < all_text for row in queued_reads))
    progress = any(row["num_waiting_reqs"] > 0
                   and row["total_prefill_uncached_tokens"] > prev["total_prefill_uncached_tokens"]
                   and row["total_prefill_busy_us"] > prev["total_prefill_busy_us"]
                   for prev, row in zip(unique, unique[1:]))
    if all_text is None:
        classification = "inconclusive_missing_first_text"
    elif not queued:
        classification = "queue_not_reproduced"
    elif queued_before_text and progress:
        classification = "consistent_with_transient_prefill_waiting"
    else:
        classification = "inconclusive_queue_phase_or_prefill_progress"
    return {"classification": classification,
            "unique_published_snapshots": len(unique),
            "queued_unique_published_snapshots": len(queued),
            "queue_observed": bool(queued),
            "all_first_text_seconds": all_text,
            "all_queued_observations_before_all_first_text": queued_before_text,
            "all_queued_observations_before_both_first_text": queued_before_text if concurrency == 2 else None,
            "prefill_counters_progressed_while_waiting": progress,
            "peak_running_batch": max(row["num_running_reqs"] for row in unique),
            "peak_waiting": max(row["num_waiting_reqs"] for row in unique),
            "peak_retracted": max(row["num_retracted_reqs"] for row in unique),
            "prefill_token_counter_delta": unique[-1]["total_prefill_uncached_tokens"] - unique[0]["total_prefill_uncached_tokens"],
            "prefill_busy_us_counter_delta": unique[-1]["total_prefill_busy_us"] - unique[0]["total_prefill_busy_us"],
            "qualification": "Sampled temporal association, not an internal scheduler trace, exact queue duration or no-queue capacity qualification"}


def run_round(args, report, *, concurrency=CONCURRENCY, prompts=None,
              cache_policy="cold", prefill_window=PREFILL_WINDOW):
    """One monitored round; the original diagnostic CLI still fixes c2/cold/5s."""
    if type(concurrency) is not int or concurrency not in (1, 2, 4, 6) or prefill_window not in (5.0, 8.0):
        raise ValueError("Unsupported bounded round policy")
    if cache_policy not in ("cold", "warm", "warmup"):
        raise ValueError("Unsupported round cache policy")
    if cache_policy == "warmup" and concurrency != 1:
        raise ValueError("Warmup must remain sequential")
    if prompts is not None and len(prompts) != concurrency:
        raise ValueError("Prompt count differs from round concurrency")
    client = Client(args.base_url, timeout=REQUEST_TIMEOUT)
    metric_client = Client(args.base_url, timeout=2)
    before = client.info()
    report["server_before"] = before
    verify_profile(before["config"], "baseline")
    check_budget(before["config"], concurrency, PROMPT_TOKENS, OUTPUT_TOKENS)
    origin = time.monotonic()
    report["initial_load_snapshot"] = snapshot(metric_client, origin)
    require_idle(report["initial_load_snapshot"], concurrency=concurrency)
    if prompts is None:
        prompts = build_prompts(PROMPT_TOKENS, concurrency, report["run_id"],
                                before["config"]["model_path"], container=args.container,
                                purpose="decode")
    report["pre_submit_snapshot"] = snapshot(metric_client, origin)
    require_idle(report["pre_submit_snapshot"], concurrency=concurrency)
    report["load_samples"] = [report["pre_submit_snapshot"]]
    report["sampling_errors"] = []
    report["safety_errors"] = []
    report["requests"] = [{"prompt_index": i, "prompt_sha256": p["sha256"],
                           "submission_attempted": False} for i, p in enumerate(prompts)]
    stop = threading.Event()
    lock = threading.Lock()
    barrier = threading.Barrier(concurrency)

    def monitor():
        while not stop.is_set():
            try:
                row = snapshot(metric_client, origin)
                report["load_samples"].append(row)
                with lock:
                    starts = [r["started_seconds"] for r in report["requests"] if "started_seconds" in r]
                try:
                    check_snapshot(row, min(starts) if starts else None,
                                   concurrency=concurrency, prefill_window=prefill_window)
                except RuntimeError as error:
                    if str(error) not in report["safety_errors"]:
                        report["safety_errors"].append(str(error))
            except Exception as error:
                report["sampling_errors"].append(str(error))
            stop.wait(POLL_SECONDS)

    def worker(index):
        row = report["requests"][index]
        try:
            barrier.wait(timeout=5)
            with lock:
                row["started_seconds"] = time.monotonic() - origin
                row["submission_attempted"] = True

            def first_text(at):
                with lock:
                    row["first_text_seconds"] = at - origin

            forced = cache_policy != "warmup"
            row["result"] = generate(client, prompts[index], OUTPUT_TOKENS, forced,
                                     on_first_text=first_text)
            validate_samples([row["result"]], PROMPT_TOKENS, OUTPUT_TOKENS, forced,
                             require_retrieval=False)
            if row["result"]["meta_info"].get("num_retractions") != 0:
                raise RuntimeError("Per-request retractions are nonzero or unavailable")
            hits = row["result"]["meta_info"].get("cached_tokens")
            if type(hits) is not int or not 0 <= hits <= PROMPT_TOKENS:
                raise RuntimeError("Cache-hit accounting unavailable or invalid")
            if cache_policy == "cold" and hits != 0:
                raise RuntimeError("Cold round unexpectedly reused a cached prefix")
            if cache_policy == "warm" and hits < PROMPT_TOKENS * 0.9:
                raise RuntimeError("Warm round did not verify >=90% prefix reuse")
        except Exception as error:
            row["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            row["finished_seconds"] = time.monotonic() - origin

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        # There is deliberately no round loop and no resubmission or cancellation.
        measured_start = time.monotonic()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(worker, i) for i in range(concurrency)]
            for future in futures:
                future.result()
        report["measured_elapsed_seconds"] = time.monotonic() - measured_start
        watermark = max(row["server_timestamp"] for row in report["load_samples"])
    finally:
        stop.set()
        thread.join(timeout=3)
        if thread.is_alive():
            report["sampling_errors"].append("Load monitor did not stop")
        try:
            report["server_after"] = client.info()
            report["configuration_unchanged"] = report["server_after"]["config"] == before["config"]
        except Exception as error:
            report["server_after_error"] = str(error)

    # Require a newer published idle snapshot, rather than a cached pre-completion
    # value. This drain phase is GET-only; no further inference is submitted.
    deadline = time.monotonic() + 3
    while True:
        final = snapshot(metric_client, origin)
        report["load_samples"].append(final)
        report["final_load_snapshot"] = final
        starts = [r["started_seconds"] for r in report["requests"] if "started_seconds" in r]
        check_snapshot(final, min(starts) if starts else None,
                       concurrency=concurrency, prefill_window=prefill_window)
        if (final["server_timestamp"] > watermark
                and final["num_running_reqs"] == 0 and final["num_waiting_reqs"] == 0):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Fresh idle state not established after diagnostic")
        time.sleep(POLL_SECONDS)
    report["analysis"] = analyze(report["load_samples"], report["requests"], concurrency=concurrency)
    report["strict_no_queue_observed"] = not report["analysis"]["queue_observed"]
    if report["sampling_errors"] or report["safety_errors"]:
        raise RuntimeError("Diagnostic telemetry or safety check failed; no further submissions")
    if any("error" in row for row in report["requests"]):
        raise RuntimeError("Diagnostic request failed; partial observations retained")
    if report.get("server_after_error") or not report.get("configuration_unchanged"):
        raise RuntimeError("Server health/configuration could not be verified")
    if report["analysis"]["classification"].startswith("inconclusive"):
        raise RuntimeError("Queue phase diagnostic is inconclusive; do not increase load")


def run(args, report):
    # Preserve the original diagnostic protocol and CLI exactly.
    return run_round(args, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    report = {"schema_version": 1, "kind": "prefill-queue-diagnostic", "label": args.label,
              "started_at": stamp(), "run_id": uuid.uuid4().hex, "passed": False,
              "performance_qualified": False,
              "policy": {"profile": "baseline", "concurrency": CONCURRENCY,
                         "prompt_tokens": PROMPT_TOKENS, "output_tokens": OUTPUT_TOKENS,
                         "rounds": 1, "warmups": 0, "max_requests": CONCURRENCY,
                         "prefill_observation_window_seconds": PREFILL_WINDOW,
                         "request_timeout_seconds": REQUEST_TIMEOUT,
                         "strict_benchmark_zero_queue_policy_changed": False}}
    path = report_path(args.label)
    with experiment_lock():
        try:
            run(args, report)
            report["passed"] = True
        except Exception as error:
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        except KeyboardInterrupt:
            report["error"] = {"type": "KeyboardInterrupt", "message": "Interrupted; verify pending server requests"}
        finally:
            report["finished_at"] = stamp()
            write_json(path, report)
    print(json.dumps({"report": str(path), "passed": report["passed"],
                      "performance_qualified": False, "analysis": report.get("analysis"),
                      "error": report.get("error")}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
