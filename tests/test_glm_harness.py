import base64
import json
import unittest
import io
from glm_update_checks import validate_literal

from glm_common import chat_stream, check_budget, decode_prompt, png_data_url, retrieval_prompt, stream_lines


class FakeClient:
    def tokenize_count(self, messages):
        return 1000


class BudgetTests(unittest.TestCase):
    def config(self, **overrides):
        base = {
            "status": "ready", "dp_size": 1, "allow_auto_truncate": False,
            "max_running_requests": 4, "context_length": 1048576,
            "max_total_num_tokens": 2965504,
        }
        base.update(overrides)
        return base

    def test_accepts_four_streams(self):
        check_budget(self.config(), 4, 1024, 256)

    def test_rejects_more_than_served_streams(self):
        with self.assertRaises(ValueError):
            check_budget(self.config(), 5, 1024, 256)

    def test_rejects_pool_overcommit(self):
        with self.assertRaises(ValueError):
            check_budget(self.config(max_total_num_tokens=1000), 4, 1024, 256)

    def test_rejects_not_ready(self):
        with self.assertRaises(ValueError):
            check_budget(self.config(status="busy"), 1, 128, 16)


class PromptTests(unittest.TestCase):
    def test_retrieval_prompt_contains_codes_and_question(self):
        prompt = retrieval_prompt(FakeClient(), 1000, 7, "unit")
        content = prompt["messages"][-1]["content"]
        for code in prompt["expected_codes"]:
            self.assertIn(code, content)
        self.assertIn("What are the three access codes?", content)
        self.assertEqual(len(prompt["expected_codes"]), 3)

    def test_decode_prompt_has_no_codes(self):
        prompt = decode_prompt(FakeClient(), 1000, 7, "unit")
        self.assertEqual(prompt["expected_codes"], [])
        self.assertIn("technical analysis", prompt["messages"][-1]["content"])

    def test_png_data_url_is_a_png(self):
        url = png_data_url(8, 8, (255, 0, 0))
        prefix = "data:image/png;base64,"
        self.assertTrue(url.startswith(prefix))
        data = base64.b64decode(url[len(prefix):])
        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))


class StreamTests(unittest.TestCase):
    def test_literal_roundtrip_rejects_spurious_calls_and_changed_content(self):
        def response(content, calls=None):
            return {"choices": [{"message": {"content": content, "tool_calls": calls}}]}
        validate_literal(response('{"literal":"<think>text</think>"}'), "<think>text</think>")
        for value in (response('{"literal":"wrong"}'), response('{"literal":"ok"}', [{"id": "unexpected"}])):
            with self.assertRaises(ValueError):
                validate_literal(value, "ok")

    def test_sampling_parameters_are_explicit_and_greedy_default_is_preserved(self):
        class Client:
            def open(self, endpoint, body):
                self.body = body
                return io.StringIO('data: {"choices":[{"delta":{"content":"ok"}}]}\n'
                                   'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":1}}\n'
                                   'data: [DONE]\n')
        client = Client()
        observed = []
        chat_stream(client, [], 1, content_observer=observed.append)
        self.assertEqual(len(observed), 1)
        self.assertIsInstance(observed[0], float)
        self.assertEqual(client.body["temperature"], 0)
        self.assertNotIn("top_p", client.body)
        chat_stream(client, [], 1, temperature=1, top_p=0.95)
        self.assertEqual(client.body["temperature"], 1)
        self.assertEqual(client.body["top_p"], 0.95)

    def test_parses_events_and_stops_at_done(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "hi"}}]}',
            'data: {"choices": [], "usage": {"completion_tokens": 1}}',
            "data: [DONE]",
            'data: {"choices": [{"delta": {"content": "never"}}]}',
        ]
        events = list(stream_lines(lines))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["usage"]["completion_tokens"], 1)

    def test_server_error_is_raised(self):
        with self.assertRaises(RuntimeError):
            list(stream_lines(['data: {"error": {"message": "boom"}}']))


if __name__ == "__main__":
    unittest.main()
