"""Offline tests only: mocked HTTP, temporary local files, no Docker or GPU calls."""

import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

import benchmark
import capture_baseline
import common
import gpu_memory
import profiles
import prompts
import prefill_diagnostic
import smoke_test
import validate_setup


def config():
    return {
        "status": "ready", "dp_size": 1, "allow_auto_truncate": False,
        "context_length": 262144, "max_req_input_len": 262138,
        "max_running_requests": 48, "max_total_num_tokens": 1587968,
    }


def sample(prompt=1024, completion=256, retractions=None):
    meta = {"prompt_tokens": prompt, "completion_tokens": completion}
    if retractions is not None:
        meta["num_retractions"] = retractions
    return {"elapsed_seconds": 2.0, "ttft_seconds": 0.1,
            "average_tpot_seconds_estimate": 0.01,
            "end_to_end_tokens_per_second": completion / 2,
            "meta_info": meta, "retrieval_passed": True}


class SafetyTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(common.label("baseline-c6"), "baseline-c6")
        for value in ("../escape", "", "x/y", "space name", "x" * 81):
            with self.assertRaises(ValueError):
                common.label(value)

    def test_exclusive_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            common.write_json(path, {"passed": False})
            with self.assertRaises(FileExistsError):
                common.write_json(path, {"passed": True})
            self.assertFalse(json.loads(path.read_text())["passed"])

    def test_secrets_redacted_not_token_counts(self):
        token = "hf_" + "X" * 30
        data = common.scrub({"api_key": "sensitive", "nested": [token], "completion_tokens": 123})
        self.assertEqual(data["api_key"], "[REDACTED]")
        self.assertEqual(data["nested"], ["[REDACTED]"])
        self.assertEqual(data["completion_tokens"], 123)

    def test_url_restrictions(self):
        for value in ("file:///etc/passwd", "http://user:secret@host", "http://host/v1", "http://host?key=secret"):
            with self.assertRaises(ValueError):
                common.Client(value)
        self.assertEqual(common.Client("http://localhost:8011/").base_url, "http://localhost:8011")

    def test_live_guards_exit_without_network(self):
        for script in ("benchmark.py", "smoke_test.py", "prefill_diagnostic.py", "scheduled_benchmark.py"):
            for flags in ([], ["--execute"], ["--confirm-idle"]):
                extra = ["--concurrency", "2", "--cache", "cold"] if script == "scheduled_benchmark.py" else []
                result = subprocess.run([sys.executable, "-B", str(common.ROOT / "tests" / script),
                                         "--label", "offline-test", "--base-url", "http://127.0.0.1:1", *extra, *flags],
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)
                self.assertIn("No inference sent", result.stderr)

    def test_local_lock(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(common, "ROOT", Path(directory)):
            with common.experiment_lock():
                with self.assertRaises(RuntimeError):
                    with common.experiment_lock():
                        self.fail("Second experiment acquired the same lock")

    def test_percentiles(self):
        self.assertEqual(common.percentile([None, 1, 3], 0.5), 2)
        self.assertIsNone(common.percentile([], 0.95))

    def test_container_restart_does_not_change_container_identity(self):
        baseline = {"id": "container-id", "image_id": "image-id", "argv": ["serve"],
                    "started_at": "before-reboot"}
        identity = {"id": "container-id", "image_id": "image-id", "argv": ["serve"]}
        state = {"StartedAt": "after-reboot"}
        self.assertEqual(validate_setup.compare_container(baseline, identity, state), (True, False))


class BudgetTests(unittest.TestCase):
    def test_normal_and_long_workloads(self):
        common.check_budget(config(), 6, 200000, 1024)
        common.check_budget(config(), 6, 230000, 1024)
        common.check_budget(config(), 1, 260000, 1024)

    def test_six_full_contexts_rejected_for_headroom(self):
        with self.assertRaisesRegex(ValueError, "shared token-pool"):
            common.check_budget(config(), 6, 260000, 1024)

    def test_context_and_input_limits(self):
        for prompt, output in ((262140, 1), (262138, 10)):
            with self.assertRaises(ValueError):
                common.check_budget(config(), 1, prompt, output)

    def test_request_cap(self):
        with self.assertRaisesRegex(ValueError, "active-request cap"):
            common.check_budget(config(), 49, 1024, 256)

    def test_dp_and_health_rejected(self):
        for changed in ({"dp_size": 4}, {"status": "loading"}, {"allow_auto_truncate": True}):
            with self.assertRaises(ValueError):
                common.check_budget({**config(), **changed}, 1, 1024, 256)

    def test_cannot_bypass_pool_guard(self):
        for fraction in (0, -1, 0.91, 1, float("nan")):
            with self.assertRaises(ValueError):
                common.check_budget(config(), 1, 1024, 256, fraction)


class ClientTests(unittest.TestCase):
    def test_null_context_falls_back_to_models(self):
        client = common.Client()
        with patch.object(client, "json", side_effect=[
            {"context_length": None, "served_model_name": "pratt-medium", "api_key": "do-not-copy"},
            {"data": [{"id": "pratt-medium", "max_model_len": 262144}]},
        ]):
            result = client.info()
        self.assertEqual(result["config"]["context_length"], 262144)
        self.assertNotIn("api_key", result["config"])

    def test_legacy_endpoint_fallback(self):
        client = common.Client()
        with patch.object(client, "json", side_effect=[
            urllib.error.HTTPError("url", 404, "missing", {}, None),
            {"context_length": 262144, "served_model_name": "test"},
            {"data": [{"id": "test", "max_model_len": 262144}]},
        ]) as mocked:
            self.assertEqual(client.info()["config"]["context_length"], 262144)
            self.assertEqual(mocked.call_args_list[1].args, ("/server_info",))

    def test_does_not_mask_auth_error(self):
        client = common.Client()
        with patch.object(client, "json", side_effect=urllib.error.HTTPError("url", 401, "denied", {}, None)) as mocked:
            with self.assertRaises(urllib.error.HTTPError):
                client.info()
            self.assertEqual(mocked.call_count, 1)


class ProfileTests(unittest.TestCase):
    def test_modify_argv(self):
        result = profiles.modify_argv(["sglang", "serve", "--tp", "4", "--enable-metrics"],
                                      {"--tp": "2", "--mem-fraction-static": "0.85"}, ["--enable-metrics"])
        self.assertEqual(result, ["sglang", "serve", "--tp", "2", "--mem-fraction-static", "0.85"])

    def test_duplicate_flags_rejected(self):
        with self.assertRaises(ValueError):
            profiles.modify_argv(["--tp", "4", "--tp=2"], {"--tp": "1"}, [])

    def test_baseline_preserved_exactly(self):
        captured = json.loads((common.ROOT / "configs/baseline.json").read_text())
        self.assertEqual(profiles.resolve_profile("baseline")["argv"], captured["container"]["argv"])
        self.assertEqual(captured["server"]["config"]["max_running_requests"], 48)

    def test_candidates_isolate_changes(self):
        self.assertEqual(profiles.resolve_profile("admission-6")["expected_config"]["max_running_requests"], 6)
        self.assertEqual(profiles.resolve_profile("prefill-4096")["expected_config"]["mem_fraction_static"], 0.85)
        self.assertNotIn("--speculative-algorithm", profiles.resolve_profile("mtp-off")["argv"])
        self.assertNotIn("max_req_input_len", profiles.resolve_profile("mtp-shallow")["expected_config"])
        baseline_argv = profiles.resolve_profile("baseline")["argv"]
        memory_profile = profiles.resolve_profile("memory-088")
        expected_argv = profiles.modify_argv(baseline_argv, {"--mem-fraction-static": "0.88"}, [])
        self.assertEqual(memory_profile["argv"], expected_argv)
        self.assertEqual(memory_profile["expected_config"]["mem_fraction_static"], 0.88)
        self.assertNotIn("max_running_requests", memory_profile["expected_config"])

    def test_profile_mismatch_prevents_inference(self):
        expected = profiles.resolve_profile("baseline")["expected_config"]
        with self.assertRaisesRegex(ValueError, "does not match"):
            common.verify_profile({**expected, "mem_fraction_static": 0.9}, "baseline")


class GPUMemoryTests(unittest.TestCase):
    def test_parse_gpu_memory_sanitized_and_sorted(self):
        result = gpu_memory.parse_gpu_memory(
            "2, 100, 40\n0, 100, 50\n3, 100, 20\n1, 100, 30\n")
        self.assertEqual([device["index"] for device in result], [0, 1, 2, 3])
        self.assertEqual(result[0]["free_mib"], 50)

    def test_rejects_missing_or_invalid_gpu_rows(self):
        with self.assertRaisesRegex(ValueError, "Expected"):
            gpu_memory.parse_gpu_memory("0, 100, 1\n", expected_gpu_count=4)
        with self.assertRaisesRegex(ValueError, "Invalid"):
            gpu_memory.parse_gpu_memory("0, 100, 101\n", expected_gpu_count=1)

    def test_summarizes_per_gpu_without_summing(self):
        samples = [
            {"devices": [{"index": index, "used_mib": 10 + index,
                          "free_mib": 90 - index} for index in range(4)]},
            {"devices": [{"index": index, "used_mib": 20 + index,
                          "free_mib": 80 - index} for index in range(4)]},
        ]
        summary = gpu_memory.summarize_gpu_memory(samples)
        self.assertEqual(summary["minimum_free_mib_by_gpu"]["0"], 80)
        self.assertEqual(summary["maximum_used_mib_by_gpu"]["3"], 23)


class StreamTests(unittest.TestCase):
    def test_first_text_observer_uses_client_monotonic_clock_once(self):
        stream = io.BytesIO(b'data: {"text":"","meta_info":{"completion_tokens":0}}\n'
                            b'data: {"text":"a","meta_info":{"completion_tokens":1}}\n'
                            b'data: {"text":"ab","meta_info":{"completion_tokens":2}}\n')
        observer = unittest.mock.Mock()
        with patch.object(benchmark.time, "monotonic", side_effect=[12.0, 13.0, 14.0]):
            result = benchmark.consume_stream(stream, 10.0, on_first_text=observer)
        observer.assert_called_once_with(12.0)
        self.assertEqual(result["ttft_seconds"], 2.0)

    def test_invisible_tokens_still_advance_timing(self):
        stream = io.BytesIO(b'data: {"text":"a","meta_info":{"completion_tokens":1}}\n'
                            b'data: {"text":"a","meta_info":{"completion_tokens":5}}\n')
        with patch.object(benchmark.time, "monotonic", side_effect=[2.0, 6.0, 7.0]):
            result = benchmark.consume_stream(stream, 1.0)
        self.assertEqual(result["average_tpot_seconds_estimate"], 1.0)
        self.assertEqual(result["completion_tokens_after_last_text_change"], 4)

    def test_speculative_first_burst_denominator(self):
        stream = io.BytesIO(b'data: {"text":"abc","meta_info":{"completion_tokens":3}}\n'
                            b'data: {"text":"abcdefg","meta_info":{"completion_tokens":7}}\n')
        with patch.object(benchmark.time, "monotonic", side_effect=[2.0, 6.0, 7.0]):
            result = benchmark.consume_stream(stream, 1.0)
        self.assertEqual(result["first_event_completion_tokens"], 3)
        self.assertEqual(result["average_tpot_seconds_estimate"], 1.0)

    def test_cumulative_stream_counts_only_final_tokens(self):
        events = [
            {"text": "", "meta_info": {"completion_tokens": 0}},
            {"text": "hello", "meta_info": {"completion_tokens": 1}},
            {"text": "hello world", "meta_info": {"completion_tokens": 3}},
        ]
        stream = io.BytesIO(("".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n\n").encode())
        with patch.object(benchmark.time, "monotonic", side_effect=[11.0, 13.0, 14.0]):
            result = benchmark.consume_stream(stream, 10.0)
        self.assertEqual(result["ttft_seconds"], 1.0)
        self.assertEqual(result["meta_info"]["completion_tokens"], 3)
        self.assertEqual(result["end_to_end_tokens_per_second"], 0.75)
        self.assertEqual(result["average_tpot_seconds_estimate"], 1.0)

    def test_empty_and_missing_usage_fail(self):
        for raw in (b"data: [DONE]\n", b'data: {"text":"hello"}\n'):
            with self.assertRaises(RuntimeError):
                benchmark.consume_stream(io.BytesIO(raw), 0)

    def test_stream_error(self):
        with self.assertRaisesRegex(RuntimeError, "Server stream error"):
            benchmark.consume_stream(io.BytesIO(b'data: {"error":"out of memory"}\n'), 0)

    def test_duplicate_text_event_does_not_reset_ttft(self):
        stream = io.BytesIO(b'data: {"text":"a","meta_info":{"completion_tokens":1}}\n'
                            b'data: {"text":"a","meta_info":{"completion_tokens":1}}\n')
        with patch.object(benchmark.time, "monotonic", side_effect=[2.0, 3.0]):
            self.assertEqual(benchmark.consume_stream(stream, 1.0)["ttft_seconds"], 1.0)


class MeasurementTests(unittest.TestCase):
    def test_dp1_load_snapshot(self):
        client = common.Client()
        with patch.object(client, "json", return_value={"loads": [{"dp_rank": 0,
                  "num_running_reqs": 6, "num_waiting_reqs": 0, "queues": {"retracted": 0}}]}):
            result = benchmark.sample_loads(client)
        self.assertEqual(result["num_running_reqs"], 6)
        self.assertEqual(result["num_retracted_reqs"], 0)

    def test_load_snapshot_rejects_multiple_dp_workers(self):
        client = common.Client()
        with patch.object(client, "json", return_value={"loads": [{"dp_rank": 0}, {"dp_rank": 1}]}):
            with self.assertRaises(ValueError):
                benchmark.sample_loads(client)

    def test_capacity_allows_queue_and_retraction_observations(self):
        benchmark.validate_observed_metrics({"samples": [
            {"num_queue_reqs": 5, "num_retracted_reqs": 1}]})

    def test_explicit_no_queue_policy_stops_later_rounds(self):
        for field in ("num_queue_reqs", "num_retracted_reqs"):
            with self.assertRaises(RuntimeError):
                benchmark.validate_observed_metrics({"samples": [{field: 1}]}, policy="no-queue")
        benchmark.validate_observed_metrics({"samples": []})

    def test_unrelated_traffic_exceeding_client_count_stops_test(self):
        with self.assertRaisesRegex(RuntimeError, "unrelated traffic"):
            benchmark.validate_observed_metrics({"samples": [{"num_running_reqs": 2}]}, max_running=1)

    def test_unknown_retractions_stay_unknown(self):
        summary = benchmark.summarize([{"samples": [sample()], "aggregate_tokens_per_second": 128}])
        self.assertIsNone(summary["total_retractions"])
        self.assertIsNone(summary["latency_p95_seconds"])

    def test_validated_usage_and_retractions(self):
        benchmark.validate_samples([sample()], 1024, 256, True)
        benchmark.validate_samples([sample(retractions=1)], 1024, 256, True)
        for result in (sample(prompt=1000), sample(completion=255)):
            with self.assertRaises(RuntimeError):
                benchmark.validate_samples([result], 1024, 256, True)
        with self.assertRaises(RuntimeError):
            benchmark.validate_samples([sample(retractions=1)], 1024, 256, True, policy="no-queue")

    def test_retrieval_failure(self):
        with self.assertRaisesRegex(RuntimeError, "Retrieval failed"):
            benchmark.validate_samples([{**sample(), "retrieval_passed": False}], 1024, 256, False)

    def test_decode_warmup_is_not_a_retrieval_quality_check(self):
        benchmark.validate_samples([{**sample(), "retrieval_passed": False}],
                                   1024, 256, False, require_retrieval=False)

    def test_duplicate_tp_metrics_are_not_summed(self):
        client = common.Client()
        payload = (b'sglang:num_running_reqs{tp_rank="0"} 4\n'
                   b'sglang:num_running_reqs{tp_rank="1"} 4\n'
                   b'sglang:num_queue_reqs{tp_rank="0"} 0\n')
        with patch.object(client, "open", return_value=io.BytesIO(payload)):
            self.assertEqual(benchmark.sample_metrics(client)["num_running_reqs"], 4)

    def test_missing_metrics_raise_not_zero(self):
        client = common.Client()
        with patch.object(client, "open", return_value=io.BytesIO(b"unrelated_metric 0\n")):
            with self.assertRaises(ValueError):
                benchmark.sample_metrics(client)

    def test_cpu_prompt_builder_is_mocked(self):
        returned = [{"input_ids": [1, 2, 3], "expected_codes": ["A", "B", "C"]}]
        with patch.object(prompts.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(returned), "")) as mocked:
            result = prompts.build_prompts(3, 1, "test", "model")
            self.assertEqual(result[0]["sha256"], common.digest([1, 2, 3]))
            self.assertEqual(mocked.call_args.args[0][:4], ["docker", "exec", "-i", common.DEFAULT_CONTAINER])
            self.assertIn("local_files_only=True", prompts.TOKENIZER_CODE)


class SmokeTests(unittest.TestCase):
    def test_tool_validation(self):
        result = {"choices": [{"message": {"tool_calls": [{"function": {
            "name": "lookup_room", "arguments": '{"room_id":"B204"}',
        }}]}}]}
        self.assertTrue(smoke_test.check_tool(result))
        result["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "not json"
        self.assertFalse(smoke_test.check_tool(result))

    def test_reasoning_must_be_separated_and_complete(self):
        result = {"choices": [{"finish_reason": "stop", "message": {"content": "42", "reasoning_content": "19+23"}}]}
        self.assertTrue(smoke_test.check_reasoning(result))
        result["choices"][0]["message"]["content"] = "<think>42</think>"
        self.assertFalse(smoke_test.check_reasoning(result))


class OfflineFlowTests(unittest.TestCase):
    def setUp(self):
        load_mock = patch.object(benchmark, "sample_loads", side_effect=ValueError("offline endpoint unavailable"))
        load_mock.start()
        self.addCleanup(load_mock.stop)
        self.args = SimpleNamespace(base_url=common.DEFAULT_URL, timeout=60, profile="baseline",
                                    concurrency=1, prompt_tokens=1024, output_tokens=256,
                                    pool_fraction=0.9, cache="cold", warmup_passes=1, seed=1,
                                    container=common.DEFAULT_CONTAINER, rounds=1, mode="decode")
        self.info = {"config": {**config(), "enable_metrics": False, "model_path": "test-model"}}
        self.report = {"run_id": "offline", "rounds": []}
        self.prompt = {"input_ids": [1], "expected_codes": ["A"], "sha256": "test"}

    def test_success_flow_without_network_or_docker(self):
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", return_value=sample()), patch("builtins.print"):
            benchmark.run(self.args, self.report)
        self.assertEqual(len(self.report["rounds"]), 1)
        self.assertFalse(self.report["metrics"]["available"])
        self.assertIsNone(self.report["metrics"]["peak_num_running_reqs"])
        self.assertEqual(self.report["configuration_drift"], {})

    def test_failure_retains_partial_round_and_after_info(self):
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaisesRegex(RuntimeError, "partial results retained"):
                benchmark.run(self.args, self.report)
        self.assertEqual(self.report["rounds"][0]["errors"][0]["message"], "synthetic failure")
        self.assertIn("server_after", self.report)

    def test_budget_failure_sends_no_inference(self):
        self.args.concurrency = 49
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "generate") as generation:
            with self.assertRaises(ValueError):
                benchmark.run(self.args, self.report)
            generation.assert_not_called()

    def test_failed_benchmark_main_still_writes_report(self):
        argv = ["benchmark.py", "--label", "offline", "--execute", "--confirm-idle"]
        with patch.object(sys, "argv", argv), \
                patch.object(benchmark, "experiment_lock", return_value=contextlib.nullcontext()), \
                patch.object(benchmark, "run", side_effect=RuntimeError("synthetic")), \
                patch.object(benchmark, "write_json") as writer, patch("builtins.print"):
            with self.assertRaises(SystemExit) as exited:
                benchmark.main()
            self.assertEqual(exited.exception.code, 1)
            report = writer.call_args.args[1]
            self.assertFalse(report["passed"])
            self.assertEqual(report["error"]["message"], "synthetic")
            self.assertTrue(report["summary"]["incomplete_or_failed_run"])

    def test_warm_reuse_missing_fails_instead_of_claiming_warm(self):
        self.args.cache = "warm"
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", return_value=sample()):
            with self.assertRaisesRegex(RuntimeError, "prefix reuse"):
                benchmark.run(self.args, self.report)

    def test_extra_warmups_are_bounded_identical_and_not_timed(self):
        self.args.cache = "warm"
        self.args.warmup_passes = 2
        self.args.rounds = 3
        samples = [sample(), sample()] + [sample() for _ in range(3)]
        for result in samples[:2]:
            result["meta_info"]["cached_tokens"] = 0
        for result in samples[2:]:
            result["meta_info"]["cached_tokens"] = 960
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]) as builder, \
                patch.object(benchmark, "generate", side_effect=samples) as generation, \
                patch("builtins.print"):
            benchmark.run(self.args, self.report)
        builder.assert_called_once()
        self.assertEqual(generation.call_count, 5)
        self.assertTrue(all(call.args[1] is self.prompt for call in generation.call_args_list))
        self.assertEqual([call.args[3] for call in generation.call_args_list],
                         [False, False, True, True, True])
        self.assertEqual([row["warmup_pass"] for row in self.report["warmup"]], [0, 1])
        self.assertEqual(self.report["warmup_policy"]["max_requests"], 2)
        self.assertEqual(self.report["summary"]["sample_count"], 3)
        self.assertTrue(all(row["warm_cache_verified"] for row in self.report["rounds"]))

    def test_extra_warmups_do_not_relax_prefix_requirement(self):
        self.args.cache = "warm"
        self.args.warmup_passes = 2
        self.args.rounds = 3
        samples = [sample() for _ in range(3)]
        for result in samples:
            result["meta_info"]["cached_tokens"] = 0
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", side_effect=samples) as generation:
            with self.assertRaisesRegex(RuntimeError, "prefix reuse"):
                benchmark.run(self.args, self.report)
        self.assertEqual(generation.call_count, 3)
        self.assertEqual(len(self.report["warmup"]), 2)
        self.assertEqual(len(self.report["rounds"]), 1)
        self.assertFalse(self.report["rounds"][0]["warm_cache_verified"])
        self.assertIn("server_after", self.report)

    def test_invalid_warmup_policy_sends_no_network_or_inference(self):
        for cache, passes in (("warm", 0), ("warm", 4), ("warm", True), ("cold", 2)):
            self.args.cache, self.args.warmup_passes = cache, passes
            with patch.object(benchmark, "Client") as client, \
                    patch.object(benchmark, "generate") as generation:
                with self.assertRaises(ValueError):
                    benchmark.run(self.args, self.report)
                client.assert_not_called()
                generation.assert_not_called()

    def test_warmup_request_failure_stops_before_timing(self):
        self.args.cache = "warm"
        self.args.warmup_passes = 3
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", side_effect=[sample(), RuntimeError("warmup failed")]) as generation:
            with self.assertRaisesRegex(RuntimeError, "warmup failed"):
                benchmark.run(self.args, self.report)
        self.assertEqual(generation.call_count, 2)
        self.assertEqual(len(self.report["warmup"]), 1)
        self.assertEqual(self.report["rounds"], [])
        self.assertIn("server_after", self.report)

    def test_unrelated_traffic_during_warmup_stops_extra_passes(self):
        self.args.cache = "warm"
        self.args.warmup_passes = 2

        def generation_with_traffic(*args):
            self.report["metrics"]["samples"].append({"num_running_reqs": 2})
            return sample()

        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", side_effect=generation_with_traffic) as generation:
            with self.assertRaisesRegex(RuntimeError, "unrelated traffic"):
                benchmark.run(self.args, self.report)
        self.assertEqual(generation.call_count, 1)
        self.assertEqual(len(self.report["warmup"]), 1)
        self.assertEqual(self.report["rounds"], [])

    def test_extra_retrieval_warmups_still_require_recall(self):
        self.args.cache = "warm"
        self.args.mode = "retrieval"
        self.args.warmup_passes = 2
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "build_prompts", return_value=[self.prompt]), \
                patch.object(benchmark, "generate", return_value={**sample(), "retrieval_passed": False}) as generation:
            with self.assertRaisesRegex(RuntimeError, "Retrieval failed"):
                benchmark.run(self.args, self.report)
        self.assertEqual(generation.call_count, 1)
        self.assertEqual(self.report["rounds"], [])

    def test_baseline_evidence_integrity(self):
        baseline = json.loads((common.ROOT / "configs/baseline.json").read_text())
        evidence = json.loads((common.ROOT / baseline["evidence"]).read_text())
        self.assertEqual(common.digest(evidence), baseline["evidence_sha256"])

    def test_busy_engine_rejected_before_inference(self):
        with patch.object(benchmark.Client, "info", return_value=self.info), \
                patch.object(benchmark, "verify_profile", return_value={}), \
                patch.object(benchmark, "sample_loads", return_value={"num_running_reqs": 1, "num_queue_reqs": 0}), \
                patch.object(benchmark, "generate") as generation:
            with self.assertRaisesRegex(RuntimeError, "not idle"):
                benchmark.run(self.args, self.report)
            generation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
