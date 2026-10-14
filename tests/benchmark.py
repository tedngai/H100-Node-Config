#!/usr/bin/env python3
"""Guarded short/long concurrency and retrieval tests. Never deploys or flushes cache."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import statistics
import threading
import time
import urllib.error
import uuid

from common import (Client, DEFAULT_CONTAINER, DEFAULT_URL, check_budget, digest,
                    experiment_lock, label, percentile, report_path, require_live,
                    scrub, stamp, verify_profile, write_json)
from prompts import build_prompts


def consume_stream(response, started, on_first_text=None):
    """SGLang SSE carries cumulative text and cumulative token counts.

    TTFT is arrival of the first non-empty decoded text, not the first SSE event.
    With speculative decoding an event can contain multiple tokens. Average TPOT
    is therefore an estimate, not a token-level latency distribution.
    """
    first_text = first_token_event = last_token_event = None
    first_count = last_count = last_text_count = 0
    final = None
    text = ""
    events = 0
    for raw in response:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        event = json.loads(payload)
        if "error" in event:
            raise RuntimeError("Server stream error: " + json.dumps(scrub(event["error"])))
        final = event
        events += 1
        current = event.get("text", "")
        count = event.get("meta_info", {}).get("completion_tokens", last_count)
        text_changed = bool(current) and current != text
        if text_changed or count > last_count:
            arrived = time.monotonic() - started
        if count > last_count:
            if first_token_event is None:
                first_token_event, first_count = arrived, count
            last_token_event, last_count = arrived, count
        if text_changed:
            last_text_count = count
            if first_text is None:
                first_text = arrived
                if on_first_text is not None:
                    on_first_text(started + arrived)
        text = current
    if final is None:
        raise RuntimeError("No generation events in stream")
    meta = final.get("meta_info", {})
    completion = meta.get("completion_tokens")
    if not isinstance(completion, int) or completion < 1 or first_text is None:
        raise RuntimeError("Missing completion-token accounting or decoded output")
    elapsed = time.monotonic() - started
    return {
        "elapsed_seconds": elapsed, "ttft_seconds": first_text,
        "first_token_event_seconds": first_token_event,
        "last_token_event_seconds": last_token_event,
        "first_event_completion_tokens": first_count,
        "average_tpot_seconds_estimate": ((last_token_event - first_token_event) / (completion - first_count)
                                          if completion > first_count and first_token_event is not None else None),
        "visible_output_characters": len(text),
        "completion_tokens_after_last_text_change": completion - last_text_count,
        "end_to_end_tokens_per_second": completion / elapsed,
        "stream_events": events, "meta_info": meta, "text": text,
    }


def generate(client, prompt, output_tokens, forced, on_first_text=None):
    started = time.monotonic()
    with client.open("/generate", {
        "input_ids": prompt["input_ids"], "stream": True,
        "sampling_params": {"temperature": 0, "max_new_tokens": output_tokens,
                            "ignore_eos": forced},
    }) as response:
        result = consume_stream(response, started, on_first_text=on_first_text)
    answer = result.pop("text").rsplit("</think>", 1)[-1]
    result["answer_excerpt"] = answer[:4096]
    result["retrieved_codes"] = {code: code in answer for code in prompt["expected_codes"]}
    result["retrieval_passed"] = all(result["retrieved_codes"].values())
    result["prompt_sha256"] = prompt["sha256"]
    return result


def sample_metrics(client):
    """Only DP1; take maxima over duplicate TP series, never sum replicas."""
    import re
    with client.open("/metrics") as response:
        text = response.read().decode()
    pattern = re.compile(r"^sglang:(num_running_reqs|num_queue_reqs|num_retracted_reqs|token_usage)(?:\{[^\n]*\})?\s+([-+\d.eE]+)$", re.M)
    values = {}
    for name, value in pattern.findall(text):
        values[name] = max(values.get(name, float("-inf")), float(value))
    if not values:
        raise ValueError("No recognized scheduler metrics")
    return {"at": stamp(), **values}


def sample_loads(client):
    """The read-only load snapshot works even when Prometheus metrics are disabled."""
    data = client.json("/v1/loads")
    rows = data.get("loads", [])
    if len(rows) != 1 or rows[0].get("dp_rank") != 0:
        raise ValueError("Load sampling requires exactly one DP0 snapshot")
    row = rows[0]
    if "num_running_reqs" not in row or "num_waiting_reqs" not in row:
        raise ValueError("Load snapshot lacks active/queue request counts")
    result = {"at": stamp(), "server_timestamp": row.get("timestamp"),
              "num_running_reqs": row["num_running_reqs"],
              "num_queue_reqs": row["num_waiting_reqs"]}
    if "token_usage" in row:
        result["token_usage"] = row["token_usage"]
    if "retracted" in row.get("queues", {}):
        result["num_retracted_reqs"] = row["queues"]["retracted"]
    return result


def summarize(rounds):
    samples = [sample for row in rounds for sample in row["samples"]]
    if not samples:
        return {"sample_count": 0}
    retractions = [s["meta_info"].get("num_retractions") for s in samples]
    return {
        "sample_count": len(samples),
        "median_aggregate_tokens_per_second": statistics.median(row["aggregate_tokens_per_second"] for row in rounds),
        "median_end_to_end_tokens_per_second_per_request": statistics.median(s["end_to_end_tokens_per_second"] for s in samples),
        "latency_p50_seconds": percentile([s["elapsed_seconds"] for s in samples], 0.5),
        "latency_p95_seconds": percentile([s["elapsed_seconds"] for s in samples], 0.95) if len(samples) >= 30 else None,
        "ttft_p50_seconds": percentile([s["ttft_seconds"] for s in samples], 0.5),
        "ttft_p95_seconds": percentile([s["ttft_seconds"] for s in samples], 0.95) if len(samples) >= 30 else None,
        "average_tpot_p50_seconds_estimate": percentile([s["average_tpot_seconds_estimate"] for s in samples], 0.5),
        "total_retractions": sum(retractions) if all(v is not None for v in retractions) else None,
        "percentile_caveat": "p95 omitted below 30 samples; larger sample counts still needed for reliable tails",
    }


def validate_samples(samples, prompt_tokens, output_tokens, forced, require_retrieval=None):
    if require_retrieval is None:
        require_retrieval = not forced
    for result in samples:
        meta = result["meta_info"]
        if meta.get("prompt_tokens") != prompt_tokens:
            raise RuntimeError("Input token count mismatch: possible truncation or wrong prompt accounting")
        if forced and meta.get("completion_tokens") != output_tokens:
            raise RuntimeError("Forced-output sample did not generate the requested token count")
        if meta.get("num_retractions", 0) > 0:
            raise RuntimeError("Request retracted; stop this workload and inspect the server")
        if require_retrieval and not result["retrieval_passed"]:
            raise RuntimeError("Retrieval failed; preserve report and investigate before increasing load")


def validate_observed_metrics(metrics, max_running=None):
    for sample in metrics["samples"]:
        if max_running is not None and sample.get("num_running_reqs", 0) > max_running:
            raise RuntimeError("More active requests than benchmark clients; unrelated traffic may be present")
        if sample.get("num_queue_reqs", 0) > 0:
            raise RuntimeError("Queueing observed; stop before submitting another round")
        # A sampled gauge is a stop signal, not a per-run event total.
        if sample.get("num_retracted_reqs", 0) > 0:
            raise RuntimeError("Scheduler retractions observed; inspect the server before proceeding")


def validate_warmup_policy(args):
    if type(args.warmup_passes) is not int or args.warmup_passes not in (1, 2, 3):
        raise ValueError("Warmup passes must be 1, 2, or 3")
    if args.cache != "warm" and args.warmup_passes != 1:
        raise ValueError("Extra warmup passes require --cache warm")


def run(args, report):
    validate_warmup_policy(args)
    client = Client(args.base_url, timeout=args.timeout)
    before = client.info()
    report["server_before"] = before
    report["profile"] = verify_profile(before["config"], args.profile)
    check_budget(before["config"], args.concurrency, args.prompt_tokens,
                 args.output_tokens, args.pool_fraction)
    report["configuration_drift"] = {}
    report["metrics"] = {"available": False, "samples": [], "errors": []}
    # Enabling metrics would change the baseline. Do not do that implicitly.
    metrics_enabled = before["config"].get("enable_metrics") is True
    metric_client = Client(args.base_url, timeout=3)
    sampler = sample_metrics if metrics_enabled else None
    try:
        idle = sample_loads(metric_client)
        report["initial_load_snapshot"] = idle
        if idle["num_running_reqs"] or idle["num_queue_reqs"]:
            raise RuntimeError("Engine is not idle; no benchmark requests submitted")
        sampler = sample_loads
        report["metrics"]["source"] = "/v1/loads"
    except RuntimeError:
        raise
    except Exception as error:
        report["metrics"]["load_snapshot_unavailable"] = str(error)
        if sampler:
            report["metrics"]["source"] = "/metrics"
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            try:
                report["metrics"]["samples"].append(sampler(metric_client))
                report["metrics"]["available"] = True
            except Exception as error:
                report["metrics"]["errors"].append(str(error))
            stop.wait(0.2)

    if not sampler:
        report["metrics"]["reason"] = "No usable load/metrics endpoint; actual active concurrency unverified"
    monitor_thread = threading.Thread(target=monitor, daemon=True) if sampler else None
    report["warmup"] = []
    report["warmup_policy"] = {
        "passes_per_prompt": args.warmup_passes if args.cache == "warm" else 0,
        "max_requests": args.concurrency * args.warmup_passes if args.cache == "warm" else 0,
        "forced_output": False,
        "timed_round_minimum_prefix_reuse": 0.9,
    }
    if monitor_thread:
        monitor_thread.start()
    try:
        warmed = None
        if args.cache == "warm":
            warmed = build_prompts(args.prompt_tokens, args.concurrency, report["run_id"],
                                   before["config"]["model_path"], args.seed, args.container,
                                   purpose=args.mode)
            # Extra passes are explicit and bounded, never an adaptive retry loop.
            # Hybrid caches may need a repeated prefix to materialize a branch checkpoint.
            for warmup_pass in range(args.warmup_passes):
                for prompt_index, prompt in enumerate(warmed):
                    validate_observed_metrics(report["metrics"], args.concurrency)
                    result = generate(client, prompt, args.output_tokens, False)
                    result["warmup_pass"] = warmup_pass
                    result["prompt_index"] = prompt_index
                    report["warmup"].append(result)
                    validate_samples([result], args.prompt_tokens, args.output_tokens, False,
                                     require_retrieval=args.mode == "retrieval")
                    validate_observed_metrics(report["metrics"], args.concurrency)

        for round_index in range(args.rounds):
            # Early unique session markers prevent cross-session/cross-round long-prefix sharing.
            prompts = warmed or build_prompts(
                args.prompt_tokens, args.concurrency, f'{report["run_id"]}-r{round_index}',
                before["config"]["model_path"], args.seed, args.container,
                purpose=args.mode,
            )
            barrier = threading.Barrier(args.concurrency)
            validate_observed_metrics(report["metrics"], args.concurrency)

            def worker(prompt):
                barrier.wait(timeout=30)
                return generate(client, prompt, args.output_tokens, args.mode == "decode")

            row = {"round": round_index, "samples": [], "errors": []}
            report["rounds"].append(row)
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [pool.submit(worker, p) for p in prompts]
                for future in futures:
                    try:
                        row["samples"].append(future.result())
                    except Exception as error:
                        row["errors"].append({"type": type(error).__name__, "message": str(error)})
            row["elapsed_seconds"] = time.monotonic() - started
            row["aggregate_tokens_per_second"] = sum(s["meta_info"]["completion_tokens"] for s in row["samples"]) / row["elapsed_seconds"]
            if row["errors"]:
                raise RuntimeError("A concurrent request failed; partial results retained")
            validate_samples(row["samples"], args.prompt_tokens, args.output_tokens, args.mode == "decode")
            validate_observed_metrics(report["metrics"], args.concurrency)
            if args.cache == "warm":
                hits = [s["meta_info"].get("cached_tokens") for s in row["samples"]]
                row["warm_cache_verified"] = all(isinstance(v, int) and v >= args.prompt_tokens * 0.9 for v in hits)
                if not row["warm_cache_verified"]:
                    raise RuntimeError("Warm run did not verify >=90% prefix reuse on every request")
            print(json.dumps({"round": round_index, "aggregate_tokens_per_second": row["aggregate_tokens_per_second"]}), flush=True)
    finally:
        stop.set()
        if monitor_thread:
            monitor_thread.join(timeout=5)
        try:
            after = client.info()
            report["server_after"] = after
            report["configuration_drift"] = {k: {"before": v, "after": after["config"].get(k)}
                for k, v in before["config"].items() if after["config"].get(k) != v}
        except Exception as error:
            report["server_after_error"] = str(error)
    if report.get("server_after_error") or report["configuration_drift"]:
        raise RuntimeError("Server health/configuration changed or could not be verified after the test")
    report["summary"] = summarize(report["rounds"])
    metrics = report["metrics"]
    for key in ("num_running_reqs", "num_queue_reqs", "num_retracted_reqs", "token_usage"):
        values = [s[key] for s in metrics["samples"] if key in s]
        metrics["peak_" + key] = max(values) if values else None
    if metrics.get("peak_num_queue_reqs", 0) and metrics["peak_num_queue_reqs"] > 0:
        raise RuntimeError("Queueing observed; this is not a no-queue concurrency result")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--profile", default="baseline")
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--mode", choices=("decode", "retrieval"), default="decode")
    parser.add_argument("--cache", choices=("cold", "warm"), default="cold")
    parser.add_argument("--warmup-passes", type=int, choices=(1, 2, 3), default=1,
                        help="Explicit sequential warmup passes per prompt; warm cache only, default 1")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--prompt-tokens", type=int, default=1024)
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--pool-fraction", type=float, default=0.9)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    try:
        validate_warmup_policy(args)
    except ValueError as error:
        parser.error(str(error))
    if min(args.concurrency, args.rounds, args.prompt_tokens, args.output_tokens, args.timeout) < 1:
        parser.error("Numeric arguments must be positive")
    report = {"schema_version": 2, "harness_revision": "token-event-timing-and-explicit-warmup-passes-v4",
              "kind": "benchmark", "label": args.label,
              "started_at": stamp(), "run_id": uuid.uuid4().hex,
              "workload": {k: v for k, v in vars(args).items() if k not in ("execute", "confirm_idle")},
              "rounds": [], "passed": False,
              "quality_scope": "Synthetic retrieval or forced-output speed only; not coding quality"}
    path = report_path(args.label)
    with experiment_lock():
        try:
            run(args, report)
            report["passed"] = True
        except Exception as error:
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        except KeyboardInterrupt:
            report["error"] = {"type": "KeyboardInterrupt", "message": "Interrupted; verify pending requests on server"}
        finally:
            report["finished_at"] = stamp()
            if "summary" not in report:
                completed = [row for row in report["rounds"] if "aggregate_tokens_per_second" in row]
                report["summary"] = summarize(completed)
                report["summary"]["incomplete_or_failed_run"] = True
            write_json(path, report)
    print(json.dumps({"report": str(path), "passed": report["passed"],
                      "summary": report.get("summary"), "error": report.get("error")}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
