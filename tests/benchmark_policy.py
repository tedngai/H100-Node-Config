"""Capacity-first benchmark policy. Pure evaluation; no server or GPU access."""

POLICY_VERSION = "capacity-first-v1"


def describe_policy(name="capacity", memory_warning_mib=3072, memory_stop_mib=None):
    return {
        "version": POLICY_VERSION,
        "name": name,
        "success_criterion": "All requested work completes with valid token counts, no observed OOM, and a healthy unchanged service",
        "queueing": "fail" if name == "no-queue" else "measure_only",
        "retractions": "fail" if name == "no-queue" else "warning",
        "memory_warning_mib": memory_warning_mib,
        "memory_stop_mib": memory_stop_mib,
        "latency": "measure_only; request errors/timeouts still fail",
        "qualification": "Bounded workload completion, not universal OOM safety or production qualification",
    }


def summarize_observations(metrics):
    samples = metrics.get("samples", [])
    result = {"sample_count": len(samples), "telemetry_errors": len(metrics.get("errors", []))}
    for key in ("num_running_reqs", "num_queue_reqs", "num_retracted_reqs", "token_usage"):
        values = [s[key] for s in samples if s.get(key) is not None]
        result["peak_" + key] = max(values) if values else None
    queue = [s["num_queue_reqs"] for s in samples if s.get("num_queue_reqs") is not None]
    result["queue_observed"] = any(v > 0 for v in queue) if queue else None
    # These are observed snapshots, not durations or independent scheduler updates.
    result["samples_with_waiting"] = sum(v > 0 for v in queue) if queue else None
    result["strict_no_queue_observed"] = not any(v > 0 for v in queue) if queue else None
    return result


def validate_observations(metrics, max_running=None, policy="capacity"):
    for sample in metrics.get("samples", []):
        running = sample.get("num_running_reqs")
        if max_running is not None and running is not None and running > max_running:
            raise RuntimeError("More active requests than benchmark clients; unrelated traffic may be present")
        if policy == "no-queue":
            if (sample.get("num_queue_reqs") or 0) > 0:
                raise RuntimeError("Queueing observed under explicit no-queue policy")
            if (sample.get("num_retracted_reqs") or 0) > 0:
                raise RuntimeError("Scheduler retractions observed under explicit no-queue policy")


def memory_status(summary, warning_mib=3072, stop_mib=None):
    values = list(summary.get("minimum_free_mib_by_gpu", {}).values())
    return {
        "warning_threshold_mib": warning_mib,
        "stop_threshold_mib": stop_mib,
        "low_memory_warning": min(values) < warning_mib if values else None,
        "floor_breached": min(values) < stop_mib if values and stop_mib is not None else None,
    }
