#!/usr/bin/env python3
"""Run pinned upstream regression tools in CPU-only, network-isolated containers."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from prepare import IMAGE, PATCHES_HASH, RECIPE_COMMIT, ROOT, TF_COMMIT, outside_repo, run, write_evidence

SOURCE_CASES = (
    "test_responses_tool_image.py", "test_mpo_first_frame.py", "test_sse_keepalive.py",
    "test_anthropic_stream_head.py", "test_get_bodies.py", "test_think_tag_mention.py",
    "test_unoffered_tool_call.py", "test_broken_health_exit.py", "test_queued_cancellation.py",
    "kept_reasoning_check.py",
)
DIRECT_CASES = ("chat_continued_check.py", "fork_point_check.py", "spill_blocks_check.py", "kv_shard_check.py")
TOKENIZER_CASES = ("literal_tokens_check.py", "reply_ids_check.py")
LOCAL_CASES = ("supervisor_check.py",)
ALL_CASES = SOURCE_CASES + DIRECT_CASES + TOKENIZER_CASES + LOCAL_CASES
# Only small, public tokenizer/template metadata; never mount model weights or the full cache.
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "chat_template.json")


def cpu_command(image_id: str, name: str, script: str, tokenizer: Path) -> list[str]:
    if script not in ALL_CASES:
        raise ValueError("unknown CPU check")
    command = ["docker", "run", "--rm", "--name", name, "--network", "none", "--runtime", "runc",
               "--read-only", "--tmpfs", "/tmp:rw,nosuid,exec,size=2g", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--cpus", "8", "--memory", "8g",
               "--pids-limit", "512", "-e", "NVIDIA_VISIBLE_DEVICES=void", "-e", "CUDA_VISIBLE_DEVICES=",
               "-e", "HF_HUB_OFFLINE=1", "-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "XDG_CACHE_HOME=/tmp/cache", "-e", "OMP_NUM_THREADS=2",
               "-e", "TRITON_CACHE_DIR=/tmp/triton", "-e", "TORCH_EXTENSIONS_DIR=/tmp/torch"]
    if script in TOKENIZER_CASES:
        for filename in TOKENIZER_FILES:
            source = (tokenizer / filename).resolve()
            if source.is_file():
                command += ["--mount", f"type=bind,source={source},target=/model/{filename},readonly"]
    if script in LOCAL_CASES:
        source = Path(__file__).resolve().parent / script
        command += ["--tmpfs", "/logs:rw,nosuid,size=16m", "--mount",
                    f"type=bind,source={source},target=/opt/h100/{script},readonly"]
    payload = (
        "import importlib.util,pathlib,runpy,sys; "
        "root=str(pathlib.Path(next(iter(importlib.util.find_spec('tensorfold').submodule_search_locations))).parent); "
        f"script='/opt/{'h100' if script in LOCAL_CASES else 'recipe-tools'}/{script}'; "
        + ("sys.argv=[script,'--source-root',root]; " if script in SOURCE_CASES else
           "sys.argv=[script,'/model']; " if script in TOKENIZER_CASES else "sys.argv=[script]; ")
        + "runpy.run_path(script,run_name='__main__')"
    )
    return command + ["--entrypoint", "python", image_id, "-B", "-c", payload]


def verify_build(build: dict, image: dict) -> str:
    if not build.get("success") or build.get("deployed") is not False:
        raise ValueError("need a successful, undeployed candidate build record")
    expected = {"recipe_commit": RECIPE_COMMIT, "tensorfold_commit": TF_COMMIT,
                "upstream_patch_hash": PATCHES_HASH, "image": IMAGE}
    if any(build.get(k) != v for k, v in expected.items()):
        raise ValueError("candidate build record does not match pinned inputs")
    if image.get("Id") != build.get("image_id") or image.get("Architecture") != "amd64":
        raise ValueError("candidate image identity/architecture mismatch")
    labels = image.get("Config", {}).get("Labels", {})
    if (labels.get("tf.patches") != PATCHES_HASH or labels.get("h100.recipe.commit") != RECIPE_COMMIT
            or labels.get("h100.tensorfold.commit") != TF_COMMIT):
        raise ValueError("candidate labels do not match build record")
    return image["Id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-evidence", type=Path, required=True)
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="fresh external directory for CPU test output")
    parser.add_argument("--case", action="append", choices=ALL_CASES, dest="cases")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    cases = args.cases or list(ALL_CASES)
    output = outside_repo(args.output_dir)
    print(json.dumps({"cases": cases, "gpu_access": False, "network": "none", "inference": False}, indent=2))
    if not args.execute:
        return 0
    build = json.loads(args.build_evidence.read_text())
    image = json.loads(run(["docker", "image", "inspect", build["image_id"]]))[0]
    image_id = verify_build(build, image)
    tokenizer = args.tokenizer_dir.expanduser().resolve()
    if any(case in TOKENIZER_CASES for case in cases):
        for filename in ("tokenizer.json", "tokenizer_config.json"):
            if not (tokenizer / filename).is_file():
                raise ValueError("missing tokenizer metadata: " + filename)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "kind": "glm53-candidate-cpu-checks", "image_id": image_id,
              "recipe_commit": RECIPE_COMMIT, "production_changed": False, "gpu_access": False,
              "inference": False, "deployed": False, "checks": [],
              "build_evidence": args.build_evidence.name,
              "started_at": datetime.now(timezone.utc).isoformat()}
    report["local_check_sha256"] = {
        script: hashlib.sha256((Path(__file__).resolve().parent / script).read_bytes()).hexdigest()
        for script in cases if script in LOCAL_CASES
    }
    if any(case in TOKENIZER_CASES for case in cases):
        report["tokenizer_metadata_sha256"] = {
            filename: hashlib.sha256((tokenizer / filename).read_bytes()).hexdigest()
            for filename in TOKENIZER_FILES if (tokenizer / filename).is_file()
        }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence = ROOT / "evidence" / f"glm53-candidate-cpu-{stamp}.json"
    try:
        for script in cases:
            name = "glm53-cpu-" + uuid.uuid4().hex
            started = time.monotonic()
            result = {"name": script}
            try:
                with (output / (script + ".txt")).open("x") as log:
                    completed = subprocess.run(cpu_command(image_id, name, script, tokenizer),
                                               stdout=log, stderr=subprocess.STDOUT, timeout=300)
                result.update(returncode=completed.returncode, success=completed.returncode == 0)
            except subprocess.TimeoutExpired:
                result.update(returncode=None, success=False, failure_type="timeout")
            finally:
                # Only this invocation's UUID-named disposable CPU container; never a serving container.
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result["seconds"] = round(time.monotonic() - started, 3)
            report["checks"].append(result)
            print(script, "PASS" if result["success"] else "FAIL", flush=True)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["success"] = len(report["checks"]) == len(cases) and all(c["success"] for c in report["checks"])
        report["full_suite"] = len(cases) == len(ALL_CASES) and set(cases) == set(ALL_CASES)
        write_evidence(evidence, report)
        print("Sanitized evidence:", evidence, flush=True)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
