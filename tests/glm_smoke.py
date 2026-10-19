#!/usr/bin/env python3
"""Guarded GLM chat, reasoning, tool-call and vision smoke checks."""

import argparse
import json
import time

from common import experiment_lock, label, report_path, require_live, stamp, write_json
from glm_common import Client, DEFAULT_CONTAINER, DEFAULT_URL, png_data_url


def check_chat(response):
    message = response["choices"][0]["message"]
    return "H100-READY" in (message.get("content") or "")


def check_reasoning(response):
    choice = response["choices"][0]
    message = choice["message"]
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or ""
    return (bool(reasoning) and "42" in content
            and " thinking" not in content and " response" not in content
            and choice.get("finish_reason") != "length")


def check_tool(response):
    for call in response["choices"][0]["message"].get("tool_calls") or []:
        function = call.get("function", {})
        try:
            arguments = json.loads(function.get("arguments", "{}"))
        except (TypeError, json.JSONDecodeError):
            continue
        if function.get("name") == "lookup_room" and arguments == {"room_id": "B204"}:
            return True
    return False


def check_vision(response):
    message = response["choices"][0]["message"]
    text = (message.get("content") or "").strip().lower()
    return bool(text) and any(word in text for word in ("red", "crimson", "scarlet"))


def run(client, report, check_vision_case):
    before = client.info()
    report["server_before"] = before
    if before["config"]["status"] != "ready":
        raise ValueError("Server is not ready")
    if not client.idle():
        raise ValueError("Server is not idle; refuse to send smoke inference")
    model = before["config"]["served_model_name"]
    common = {"model": model, "temperature": 0, "max_tokens": 2048, "stream": False}
    cases = [
        ("chat", {"messages": [{"role": "user", "content": "Reply with exactly H100-READY."}],
                  "chat_template_kwargs": {"enable_thinking": False}}, check_chat),
        ("reasoning", {"messages": [{"role": "user", "content":
                        "Think briefly: what is 19 + 23? Put the answer in your final response."}],
                       "chat_template_kwargs": {"enable_thinking": True}}, check_reasoning),
        ("tool_call", {
            "messages": [{"role": "user", "content": "Call lookup_room for room B204. Do not answer in prose."}],
            "chat_template_kwargs": {"enable_thinking": False},
            "tools": [{"type": "function", "function": {
                "name": "lookup_room", "description": "Synthetic test function; nothing is executed.",
                "parameters": {"type": "object", "properties": {"room_id": {"type": "string"}},
                               "required": ["room_id"], "additionalProperties": False},
            }}], "tool_choice": {"type": "function", "function": {"name": "lookup_room"}},
        }, check_tool),
    ]
    if check_vision_case:
        vision_messages = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": png_data_url()}},
            {"type": "text", "text": "What is the dominant colour of this image? Answer with one word."},
        ]}]
        cases.append(("vision", {"messages": vision_messages,
                                 "chat_template_kwargs": {"enable_thinking": False}}, check_vision))

    try:
        for name, extra, check in cases:
            started = time.monotonic()
            response = client.json("/v1/chat/completions", {**common, **extra})
            passed = check(response)
            report["checks"].append({"name": name, "passed": passed,
                                     "elapsed_seconds": time.monotonic() - started,
                                     "response": response})
            if not passed:
                raise RuntimeError(name + " check failed; response retained")
    finally:
        try:
            report["server_after"] = client.info()
        except Exception as error:  # noqa: BLE001
            report["server_after_error"] = str(error)
    if report.get("server_after_error") or report["server_after"]["config"] != before["config"]:
        raise RuntimeError("Could not verify unchanged, healthy server after smoke checks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--profile", default="glm53-flash-exl3-1m")
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--vision", action="store_true", help="also send a synthetic red image")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    report = {"schema_version": 1, "kind": "glm-interface-smoke", "label": args.label,
              "started_at": stamp(), "checks": [], "passed": False, "base_url": args.base_url}
    path = report_path(args.label)
    with experiment_lock():
        try:
            run(Client(args.base_url), report, args.vision)
            report["passed"] = True
        except Exception as error:  # noqa: BLE001
            report["error"] = {"type": type(error).__name__, "message": str(error)}
        except KeyboardInterrupt:
            report["error"] = {"type": "KeyboardInterrupt"}
        finally:
            report["finished_at"] = stamp()
            write_json(path, report)
    print(json.dumps({"report": str(path), "passed": report["passed"], "error": report.get("error")}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
