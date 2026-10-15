"""Offline capacity policy, OOM audit, and multi-round regression tests."""

import contextlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark
from benchmark_policy import describe_policy, memory_status, summarize_observations
import runtime_audit


class PolicyTests(unittest.TestCase):
    def test_missing_metrics_are_unknown(self):
        result = summarize_observations({"samples": [], "errors": []})
        self.assertIsNone(result["peak_num_running_reqs"])
        self.assertIsNone(result["queue_observed"])
        self.assertIsNone(result["strict_no_queue_observed"])
        self.assertIsNone(memory_status({})["low_memory_warning"])

    def test_peaks_not_summed_and_waiting_not_inferred_from_clients(self):
        result = summarize_observations({"samples": [
            {"num_running_reqs": 0, "num_queue_reqs": 5},
            {"num_running_reqs": 6, "num_queue_reqs": 0}]})
        self.assertEqual(result["peak_num_running_reqs"], 6)
        self.assertEqual(result["samples_with_waiting"], 1)
        self.assertTrue(result["queue_observed"])

    def test_low_memory_is_warning_unless_hard_floor_explicit(self):
        summary = {"minimum_free_mib_by_gpu": {"0": 2297, "1": 2731}}
        self.assertTrue(memory_status(summary)["low_memory_warning"])
        self.assertIsNone(memory_status(summary)["floor_breached"])
        self.assertTrue(memory_status(summary, stop_mib=3072)["floor_breached"])
        self.assertEqual(describe_policy()["queueing"], "measure_only")


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.state = {"id": "x", "image_id": "y", "argv": ["serve"], "running": True,
                      "oom_killed": False, "started_at": "now", "restart_count": 0}

    def test_raw_logs_and_unknown_routes_never_saved(self):
        result = runtime_audit.parse_logs('INFO "POST /generate HTTP/1.1" 200 OK\n'
                                         'INFO "GET /secret-path?token=secret HTTP/1.1" 200 OK\n'
                                         'torch.OutOfMemoryError: CUDA out of memory\n')
        self.assertEqual(result["oom_marker_lines"], 1)
        self.assertNotIn("secret", json.dumps(result))
        self.assertFalse(result["raw_logs_saved"])

    def test_audit_rejects_oom_restarts_and_other_inference(self):
        result = {**runtime_audit.parse_logs('"POST /generate HTTP/1.1" 200 OK'),
                  "container": self.state}
        runtime_audit.validate_audit(result, self.state, 1)
        for changed in ({"oom_marker_lines": 1},
                        {"container": {**self.state, "restart_count": 1}},
                        {"container": {**self.state, "oom_killed": True}},
                        {"access_counts": {"POST /generate 200": 1, "POST /v1/chat/completions 200": 1}}):
            with self.assertRaises(RuntimeError):
                runtime_audit.validate_audit({**result, **changed}, self.state, 1)

    def test_failed_audit_is_unavailable_not_zero(self):
        completed = SimpleNamespace(returncode=1, stdout="", stderr="private error")
        with patch.object(runtime_audit.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "unknown"):
                runtime_audit.audit("candidate", "20261015T164404.677918Z")


class CapacityFlowTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(base_url="http://127.0.0.1:8011", timeout=60,
                                    profile="memory-088", concurrency=6, prompt_tokens=100000,
                                    output_tokens=512, rounds=3, pool_fraction=.9, cache="cold",
                                    warmup_passes=1, seed=1, container="candidate", mode="decode",
                                    policy="capacity", memory_warning_mib=3072, min_free_gpu_mib=None)
        self.info = {"config": {"status": "ready", "dp_size": 1, "model_path": "model",
                               "allow_auto_truncate": False, "context_length": 262144,
                               "max_req_input_len": 262138, "max_running_requests": 48,
                               "max_total_num_tokens": 1717184, "enable_metrics": False}}
        self.state = {"id": "x", "image_id": "y", "argv": ["serve"], "running": True,
                      "oom_killed": False, "started_at": "now", "restart_count": 0}
        self.report = {"started_at": "20261015T164404.677918Z", "run_id": "offline", "rounds": []}
        self.gpu = {"at": "now", "devices": [{"index": i, "total_mib": 81559,
                                               "used_mib": 79262, "free_mib": 2297} for i in range(4)]}
        self.requests = 0

    def generate(self, *args):
        self.requests += 1
        self.report["metrics"]["samples"].append({"num_running_reqs": 6, "num_queue_reqs": 5,
                                                  "num_retracted_reqs": 0})
        return {"meta_info": {"prompt_tokens": 100000, "completion_tokens": 512, "num_retractions": 0},
                "elapsed_seconds": 23, "ttft_seconds": 12, "end_to_end_tokens_per_second": 22,
                "average_tpot_seconds_estimate": .02, "retrieval_passed": True}

    def audit(self, *args):
        return {"container": self.state, "access_counts": {"POST /generate 200": self.requests},
                "oom_marker_lines": 0, "error_marker_lines": 0, "unparsed_request_lines": 0}

    @contextlib.contextmanager
    def mocks(self):
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value=self.state), \
                patch.object(benchmark, "container_state", return_value=self.state), \
                patch.object(benchmark, "audit", side_effect=self.audit), \
                patch.object(benchmark, "sample_loads", return_value={"num_running_reqs": 0, "num_queue_reqs": 0}), \
                patch.object(benchmark, "sample_gpu_memory", return_value=self.gpu), \
                patch.object(benchmark, "build_prompts", return_value=[{} for _ in range(6)]), \
                patch.object(benchmark, "generate", side_effect=self.generate), patch("builtins.print"):
            yield

    def test_three_c6_rounds_continue_through_queue_and_low_memory(self):
        with self.mocks():
            benchmark.run(self.args, self.report)
        self.assertEqual(self.requests, 18)
        self.assertTrue(all(row["completed"] for row in self.report["rounds"]))
        self.assertTrue(self.report["gpu_memory"]["low_memory_warning"])
        self.assertIsNone(self.report["gpu_memory"]["floor_breached"])
        self.assertFalse(self.report["oom_observed"])
        self.assertTrue(self.report["metrics"]["queue_observed"])

    def test_oom_in_audit_stops_after_first_round(self):
        clean_audit = self.audit
        self.audit = lambda *args: {**clean_audit(*args), "oom_marker_lines": 1}
        with self.mocks():
            with self.assertRaisesRegex(RuntimeError, "OOM observed"):
                benchmark.run(self.args, self.report)
        self.assertEqual(self.requests, 6)
        self.assertTrue(self.report["oom_observed"])
        self.assertTrue(self.report["gpu_memory"]["low_memory_warning"])
        self.assertIn("server_after", self.report)

    def test_no_queue_remains_explicit_opt_in(self):
        self.args.policy = "no-queue"
        with self.mocks():
            with self.assertRaisesRegex(RuntimeError, "Queueing"):
                benchmark.run(self.args, self.report)
        self.assertEqual(self.requests, 6)

    def test_explicit_memory_floor_still_prevents_inference(self):
        self.args.min_free_gpu_mib = 3072
        with self.mocks():
            with self.assertRaisesRegex(RuntimeError, "no inference sent"):
                benchmark.run(self.args, self.report)
        self.assertEqual(self.requests, 0)

    def test_health_change_stops_later_rounds(self):
        with self.mocks(), patch.object(benchmark.Client, "info", side_effect=[self.info,
                {"config": {**self.info["config"], "status": "error"}}, self.info]):
            with self.assertRaisesRegex(RuntimeError, "health/configuration"):
                benchmark.run(self.args, self.report)
        self.assertEqual(self.requests, 6)

    def test_later_gpu_query_failure_is_unknown_telemetry_not_oom(self):
        calls = 0

        def gpu_query():
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("mock telemetry unavailable")
            return self.gpu

        with self.mocks(), patch.object(benchmark, "sample_gpu_memory", side_effect=gpu_query):
            benchmark.run(self.args, self.report)
        self.assertEqual(self.requests, 18)
        self.assertFalse(self.report["telemetry_complete"])
        self.assertFalse(self.report["oom_observed"])

    def test_unavailable_final_audit_cannot_claim_no_oom(self):
        clean_audit = self.audit
        calls = 0

        def audited(*args):
            nonlocal calls
            calls += 1
            if calls > 3:
                raise RuntimeError("audit unavailable")
            return clean_audit(*args)

        self.audit = audited
        with self.mocks():
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                benchmark.run(self.args, self.report)
        self.assertIsNone(self.report["oom_observed"])

    def test_idle_wait_uses_selected_metric_source(self):
        source = lambda client: {"num_running_reqs": 0, "num_queue_reqs": 0}
        with patch.object(benchmark, "sample_loads", side_effect=RuntimeError("unavailable")):
            self.assertEqual(benchmark.wait_for_idle(None, sampler=source)["num_running_reqs"], 0)


if __name__ == "__main__":
    unittest.main()
