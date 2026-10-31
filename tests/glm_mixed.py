#!/usr/bin/env python3
"""One bounded long-prefill/streaming overlap screen; explicit idle-window approval required."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
import uuid

from common import experiment_lock, label, report_path, require_live, stamp, write_json
from glm_common import Client, chat_stream, check_budget, health_snapshot, retrieval_prompt
from glm_update_checks import wait_idle
from gpu_memory import sample_gpu_memory, summarize_gpu_memory
from runtime_audit import audit, container_state


def run(args, report):
    client = Client(timeout=1200)
    before = client.info()
    if not client.idle():
        raise RuntimeError("service is not idle")
    check_budget(before["config"], 2, args.prompt_tokens, args.output_tokens)
    report["server_before"] = before
    state = container_state(args.container)
    report["container_before"] = state
    prompt = retrieval_prompt(client, args.prompt_tokens, 20261031, uuid.uuid4().hex[:8])
    ready, stop = threading.Event(), threading.Event()
    times, health, memory, errors = [], [], [], []

    def observe(at):
        times.append(at)
        ready.set()

    def sample():
        while not stop.is_set():
            try:
                health.append(health_snapshot(client))
                memory.append(sample_gpu_memory(timeout=2))
            except Exception as error:
                errors.append(type(error).__name__)
            stop.wait(1)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            decode = pool.submit(chat_stream, client,
                [{"role": "user", "content": "Write a very long detailed technical guide to distributed inference and continue until the token budget ends."}],
                args.output_tokens, ignore_eos=True, thinking=False,
                model=before["config"]["served_model_name"], content_observer=observe)
            if not ready.wait(120):
                raise TimeoutError("stream did not produce first content before long request")
            prefill_started = time.monotonic()
            long = pool.submit(chat_stream, client, prompt["messages"], 128, thinking=False,
                               model=before["config"]["served_model_name"])
            long_result = long.result()
            decode_result = decode.result()
        if decode_result["completion_tokens"] != args.output_tokens:
            raise RuntimeError("decode did not consume its bounded forced-output budget")
        if not all(code in long_result["text"] for code in prompt["expected_codes"]):
            raise RuntimeError("long request did not return all retrieval codes")
        wait_idle(client)
        after = client.info()
        if after["config"] != before["config"]:
            raise RuntimeError("configuration changed during mixed screen")
        delta = after["health"]["requests_total"] - before["health"]["requests_total"]
        if delta != 2:
            raise RuntimeError("unexpected traffic during mixed screen")
        result = audit(args.container, report["started_at"])
        report["audit"] = result
        if (not result["container"]["running"] or result["container"]["id"] != state["id"]
                or result["container"]["started_at"] != state["started_at"]
                or result["oom_marker_lines"] or result["container"]["oom_killed"]):
            raise RuntimeError("container health/restart/OOM audit failed")
        gaps = [b - a for a, b in zip(times, times[1:]) if b >= prefill_started]
        # Drop unbounded text; retain bounded excerpts and token/time accounting.
        decode_result.pop("text", None)
        long_result.pop("text", None)
        report.update(passed=True, elapsed_seconds=time.monotonic() - started,
                      decode=decode_result, long_prefill=long_result,
                      stream_events_during_or_after_prefill=sum(t >= prefill_started for t in times),
                      max_stream_gap_seconds=max(gaps, default=None), traffic_delta=delta,
                      server_after=after)
    finally:
        stop.set()
        sampler.join(timeout=5)
        report["gpu_memory"] = summarize_gpu_memory(memory)
        report["telemetry_errors"] = errors
        report["health_sample_count"] = len(health)
        report["observed_decode_prefill_overlap"] = any(
            (h.get("decoding") or 0) > 0 and ((h.get("prefilling") or 0) > 0 or (h.get("filling") or 0) > 0)
            for h in health)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", type=label, required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--prompt-tokens", type=int, default=200000)
    parser.add_argument("--output-tokens", type=int, default=4096)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    report = {"schema_version": 1, "kind": "glm-mixed-prefill-screen", "label": args.label,
              "started_at": stamp(), "passed": False, "production_qualified": False,
              "target_prompt_tokens": args.prompt_tokens, "forced_decode_tokens": args.output_tokens}
    path = report_path(args.label)
    with experiment_lock():
        try:
            run(args, report)
        except Exception as error:
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            report["finished_at"] = stamp()
            write_json(path, report)
    print(json.dumps({"report": str(path), "passed": report["passed"], "error": report.get("error")}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
