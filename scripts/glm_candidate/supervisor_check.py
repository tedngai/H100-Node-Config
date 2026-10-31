"""CPU-only integration test of the baked supervisor with fake rank processes.

Run inside the candidate image, no GPUs/network/model mounts, with writable
scratch at /tmp and /logs. No TensorFold inference or CUDA initialization occurs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, signal, sys, time
root = pathlib.Path(os.environ['SUPERVISOR_TEST_STATE'])
rank = sys.argv[sys.argv.index('--rank') + 1]
def stop(_signal, _frame):
    (root / (rank + '.term')).touch()
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
(root / (rank + '.json')).write_text(json.dumps({'rank': int(rank), 'device': int(os.environ['TF_GLM_DEVICE']), 'pid': os.getpid()}))
deadline = time.monotonic() + 10
while len(list(root.glob('*.json'))) != 4:
    if time.monotonic() > deadline: raise SystemExit(99)
    time.sleep(0.01)
if rank == os.environ.get('SUPERVISOR_TEST_FAIL_RANK'):
    time.sleep(0.1)
    raise SystemExit(int(os.environ['SUPERVISOR_TEST_FAIL_CODE']))
while True: time.sleep(0.05)
'''


def scenario(failing_rank: str, code: int, terminate: bool = False) -> dict:
    with tempfile.TemporaryDirectory(prefix="supervisor-check-") as tmp:
        root = Path(tmp)
        binary = root / "tensorfold"
        binary.write_text(FAKE)
        binary.chmod(0o755)
        env = dict(os.environ, PATH=str(root) + ":" + os.environ["PATH"],
                   BASH_ENV="/dev/null", ENV="/dev/null", TENSORFOLD_NO_UPDATE_CHECK="1",
                   SUPERVISOR_TEST_STATE=str(root), SUPERVISOR_TEST_FAIL_RANK=failing_rank,
                   SUPERVISOR_TEST_FAIL_CODE=str(code), MODEL_PATH="unused", DRAFTER_ARG="unused",
                   API_PORT="8011", MASTER_PORT="29561", SERVED_NAME="supervisor-test",
                   CONTEXT="1048576", PARALLEL="4", MAX_TOKENS="32768", TP="4", VISION="1", THINKING="1")
        process = subprocess.Popen(["bash", "/opt/h100/entrypoint.sh"], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while len(list(root.glob("*.json"))) != 4:
                if process.poll() is not None:
                    output, _ = process.communicate()
                    logs = {p.name: p.read_text() for p in Path('/logs').glob('rank*.log')}
                    raise AssertionError(f"supervisor exited during fake startup ({process.returncode}): "
                                         + output.decode() + repr(logs))
                if time.monotonic() > deadline:
                    raise AssertionError("supervisor did not launch all fake ranks")
                time.sleep(0.01)
            if terminate:
                process.terminate()
            output, _ = process.communicate(timeout=10)
            expected = 143 if terminate else (code or 1)
            assert process.returncode == expected, (process.returncode, output.decode())
            ranks = [json.loads(p.read_text()) for p in root.glob("*.json")]
            assert sorted((r["rank"], r["device"]) for r in ranks) == [(i, i) for i in range(4)]
            assert len(list(root.glob("*.term"))) == (4 if terminate else 3)
            for rank in ranks:
                try:
                    os.kill(rank["pid"], 0)
                except ProcessLookupError:
                    pass
                else:
                    raise AssertionError("orphan fake rank remains")
            return {"scenario": "sigterm" if terminate else f"rank-{failing_rank}-exit-{code}",
                    "success": True, "supervisor_returncode": process.returncode,
                    "rank_device_mapping": "0:0,1:1,2:2,3:3", "orphan_ranks": False}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()


def main() -> None:
    package = Path(next(iter(importlib.util.find_spec("tensorfold").submodule_search_locations)))
    engine = package / "families/glm5_next/cuda/engine.py"
    before = hashlib.sha256(engine.read_bytes()).hexdigest()
    results = [scenario("0", 17), scenario("2", 0), scenario("", 0, terminate=True)]
    assert hashlib.sha256(engine.read_bytes()).hexdigest() == before, "startup modified engine source"
    print(json.dumps({"success": True, "engine_source_unchanged": True,
                      "gpu_access": False, "inference": False, "checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
