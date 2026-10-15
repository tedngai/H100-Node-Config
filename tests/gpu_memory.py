"""Low-rate, sanitized host GPU-memory sampling for the memory-fraction candidate."""

import csv
import io
import subprocess

from common import stamp


EXPECTED_GPU_COUNT = 4


def parse_gpu_memory(stdout, expected_gpu_count=EXPECTED_GPU_COUNT):
    rows = list(csv.reader(io.StringIO(stdout)))
    if len(rows) != expected_gpu_count:
        raise ValueError(f"Expected {expected_gpu_count} GPU rows, got {len(rows)}")

    devices = []
    for row in rows:
        if len(row) != 3:
            raise ValueError("Unexpected nvidia-smi memory-query format")
        index, total, used = (int(value.strip()) for value in row)
        if index < 0 or total <= 0 or used < 0 or used > total:
            raise ValueError("Invalid GPU memory values")
        devices.append({"index": index, "total_mib": total, "used_mib": used,
                        "free_mib": total - used})

    devices.sort(key=lambda device: device["index"])
    if [device["index"] for device in devices] != list(range(expected_gpu_count)):
        raise ValueError("GPU indices are missing or duplicated")
    return devices


def sample_gpu_memory(timeout=5):
    """Return parsed capacities only; never retain raw command output or stderr."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,memory.total,memory.used",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi exited with status {result.returncode}")
    return {"at": stamp(), "devices": parse_gpu_memory(result.stdout)}


def summarize_gpu_memory(samples):
    """Summarize per-device values; never sum duplicated or TP GPU metrics."""
    if not samples:
        return {"sample_count": 0, "minimum_free_mib_by_gpu": None,
                "maximum_used_mib_by_gpu": None}
    indices = [device["index"] for device in samples[0]["devices"]]
    if any([device["index"] for device in sample["devices"]] != indices
           for sample in samples):
        raise ValueError("GPU set changed during memory sampling")
    return {
        "sample_count": len(samples),
        "minimum_free_mib_by_gpu": {
            str(index): min(next(d["free_mib"] for d in sample["devices"]
                                 if d["index"] == index) for sample in samples)
            for index in indices
        },
        "maximum_used_mib_by_gpu": {
            str(index): max(next(d["used_mib"] for d in sample["devices"]
                                 if d["index"] == index) for sample in samples)
            for index in indices
        },
    }
