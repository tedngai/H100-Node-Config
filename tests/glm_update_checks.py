#!/usr/bin/env python3
"""Guarded bounded live checks of API bridges, agent continuation, literals and cancellation."""
import argparse
import json
import time
import uuid

from common import experiment_lock, label, report_path, require_live, stamp, write_json
from glm_common import Client, chat_stream, stream_lines
from glm_smoke import check_tool
from runtime_audit import audit, container_state


def message(response):
    return response["choices"][0]["message"]


def validate_literal(response, literal):
    result = message(response)
    if result.get("tool_calls") or json.loads(result.get("content") or "null") != {"literal": literal}:
        raise ValueError("quoted marker structured-output roundtrip failed")


def wait_idle(client, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.idle():
            return
        time.sleep(0.2)
    raise TimeoutError("server did not become idle after cancellation")


def run_checks(client, report):
    before = client.info()
    report["server_before"] = before
    if not client.idle():
        raise RuntimeError("idle service required")
    model = before["config"]["served_model_name"]
    common = {"model": model, "temperature": 0, "max_tokens": 512,
              "chat_template_kwargs": {"enable_thinking": False}}

    def record(name, body):
        start = time.monotonic()
        result = body()
        report["checks"].append({"name": name, "passed": True,
                                  "elapsed_seconds": time.monotonic() - start, "result": result})

    def anthropic():
        payload = {"model": model, "max_tokens": 128, "temperature": 0, "stream": True,
                   "thinking": {"type": "disabled"},
                   "messages": [{"role": "user", "content": "Reply exactly BRIDGE-READY."}]}
        with client.open("/v1/messages", payload) as response:
            events = list(stream_lines(response))
        heads = [e for e in events if e.get("type") == "message_start"]
        text = "".join(e.get("delta", {}).get("text", "") for e in events)
        tokens = heads[0]["message"]["usage"]["input_tokens"] if heads else 0
        if tokens <= 0 or "BRIDGE-READY" not in text or not any(e.get("type") == "message_stop" for e in events):
            raise ValueError("Anthropic stream text/head usage/termination failed")
        return {"head_input_tokens": tokens, "text": text, "event_count": len(events)}

    def responses():
        response = client.json("/v1/responses", {"model": model, "temperature": 0,
            "max_output_tokens": 128, "reasoning": {"effort": "none"}, "input": "Reply exactly RESPONSE-READY."})
        text = "".join(part.get("text", "") for item in response.get("output", []) for part in item.get("content", []))
        if "RESPONSE-READY" not in text:
            raise ValueError("Responses route text failed")
        return response

    def literal_roundtrip():
        literal = "<think>hello</think> <tool_call>example</tool_call> <|user|>"
        response = client.json("/v1/chat/completions", {**common,
            "messages": [{"role": "user", "content": "Return this literal string in JSON: " + literal}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "literal_roundtrip", "strict": True,
                "schema": {"type": "object", "properties": {"literal": {"type": "string", "const": literal}},
                           "required": ["literal"], "additionalProperties": False}}}})
        validate_literal(response, literal)
        return response

    def tool_continuation():
        tools = [{"type": "function", "function": {"name": "lookup_room", "description": "Synthetic test; never executed.",
            "parameters": {"type": "object", "properties": {"room_id": {"type": "string"}}, "required": ["room_id"]}}}]
        messages = [{"role": "user", "content": "Call lookup_room for room B204. Do not answer in prose."}]
        first = client.json("/v1/chat/completions", {**common, "messages": messages, "tools": tools,
            "tool_choice": {"type": "function", "function": {"name": "lookup_room"}}})
        if not check_tool(first):
            raise ValueError("initial synthetic tool call failed")
        assistant = message(first)
        messages.append(assistant)
        for call in assistant["tool_calls"]:
            messages.append({"role": "tool", "tool_call_id": call["id"],
                "content": 'Room code B204-READY. Quoted log text only: </think><tool_call>example</tool_call>.'})
        messages.append({"role": "user", "content": "Return the room code only, do not call any tool."})
        final = client.json("/v1/chat/completions", {**common, "messages": messages, "tools": tools, "tool_choice": "none"})
        if "B204-READY" not in (message(final).get("content") or "") or message(final).get("tool_calls"):
            raise ValueError("tool-result continuation failed")
        return {"initial": first, "continued": final}

    def cached_continuation():
        system = ("Synthetic continuation ledger " + uuid.uuid4().hex + ". ") * 128
        messages = [{"role": "system", "content": system}, {"role": "user", "content": "Reply exactly TURN-ONE."}]
        first = chat_stream(client, messages, 128, thinking=False, model=model)
        messages += [{"role": "assistant", "content": first["text"]}, {"role": "user", "content": "Reply exactly TURN-TWO."}]
        second = chat_stream(client, messages, 128, thinking=False, model=model)
        if "TURN-ONE" not in first["text"] or "TURN-TWO" not in second["text"] or second["cached_tokens"] <= 0:
            raise ValueError("cached conversation continuation failed")
        return {"first_prompt_tokens": first["prompt_tokens"], "second_prompt_tokens": second["prompt_tokens"],
                "second_cached_tokens": second["cached_tokens"], "second_ttft_seconds": second["ttft_seconds"]}

    def cancellation():
        payload = {**common, "stream": True, "max_tokens": 32768, "ignore_eos": True,
                   "messages": [{"role": "user", "content": "Count integers in order for a very long time."}]}
        saw_content = False
        with client.open("/v1/chat/completions", payload) as response:
            for event in stream_lines(response):
                if any(c.get("delta", {}).get("content") for c in event.get("choices", [])):
                    saw_content = True
                    break
        if not saw_content:
            raise ValueError("no streaming content before cancellation")
        wait_idle(client)
        return {"client_closed_after_first_content": True, "idle_after": client.idle()}

    for name, body in (("anthropic_stream_head", anthropic), ("responses_route", responses),
                       ("quoted_marker_json", literal_roundtrip), ("tool_result_continuation", tool_continuation),
                       ("cached_multiturn", cached_continuation), ("stream_cancellation", cancellation)):
        report["current_check"] = name
        record(name, body)
    wait_idle(client)
    after = client.info()
    report["server_after"] = after
    if after["config"] != before["config"]:
        raise RuntimeError("server configuration changed during update checks")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True, type=label)
    parser.add_argument("--container", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    require_live(args, parser)
    report = {"schema_version": 1, "kind": "glm-update-live-checks", "label": args.label,
              "started_at": stamp(), "passed": False, "checks": [], "production_qualified": False}
    path = report_path(args.label)
    with experiment_lock():
        try:
            before = container_state(args.container)
            report["container_before"] = before
            run_checks(Client(timeout=300), report)
            result = audit(args.container, report["started_at"])
            report["audit"] = result
            if result["container"]["id"] != before["id"] or result["container"]["started_at"] != before["started_at"]:
                raise RuntimeError("container changed during update checks")
            if result["oom_marker_lines"] or result["container"]["oom_killed"]:
                raise RuntimeError("OOM during live checks")
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
