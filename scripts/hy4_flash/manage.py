#!/usr/bin/env python3
"""Guarded Hy4-Flash lifecycle. Dry-run by default; never removes containers."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/hy4-flash-h100.json"
OWNER = "h100-node-config.hy4-flash"


def run(args):
    return subprocess.check_output(args, text=True).strip()


def inspect(name):
    # Keep the raw object in memory only. Never dump env, mounts or credentials.
    return json.loads(run(["docker", "inspect", name]))[0]


def snapshot(c):
    return (Path(c["cache"]) / ("models--" + c["model"].replace("/", "--"))
            / "snapshots" / c["revision"])


def lock_path(c):
    return Path(c["runtime"]) / "image-lock.json"


def stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def record(kind, data):
    path = ROOT / "evidence" / f"hy4-flash-{kind}-{stamp()}.json"
    with path.open("x") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Evidence: {path}")


def get_json(c, route):
    with urllib.request.urlopen(f"http://127.0.0.1:{c['port']}{route}", timeout=15) as r:
        return json.load(r)


def health_ok(c):
    # SGLang /health has an empty HTTP 200 body, unlike TensorFold's JSON health.
    with urllib.request.urlopen(f"http://127.0.0.1:{c['port']}/health", timeout=15) as r:
        return r.status == 200


def validate_checkpoint(c):
    p = snapshot(c)
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json",
                 "processor_config.json", "chat_template.jinja"):
        if not (p / name).is_file():
            raise RuntimeError(f"Missing checkpoint file: {name}")
    index = json.loads((p / "model.safetensors.index.json").read_text())
    names = set(index["weight_map"].values())
    if any(not (p / n).is_file() for n in names):
        raise RuntimeError("Checkpoint shards are missing; complete download first")
    total = sum((p / n).stat().st_size for n in names)
    if total != c["checkpoint_bytes"]:
        raise RuntimeError(f"Checkpoint size mismatch: {total}")
    return {"shards": len(names), "bytes": total, "revision": c["revision"]}


def flags(c):
    return [
        "sglang", "serve", "--trust-remote-code",
        "--model-path", f"/models/{c['revision']}",
        "--served-model-name", c["served_model_name"],
        "--tp", str(c["tp"]),
        "--cuda-graph-backend-prefill", "disabled",
        "--context-length", str(c["context_length"]),
        "--max-running-requests", str(c["max_running_requests"]),
        "--chunked-prefill-size", str(c["chunked_prefill_size"]),
        "--mem-fraction-static", str(c["mem_fraction_static"]),
        "--reasoning-parser", "hunyuan", "--tool-call-parser", "hunyuan",
        "--host", c["host"], "--port", str(c["port"]),
    ]


def recipe_hash(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()


def start_command(c, image):
    # Mount the repository cache (snapshot + sibling blobs) as one read-only tree.
    repo_cache = snapshot(c).parents[1]
    return [
        "docker", "run", "-d", "--pull", "never", "--name", c["container"],
        "--label", f"deployment.owner={OWNER}",
        "--label", f"deployment.recipe={recipe_hash(c)}",
        "--gpus", "all", "--ipc", "host", "--network", "host",
        "--restart", "no", "--ulimit", "memlock=-1:-1",
        "--ulimit", "stack=67108864",
        "--log-opt", "max-size=50m", "--log-opt", "max-file=3",
        "--mount", f"type=bind,src={repo_cache},dst=/checkpoint,readonly",
        "--mount", f"type=bind,src={Path(c['runtime']) / 'cache'},dst=/root/.cache",
        "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1",
        "--env", "NCCL_NET_PLUGIN=none", "--env", "NCCL_GIN_ENABLE=0",
        "--entrypoint", "sglang", image,
        *[f"/checkpoint/snapshots/{c['revision']}" if v == f"/models/{c['revision']}"
          else v for v in flags(c)[1:]],
    ]


def ensure_owned(c, d):
    labels = d["Config"].get("Labels") or {}
    if labels.get("deployment.owner") != OWNER:
        raise RuntimeError("Refusing to touch an unowned container")
    if labels.get("deployment.recipe") != recipe_hash(c):
        raise RuntimeError("Existing container has a different recipe; preserve it and choose a new name")


def gpu_idle():
    processes = run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"])
    if processes:
        raise RuntimeError("GPU compute processes still present; refusing startup")
    rows = run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    if len(rows.splitlines()) != 4 or any(int(x) > 1024 for x in rows.splitlines()):
        raise RuntimeError("Expected four idle GPUs, each using <=1024 MiB")


def port_free(c):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", c["port"]))
        sock.listen(1)


def lock_image(c):
    p = lock_path(c)
    if not p.is_file():
        raise RuntimeError("Run pin-image after pulling the official image")
    lock = json.loads(p.read_text())
    image = lock["image_id"]
    actual = json.loads(run(["docker", "image", "inspect", image]))[0]
    if actual["Id"] != image or actual["Architecture"] != "amd64":
        raise RuntimeError("Pinned image is missing or not amd64")
    return image


def start(c):
    validate_checkpoint(c)
    image = lock_image(c)
    names = run(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
    if c["container"] in names:
        d = inspect(c["container"])
        ensure_owned(c, d)
        if d["Image"] != image:
            raise RuntimeError("Preserved container image does not match lock")
        if d["State"]["Running"]:
            raise RuntimeError("Hy4 container is already running")
        command = ["docker", "start", c["container"]]
    else:
        command = start_command(c, image)
    gpu_idle()
    port_free(c)
    (Path(c["runtime"]) / "cache").mkdir(parents=True, exist_ok=True)
    print(run(command))


def stop(c):
    d = inspect(c["container"])
    ensure_owned(c, d)
    run(["docker", "update", "--restart", "no", c["container"]])
    if d["State"]["Running"]:
        run(["docker", "stop", "-t", "120", c["container"]])


def ready(c, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        container = inspect(c["container"])
        ensure_owned(c, container)
        if not container["State"]["Running"]:
            raise RuntimeError("Hy4 exited during startup; inspect container logs")
        try:
            models = get_json(c, "/v1/models")
            if not health_ok(c):
                raise RuntimeError("Hy4 health is not ready")
            info = get_json(c, "/server_info")
            if c["served_model_name"] not in [m["id"] for m in models["data"]]:
                raise RuntimeError("Unexpected served model")
            # Current SGLang exposes resolved fields flat; older builds nest them.
            args = info.get("server_args", info)
            for key, expected in (
                ("context_length", c["context_length"]),
                ("max_running_requests", c["max_running_requests"]),
                ("tp_size", c["tp"]), ("dp_size", 1),
                ("served_model_name", c["served_model_name"]),
                ("reasoning_parser", "hunyuan"), ("tool_call_parser", "hunyuan"),
            ):
                if args.get(key) != expected:
                    raise RuntimeError(f"Unexpected effective {key}")
            return {k: args.get(k) for k in (
                "context_length", "max_running_requests", "tp_size", "dp_size",
                "mem_fraction_static", "attention_backend", "moe_runner_backend",
                "reasoning_parser", "tool_call_parser", "kv_cache_dtype",
                "speculative_algorithm", "chunked_prefill_size")}
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(5)
    raise RuntimeError("Hy4 readiness timed out")


def glm_profile():
    return json.loads((ROOT / "configs/glm53-production.json").read_text())


def glm_idle(p):
    expected = p["container"]
    d = inspect(expected["name"])
    if d["Id"] != expected["id"] or d["Image"] != expected["image_id"]:
        raise RuntimeError("GLM identity differs from authoritative profile")
    if not d["State"]["Running"]:
        raise RuntimeError("Expected GLM to be running before trial")
    def health():
        with urllib.request.urlopen(expected["health"], timeout=15) as r:
            h = json.load(r)
        if (h.get("ok") is not True or h.get("busy") is not False
                or h.get("requests_running") != 0
                or any(h.get("streams", {}).get(k, -1) != 0
                       for k in ("decoding", "prefilling", "filling", "paused"))
                or not isinstance(h.get("requests_total"), int)
                or h.get("context_length") != p["effective_settings"]["context"]
                or h.get("streams", {}).get("max") != p["effective_settings"]["parallel"]):
            raise RuntimeError("GLM is not healthy and idle; pause/drain all clients")
        return h
    before = health()
    time.sleep(5)
    after = health()
    if after.get("requests_total") != before.get("requests_total"):
        raise RuntimeError("GLM traffic changed during idle guard")
    return {"container": d["Name"].lstrip("/"), "image_id": d["Image"],
            "context_length": after["context_length"],
            "requests_total": after.get("requests_total")}


def restore_glm(p):
    name = p["container"]["name"]
    d = inspect(name)
    if d["Id"] != p["container"]["id"] or d["Image"] != p["container"]["image_id"]:
        raise RuntimeError("Refusing changed GLM rollback identity")
    if not d["State"]["Running"]:
        gpu_idle()
        run(["docker", "start", name])
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(p["container"]["health"], timeout=15) as r:
                h = json.load(r)
            with urllib.request.urlopen(p["container"]["api"] + "/models", timeout=15) as r:
                models = json.load(r)
            if (h.get("ok") is True
                    and h.get("context_length") == p["effective_settings"]["context"]
                    and h.get("streams", {}).get("max") == p["effective_settings"]["parallel"]
                    and p["model"]["served_name"] in [m["id"] for m in models["data"]]):
                run(["docker", "update", "--restart", p["container"]["restart_policy"], name])
                return {"healthy": True, "container": name, "context_length": h["context_length"]}
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(5)
    raise RuntimeError("GLM rollback readiness timed out; manual intervention needed")


def preserve_glm_logs(c, p):
    # The preserved TensorFold entrypoint truncates rank logs on restart.
    # Archive only stopped rank log files, OUTSIDE the configuration repository.
    source = Path(p["container"]["rank_logs"]).parent
    archive = Path(c["runtime"]) / f"glm-rollback-logs-{stamp()}"
    archive.mkdir(mode=0o700)
    count, size = 0, 0
    for rank in range(4):
        old = source / f"rank{rank}.log"
        if old.is_file():
            dest = archive / old.name
            shutil.copy2(old, dest)
            dest.chmod(0o600)
            count += 1
            size += dest.stat().st_size
    if count != 4:
        raise RuntimeError("Expected all four stopped GLM rank logs for rollback archive")
    return {"archive": str(archive), "files": count, "bytes": size}


def smoke(c):
    body = {
        "model": c["served_model_name"],
        "messages": [{"role": "user", "content": "Reply with exactly HY4-READY."}],
        "max_tokens": 64, "temperature": 0,
        "chat_template_kwargs": {"reasoning_effort": "no_think"},
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{c['port']}/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        result = json.load(r)
    message = result["choices"][0]["message"]
    if "HY4-READY" not in (message.get("content") or ""):
        raise RuntimeError("Bounded chat smoke did not return expected marker")
    return {"passed": True, "usage": result.get("usage")}


def trial(c, timeout):
    report = {"started_at": stamp(), "status": "failed", "production_promoted": False,
              "stage": "preflight"}
    p = glm_profile()
    changed = False
    try:
        # Fail BEFORE downtime if downloads or pinning are incomplete.
        report["checkpoint"] = validate_checkpoint(c)
        report["image_id"] = lock_image(c)
        names = run(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
        if c["container"] in names:
            existing = inspect(c["container"])
            ensure_owned(c, existing)
            if existing["State"]["Running"] or existing["Image"] != report["image_id"]:
                raise RuntimeError("Existing Hy4 container conflicts with trial")
        report["glm_before"] = glm_idle(p)
        changed = True
        report["stage"] = "glm-stop"
        run(["docker", "update", "--restart", "no", p["container"]["name"]])
        run(["docker", "stop", "-t", "120", p["container"]["name"]])
        report["stage"] = "glm-log-preservation"
        report["glm_log_archive"] = preserve_glm_logs(c, p)
        report["stage"] = "hy4-start"
        start(c)
        report["stage"] = "hy4-readiness"
        report["effective_settings"] = ready(c, timeout)
        report["stage"] = "hy4-smoke"
        report["smoke"] = smoke(c)
        report["status"] = "bounded smoke passed; GLM restored, not promoted"
        report["stage"] = "trial-complete"
    except Exception as e:
        report["error_type"] = type(e).__name__
        # Exceptions may include API bodies; don't persist them as public evidence.
        print(f"Trial failed ({type(e).__name__}): {str(e)[:200]}", file=sys.stderr)
        raise
    finally:
        try:
            if changed:
                names = run(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
                if c["container"] in names:
                    stop(c)
                try:
                    report["rollback"] = restore_glm(p)
                except BaseException:
                    report["rollback"] = {"healthy": False, "manual_intervention_needed": True}
                    raise
        finally:
            report["finished_at"] = stamp()
            record("trial", report)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("pin-image", "start", "stop", "wait", "smoke", "trial", "status"))
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--confirm-idle", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    c = json.loads(a.config.read_text())
    if a.action == "status":
        d = inspect(c["container"])
        ensure_owned(c, d)
        print(json.dumps({"container": c["container"], "image_id": d["Image"],
                          "state": d["State"]["Status"],
                          "restart_policy": d["HostConfig"]["RestartPolicy"]["Name"]}, indent=2))
        return
    if not a.execute:
        print(f"DRY RUN: {a.action}; no mutation or inference")
        if a.action == "start":
            print(shlex.join(start_command(c, "<pinned-image-id>")))
        return
    if a.action != "pin-image" and not a.confirm_idle:
        ap.error("Live operations require --execute --confirm-idle and operator approval")
    runtime = Path(c["runtime"])
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "operation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute_action(a, c)


def execute_action(a, c):
    if a.action == "pin-image":
        d = json.loads(run(["docker", "image", "inspect", c["image_tag"]]))[0]
        if d["Architecture"] != "amd64":
            raise RuntimeError("Expected amd64 image")
        path = lock_path(c)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"image_id": d["Id"], "repo_digests": d.get("RepoDigests", []),
                "architecture": d["Architecture"], "pinned_at": stamp()}
        if path.exists():
            if json.loads(path.read_text())["image_id"] != d["Id"]:
                raise RuntimeError("Refusing to overwrite a different image lock")
        else:
            with path.open("x") as f:
                json.dump(data, f, indent=2)
        record("image-pin", data)
    elif a.action == "start":
        start(c)
    elif a.action == "stop":
        stop(c)
    elif a.action == "wait":
        print(json.dumps(ready(c, a.timeout), indent=2))
    elif a.action == "smoke":
        ready(c, min(a.timeout, 30))
        record("smoke", smoke(c))
    elif a.action == "trial":
        trial(c, a.timeout)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}; unwinding with rollback")
    signal.signal(signal.SIGTERM, interrupted)
    main()
