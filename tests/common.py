"""Standard-library utilities; no inference or deployment on import."""

import contextlib
import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "http://127.0.0.1:8011"
DEFAULT_CONTAINER = "sglang-qwen38-flash-next"
CONFIG_KEYS = (
    "version", "status", "model_path", "tokenizer_path", "served_model_name",
    "context_length", "max_req_input_len", "max_running_requests",
    "max_queued_requests", "max_total_num_tokens", "tp_size", "ep_size", "dp_size",
    "pp_size", "dtype", "kv_cache_dtype", "mem_fraction_static",
    "chunked_prefill_size", "max_prefill_tokens", "attention_backend",
    "decode_attention_backend", "prefill_attention_backend", "linear_attn_backend",
    "linear_attn_prefill_backend", "linear_attn_decode_backend",
    "linear_attn_verify_backend", "mamba_ssm_dtype", "mamba_full_memory_ratio",
    "mamba_radix_cache_strategy", "max_mamba_cache_size", "uses_mamba_radix_cache",
    "speculative_algorithm", "speculative_num_steps", "speculative_eagle_topk",
    "speculative_num_draft_tokens", "speculative_draft_model_path",
    "reasoning_parser", "tool_call_parser", "allow_auto_truncate", "enable_metrics",
    "enable_hierarchical_cache", "schedule_policy", "page_size",
)
SECRET_KEY = re.compile(r"api.?key|password|secret|authorization|^hf_token$|^github_pat$", re.I)
SECRET_VALUE = re.compile(r"\bhf_[A-Za-z0-9]{16,}\b|\bgh[pousr]_[A-Za-z0-9]{16,}\b|\bgithub_pat_[A-Za-z0-9_]+\b")


def scrub(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if SECRET_KEY.search(k) else scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return SECRET_VALUE.sub("[REDACTED]", value)
    return value


def label(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Label must be 1-80 letters, digits, underscores or hyphens")
    return value


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def write_json(path, data):
    """Exclusive creation: reports and baselines are never overwritten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(scrub(data), stream, indent=2, allow_nan=False)
        stream.write("\n")
    return path


def report_path(name):
    return ROOT / "evidence" / f"{label(name)}-{stamp()}.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Client:
    def __init__(self, base_url=DEFAULT_URL, timeout=600):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path.rstrip("/")):
            raise ValueError("Use an http(s) server origin, without credentials or a path")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def open(self, endpoint, payload=None):
        headers = {"Content-Type": "application/json"}
        if os.environ.get("SGLANG_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["SGLANG_API_KEY"]
        data = None if payload is None else json.dumps(payload).encode()
        return urllib.request.urlopen(urllib.request.Request(
            self.base_url + endpoint, data=data, headers=headers,
        ), timeout=self.timeout)

    def json(self, endpoint, payload=None):
        with self.open(endpoint, payload) as response:
            return json.load(response)

    def info(self):
        try:
            raw = self.json("/get_server_info")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            raw = self.json("/server_info")
        models = self.json("/v1/models")["data"]
        match = [m for m in models if m["id"] == raw.get("served_model_name")]
        if len(match) != 1:
            raise ValueError("Cannot identify the served model in /v1/models")
        config = {k: raw.get(k) for k in CONFIG_KEYS}
        config["context_length"] = raw.get("context_length") or match[0].get("max_model_len")
        if not config["context_length"]:
            raise ValueError("Context length unavailable from both server endpoints")
        states = [{k: state.get(k) for k in (
            "memory_usage", "effective_max_running_requests_per_dp", "max_mamba_cache_size",
        )} for state in raw.get("internal_states", [])]
        return {"config": config, "internal_states": states, "model": match[0]}


def check_budget(config, concurrency, prompt_tokens, output_tokens, pool_fraction=0.9):
    if min(concurrency, prompt_tokens, output_tokens) < 1:
        raise ValueError("Concurrency and token counts must be positive")
    if not 0 < pool_fraction <= 0.9:
        raise ValueError("Pool fraction must be positive and no greater than 0.90")
    if config.get("status") != "ready" or config.get("dp_size") != 1:
        raise ValueError("This harness requires a ready DP1 server; DP metrics need separate accounting")
    if config.get("allow_auto_truncate") is not False:
        raise ValueError("Disable automatic truncation before measurement")
    if not config.get("max_running_requests") or concurrency > config["max_running_requests"]:
        raise ValueError("Client concurrency exceeds the server's active-request cap")
    if prompt_tokens > (config.get("max_req_input_len") or config["context_length"]):
        raise ValueError("Prompt exceeds the effective input-token limit")
    if prompt_tokens + output_tokens > config["context_length"]:
        raise ValueError("Prompt plus output exceeds the context window")
    capacity = config.get("max_total_num_tokens")
    if not capacity or concurrency * (prompt_tokens + output_tokens) > capacity * pool_fraction:
        raise ValueError("Workload exceeds the guarded shared token-pool budget")


def verify_profile(config, profile_name):
    from profiles import resolve_profile
    profile = resolve_profile(profile_name)
    differences = {k: {"expected": v, "actual": config.get(k)}
                   for k, v in profile["expected_config"].items() if config.get(k) != v}
    if differences:
        raise ValueError("Live server does not match profile: " + json.dumps(differences))
    return profile


def require_live(args, parser):
    if not args.execute or not args.confirm_idle:
        parser.error("No inference sent: both --execute and --confirm-idle are required")


@contextlib.contextmanager
def experiment_lock():
    """Coordinates this workspace's tests, not other clients or other workspaces."""
    with (ROOT / ".benchmark.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another experiment in this workspace is running") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def percentile(values, fraction):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    if not values:
        return None
    position = (len(values) - 1) * fraction
    left, right = math.floor(position), math.ceil(position)
    return values[left] + (values[right] - values[left]) * (position - left)
