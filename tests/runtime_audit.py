"""Read-only, allowlisted Docker state and aggregate log audit. Never saves raw logs."""

from collections import Counter
from datetime import datetime, timezone
import json
import re
import subprocess

ACCESS = re.compile(r'"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|CONNECT)\s+(\S+)\s+HTTP/[0-9.]+"\s+(\d{3})(?:\s|$)')
OOM = re.compile(r'out[ -]of[ -]memory|OutOfMemoryError|CUDA_ERROR_OUT_OF_MEMORY|\bOOM\b', re.I)


def container_state(container):
    # Never fetch the container environment or full inspect output.
    template = ('{"id":{{json .Id}},"image_id":{{json .Image}},'
                '"argv":{{json .Config.Cmd}},"running":{{json .State.Running}},'
                '"oom_killed":{{json .State.OOMKilled}},'
                '"started_at":{{json .State.StartedAt}},"restart_count":{{.RestartCount}}}')
    result = subprocess.run(["docker", "inspect", "--format", template, container],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Allowlisted Docker state query failed")
    return json.loads(result.stdout)


def parse_logs(text):
    counts = Counter()
    oom = errors = unparsed = 0
    for line in text.splitlines():
        match = ACCESS.search(line)
        if match:
            method, target, status = match.groups()
            # Never save unknown paths, query strings, request IDs or response text.
            path = target.split("?", 1)[0]
            known = path if path in ("/generate", "/v1/chat/completions", "/v1/completions",
                                     "/get_server_info", "/server_info", "/v1/models",
                                     "/v1/loads", "/metrics", "/health") else "[other-route]"
            counts[f"{method} {known} {status}"] += 1
        elif re.search(r'\b(?:GET|POST|PUT|PATCH|DELETE)\s+\S+\s+HTTP/', line):
            unparsed += 1
        # Count explicit OOM markers, without assuming other warnings imply OOM.
        oom += bool(OOM.search(line))
        errors += bool(re.search(r'\b(error|exception|traceback|fatal|critical)\b', line, re.I))
    return {"access_counts": dict(counts), "oom_marker_lines": oom,
            "error_marker_lines": errors, "unparsed_request_lines": unparsed,
            "raw_logs_saved": False}


def audit(container, since):
    if re.fullmatch(r"\d{8}T\d{6}\.\d+Z", since):
        since = datetime.strptime(since, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).isoformat()
    until = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    result = subprocess.run(["docker", "logs", "--since", since, "--until", until,
                             "--timestamps", container], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError("Docker log audit unavailable; OOM observation unknown")
    return {"since": since, "until": until, **parse_logs(result.stdout + "\n" + result.stderr),
            "container": container_state(container)}


def validate_audit(result, initial_state, expected_requests):
    state = result["container"]
    if result["oom_marker_lines"] or state["oom_killed"]:
        raise RuntimeError("OOM observed; stop before another round")
    if not state["running"] or any(state[k] != initial_state[k] for k in (
            "id", "image_id", "argv", "started_at", "restart_count")):
        raise RuntimeError("Container stopped, restarted or changed during benchmark")
    counts = result["access_counts"]
    actual = counts.get("POST /generate 200", 0)
    other_writes = sum(n for key, n in counts.items()
                       if not key.startswith(("GET ", "HEAD ", "OPTIONS ")) and key != "POST /generate 200")
    if actual != expected_requests or other_writes or result["unparsed_request_lines"]:
        raise RuntimeError("Inference traffic audit does not match benchmark requests")
