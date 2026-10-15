"""Offline-only tests of the explicitly separate scheduling-aware protocol."""

import contextlib
import itertools
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark
import common
import prefill_diagnostic as diagnostic
import scheduled_benchmark as scheduled
from test_prefill_diagnostic import observation


def result(hits=0):
    return {"elapsed_seconds": 2.0, "ttft_seconds": 1.0,
            "end_to_end_tokens_per_second": 256.0,
            "average_tpot_seconds_estimate": 0.002,
            "meta_info": {"prompt_tokens": 32768, "completion_tokens": 512,
                          "cached_tokens": hits, "num_retractions": 0}}


class ScheduledTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(base_url=common.DEFAULT_URL, container=common.DEFAULT_CONTAINER,
                                    concurrency=2, cache="cold")
        self.info = {"config": {"status": "ready", "dp_size": 1, "allow_auto_truncate": False,
                                "max_running_requests": 48, "context_length": 262144,
                                "max_total_num_tokens": 1587968, "model_path": "mock"}}
        self.report = {"run_id": "offline", "rounds": [], "warmup": [], "warmup_phases": []}

    def fake_round(self, args, phase, *, concurrency, prompts, cache_policy, prefill_window):
        self.assertEqual(prefill_window, 8)
        phase["requests"] = [{"result": result(32704 if cache_policy == "warm" else 0),
                              "submission_attempted": True} for _ in range(concurrency)]
        phase["measured_elapsed_seconds"] = 2
        phase["strict_no_queue_observed"] = cache_policy != "cold"
        phase["analysis"] = {"classification": "consistent_with_transient_prefill_waiting" if cache_policy == "cold" else "queue_not_reproduced",
                             "peak_waiting": concurrency - 1 if cache_policy == "cold" else 0}

    def test_cold_three_rounds_are_bounded_and_separate(self):
        with patch.object(scheduled.Client, "info", return_value=self.info), \
                patch.object(scheduled, "verify_profile", return_value={}), \
                patch.object(scheduled, "snapshot", return_value=observation()), \
                patch.object(scheduled, "run_round", side_effect=self.fake_round) as runner, patch("builtins.print"):
            scheduled.run(self.args, self.report)
        self.assertEqual(runner.call_count, 3)
        self.assertEqual(self.report["summary"]["sample_count"], 6)
        self.assertFalse(self.report["strict_no_queue_observed"])
        self.assertTrue(all(row["passed"] for row in self.report["rounds"]))

    def test_warmups_sequential_two_passes_exact_prompts_not_timed(self):
        self.args.cache = "warm"
        prompts = [{"sha256": "one"}, {"sha256": "two"}]
        with patch.object(scheduled.Client, "info", return_value=self.info), \
                patch.object(scheduled, "verify_profile", return_value={}), \
                patch.object(scheduled, "snapshot", return_value=observation()), \
                patch.object(scheduled, "build_prompts", return_value=prompts) as builder, \
                patch.object(scheduled, "run_round", side_effect=self.fake_round) as runner, patch("builtins.print"):
            scheduled.run(self.args, self.report)
        builder.assert_called_once()
        self.assertEqual(runner.call_count, 7)
        self.assertEqual([call.kwargs["concurrency"] for call in runner.call_args_list], [1,1,1,1,2,2,2])
        self.assertEqual([row["warmup_pass"] for row in self.report["warmup"]], [0,0,1,1])
        self.assertEqual(self.report["summary"]["sample_count"], 6)
        self.assertTrue(all(call.kwargs["prompts"] is prompts for call in runner.call_args_list[4:]))
        self.assertTrue(all(row["warm_cache_verified"] for row in self.report["rounds"]))

    def test_failed_round_preserved_and_no_later_round(self):
        count = 0

        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            self.fake_round(*args, **kwargs)
            if count == 2:
                raise RuntimeError("unsafe queue phase")

        with patch.object(scheduled.Client, "info", return_value=self.info), \
                patch.object(scheduled, "verify_profile", return_value={}), \
                patch.object(scheduled, "snapshot", return_value=observation()), \
                patch.object(scheduled, "run_round", side_effect=fail_second) as runner, patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "unsafe queue phase"):
                scheduled.run(self.args, self.report)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(len(self.report["rounds"]), 2)
        self.assertFalse(self.report["rounds"][1]["passed"])
        self.assertEqual(len(self.report["rounds"][1]["samples"]), 2)
        self.assertIn("server_after", self.report)

    def test_warmup_failure_preserves_attempt_and_prevents_timing(self):
        self.args.cache = "warm"
        with patch.object(scheduled.Client, "info", return_value=self.info), \
                patch.object(scheduled, "verify_profile", return_value={}), \
                patch.object(scheduled, "snapshot", return_value=observation()), \
                patch.object(scheduled, "build_prompts", return_value=[{"sha256":"one"},{"sha256":"two"}]), \
                patch.object(scheduled, "run_round", side_effect=RuntimeError("warmup failure")) as runner:
            with self.assertRaisesRegex(RuntimeError, "warmup failure"):
                scheduled.run(self.args, self.report)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(len(self.report["warmup_phases"]), 1)
        self.assertFalse(self.report["warmup_phases"][0]["passed"])
        self.assertEqual(self.report["rounds"], [])

    def test_unsupported_policies_make_no_client_calls(self):
        for value in (0, 1, 3, 8, True):
            self.args.concurrency = value
            with patch.object(scheduled, "Client") as client:
                with self.assertRaises(ValueError):
                    scheduled.run(self.args, self.report)
                client.assert_not_called()
        with patch.object(diagnostic, "Client") as client:
            with self.assertRaises(ValueError):
                diagnostic.run_round(self.args, {}, concurrency=6, cache_policy="warmup")
            with self.assertRaises(ValueError):
                diagnostic.run_round(self.args, {}, prefill_window=100)
            client.assert_not_called()

    def test_default_five_second_diagnostic_and_new_eight_second_screen_are_distinct(self):
        row = observation(waiting=1, elapsed=6)
        with self.assertRaises(RuntimeError):
            diagnostic.check_snapshot(row, first_submission=0)
        diagnostic.check_snapshot(row, first_submission=0, concurrency=4, prefill_window=8)
        with self.assertRaises(RuntimeError):
            benchmark.validate_observed_metrics({"samples": [{"num_queue_reqs": 1}]}, 4, policy="no-queue")

    def test_phase_classification_uses_all_clients_not_two(self):
        rows = [observation(), observation(2, 1, waiting=3, tokens=8192, busy=100)]
        requests = [{"first_text_seconds": i} for i in (0.5, 0.8, 1.2, 1.5)]
        analysis = diagnostic.analyze(rows, requests, concurrency=4)
        self.assertEqual(analysis["classification"], "consistent_with_transient_prefill_waiting")
        self.assertIsNone(analysis["all_queued_observations_before_both_first_text"])
        self.assertTrue(analysis["all_queued_observations_before_all_first_text"])

    def test_worker_retains_warm_cache_guard_and_unforced_warmup(self):
        sequence = itertools.count(1)

        def fake_snapshot(*args):
            return observation(timestamp=next(sequence))

        def fake_generate(*args, on_first_text=None):
            on_first_text(time.monotonic())
            return result(0)

        for policy in ("warm", "warmup"):
            phase = {"run_id": "offline"}
            with patch.object(diagnostic.Client, "info", return_value=self.info), \
                    patch.object(diagnostic, "verify_profile", return_value={}), \
                    patch.object(diagnostic, "snapshot", side_effect=fake_snapshot), \
                    patch.object(diagnostic, "generate", side_effect=fake_generate) as generation:
                if policy == "warm":
                    with self.assertRaisesRegex(RuntimeError, "request failed"):
                        diagnostic.run_round(self.args, phase, concurrency=1, prompts=[{"sha256":"one"}], cache_policy=policy, prefill_window=8)
                    self.assertIn("prefix reuse", phase["requests"][0]["error"]["message"])
                else:
                    diagnostic.run_round(self.args, phase, concurrency=1, prompts=[{"sha256":"one"}], cache_policy=policy, prefill_window=8)
                    self.assertFalse(generation.call_args.args[3])

    def test_new_report_kind_and_failed_report_retention(self):
        argv = ["scheduled_benchmark.py", "--label", "offline", "--concurrency", "2", "--cache", "cold", "--execute", "--confirm-idle"]
        with patch.object(sys, "argv", argv), \
                patch.object(scheduled, "experiment_lock", return_value=contextlib.nullcontext()), \
                patch.object(scheduled, "run", side_effect=RuntimeError("synthetic")), \
                patch.object(scheduled, "write_json") as writer, patch("builtins.print"):
            with self.assertRaises(SystemExit):
                scheduled.main()
        report = writer.call_args.args[1]
        self.assertEqual(report["kind"], "scheduling-aware-benchmark")
        self.assertFalse(report["passed"])
        self.assertFalse(report["no_queue_qualified"])
        self.assertFalse(report["production_qualified"])
        self.assertEqual(report["policy"]["max_requests"], 6)
        self.assertEqual(report["workload"]["prompt_tokens"], 32768)
