#!/usr/bin/env python3
"""Change only KV precision; preserve BF16 Hy4 for recovery, never restore GLM."""
import argparse
import fcntl
import json
from pathlib import Path
import time

import manage as m


def idle_snapshot(c):
    data = m.get_json(c, "/v1/loads?include=core,queues")
    loads = data.get("loads", [])
    if len(loads) != 1 or loads[0].get("dp_rank") != 0:
        raise RuntimeError("Expected one DP0 load report")
    load = loads[0]
    if any(load.get(k) != 0 for k in ("num_running_reqs", "num_waiting_reqs")):
        raise RuntimeError("Hy4 has live requests; pause/drain clients first")
    queues = load.get("queues", {})
    if any(queues.get(k) != 0 for k in (
        "waiting", "grammar", "paused", "retracted", "prealloc_ready"
    )):
        raise RuntimeError("Hy4 queues are not confirmed empty")
    counter = load.get("total_prefill_uncached_tokens")
    if not isinstance(counter, (int, float)):
        raise RuntimeError("Prefill counter unavailable")
    return {"num_running_reqs": load["num_running_reqs"],
            "num_waiting_reqs": load["num_waiting_reqs"],
            "total_prefill_uncached_tokens": counter,
            "max_total_num_tokens": load.get("max_total_num_tokens")}


def metadata(c):
    info = m.get_json(c, "/server_info")
    fields = ("context_length", "max_running_requests", "max_total_num_tokens",
              "mem_fraction_static", "attention_backend", "dsa_prefill_backend",
              "dsa_decode_backend", "kv_cache_dtype", "swa_full_tokens_ratio",
              "speculative_algorithm", "chunked_prefill_size")
    return {
        "settings": {k: info.get(k) for k in fields},
        "memory_by_reported_dp": [
            {"dp_rank": state.get("dp_rank"),
             "memory_usage": state.get("memory_usage")}
            for state in info.get("internal_states", [])
        ],
    }


def validate_pair(before, after):
    administrative = {"container", "status", "note"}
    changes = {k for k in before.keys() | after.keys()
               if before.get(k) != after.get(k)} - administrative
    if changes != {"kv_cache_dtype"} or after.get("kv_cache_dtype") != "fp8_e4m3":
        raise ValueError("Only KV dtype may change in this probe")
    if before["container"] == after["container"]:
        raise ValueError("Use a different container to preserve the BF16 service")


def probe(before, after, timeout):
    report = {"started_at": m.stamp(), "status": "failed", "stage": "preflight",
              "inference_tests_run": False, "glm_restore": False,
              "source_container": before["container"], "target_container": after["container"]}
    changed = False
    try:
        validate_pair(before, after)
        m.validate_checkpoint(after)
        image = m.lock_image(after)
        old = m.inspect(before["container"])
        m.ensure_owned(before, old)
        if not old["State"]["Running"] or old["Image"] != image:
            raise RuntimeError("BF16 Hy4 is not the expected running image")
        if after["container"] in m.run(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines():
            raise RuntimeError("FP8 probe name already exists; preserve it and choose a new name")
        report["before"] = metadata(before)
        report["idle_before"] = idle_snapshot(before)
        time.sleep(5)
        idle_after = idle_snapshot(before)
        if idle_after["total_prefill_uncached_tokens"] != report["idle_before"]["total_prefill_uncached_tokens"]:
            raise RuntimeError("Traffic changed during idle guard")
        changed = True
        report["stage"] = "stop-bf16"
        m.stop(before)
        report["stage"] = "start-fp8"
        m.start(after)
        report["stage"] = "fp8-readiness"
        report["effective_settings"] = m.ready(after, timeout)
        report["after"] = metadata(after)
        report["status"] = "ready for operator testing; no inference qualification"
        report["stage"] = "complete"
    except BaseException as e:
        report["error_type"] = type(e).__name__
        print(f"FP8 probe failed: {type(e).__name__}: {str(e)[:200]}")
        if changed:
            try:
                if after["container"] in m.run(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines():
                    m.stop(after)
                if not m.inspect(before["container"])["State"]["Running"]:
                    m.start(before)
                m.ready(before, 600)
                report["recovery"] = "previous BF16 Hy4 restored; GLM untouched"
            except BaseException as recovery_error:
                report["recovery"] = "failed; manual intervention needed"
                report["recovery_error_type"] = type(recovery_error).__name__
                raise
        raise
    finally:
        report["finished_at"] = m.stamp()
        m.record("fp8-kv-probe", report)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--confirm-idle", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    before = json.loads((m.ROOT / "configs/hy4-flash-h100-mem093.json").read_text())
    after = json.loads((m.ROOT / "configs/hy4-flash-h100-mem093-fp8kv.json").read_text())
    validate_pair(before, after)
    if not a.execute:
        print("DRY RUN: FP8 KV only; preserve BF16 Hy4; never restore GLM; no inference")
        return
    if not a.confirm_idle:
        ap.error("--execute requires --confirm-idle and approved paused clients")
    with (Path(after["runtime"]) / "operation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe(before, after, a.timeout)


if __name__ == "__main__":
    main()
