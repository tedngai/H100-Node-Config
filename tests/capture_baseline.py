#!/usr/bin/env python3
"""Read-only service inventory; writes sanitized local evidence, never inference."""

import argparse
import json
from pathlib import Path
import platform
import subprocess

from common import Client, DEFAULT_CONTAINER, DEFAULT_URL, ROOT, digest, label, report_path, stamp, write_json


def command(argv, timeout=30):
    result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def safe_container(raw):
    # Intentionally never copy Config.Env or raw Docker inspect into evidence.
    host, config = raw["HostConfig"], raw["Config"]
    return {
        "id": raw["Id"], "name": raw["Name"].lstrip("/"), "image_id": raw["Image"],
        "image_tag": config["Image"], "entrypoint": config["Entrypoint"],
        "argv": config["Cmd"], "working_directory": config["WorkingDir"],
        "started_at": raw["State"]["StartedAt"], "restart_count": raw["RestartCount"],
        "network_mode": host["NetworkMode"], "port_bindings": host["PortBindings"],
        "ipc_mode": host["IpcMode"], "shm_size_bytes": host["ShmSize"],
        "restart_policy": host["RestartPolicy"], "gpu_requests": host["DeviceRequests"],
        "security_options": host["SecurityOpt"], "memory_limit_bytes": host["Memory"],
        "bind_mounts": host["Binds"],
        "build_labels": {k: v for k, v in (config.get("Labels") or {}).items()
                         if k.startswith(("ai.sglang.", "ai.radixark.", "org.opencontainers.image."))},
        "credentials": "Environment deliberately omitted; supply credentials separately if needed",
    }


MODEL_METADATA = r'''
import hashlib, json
from pathlib import Path
root = Path('/root/.cache/huggingface/hub/models--Qwen--Qwen3.8-Flash-Next-FP8')
ref = root / 'refs/main'
revision = ref.read_text().strip() if ref.exists() else None
result = {'cached_main_revision': revision, 'note': 'Cache metadata is not proof of the revision loaded by an already-running process'}
if revision:
    directory = root / 'snapshots' / revision
    result['file_sha256'] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                             for name in ('config.json','tokenizer_config.json') if (directory / name).exists()}
    data = json.loads((directory / 'config.json').read_text())
    keys = ('model_type','architectures','torch_dtype','max_position_embeddings','num_hidden_layers','num_attention_heads','num_key_value_heads')
    result['model_config'] = {k: data[k] for k in keys if k in data}
    result['text_config'] = {k: data.get('text_config',{}).get(k) for k in keys if k in data.get('text_config',{})}
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--label", default="baseline", type=label)
    parser.add_argument("--initialize", action="store_true", help="Create immutable configs/baseline.json once")
    args = parser.parse_args()
    baseline_path = ROOT / "configs/baseline.json"
    if args.initialize and baseline_path.exists():
        parser.error("Baseline already exists; omit --initialize to capture a new evidence snapshot")
    info = Client(args.base_url, timeout=15).info()
    raw = json.loads(subprocess.check_output(["docker", "inspect", args.container], text=True))[0]
    container = safe_container(raw)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", container["image_id"]], text=True))[0]
    container["repo_digests"] = image.get("RepoDigests") or []
    query = ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,driver_version,uuid", "--format=csv"]
    metadata = command(["docker", "exec", args.container, "python3", "-B", "-c", MODEL_METADATA])
    report = {
        "schema_version": 1, "captured_at": stamp(), "kind": "read-only-inventory",
        "base_url": args.base_url, "server": info, "container": container,
        "hardware": {
            "platform": platform.platform(), "python": platform.python_version(),
            "kernel_nvidia_version": Path("/proc/driver/nvidia/version").read_text(),
            "host_gpu_query": command(query),
            "container_gpu_query": command(["docker", "exec", args.container] + query),
            "gpu_topology": command(["docker", "exec", args.container, "nvidia-smi", "topo", "-m"]),
            "memory": command(["free", "-b"]),
        },
        "cached_model_metadata": json.loads(metadata["stdout"]) if metadata["returncode"] == 0 else metadata,
        "inference_requests_sent": 0,
        "reference": {"url": "https://github.com/tedngai/H200-Node-Config.git",
                      "commit": "0c2b32a7c5d62ea058207ead1c856d9544ac3f5a"},
    }
    after = Client(args.base_url, timeout=15).info()
    report["server_unchanged_during_capture"] = info["config"] == after["config"]
    path = write_json(report_path(args.label), report)
    if args.initialize:
        if not report["server_unchanged_during_capture"]:
            raise RuntimeError("Configuration changed during capture; evidence retained, baseline not initialized")
        write_json(baseline_path, {
            "schema_version": 1, "label": "baseline", "captured_at": report["captured_at"],
            "evidence": str(path.relative_to(ROOT)), "evidence_sha256": digest(report),
            "base_url": args.base_url, "container": container, "server": info,
        })
    print(json.dumps({"report": str(path), "baseline_initialized": args.initialize,
                      "server_unchanged": report["server_unchanged_during_capture"]}, indent=2))


if __name__ == "__main__":
    main()
