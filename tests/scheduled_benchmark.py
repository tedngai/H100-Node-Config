#!/usr/bin/env python3
"""Separate scheduling-aware 32K screening. No deployment or unattended matrix.

One invocation = c2, c4 or c6, cold or two-pass warm, three rounds. Initial
prefill waiting must fit a fixed eight-second observation window, clear before
all first-text observations, and accompany cumulative prefill progress. This is
not a no-queue result. This legacy fixed protocol is retained for reproducing old
screens; use benchmark.py's capacity policy for new general workload tests.
"""

import argparse
import json
import uuid

from benchmark import summarize
from common import (Client, DEFAULT_CONTAINER, DEFAULT_URL, check_budget,
                    effective_active_request_limit,
                    experiment_lock, label, report_path, require_live, stamp,
                    verify_profile, write_json)
from prefill_diagnostic import (OUTPUT_TOKENS, PROMPT_TOKENS, REQUEST_TIMEOUT,
                               require_idle, run_round, snapshot)
from prompts import build_prompts

ROUNDS = 3
WARMUP_PASSES = 2
PREFILL_WINDOW = 8.0


def validate_policy(args):
    if type(args.concurrency) is not int or args.concurrency not in (2, 4, 6):
        raise ValueError("Scheduling-aware screening supports only c2/c4/c6")
    if args.cache not in ("cold", "warm"):
        raise ValueError("Unsupported cache policy")


def run(args, report):
    validate_policy(args)
    client = Client(args.base_url, timeout=REQUEST_TIMEOUT)
    report["server_before"] = client.info()
    verify_profile(report["server_before"]["config"], "baseline")
    report["effective_active_request_limit"] = effective_active_request_limit(
        report["server_before"]["config"], report["server_before"].get("internal_states", []))
    check_budget(report["server_before"]["config"], args.concurrency,
                 PROMPT_TOKENS, OUTPUT_TOKENS,
                 internal_states=report["server_before"].get("internal_states", []))
    require_idle(snapshot(client, 0), concurrency=args.concurrency)
    warmed = None
    try:
        if args.cache == "warm":
            warmed = build_prompts(PROMPT_TOKENS, args.concurrency, report["run_id"],
                                   report["server_before"]["config"]["model_path"],
                                   container=args.container, purpose="decode")
            for warmup_pass in range(WARMUP_PASSES):
                for index, prompt in enumerate(warmed):
                    phase = {"run_id": report["run_id"], "warmup_pass": warmup_pass,
                             "prompt_index": index, "passed": False}
                    report["warmup_phases"].append(phase)
                    # Warmup is sequential, unforced and never included in timing.
                    run_round(args, phase, concurrency=1, prompts=[prompt],
                              cache_policy="warmup", prefill_window=PREFILL_WINDOW)
                    phase["passed"] = True
                    result = dict(phase["requests"][0]["result"])
                    result.update({"warmup_pass": warmup_pass, "prompt_index": index})
                    report["warmup"].append(result)
        for round_index in range(ROUNDS):
            phase = {"run_id": f'{report["run_id"]}-r{round_index}',
                     "round": round_index, "samples": [], "errors": [], "passed": False}
            report["rounds"].append(phase)
            try:
                run_round(args, phase, concurrency=args.concurrency, prompts=warmed,
                          cache_policy=args.cache, prefill_window=PREFILL_WINDOW)
                phase["passed"] = True
                if args.cache == "warm":
                    phase["warm_cache_verified"] = True
            finally:
                phase["samples"] = [row["result"] for row in phase.get("requests", []) if "result" in row]
                phase["errors"] = [row["error"] for row in phase.get("requests", []) if "error" in row]
                elapsed = phase.get("measured_elapsed_seconds")
                if elapsed:
                    phase["aggregate_tokens_per_second"] = sum(s["meta_info"]["completion_tokens"] for s in phase["samples"]) / elapsed
            print(json.dumps({"round": round_index,
                              "aggregate_tokens_per_second": phase["aggregate_tokens_per_second"],
                              "queue_classification": phase["analysis"]["classification"],
                              "peak_waiting": phase["analysis"]["peak_waiting"]}), flush=True)
    finally:
        try:
            report["server_after"] = client.info()
            report["configuration_unchanged"] = report["server_after"]["config"] == report["server_before"]["config"]
        except Exception as error:
            report["server_after_error"] = str(error)
    if report.get("server_after_error") or not report.get("configuration_unchanged"):
        raise RuntimeError("Server configuration/health could not be verified")
    report["summary"] = summarize(report["rounds"])
    report["strict_no_queue_observed"] = all(row["strict_no_queue_observed"] for row in report["rounds"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--concurrency", required=True, type=int, choices=(2, 4, 6))
    parser.add_argument("--cache", required=True, choices=("cold", "warm"))
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    report = {"schema_version": 1, "kind": "scheduling-aware-benchmark",
              "protocol_revision": "scheduled-32k-v1", "label": args.label,
              "started_at": stamp(), "run_id": uuid.uuid4().hex, "passed": False,
              "production_qualified": False, "no_queue_qualified": False,
              "workload": {"profile": "baseline", "mode": "decode", "cache": args.cache,
                           "concurrency": args.concurrency, "prompt_tokens": PROMPT_TOKENS,
                           "output_tokens": OUTPUT_TOKENS, "rounds": ROUNDS,
                           "warmup_passes": WARMUP_PASSES if args.cache == "warm" else 0},
              "policy": {"prefill_observation_window_seconds": PREFILL_WINDOW,
                         "request_timeout_seconds": REQUEST_TIMEOUT,
                         "strict_benchmark_zero_queue_policy_changed": False,
                         "max_requests": args.concurrency * (ROUNDS + (WARMUP_PASSES if args.cache == "warm" else 0))},
              "rounds": [], "warmup": [], "warmup_phases": [],
              "qualification": "Scheduling-aware screening includes initial prefill waiting, not strict no-queue qualification or reliable production tails"}
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
