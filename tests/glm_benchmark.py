#!/usr/bin/env python3
"""Capacity-first GLM-5.3-Flash / TensorFold short and long workload screening.

The workload is bounded: one mode, one cache state, one concurrency, N rounds.
It never deploys, restarts, flushes cache, or changes server settings.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import statistics
import threading
import time
import uuid
from pathlib import Path

from common import (experiment_lock, label, percentile, report_path, require_live,
                    stamp, write_json)
from glm_common import (Client, DEFAULT_CONTAINER, DEFAULT_URL, check_budget, chat_stream,
                        decode_prompt, health_snapshot, retrieval_prompt, scan_rank_logs,
                        validate_glm_audit)
from runtime_audit import audit, container_state

LOG_DIR = Path(os.environ.get("GLM_LOG_DIR", "/home/tngai/GLM53-Flash-EXL3-H100-Test/logs"))
RANK_LOG_PATHS = [LOG_DIR / f"rank{r}.log" for r in range(4)]


def load_profile(name):
    path = Path(__file__).resolve().parents[1] / "configs" / "glm53-production.json"
    data = json.loads(path.read_text())
    if data.get("label") != name:
        raise ValueError(f"Profile {name!r} does not match {path}")
    return data


def verify_profile(config, profile):
    expected = profile.get("expected_config") or {}
    differences = {key: {"expected": value, "actual": config.get(key)}
                   for key, value in expected.items() if config.get(key) != value}
    if differences:
        raise ValueError("Live server does not match profile: " + json.dumps(differences))
    return profile


def wait_idle(client, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.idle():
            return True
        time.sleep(0.2)
    return False


def build_prompts(client, args, round_index, warm_prompts=None):
    if warm_prompts is not None:
        return warm_prompts
    prompts = []
    for index in range(args.concurrency):
        run_id = f"{args.seed}-r{round_index}-q{index}-{uuid.uuid4().hex[:8]}"
        if args.mode == "retrieval":
            prompt = retrieval_prompt(client, args.prompt_tokens, args.seed, run_id)
        else:
            prompt = decode_prompt(client, args.prompt_tokens, args.seed, run_id)
        prompts.append(prompt)
    return prompts


def one_request(client, prompt, args, barrier):
    barrier.wait(timeout=120)
    result = chat_stream(
        client, prompt["messages"], args.output_tokens,
        ignore_eos=(args.mode == "decode"),
        thinking=False,
    )
    result["expected_codes"] = prompt["expected_codes"]
    result["prompt_sha256"] = prompt["sha256"]
    result["target_prompt_tokens"] = prompt["actual_tokens"]
    answer = result.pop("text")
    result["answer_excerpt"] = answer[:4096]
    result["retrieved_codes"] = {code: code in answer for code in prompt["expected_codes"]}
    result["retrieval_passed"] = all(result["retrieved_codes"].values()) if prompt["expected_codes"] else None
    return result


def run_round(client, prompts, args, round_index, expected_requests):
    samples = []
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            try:
                samples.append(health_snapshot(client))
            except Exception:  # noqa: BLE001 - telemetry gaps are reported, not invented
                pass
            stop.wait(0.25)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    barrier = threading.Barrier(args.concurrency)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(one_request, client, prompt, args, barrier) for prompt in prompts]
        results = [future.result() for future in futures]
    wall = time.monotonic() - started
    idle = wait_idle(client)
    stop.set()
    sampler.join(timeout=2)

    if not idle:
        raise RuntimeError("Service did not return idle after the round")
    for result in results:
        if args.mode == "decode" and result["completion_tokens"] != args.output_tokens:
            raise RuntimeError("Forced-output sample did not generate the requested token count")
        if args.mode == "retrieval" and not result["retrieval_passed"]:
            raise RuntimeError("Retrieval failed; preserve report and investigate before increasing load")
        if args.cache == "warm" and result["cached_tokens"] < 0.9 * result["prompt_tokens"]:
            raise RuntimeError("Warm sample reused less than 90% of its prompt; mislabeled workload")
        # TensorFold's /tokenize renders the chat template slightly differently from
        # the chat route (a few template tokens); the prompt builder targets a size
        # within ~5% and both counts are recorded for every sample.
        tolerance = max(16, result["target_prompt_tokens"] // 20)
        if abs(result["prompt_tokens"] - result["target_prompt_tokens"]) > tolerance:
            raise RuntimeError("Input token count mismatch between /tokenize and usage")

    completion = sum(result["completion_tokens"] for result in results)
    round_row = {
        "round": round_index,
        "wall_seconds": wall,
        "aggregate_tokens_per_second": completion / wall,
        "requests": len(results),
        "completion_tokens": completion,
        "prompt_tokens": [result["prompt_tokens"] for result in results],
        "cached_tokens": [result["cached_tokens"] for result in results],
        "samples": results,
        "health": {
            "sample_count": len(samples),
            "peak_decoding": max((s.get("decoding") or 0) for s in samples) if samples else None,
            "peak_requests_running": max((s.get("requests_running") or 0) for s in samples) if samples else None,
            "min_pool_free_tokens": min((s["pool_free_tokens"] for s in samples
                                         if s.get("pool_free_tokens") is not None), default=None),
        },
        "health_after": health_snapshot(client),
    }
    return round_row


def summarize(rounds):
    samples = [sample for row in rounds for sample in row["samples"]]
    if not samples:
        return {"sample_count": 0}
    return {
        "sample_count": len(samples),
        "median_aggregate_tokens_per_second": statistics.median(
            row["aggregate_tokens_per_second"] for row in rounds),
        "median_end_to_end_tokens_per_second_per_request": statistics.median(
            sample["completion_tokens"] / sample["elapsed_seconds"] for sample in samples),
        "latency_p50_seconds": percentile([s["elapsed_seconds"] for s in samples], 0.5),
        "latency_p95_seconds": percentile([s["elapsed_seconds"] for s in samples], 0.95)
        if len(samples) >= 30 else None,
        "ttft_p50_seconds": percentile([s["ttft_seconds"] for s in samples], 0.5),
        "ttft_p95_seconds": percentile([s["ttft_seconds"] for s in samples], 0.95)
        if len(samples) >= 30 else None,
        "median_decode_tokens_per_second_estimate": statistics.median(
            s["completion_tokens"] / max(1e-9, s["elapsed_seconds"] - (s["ttft_seconds"] or 0))
            for s in samples),
        "percentile_caveat": "p95 omitted below 30 samples; larger sample counts still needed for reliable tails",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--profile", default="glm53-flash-exl3-1m")
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--mode", choices=("decode", "retrieval"), default="decode")
    parser.add_argument("--cache", choices=("cold", "warm"), default="cold")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--prompt-tokens", type=int, default=1024)
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261019)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    if args.rounds < 1 or args.concurrency < 1:
        parser.error("rounds and concurrency must be positive")

    report = {
        "schema_version": 1,
        "kind": "glm-capacity-benchmark",
        "label": args.label,
        "started_at": stamp(),
        "base_url": args.base_url,
        "policy": "capacity",
        "production_qualified": False,
        "workload": {
            "mode": args.mode, "cache": args.cache, "concurrency": args.concurrency,
            "prompt_tokens": args.prompt_tokens, "output_tokens": args.output_tokens,
            "rounds": args.rounds, "seed": args.seed,
        },
        "warnings": [],
    }
    path = report_path(args.label)
    with experiment_lock():
        client = Client(args.base_url, timeout=args.timeout)
        try:
            profile = load_profile(args.profile)
            before = client.info()
            report["profile"] = verify_profile(before["config"], profile)
            report["server_before"] = before
            check_budget(before["config"], args.concurrency, args.prompt_tokens, args.output_tokens)
            if not client.idle():
                raise RuntimeError("Service is not idle; no inference sent")
            initial_state = container_state(args.container)
            report["container_before"] = initial_state
            report["traffic_before"] = {
                "requests_total": before["health"].get("requests_total"),
                "prompt_tokens_total": before["health"].get("prompt_tokens_total"),
                "completion_tokens_total": before["health"].get("completion_tokens_total"),
            }

            warm_prompts = None
            warmups = 0
            if args.cache == "warm":
                warm_prompts = build_prompts(client, args, "warm")
                for prompt in warm_prompts:
                    if args.mode == "decode":
                        # Prompt-cache warmup: force one token so the prefill state is
                        # kept. A longer unforced warmup did not preserve all four
                        # concurrent states on TensorFold, while this does.
                        warmup = chat_stream(client, prompt["messages"], 1,
                                             ignore_eos=True, thinking=False)
                    else:
                        warmup = chat_stream(client, prompt["messages"],
                                             min(64, args.output_tokens),
                                             ignore_eos=False, thinking=False)
                    warmups += 1
                    if args.mode == "retrieval" and not all(
                            code in warmup["text"] for code in prompt["expected_codes"]):
                        raise RuntimeError("Warmup retrieval failed; prompt or model is not reliable")

            rounds = []
            for index in range(args.rounds):
                prompts = build_prompts(client, args, index, warm_prompts)
                rounds.append(run_round(client, prompts, args, index, args.concurrency))
                print(json.dumps({"round": index,
                                  "aggregate_tokens_per_second": rounds[-1]["aggregate_tokens_per_second"]},
                                 indent=2), flush=True)
            report["rounds"] = rounds
            report["summary"] = summarize(rounds)

            after = client.info()
            report["server_after"] = after
            if after["config"] != before["config"]:
                raise RuntimeError("Server health/configuration changed during the test")
            expected_requests = warmups + args.rounds * args.concurrency
            report["traffic_after"] = {
                "requests_total": after["health"].get("requests_total"),
                "prompt_tokens_total": after["health"].get("prompt_tokens_total"),
                "completion_tokens_total": after["health"].get("completion_tokens_total"),
            }
            before_total = report["traffic_before"]["requests_total"]
            after_total = report["traffic_after"]["requests_total"]
            if isinstance(before_total, int) and isinstance(after_total, int):
                delta = after_total - before_total
                report["traffic_delta"] = delta
                report["traffic_expected"] = expected_requests
                report["isolation_ok"] = delta == expected_requests
                if delta != expected_requests:
                    report["warnings"].append(
                        f"requests_total delta {delta} != expected {expected_requests}; "
                        "other traffic or a counter reset")
            else:
                report["isolation_ok"] = None
                report["warnings"].append("requests_total unavailable; traffic isolation unknown")

            result = audit(args.container, report["started_at"])
            report["audit"] = result
            report["audit_check"] = validate_glm_audit(result, initial_state, expected_requests)
            rank_oom = scan_rank_logs(RANK_LOG_PATHS)
            report["rank_log_oom_markers"] = rank_oom
            report["oom_observed"] = bool(result["oom_marker_lines"] or result["container"]["oom_killed"] or rank_oom)
            if report["oom_observed"]:
                raise RuntimeError("OOM observed; stop before another round")
            report["telemetry_complete"] = bool(rounds and all(
                row["health"]["sample_count"] > 0 for row in rounds))
            if not report["telemetry_complete"]:
                report["warnings"].append("Health telemetry incomplete; missing metrics are unknown, not zero")
            report["passed"] = True
        except Exception as error:  # noqa: BLE001
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        except KeyboardInterrupt:
            report["error"] = {"type": "KeyboardInterrupt"}
        finally:
            report["finished_at"] = stamp()
            write_json(path, report)
    print(json.dumps({"report": str(path), "passed": report.get("passed", False),
                      "summary": report.get("summary"), "error": report.get("error")}, indent=2))
    raise SystemExit(0 if report.get("passed") else 1)


if __name__ == "__main__":
    main()
