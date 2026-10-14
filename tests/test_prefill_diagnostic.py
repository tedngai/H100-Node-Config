"""Offline-only scheduling diagnostic tests: no Docker, HTTP, GPU or inference."""

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


def observation(timestamp=1, elapsed=0, waiting=0, running=0, tokens=0, busy=0):
    return {"server_timestamp": timestamp, "sample_started_seconds": elapsed,
            "sample_finished_seconds": elapsed + 0.001,
            "num_running_reqs": running, "num_waiting_reqs": waiting,
            "num_retracted_reqs": 0, "total_prefill_uncached_tokens": tokens,
            "total_prefill_busy_us": busy}


class DiagnosticTests(unittest.TestCase):
    def test_transient_wait_with_prefill_progress_is_separately_classified(self):
        samples = [observation(), observation(2, 0.5, waiting=1, tokens=8192, busy=100),
                   observation(3, 1, running=2, tokens=65536, busy=1000)]
        requests = [{"first_text_seconds": 0.8}, {"first_text_seconds": 1.2}]
        result = diagnostic.analyze(samples, requests)
        self.assertEqual(result["classification"], "consistent_with_transient_prefill_waiting")
        self.assertTrue(result["queue_observed"])
        self.assertTrue(result["prefill_counters_progressed_while_waiting"])
        # The identical observation still fails the ordinary benchmark policy.
        with self.assertRaisesRegex(RuntimeError, "Queueing observed"):
            benchmark.validate_observed_metrics({"samples": [{"num_queue_reqs": 1}]}, 2)

    def test_duplicate_publications_are_not_distinct_events(self):
        row = observation(2, 0.5, waiting=1, tokens=8192, busy=100)
        result = diagnostic.analyze([observation(), row, dict(row)],
                                    [{"first_text_seconds": 1}, {"first_text_seconds": 2}])
        self.assertEqual(result["queued_unique_published_snapshots"], 1)
        self.assertEqual(result["unique_published_snapshots"], 2)

    def test_late_repeat_of_queue_snapshot_is_not_confidently_prefill_only(self):
        row = observation(2, 0.5, waiting=1, tokens=8192, busy=100)
        late = {**row, "sample_started_seconds": 3, "sample_finished_seconds": 3.001}
        result = diagnostic.analyze([observation(), row, late],
                                    [{"first_text_seconds": 1}, {"first_text_seconds": 2}])
        self.assertTrue(result["classification"].startswith("inconclusive"))

    def test_counter_reset_or_conflicting_publication_is_rejected(self):
        for rows in ([observation(tokens=100), observation(2, tokens=50)],
                     [observation(), observation(tokens=50)],
                     [observation(2), observation(1)]):
            with self.assertRaises(ValueError):
                diagnostic.analyze(rows, [])

    def test_queue_without_prefill_progress_is_inconclusive(self):
        result = diagnostic.analyze([observation(), observation(2, 0.5, waiting=1)],
                                    [{"first_text_seconds": 1}, {"first_text_seconds": 2}])
        self.assertTrue(result["classification"].startswith("inconclusive"))

    def test_missing_first_text_or_no_samples_is_not_assumed_passed(self):
        result = diagnostic.analyze([observation()], [{}, {}])
        self.assertTrue(result["classification"].startswith("inconclusive"))
        with self.assertRaises(ValueError):
            diagnostic.analyze([], [])

    def test_queue_window_and_unrelated_traffic_and_retractions_are_bounded(self):
        diagnostic.check_snapshot(observation(waiting=1, elapsed=2), first_submission=0)
        for row in (observation(waiting=1, elapsed=6), observation(waiting=1, running=2),
                    {**observation(), "num_retracted_reqs": 1}):
            with self.assertRaises(RuntimeError):
                diagnostic.check_snapshot(row, first_submission=0)

    def test_required_metrics_remain_unavailable_not_zero(self):
        base = {**observation(timestamp=100), "dp_rank": 0, "timestamp": 100,
                "queues": {"retracted": 0}}
        client = common.Client()
        for key in (*diagnostic.REQUIRED_COUNTS, "queues"):
            row = dict(base)
            row.pop(key)
            with patch.object(client, "json", return_value={"loads": [row]}), \
                    patch.object(diagnostic.time, "time", return_value=100):
                with self.assertRaises(ValueError):
                    diagnostic.snapshot(client, 0)

    def test_snapshot_requires_single_dp_and_fresh_publication(self):
        client = common.Client()
        base = {**observation(), "dp_rank": 0, "timestamp": 100, "queues": {"retracted": 0}}
        for rows, now in (([base, base], 100), ([{**base, "dp_rank": 1}], 100),
                          ([base], 110)):
            with patch.object(client, "json", return_value={"loads": rows}), \
                    patch.object(diagnostic.time, "time", return_value=now):
                with self.assertRaises(ValueError):
                    diagnostic.snapshot(client, 0)

    def test_busy_engine_sends_no_inference(self):
        args = SimpleNamespace(base_url=common.DEFAULT_URL, container=common.DEFAULT_CONTAINER)
        info = {"config": {"status": "ready", "dp_size": 1, "allow_auto_truncate": False,
                           "max_running_requests": 48, "context_length": 262144,
                           "max_total_num_tokens": 1587968, "model_path": "mock"}}
        with patch.object(diagnostic.Client, "info", return_value=info), \
                patch.object(diagnostic, "verify_profile", return_value={}), \
                patch.object(diagnostic, "snapshot", return_value=observation(waiting=1)), \
                patch.object(diagnostic, "generate") as generation, \
                patch.object(diagnostic, "build_prompts") as prompts:
            with self.assertRaisesRegex(RuntimeError, "not idle"):
                diagnostic.run(args, {"run_id": "offline"})
        generation.assert_not_called()
        prompts.assert_not_called()

    def test_fixed_two_request_flow_without_network(self):
        args = SimpleNamespace(base_url=common.DEFAULT_URL, container=common.DEFAULT_CONTAINER)
        info = {"config": {"status": "ready", "dp_size": 1, "allow_auto_truncate": False,
                           "max_running_requests": 48, "context_length": 262144,
                           "max_total_num_tokens": 1587968, "model_path": "mock"}}
        sequence = itertools.count(1)

        def fake_snapshot(*args):
            return observation(timestamp=next(sequence))

        def fake_generate(*args, on_first_text=None):
            on_first_text(time.monotonic())
            return {"meta_info": {"prompt_tokens": 32768, "completion_tokens": 512,
                                  "num_retractions": 0, "cached_tokens": 0}}

        report = {"run_id": "offline", "performance_qualified": False}
        with patch.object(diagnostic.Client, "info", return_value=info), \
                patch.object(diagnostic, "verify_profile", return_value={}), \
                patch.object(diagnostic, "snapshot", side_effect=fake_snapshot), \
                patch.object(diagnostic, "build_prompts", return_value=[{"sha256": "one"}, {"sha256": "two"}]), \
                patch.object(diagnostic, "generate", side_effect=fake_generate) as generation:
            diagnostic.run(args, report)
        self.assertEqual(generation.call_count, 2)
        self.assertEqual(len(report["requests"]), 2)
        self.assertEqual(report["analysis"]["classification"], "queue_not_reproduced")
        self.assertFalse(report["performance_qualified"])
        self.assertTrue(report["configuration_unchanged"])

    def test_failure_report_preserves_separate_protocol(self):
        argv = ["prefill_diagnostic.py", "--label", "offline-diag", "--execute", "--confirm-idle"]
        with patch.object(sys, "argv", argv), \
                patch.object(diagnostic, "experiment_lock", return_value=contextlib.nullcontext()), \
                patch.object(diagnostic, "run", side_effect=RuntimeError("synthetic failure")), \
                patch.object(diagnostic, "write_json") as writer, patch("builtins.print"):
            with self.assertRaises(SystemExit):
                diagnostic.main()
        report = writer.call_args.args[1]
        self.assertFalse(report["passed"])
        self.assertFalse(report["performance_qualified"])
        self.assertEqual(report["kind"], "prefill-queue-diagnostic")
        self.assertEqual(report["policy"]["max_requests"], 2)
        self.assertEqual(report["policy"]["rounds"], 1)
        self.assertFalse(report["policy"]["strict_benchmark_zero_queue_policy_changed"])
