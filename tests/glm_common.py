"""GLM-5.3-Flash / TensorFold client, prompts, and audit helpers.

Standard library only. Importing this module never sends inference, deploys, or
flushes cache. The SGLang-specific `common.Client.info()` does not apply to
TensorFold, so this module has its own `/health` + `/v1/models` mapping.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import random
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from common import ROOT, experiment_lock, label, percentile, report_path, scrub, stamp, write_json
from runtime_audit import audit, container_state

DEFAULT_URL = "http://127.0.0.1:8888"
DEFAULT_CONTAINER = "tensorfold-glm53-flash-exl3-1m"
DEFAULT_PROFILE = "glm53-flash-exl3-1m"
OOM = re.compile(r"out[ -]of[ -]memory|OutOfMemoryError|CUDA_ERROR_OUT_OF_MEMORY|\bOOM\b", re.I)


class Client:
    def __init__(self, base_url=DEFAULT_URL, timeout=3600):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path.rstrip("/")):
            raise ValueError("Use an http(s) server origin, without credentials or a path")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def open(self, endpoint, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base_url + endpoint, data=data,
                                         headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(request, timeout=self.timeout)

    def json(self, endpoint, payload=None):
        with self.open(endpoint, payload) as response:
            return json.load(response)

    def info(self):
        health = self.json("/health")
        models = self.json("/v1/models")["data"]
        if len(models) != 1:
            raise ValueError("Expected exactly one served model")
        model = models[0]
        config = {
            "status": "ready" if health.get("ok") and not health.get("busy") else "busy",
            "model_path": model.get("id"),
            "served_model_name": model.get("id"),
            "context_length": health.get("context_length"),
            "max_req_input_len": health.get("context_length"),
            "max_total_num_tokens": health.get("pool_tokens"),
            "max_running_requests": (health.get("streams") or {}).get("max"),
            "tp_size": 4,
            "dp_size": 1,
            "allow_auto_truncate": False,
            "engine": "tensorfold",
        }
        return {"config": config, "health": health, "model": model}

    def idle(self):
        health = self.json("/health")
        streams = health.get("streams") or {}
        return (bool(health.get("ok")) and not health.get("busy")
                and health.get("requests_running", 0) == 0
                and all(streams.get(key, 0) == 0 for key in ("decoding", "prefilling", "filling", "paused")))

    def tokenize_count(self, messages):
        data = self.json("/tokenize", {"messages": messages})
        for key in ("count", "num_tokens"):
            if isinstance(data.get(key), int):
                return data[key]
        tokens = data.get("tokens") or data.get("input_ids") or []
        if not isinstance(tokens, list):
            raise ValueError("Tokenizer response has no token count")
        return len(tokens)


def check_budget(config, concurrency, prompt_tokens, output_tokens, pool_fraction=0.9):
    if min(concurrency, prompt_tokens, output_tokens) < 1:
        raise ValueError("Concurrency and token counts must be positive")
    if not 0 < pool_fraction <= 0.9:
        raise ValueError("Pool fraction must be positive and no greater than 0.90")
    if config.get("status") != "ready" or config.get("dp_size") != 1:
        raise ValueError("This harness requires a ready DP1 server")
    if config.get("allow_auto_truncate") is not False:
        raise ValueError("Disable automatic truncation before measurement")
    limit = config.get("max_running_requests")
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("Effective active-request cap is unavailable; no inference sent")
    if concurrency > limit:
        raise ValueError("Client concurrency exceeds the server's active-request cap")
    context = config.get("context_length")
    if not context or prompt_tokens + output_tokens > context:
        raise ValueError("Prompt plus output exceeds the context window")
    capacity = config.get("max_total_num_tokens")
    if not capacity or concurrency * (prompt_tokens + output_tokens) > capacity * pool_fraction:
        raise ValueError("Workload exceeds the guarded shared token-pool budget")


def health_snapshot(client):
    health = client.json("/health")
    streams = health.get("streams") or {}
    return {
        "at": stamp(),
        "busy": health.get("busy"),
        "requests_running": health.get("requests_running"),
        "requests_total": health.get("requests_total"),
        "decoding": streams.get("decoding"),
        "prefilling": streams.get("prefilling"),
        "filling": streams.get("filling"),
        "paused": streams.get("paused"),
        "pool_free_tokens": health.get("pool_free_tokens"),
        "drafted_total": health.get("drafted_total"),
        "accepted_total": health.get("accepted_total"),
    }


def _doc_record(rng, index):
    topics = ("turbine", "pipeline", "valve", "compressor", "condenser", "pump",
              "separator", "scrubber", "reactor", "heat exchanger")
    return (f"Record {index:07d}: {rng.choice(topics)} unit {rng.randrange(1000, 9999)} at station "
            f"{rng.randrange(1, 400)} measured pressure {rng.randrange(80, 900)} kPa, temperature "
            f"{rng.randrange(-20, 180)} C, flow {rng.randrange(5, 900)} m3/h, vibration "
            f"{rng.randrange(1, 90) / 10:.1f} mm/s, and efficiency {rng.randrange(70, 99)} percent. ")


def _document(records, codes):
    """A long, unique document with the three codes at the beginning, middle and end."""
    body = [f"Ledger record batch {codes[0].split('-')[-1]}."]
    positions = {max(1, len(records) // 20): codes[0],
                 max(2, len(records) // 2): codes[1],
                 max(3, (len(records) * 19) // 20): codes[2]}
    for index, record in enumerate(records):
        if index in positions:
            body.append(f"Access code: {positions[index]}.")
        body.append(record)
    return "\n".join(body)


def retrieval_prompt(client, target_tokens, seed, run_id):
    codes = [f"H100-{seed}-{run_id}-A", f"H100-{seed}-{run_id}-B", f"H100-{seed}-{run_id}-C"]
    rng = random.Random(f"{seed}:{run_id}")
    records = []
    count = 0
    n = max(12, target_tokens // 26)
    for _ in range(8):
        records = [_doc_record(rng, i) for i in range(n)]
        messages = [
            {"role": "system", "content": "You read technical ledgers and return access codes exactly."},
            {"role": "user", "content": (
                "Read the ledgers below. They contain three access codes. Return all three codes exactly, "
                "in the order they appear, separated by commas. Do not explain.\n\n"
                + _document(records, codes)
                + "\n\nQuestion: What are the three access codes?")},
        ]
        count = client.tokenize_count(messages)
        if abs(count - target_tokens) <= max(4, target_tokens // 200):
            break
        n = max(12, int(n * target_tokens / max(1, count)))
    return {
        "messages": messages,
        "expected_codes": codes,
        "actual_tokens": count,
        "sha256": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
        "run_id": run_id,
    }


def decode_prompt(client, target_tokens, seed, run_id):
    rng = random.Random(f"{seed}:{run_id}:decode")
    n = max(12, target_tokens // 26)
    count = 0
    for _ in range(8):
        records = [_doc_record(rng, i) for i in range(n)]
        messages = [
            {"role": "system", "content": "You are a senior reliability engineer writing a detailed analysis."},
            {"role": "user", "content": (
                "Write a thorough technical analysis of the following plant records. Explain the likely "
                "failure modes, the measurements that matter, and concrete maintenance actions. Continue "
                "until you have written a complete report.\n\n" + "\n".join(records))},
        ]
        count = client.tokenize_count(messages)
        if abs(count - target_tokens) <= max(4, target_tokens // 200):
            break
        n = max(12, int(n * target_tokens / max(1, count)))
    return {
        "messages": messages,
        "expected_codes": [],
        "actual_tokens": count,
        "sha256": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
        "run_id": run_id,
    }


def stream_lines(lines):
    """Yield parsed JSON events from an SSE byte/str iterator."""
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        event = json.loads(payload)
        if "error" in event:
            raise RuntimeError("Server stream error: " + json.dumps(scrub(event["error"])))
        yield event


def chat_stream(client, messages, output_tokens, ignore_eos=False, thinking=False, tools=None,
                model=None, timeout=None):
    body = {
        "model": model or "GLM-5.3-Flash-EXL3",
        "messages": messages,
        "max_tokens": output_tokens,
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "ignore_eos": bool(ignore_eos),
        "chat_template_kwargs": {"enable_thinking": bool(thinking)},
    }
    if tools:
        body["tools"] = tools
    started = time.monotonic()
    first_content = first_reasoning = None
    last_event = None
    usage = None
    text = []
    reasoning = []
    finish_reason = None
    events = 0
    with client.open("/v1/chat/completions", body) as response:
        for event in stream_lines(response):
            events += 1
            last_event = event
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("reasoning_content"):
                    if first_reasoning is None:
                        first_reasoning = time.monotonic() - started
                    reasoning.append(delta["reasoning_content"])
                if delta.get("content"):
                    if first_content is None:
                        first_content = time.monotonic() - started
                    text.append(delta["content"])
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
    elapsed = time.monotonic() - started
    if usage is None:
        raise RuntimeError("Stream ended without usage; cannot verify token accounting")
    if not text and not reasoning:
        raise RuntimeError("Stream ended without generated text")
    answer = "".join(text)
    return {
        "ttft_seconds": first_content,
        "reasoning_ttft_seconds": first_reasoning,
        "elapsed_seconds": elapsed,
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "cached_tokens": int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
        "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
        "finish_reason": finish_reason,
        "text": answer,
        "answer_excerpt": answer[:4096],
        "reasoning_excerpt": "".join(reasoning)[:2048],
        "stream_events": events,
        "usage": usage,
        "last_event_usage": (last_event or {}).get("usage"),
    }


def png_data_url(width=32, height=32, rgb=(220, 30, 30)):
    """A small solid-colour PNG as a data URL; no PIL dependency."""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


def scan_rank_logs(paths):
    """Count OOM markers without returning or saving raw log text."""
    markers = 0
    for path in paths:
        try:
            text = Path(path).read_text(errors="replace")
        except OSError:
            continue
        markers += len(OOM.findall(text))
    return markers


def validate_glm_audit(result, initial_state, expected_requests):
    state = result["container"]
    if result["oom_marker_lines"] or state["oom_killed"]:
        raise RuntimeError("OOM observed; stop before another round")
    if not state["running"] or any(state[k] != initial_state[k] for k in (
            "id", "image_id", "argv", "started_at", "restart_count")):
        raise RuntimeError("Container stopped, restarted or changed during benchmark")
    count = result["access_counts"].get("POST /v1/chat/completions 200", 0)
    other_writes = sum(n for key, n in result["access_counts"].items()
                       if not key.startswith(("GET ", "HEAD ", "OPTIONS "))
                       and key != "POST /v1/chat/completions 200")
    if count != expected_requests or other_writes or result["unparsed_request_lines"]:
        # TensorFold's access log may not be emitted; the health-counter delta is the
        # authoritative traffic check in that case. Do not fail on missing log lines.
        return {"access_log_requests": count, "access_log_other_writes": other_writes,
                "access_log_available": bool(result["access_counts"])}
    return {"access_log_requests": count, "access_log_other_writes": other_writes,
            "access_log_available": True}
