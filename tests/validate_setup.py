#!/usr/bin/env python3
"""Offline validation plus optional read-only inventory and CPU tokenization.

Never submits inference, changes server configuration, or restarts anything.
"""

import argparse
import ast
import json
import subprocess
import sys

from common import (Client, DEFAULT_CONTAINER, DEFAULT_URL, ROOT, SECRET_VALUE,
                    digest, report_path, stamp, verify_profile, write_json)
from prompts import build_prompts
from profiles import resolve_profile

SOFTWARE_CODE = r'''
import hashlib, importlib.metadata, json
from pathlib import Path
packages = {}
for name in ('sglang','torch','triton','transformers','flashinfer-python','sgl-kernel'):
    try:
        packages[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        packages[name] = None
path = Path('/sgl-workspace/sglang/python/sglang/srt/server_args.py')
text = path.read_text()
fields = ('max_running_requests','chunked_prefill_size','mem_fraction_static',
          'speculative_algorithm','speculative_num_steps','speculative_eagle_topk',
          'speculative_num_draft_tokens','enable_metrics')
print(json.dumps({'packages': packages, 'server_args_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'declared_candidate_fields': {key: key + ':' in text for key in fields},
                  'compatibility_scope': 'Source declarations only; no parser/startup/kernel validation'}))
'''


def compare_container(baseline_container, identity, state):
    """Separate stable container identity from runtime start time."""
    identity_matches = all(identity[key] == baseline_container[key]
                           for key in ("id", "image_id", "argv"))
    started_at_matches = state.get("StartedAt") == baseline_container["started_at"]
    return identity_matches, started_at_matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true", help="GET server info and inspect software metadata read-only")
    parser.add_argument("--check-tokenizer", action="store_true", help="Build two short prompts on CPU; no model loading/inference")
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    args = parser.parse_args()
    report = {"schema_version": 1, "kind": "setup-validation", "started_at": stamp(),
              "live_inference_requests_sent": 0, "passed": False}
    path = report_path("setup-validation")
    try:
        files = sorted((ROOT / "tests").glob("*.py"))
        for file in files:
            ast.parse(file.read_text(), filename=str(file))
        report["python_files_parsed"] = len(files)
        for file in (ROOT / "configs").glob("*.json"):
            json.loads(file.read_text())
        baseline = json.loads((ROOT / "configs/baseline.json").read_text())
        original_evidence = json.loads((ROOT / baseline["evidence"]).read_text())
        if digest(original_evidence) != baseline["evidence_sha256"]:
            raise ValueError("Baseline evidence integrity check failed")
        report["baseline_evidence_integrity"] = True
        candidates = json.loads((ROOT / "configs/candidates.json").read_text())
        report["profiles_resolved"] = {name: digest(resolve_profile(name)["argv"]) for name in candidates}
        # Record paths for secret findings, never the matching values.
        secret_paths = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                        if p.is_file() and ".git" not in p.parts
                        and p.suffix in (".json", ".md", ".py")
                        and SECRET_VALUE.search(p.read_text())]
        report["credential_scan_paths"] = secret_paths
        if secret_paths:
            raise ValueError("Credential-like string detected; inspect privately before publishing")
        result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                                cwd=ROOT, text=True, capture_output=True, timeout=90)
        report["unit_tests"] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        if result.returncode:
            raise RuntimeError("Offline unit tests failed")
        before = None
        if args.inventory:
            before = Client(args.base_url, timeout=15).info()
            verify_profile(before["config"], "baseline")
            report["server_before"] = before
            software = subprocess.check_output(["docker", "exec", args.container, "python3", "-B", "-c", SOFTWARE_CODE],
                                               text=True, timeout=30)
            report["software"] = json.loads(software)
            template = '{"id":{{json .Id}},"image_id":{{json .Image}},"argv":{{json .Config.Cmd}},"state":{{json .State}}}'
            identity = json.loads(subprocess.check_output(["docker", "inspect", "--format",
                template, args.container], text=True, timeout=10))
            container = identity.pop("state")
            report["container_identity"] = identity
            report["container_state"] = {k: container.get(k) for k in ("Running", "StartedAt", "OOMKilled", "Restarting")}
            identity_matches, started_at_matches = compare_container(baseline["container"], identity, container)
            report["original_container_identity_matches"] = identity_matches
            report["container_started_at_matches_baseline"] = started_at_matches
            if not identity_matches:
                raise ValueError("Container/image/launch identity changed since baseline capture")
            if not container.get("Running") or container.get("Restarting"):
                raise ValueError("Container is not stably running")
        if args.check_tokenizer:
            prompts = build_prompts(1024, 2, "setup-cpu-check", baseline["server"]["config"]["model_path"],
                                    container=args.container)
            report["cpu_tokenizer_check"] = {
                "prompt_lengths": [len(p["input_ids"]) for p in prompts],
                "prompt_hashes": [p["sha256"] for p in prompts],
                "independent_early_prefixes": len({tuple(p["input_ids"][:256]) for p in prompts}) == 2,
                "model_weights_loaded": False, "inference_requests_sent": 0,
            }
            if not report["cpu_tokenizer_check"]["independent_early_prefixes"]:
                raise ValueError("Synthetic sessions do not have distinct early prefixes")
        if before:
            after = Client(args.base_url, timeout=15).info()
            report["server_after"] = after
            report["live_config_matches_baseline"] = before["config"] == after["config"]
            if not report["live_config_matches_baseline"]:
                raise ValueError("Live configuration changed during setup validation")
        report["passed"] = True
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["finished_at"] = stamp()
        write_json(path, report)
    print(json.dumps({"report": str(path), "passed": report["passed"], "error": report.get("error")}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
