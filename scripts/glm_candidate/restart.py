#!/usr/bin/env python3
"""Explicit maintenance-window restart check for the named candidate only."""
import argparse
from datetime import datetime, timezone
import json
import subprocess
import time
import urllib.request

from launch import NAME, check_ready
from prepare import ROOT, run, write_evidence
from validate import verify_build


def state():
    template = '{"id":{{json .Id}},"image_id":{{json .Image}},"started_at":{{json .State.StartedAt}},"running":{{json .State.Running}}}'
    return json.loads(run(["docker", "inspect", "--format", template, NAME]))


def engine_hash():
    code = ("import hashlib,importlib.util,pathlib; "
            "p=pathlib.Path(next(iter(importlib.util.find_spec('tensorfold').submodule_search_locations))); "
            "print(hashlib.sha256((p/'families/glm5_next/cuda/engine.py').read_bytes()).hexdigest())")
    return run(["docker", "exec", NAME, "python", "-B", "-c", code])


def get(endpoint):
    with urllib.request.urlopen("http://127.0.0.1:8011" + endpoint, timeout=3) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-evidence", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    if not args.execute or not args.confirm_idle:
        parser.error("restart requires --execute --confirm-idle and explicit maintenance approval")
    from pathlib import Path
    build = json.loads(Path(args.build_evidence).read_text())
    verify_build(build, json.loads(run(["docker", "image", "inspect", build["image_id"]]))[0])
    before = state()
    if not before["running"] or before["image_id"] != build["image_id"]:
        raise ValueError("running named candidate must match the validated build")
    profile = json.loads((ROOT / "configs/glm53-production.json").read_text())
    health = get("/health")
    check_ready(health, get("/v1/models"), profile)
    if health.get("requests_running") != 0 or any(health["streams"].get(k) != 0 for k in ("decoding", "prefilling", "filling", "paused")):
        raise ValueError("candidate must be idle before restart")
    source_hash = engine_hash()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"schema_version": 1, "kind": "glm53-candidate-real-restart", "success": False,
              "container": NAME, "before": before, "engine_source_before_sha256": source_hash,
              "production_profile_changed": False, "started_at": datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    try:
        subprocess.run(["docker", "restart", "-t", "60", NAME], check=True, timeout=180)
        while time.monotonic() - started < 1200:
            after = state()
            if not after["running"]:
                raise RuntimeError("candidate exited after restart")
            try:
                health = get("/health")
                check_ready(health, get("/v1/models"), profile)
                if after["id"] != before["id"] or after["image_id"] != before["image_id"] or after["started_at"] == before["started_at"]:
                    raise RuntimeError("restart identity/start-time verification failed")
                after_hash = engine_hash()
                if after_hash != source_hash:
                    raise RuntimeError("restart changed installed engine source")
                report.update(success=True, after=after, engine_source_after_sha256=after_hash,
                              load_seconds=round(time.monotonic() - started, 3),
                              context_length=health["context_length"], pool_tokens=health["pool_tokens"])
                break
            except (OSError, ValueError):
                time.sleep(5)
        if not report["success"]:
            raise TimeoutError("candidate restart readiness deadline exceeded")
    except BaseException as error:
        report["failure_type"] = type(error).__name__
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        path = ROOT / "evidence" / f"glm53-update-candidate-restart-{stamp}.json"
        write_evidence(path, report)
        print(json.dumps(report, indent=2)); print("Evidence:", path)


if __name__ == "__main__":
    main()
