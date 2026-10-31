#!/usr/bin/env python3
"""Guarded candidate launch, never a production stop/remove or automatic cutover."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

from prepare import ROOT, outside_repo, run, write_evidence
from validate import ALL_CASES, verify_build

NAME = "tensorfold-glm53-candidate-789e8f3bdfa2"
DFLASH_ID = "incoai/GLM-5.3-Flash-DFlash2"
DFLASH_REV = "bf582e4eacc1810f76656d1811693ff6c6737d2a"


def launch_command(profile: dict, image_id: str, cache: Path, runtime: Path, iface: str) -> list[str]:
    settings = profile["effective_settings"]
    if settings["tp"] != 4 or settings["parallel"] != 4 or settings["drafter"] != "dflash2":
        raise ValueError("this candidate launcher requires the recorded TP4/parallel4/DFlash2 profile")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", iface):
        raise ValueError("invalid NCCL interface")
    model = profile["model"]
    snapshot = f"hub/models--{model['id'].replace('/', '--')}/snapshots/{model['revision']}"
    drafter = f"hub/models--{DFLASH_ID.replace('/', '--')}/snapshots/{DFLASH_REV}"
    values = {
        "MODEL_PATH": "/root/.cache/huggingface/" + snapshot,
        "DRAFTER_ARG": "/root/.cache/huggingface/" + drafter,
        "TP": 4, "PARALLEL": settings["parallel"], "CONTEXT": settings["context"],
        "MAX_TOKENS": settings["max_tokens"], "SERVED_NAME": model["served_name"],
        "API_PORT": 8011, "MASTER_PORT": 29561,
        "THINKING": int(settings["thinking_default"]), "VISION": int(settings["vision"]),
        "HF_HUB_OFFLINE": 1, "TORCH_EXTENSIONS_DIR": "/cache/torch_extensions",
        "TRITON_CACHE_DIR": "/cache/triton", "NCCL_IB_DISABLE": 1,
        "NCCL_NET_PLUGIN": "none", "NCCL_GIN_ENABLE": 0, "NCCL_SOCKET_IFNAME": iface, "NCCL_DEBUG": "WARN",
        "TF_GLM_COMM": settings["comm"], "TF_GLM_KV": settings["kv"], "TF_GLM_DENSE": settings["dense"],
        "TF_GLM_MTP": "auto", "TF_GLM_CACHE_GIB": settings["kv_pool_gib"],
        "TF_GLM_CACHE_ENTRIES": settings["cache_entries"],
        "TF_GLM_SHARED_PREFIX": int(settings["shared_prefix"]),
        "TF_GLM_ASSISTANT_ENDS": int(settings["assistant_ends"]),
        "TENSORFOLD_MEMORY_RESERVE_GIB": settings["memory_reserve_gib"], "TENSORFOLD_NO_UPDATE_CHECK": 1,
        # Engine-only candidate: explicitly retain current tuning behavior, not Spark recipe defaults.
        "TF_GLM_DFLASH_POLICY": "fc5:0.3", "TENSORFOLD_NUCLEUS_UNION": 0,
        "TF_GLM_FILL_ROWS": 1024, "TF_GLM_MULTI_PREFILL": 0, "TF_GLM_KDA_CHUNKED": 0,
        "TF_GLM_FILL_BUDGET_MS": 0, "TF_GLM_FILL_DRAFTS": 0,
        "TF_GLM_HC_SPLIT": 0, "TF_GLM_PREFILL_OVERLAP": 0, "TF_GLM_L2PF": 0,
        "TF_GLM_EXL3_LOADS": 0, "TF_GLM_WIDE_GRAPHS": 0,
        "TF_GLM_KV_SHARD": 0, "TF_GLM_PREFIX_WAIT": 0, "TF_GLM_EXIT_ON_BROKEN": 0,
    }
    command = ["docker", "create", "--name", NAME, "--restart", "no", "--gpus", "all",
               "--ipc", "host", "--network", "host", "--shm-size", "16g",
               "--ulimit", "memlock=-1", "--ulimit", "stack=67108864", "--cap-add", "IPC_LOCK", "--init",
               "--mount", f"type=bind,source={cache},target=/root/.cache/huggingface,readonly",
               "--mount", f"type=bind,source={runtime / 'cache'},target=/cache",
               "--mount", f"type=bind,source={runtime / 'logs'},target=/logs"]
    for key, value in values.items():
        command += ["-e", f"{key}={value}"]
    return command + [image_id]


def check_ready(health: dict, models: dict, profile: dict) -> None:
    expected = profile["effective_settings"]
    if health.get("ok") is not True or health.get("broken"):
        raise ValueError("engine is not healthy")
    if health.get("backend") != "tensorfold" or health.get("context_length") != expected["context"]:
        raise ValueError("unexpected engine/context")
    if health.get("streams", {}).get("max") != expected["parallel"]:
        raise ValueError("unexpected stream capacity")
    if not isinstance(health.get("pool_tokens"), int) or health["pool_tokens"] < expected["context"]:
        raise ValueError("pool capacity unavailable or smaller than context")
    data = models.get("data", [])
    if len(data) != 1 or data[0].get("id") != profile["model"]["served_name"]:
        raise ValueError("unexpected served model")


def verify_cpu(record: dict, image_id: str) -> None:
    checks = record.get("checks", [])
    if (record.get("success") is not True or record.get("full_suite") is not True
            or record.get("image_id") != image_id or len(checks) != len(ALL_CASES)
            or {c.get("name") for c in checks} != set(ALL_CASES)
            or any(c.get("success") is not True for c in checks)):
        raise ValueError("full passing CPU suite for this exact image is required")


def check_port_available(port: int) -> None:
    # Match HTTP/TCPStore server reuse: recently closed sockets may be TIME_WAIT.
    # listen() still refuses an actual listener; no SO_REUSEPORT is requested.
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.listen(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-evidence", type=Path, required=True)
    parser.add_argument("--cpu-evidence", type=Path, required=True)
    parser.add_argument("--hf-cache", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True, help="fresh external cache/log directory")
    parser.add_argument("--nccl-iface", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    if args.execute and not args.confirm_idle:
        parser.error("--execute requires --confirm-idle and an approved maintenance window")
    profile = json.loads((ROOT / "configs/glm53-production.json").read_text())
    build = json.loads(args.build_evidence.read_text())
    cpu = json.loads(args.cpu_evidence.read_text())
    image_id = build["image_id"]
    verify_cpu(cpu, image_id)
    runtime = outside_repo(args.runtime_dir)
    cache = args.hf_cache.expanduser().resolve()
    command = launch_command(profile, image_id, cache, runtime, args.nccl_iface)
    if not args.execute:
        print(json.dumps({"dry_run": True, "container": NAME, "image_id": image_id,
                          "restart_policy": "no", "context": profile["effective_settings"]["context"],
                          "parallel": profile["effective_settings"]["parallel"],
                          "production_stop_or_remove": False}, indent=2))
        return 0
    image = json.loads(run(["docker", "image", "inspect", image_id]))[0]
    verify_build(build, image)
    running = run(["docker", "inspect", "--format", "{{.State.Running}}", profile["container"]["name"]])
    if running != "false":
        raise ValueError("production container must already be stopped in an approved window; no automatic stop")
    if runtime.exists():
        raise ValueError("runtime directory already exists; refusing cache/log reuse")
    if subprocess.run(["docker", "inspect", NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        raise ValueError("candidate container already exists; inspect/preserve it manually, never auto-remove")
    gpu_rows = run(["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"]).splitlines()
    if len(gpu_rows) != 4 or any(int(row.split(",")[1].strip()) > 4096 for row in gpu_rows):
        raise ValueError("four idle GPUs with at most 4096 MiB allocated each are required")
    for port in (8011, 29561):
        check_port_available(port)
    for snapshot in (f"models--{profile['model']['id'].replace('/', '--')}/snapshots/{profile['model']['revision']}",
                     f"models--{DFLASH_ID.replace('/', '--')}/snapshots/{DFLASH_REV}"):
        if not (cache / "hub" / snapshot / "config.json").is_file():
            raise ValueError("pinned checkpoint/drafter unavailable in supplied cache")
    runtime.mkdir(parents=True)
    (runtime / "cache").mkdir()
    (runtime / "logs").mkdir()
    report = {"schema_version": 1, "kind": "glm53-candidate-startup", "image_id": image_id,
              "container": NAME, "production_profile_changed": False, "production_stop_or_remove": False,
              "started_at": datetime.now(timezone.utc).isoformat(), "success": False}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    container_id = None
    try:
        container_id = run(command)
        report["container_id"] = container_id
        run(["docker", "start", container_id])
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            if run(["docker", "inspect", "--format", "{{.State.Running}}", container_id]) != "true":
                raise RuntimeError("candidate exited before readiness")
            try:
                def get(endpoint):
                    with urllib.request.urlopen("http://127.0.0.1:8011" + endpoint, timeout=3) as response:
                        return json.load(response)
                health, models = get("/health"), get("/v1/models")
                check_ready(health, models, profile)
                report.update(success=True, context_length=health["context_length"],
                              pool_tokens=health["pool_tokens"], streams_max=health["streams"]["max"])
                break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
                time.sleep(5)
        if not report["success"]:
            raise TimeoutError("candidate readiness deadline exceeded")
    except BaseException as exc:
        report["failure_type"] = type(exc).__name__
        if container_id:
            # Only the new container this invocation created; retain its filesystem/logs for inspection.
            subprocess.run(["docker", "stop", "-t", "60", container_id], check=False)
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        evidence = ROOT / "evidence" / f"glm53-candidate-startup-{stamp}.json"
        write_evidence(evidence, report)
        print("Sanitized evidence:", evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
