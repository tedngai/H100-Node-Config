#!/usr/bin/env python3
"""Capacity-first short/long workload screening. Never deploys or flushes cache."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import statistics
import threading
import time
import urllib.error
import uuid

from common import (Client, DEFAULT_CONTAINER, DEFAULT_URL, check_budget, digest,
                    effective_active_request_limit,
                    experiment_lock, label, percentile, report_path, require_live,
                    scrub, stamp, verify_profile, write_json)
from gpu_memory import sample_gpu_memory, summarize_gpu_memory
from benchmark_policy import (describe_policy, memory_status, summarize_observations,
                              validate_observations)
from runtime_audit import audit, container_state, validate_audit
from prompts import CODING_CONTEXT_REVISION, build_prompts

MEMORY_PROFILES = frozenset({"memory-088", "memory-088-mtp-off", "memory-088-mamba-070",
                             "memory-088-mamba-070-ple-off"})


def is_memory_profile(profile):
    return profile in MEMORY_PROFILES


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
    answer_limit = 16384 if prompt.get("task_id") else 4096
    result["answer_excerpt"] = answer[:answer_limit]
    result["answer_excerpt_truncated"] = len(answer) > answer_limit
    result["retrieved_codes"] = {code: code in answer for code in prompt["expected_codes"]}
    result["retrieval_passed"] = all(result["retrieved_codes"].values())
    result["prompt_sha256"] = prompt["sha256"]
    if prompt.get("task_id"):
        result["task_id"] = prompt["task_id"]
        result["coding_context_revision"] = prompt.get("coding_context_revision")
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


def validate_samples(samples, prompt_tokens, output_tokens, forced, require_retrieval=None,
                     policy="capacity"):
    if require_retrieval is None:
        require_retrieval = not forced
    for result in samples:
        meta = result["meta_info"]
        if meta.get("prompt_tokens") != prompt_tokens:
            raise RuntimeError("Input token count mismatch: possible truncation or wrong prompt accounting")
        if forced and meta.get("completion_tokens") != output_tokens:
            raise RuntimeError("Forced-output sample did not generate the requested token count")
        if policy == "no-queue" and (meta.get("num_retractions") or 0) > 0:
            raise RuntimeError("Request retracted; stop this workload and inspect the server")
        if require_retrieval and not result["retrieval_passed"]:
            raise RuntimeError("Retrieval failed; preserve report and investigate before increasing load")


def validate_observed_metrics(metrics, max_running=None, policy="capacity"):
    validate_observations(metrics, max_running, policy)


def wait_for_idle(client, timeout=5, sampler=None):
    """Allow load-snapshot publication to catch up after completed streams."""
    deadline = time.monotonic() + timeout
    while True:
        snapshot = (sampler or sample_loads)(client)
        if snapshot.get("num_running_reqs") == 0 and snapshot.get("num_queue_reqs") == 0:
            return snapshot
        if time.monotonic() >= deadline:
            raise RuntimeError("Service did not return idle after completed requests")
        time.sleep(0.2)


def validate_warmup_policy(args):
    if type(args.warmup_passes) is not int or args.warmup_passes not in (1, 2, 3):
        raise ValueError("Warmup passes must be 1, 2, or 3")
    if args.cache != "warm" and args.warmup_passes != 1:
        raise ValueError("Extra warmup passes require --cache warm")


def planned_arrival_offsets(concurrency, stagger_seconds, timeout):
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
        raise ValueError("Concurrency must be a positive integer")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ValueError("Timeout must be a positive integer")
    if isinstance(stagger_seconds, bool) or not isinstance(stagger_seconds, (int, float)):
        raise ValueError("Arrival stagger must be a finite, nonnegative number")
    try:
        stagger_seconds = float(stagger_seconds)
    except (OverflowError, ValueError):
        raise ValueError("Arrival stagger must be a finite, nonnegative number") from None
    if not math.isfinite(stagger_seconds) or stagger_seconds < 0:
        raise ValueError("Arrival stagger must be a finite, nonnegative number")
    offsets = [index * stagger_seconds for index in range(concurrency)]
    if offsets[-1] > timeout:
        raise ValueError("Arrival schedule span cannot exceed the per-request timeout")
    return offsets


def wait_for_arrival_slot(round_started, scheduled_offset, *, clock=None, sleeper=None):
    clock = clock or time.monotonic
    sleeper = sleeper or time.sleep
    remaining = round_started + scheduled_offset - clock()
    if remaining > 0:
        sleeper(remaining)
    return clock() - round_started


def run(args, report):
    validate_warmup_policy(args)
    stagger_seconds = getattr(args, "arrival_stagger_seconds", 0.0)
    planned_offsets = planned_arrival_offsets(args.concurrency, stagger_seconds, args.timeout)
    policy = getattr(args, "policy", "capacity")
    warning_mib = getattr(args, "memory_warning_mib", 3072)
    stop_mib = getattr(args, "min_free_gpu_mib", None)
    memory_candidate = is_memory_profile(args.profile)
    audit_enabled = memory_candidate or getattr(args, "audit_container", False)
    report["policy"] = describe_policy(policy, warning_mib, stop_mib)
    report["runtime_audits"] = []
    report["warnings"] = []
    report["oom_observed"] = None
    initial_state = None
    if audit_enabled:
        initial_state = container_state(args.container)
        report["container_before"] = initial_state
        if not initial_state["running"] or initial_state["oom_killed"]:
            raise RuntimeError("Container not running or reports OOMKilled; no inference sent")
    client = Client(args.base_url, timeout=args.timeout)
    before = client.info()
    report["server_before"] = before
    report["profile"] = verify_profile(before["config"], args.profile)
    if initial_state and (initial_state["argv"] != report["profile"]["argv"] or
                          initial_state["image_id"] != report["profile"]["image_id"]):
        raise RuntimeError("Container image/argv does not match profile; no inference sent")
    report["effective_active_request_limit"] = effective_active_request_limit(
        before["config"], before.get("internal_states", []))
    check_budget(before["config"], args.concurrency, args.prompt_tokens,
                 args.output_tokens, args.pool_fraction,
                 internal_states=before.get("internal_states", []))
    if memory_candidate:
        # Refuse inference if the pre-test host memory query is unavailable.
        report["gpu_memory"] = {
            "source": "host nvidia-smi aggregate per-device usage",
            "sampling_interval_seconds": 1,
            "minimum_free_floor_mib": stop_mib,
            "warning_threshold_mib": warning_mib,
            "samples": [sample_gpu_memory()],
            "errors": [],
            "limitation": "One-second samples can miss transient peaks; aggregate device usage is not process attribution or OOM-safety proof.",
        }
        if stop_mib is not None and min(device["free_mib"] for device in report["gpu_memory"]["samples"][0]["devices"]) < stop_mib:
            raise RuntimeError("Initial free GPU memory is below the configured floor; no inference sent")
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
    if memory_candidate and not sampler:
        raise RuntimeError("Memory candidate requires live scheduler-load telemetry before inference")
    stop = threading.Event()

    def monitor():
        next_gpu_sample = time.monotonic() + 1
        while not stop.is_set():
            try:
                report["metrics"]["samples"].append(sampler(metric_client))
                report["metrics"]["available"] = True
            except Exception as error:
                report["metrics"]["errors"].append(str(error))
            if memory_candidate and time.monotonic() >= next_gpu_sample:
                try:
                    report["gpu_memory"]["samples"].append(sample_gpu_memory())
                except Exception as error:
                    report["gpu_memory"]["errors"].append(type(error).__name__)
                next_gpu_sample = time.monotonic() + 1
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

    prompt_set_id = getattr(args, "prompt_set_id", None) or report["run_id"]
    report["prompt_set_id"] = prompt_set_id

    def check_round(row):
        # HTTP completion, service health and actual traffic are the capacity gates.
        # Queue and low NVML-free memory are observations unless explicitly opted in.
        if sampler:
            row["loads_after"] = wait_for_idle(metric_client, sampler=sampler)
        health = client.info()
        row["service_ready"] = health["config"].get("status") == "ready"
        if health["config"] != before["config"] or not row["service_ready"]:
            raise RuntimeError("Service health/configuration changed; stop before another round")
        if audit_enabled:
            result = audit(args.container, report["started_at"])
            report["runtime_audits"].append(result)
            report["oom_observed"] = bool(result["oom_marker_lines"] or result["container"]["oom_killed"])
            expected = len(report["warmup"]) + sum(len(r["samples"]) for r in report["rounds"])
            validate_audit(result, initial_state, expected)

    try:
        warmed = None
        if args.cache == "warm":
            warmed = build_prompts(args.prompt_tokens, args.concurrency, prompt_set_id,
                                   before["config"]["model_path"], args.seed, args.container,
                                   purpose=args.mode)
            # Extra passes are explicit and bounded, never an adaptive retry loop.
            # Hybrid caches may need a repeated prefix to materialize a branch checkpoint.
            for warmup_pass in range(args.warmup_passes):
                for prompt_index, prompt in enumerate(warmed):
                    validate_observed_metrics(report["metrics"], args.concurrency, policy)
                    result = generate(client, prompt, args.output_tokens, False)
                    result["warmup_pass"] = warmup_pass
                    result["prompt_index"] = prompt_index
                    report["warmup"].append(result)
                    validate_samples([result], args.prompt_tokens, args.output_tokens, False,
                                      require_retrieval=args.mode == "retrieval", policy=policy)
                    validate_observed_metrics(report["metrics"], args.concurrency, policy)
                    check_round(result)

        for round_index in range(args.rounds):
            # Early unique session markers prevent cross-session/cross-round long-prefix sharing.
            prompts = warmed or build_prompts(
                args.prompt_tokens, args.concurrency, f'{prompt_set_id}-r{round_index}',
                before["config"]["model_path"], args.seed, args.container,
                purpose=args.mode,
            )
            barrier = threading.Barrier(args.concurrency) if stagger_seconds == 0 else None
            validate_observed_metrics(report["metrics"], args.concurrency, policy)

            def worker(prompt, client_index):
                if barrier is not None:
                    barrier.wait(timeout=30)
                    actual_offset = time.monotonic() - started
                else:
                    actual_offset = wait_for_arrival_slot(started, planned_offsets[client_index])
                result = generate(client, prompt, args.output_tokens, args.mode == "decode")
                result["client_index"] = client_index
                result["scheduled_arrival_offset_seconds"] = planned_offsets[client_index]
                result["client_start_offset_seconds"] = actual_offset
                return result

            row = {
                "round": round_index, "samples": [], "errors": [], "started_at": stamp(),
                "arrival_schedule": {
                    "mode": "synchronized" if barrier is not None else "staggered",
                    "stagger_seconds": float(stagger_seconds),
                    "planned_offsets_seconds": planned_offsets,
                },
            }
            report["rounds"].append(row)
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [pool.submit(worker, prompt, index)
                           for index, prompt in enumerate(prompts)]
                for future in futures:
                    try:
                        row["samples"].append(future.result())
                    except Exception as error:
                        row["errors"].append({"type": type(error).__name__, "message": str(error)})
            row["elapsed_seconds"] = time.monotonic() - started
            row["requests_finished_at"] = stamp()
            row["aggregate_tokens_per_second"] = sum(s["meta_info"]["completion_tokens"] for s in row["samples"]) / row["elapsed_seconds"]
            if row["errors"]:
                raise RuntimeError("A concurrent request failed; partial results retained")
            validate_samples(
                row["samples"], args.prompt_tokens, args.output_tokens,
                args.mode == "decode", require_retrieval=args.mode == "retrieval",
                policy=policy,
            )
            validate_observed_metrics(report["metrics"], args.concurrency, policy)
            if args.cache == "warm":
                hits = [s["meta_info"].get("cached_tokens") for s in row["samples"]]
                row["warm_cache_verified"] = all(isinstance(v, int) and v >= args.prompt_tokens * 0.9 for v in hits)
                if not row["warm_cache_verified"]:
                    raise RuntimeError("Warm run did not verify >=90% prefix reuse on every request")
            if memory_candidate:
                # A performance-monitor query failure is not an OOM event. An
                # explicitly requested hard floor still requires working telemetry.
                try:
                    report["gpu_memory"]["samples"].append(sample_gpu_memory())
                except Exception as error:
                    report["gpu_memory"]["errors"].append(type(error).__name__)
                    if stop_mib is not None:
                        raise RuntimeError("Cannot enforce explicit GPU memory floor") from error
                min_free = min(device["free_mib"]
                               for sample in report["gpu_memory"]["samples"]
                               for device in sample["devices"])
                row["minimum_sampled_free_gpu_mib"] = min_free
                if stop_mib is not None and min_free < stop_mib:
                    raise RuntimeError("GPU free-memory floor breached; stop before another round")
            check_round(row)
            row["completed"] = True
            print(json.dumps({"round": round_index, "aggregate_tokens_per_second": row["aggregate_tokens_per_second"]}), flush=True)
    finally:
        stop.set()
        if monitor_thread:
            monitor_thread.join(timeout=5)
        if memory_candidate:
            try:
                report["gpu_memory"]["samples"].append(sample_gpu_memory())
            except Exception as error:
                report["gpu_memory"]["errors"].append(type(error).__name__)
            try:
                report["gpu_memory"].update(
                    summarize_gpu_memory(report["gpu_memory"]["samples"]))
                report["gpu_memory"].update(memory_status(report["gpu_memory"], warning_mib, stop_mib))
            except Exception as error:
                report["gpu_memory"]["errors"].append(type(error).__name__)
                report["gpu_memory"]["floor_breached"] = None
        try:
            after = client.info()
            report["server_after"] = after
            report["configuration_drift"] = {k: {"before": v, "after": after["config"].get(k)}
                for k, v in before["config"].items() if after["config"].get(k) != v}
        except Exception as error:
            report["server_after_error"] = str(error)
        report["metrics"].update(summarize_observations(report["metrics"]))
        if report["metrics"].get("queue_observed"):
            report["warnings"].append("Queueing observed; included in end-to-end timing, not a capacity failure")
        if report["metrics"].get("peak_num_retracted_reqs"):
            report["warnings"].append("Scheduler retractions observed; completion does not imply stall-free service")
        if any((s["meta_info"].get("num_retractions") or 0) > 0
               for r in report["rounds"] for s in r["samples"]):
            report["warnings"].append("Request retractions observed")
        if report.get("gpu_memory", {}).get("low_memory_warning"):
            report["warnings"].append("Sampled free GPU memory below warning threshold; not an OOM event")
        telemetry_complete = bool(report["metrics"]["available"] and not report["metrics"]["errors"])
        if memory_candidate:
            telemetry_complete = telemetry_complete and not report["gpu_memory"]["errors"]
        report["telemetry_complete"] = telemetry_complete
        if not telemetry_complete:
            report["warnings"].append("Telemetry incomplete; missing metrics are unknown, not zero")
        if audit_enabled:
            try:
                result = audit(args.container, report["started_at"])
                report["runtime_audits"].append(result)
                report["oom_observed"] = bool(result["oom_marker_lines"] or result["container"]["oom_killed"])
                expected = len(report["warmup"]) + sum(len(r["samples"]) for r in report["rounds"])
                validate_audit(result, initial_state, expected)
            except Exception as error:
                report["runtime_audit_error"] = str(error)
                if not report["oom_observed"]:
                    report["oom_observed"] = None
    if report.get("server_after_error") or report["configuration_drift"]:
        raise RuntimeError("Server health/configuration changed or could not be verified after the test")
    if report.get("runtime_audit_error"):
        raise RuntimeError(report["runtime_audit_error"])
    if memory_candidate:
        if report["gpu_memory"]["floor_breached"]:
            raise RuntimeError("GPU free-memory floor breached; do not continue this candidate stage")
    report["summary"] = summarize(report["rounds"])
    validate_observed_metrics(report["metrics"], args.concurrency, policy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--profile", default="baseline")
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--mode", choices=("decode", "retrieval", "coding"), default="decode")
    parser.add_argument("--cache", choices=("cold", "warm"), default="cold")
    parser.add_argument("--warmup-passes", type=int, choices=(1, 2, 3), default=1,
                        help="Explicit sequential warmup passes per prompt; warm cache only, default 1")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--prompt-tokens", type=int, default=1024)
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--arrival-stagger-seconds", type=float, default=0.0,
                        help="Seconds between request starts per round; 0 synchronizes arrivals")
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--prompt-set-id", type=label,
                        help="Stable prompt namespace for matched A/B runs; use the same value in each arm")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--pool-fraction", type=float, default=0.9)
    parser.add_argument("--policy", choices=("capacity", "no-queue"), default="capacity",
                        help="capacity (default): measure waiting/retractions without failing completed work")
    parser.add_argument("--memory-warning-mib", type=int, default=3072,
                        help="Advisory per-GPU free-memory threshold; never fails capacity runs")
    parser.add_argument("--audit-container", action="store_true",
                        help="Audit container identity/OOM markers and exact inference traffic; automatic for memory-088")
    parser.add_argument("--min-free-gpu-mib", type=int,
                        help="Optional explicit hard floor for memory-088; omitted by default, never cancels in-flight work")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    if args.min_free_gpu_mib is not None and args.min_free_gpu_mib < 1:
        parser.error("--min-free-gpu-mib must be positive")
    if args.min_free_gpu_mib is not None and not is_memory_profile(args.profile):
        parser.error("--min-free-gpu-mib requires a memory-088 candidate with GPU sampling")
    if args.memory_warning_mib < 0:
        parser.error("--memory-warning-mib must be nonnegative")
    try:
        validate_warmup_policy(args)
    except ValueError as error:
        parser.error(str(error))
    if min(args.concurrency, args.rounds, args.prompt_tokens, args.output_tokens, args.timeout) < 1:
        parser.error("Numeric arguments must be positive")
    try:
        planned_arrival_offsets(args.concurrency, args.arrival_stagger_seconds, args.timeout)
    except ValueError as error:
        parser.error(str(error))
    report = {"schema_version": 3, "harness_revision": "capacity-first-v1",
              "kind": "benchmark", "label": args.label,
              "started_at": stamp(), "run_id": uuid.uuid4().hex,
              "workload": {k: v for k, v in vars(args).items() if k not in ("execute", "confirm_idle")},
               "policy": describe_policy(args.policy, args.memory_warning_mib, args.min_free_gpu_mib),
               "rounds": [], "passed": False, "capacity_passed": False,
              "quality_scope": ("Code-edit prompts; generated patches are captured for review, not automatically executed or quality-graded"
                                 if args.mode == "coding" else
                                 "Synthetic retrieval or forced-output speed only; not coding quality")}
    if args.mode == "coding":
        report["coding_prompt_context_revision"] = CODING_CONTEXT_REVISION
    path = report_path(args.label)
    with experiment_lock():
        try:
            run(args, report)
            report["passed"] = True
            report["capacity_passed"] = True
        except Exception as error:
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        except KeyboardInterrupt:
            report["error"] = {"type": "KeyboardInterrupt", "message": "Interrupted; verify pending requests on server"}
        finally:
            report["finished_at"] = stamp()
            report["completed_requests"] = sum(len(row["samples"]) for row in report["rounds"])
            report["expected_requests"] = args.concurrency * args.rounds
            report["production_qualified"] = False
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
