import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "hy4_manage", ROOT / "scripts/hy4_flash/manage.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class Hy4FlashTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads(M.CONFIG.read_text())

    def test_cookbook_unchanged_strategy(self):
        c = json.loads((ROOT / "configs/hy4-flash-cookbook.json").read_text())
        self.assertIn("H200", c["hardware"])
        self.assertIn("--tp", c["argv"])
        self.assertNotIn("--speculative-algorithm", c["argv"])

    def test_command_immutable_offline_preserved(self):
        args = M.start_command(self.c, "sha256:test")
        self.assertEqual(args[args.index("--pull") + 1], "never")
        self.assertEqual(args[args.index("--restart") + 1], "no")
        self.assertNotIn("--rm", args)
        self.assertIn("HF_HUB_OFFLINE=1", args)
        self.assertIn("sha256:test", args)
        self.assertNotIn("--speculative-algorithm", args)
        self.assertNotIn("--engram-config", args)
        self.assertNotIn("HF_TOKEN", " ".join(args))
        self.assertIn("--reasoning-parser", args)
        self.assertIn("--tool-call-parser", args)
        self.assertIn("hunyuan", args)

    def test_snapshot_mount_keeps_blob_symlinks(self):
        args = M.start_command(self.c, "sha256:test")
        mount = next(v for v in args if "dst=/checkpoint," in v)
        self.assertIn("models--tencent--Hy4-flash-FP8", mount)
        self.assertIn("readonly", mount)
        self.assertNotIn("/snapshots/", mount)
        self.assertIn("/checkpoint/snapshots/" + self.c["revision"], args)

    def test_owner_and_recipe_guards(self):
        with self.assertRaises(RuntimeError):
            M.ensure_owned(self.c, {"Config": {"Labels": {}}})
        d = {"Config": {"Labels": {
            "deployment.owner": M.OWNER,
            "deployment.recipe": M.recipe_hash(self.c)}}}
        M.ensure_owned(self.c, d)
        changed = copy.deepcopy(self.c)
        changed["context_length"] += 1
        with self.assertRaises(RuntimeError):
            M.ensure_owned(changed, d)

    def test_gpu_process_guard(self):
        with patch.object(M, "run", return_value="123"):
            with self.assertRaises(RuntimeError):
                M.gpu_idle()
        with patch.object(M, "run", side_effect=["", "14\n14\n14\n14"]):
            M.gpu_idle()
        with patch.object(M, "run", side_effect=["", "14\n2000\n14\n14"]):
            with self.assertRaises(RuntimeError):
                M.gpu_idle()

    def test_dry_run_does_not_call_docker_or_inference(self):
        with patch.object(sys, "argv", ["manage.py", "trial"]):
            with patch.object(M, "run", side_effect=AssertionError("live call")):
                with patch.object(M, "get_json", side_effect=AssertionError("network")):
                    with contextlib.redirect_stdout(io.StringIO()):
                        M.main()

    def test_live_requires_confirmation(self):
        with patch.object(sys, "argv", ["manage.py", "trial", "--execute"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    M.main()

    def test_incomplete_download_fails_before_downtime(self):
        with patch.object(M, "validate_checkpoint", side_effect=RuntimeError("missing")):
            with patch.object(M, "record") as record, patch.object(M, "run") as run:
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(RuntimeError):
                        M.trial(self.c, 1)
                run.assert_not_called()
                self.assertEqual(record.call_args.args[1]["status"], "failed")

    def test_failed_start_still_restores_glm(self):
        with contextlib.ExitStack() as stack:
            for name, result in (("validate_checkpoint", {}), ("lock_image", "sha256:test"),
                                 ("glm_idle", {}), ("preserve_glm_logs", {}),
                                 ("restore_glm", {"healthy": True})):
                stack.enter_context(patch.object(M, name, return_value=result))
            stack.enter_context(patch.object(M, "run", return_value=""))
            stack.enter_context(patch.object(M, "start", side_effect=RuntimeError("failed")))
            record = stack.enter_context(patch.object(M, "record"))
            restore = M.restore_glm
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    M.trial(self.c, 1)
            restore.assert_called_once()
            self.assertTrue(record.call_args.args[1]["rollback"]["healthy"])

    def test_readiness_uses_empty_http_health_and_effective_settings(self):
        info = {"server_args": {
            "context_length": self.c["context_length"],
            "max_running_requests": self.c["max_running_requests"],
            "tp_size": 4, "dp_size": 1, "served_model_name": "pratt-medium",
            "reasoning_parser": "hunyuan", "tool_call_parser": "hunyuan"}}
        container = {"State": {"Running": True}, "Config": {"Labels": {
            "deployment.owner": M.OWNER, "deployment.recipe": M.recipe_hash(self.c)}}}
        with patch.object(M, "inspect", return_value=container):
            with patch.object(M, "health_ok", return_value=True):
                for response in (info, info["server_args"]):
                    with patch.object(M, "get_json", side_effect=[
                        {"data": [{"id": "pratt-medium"}]}, response]):
                        result = M.ready(self.c, 1)
                        self.assertEqual(result["tp_size"], 4)

    def test_trial_success_also_stops_candidate_and_restores_glm(self):
        with contextlib.ExitStack() as stack:
            mocks = {}
            for name, result in (
                ("validate_checkpoint", {}), ("lock_image", "sha256:test"),
                ("glm_idle", {}), ("restore_glm", {"healthy": True}),
                ("preserve_glm_logs", {}),
                ("start", None), ("ready", {}), ("smoke", {"passed": True}),
                ("stop", None), ("record", None)):
                mocks[name] = stack.enter_context(patch.object(M, name, return_value=result))
            stack.enter_context(patch.object(
                M, "run", side_effect=["", "", "", self.c["container"]]))
            M.trial(self.c, 1)
            mocks["stop"].assert_called_once_with(self.c)
            mocks["restore_glm"].assert_called_once()
            self.assertFalse(mocks["record"].call_args.args[1]["production_promoted"])

    def test_stopped_rank_log_archive_is_external_and_private(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as tmp:
            root = Path(tmp)
            source, runtime = root / "logs", root / "runtime"
            source.mkdir()
            runtime.mkdir()
            for rank in range(4):
                (source / f"rank{rank}.log").write_text("synthetic test log")
            c = {**self.c, "runtime": str(runtime)}
            p = {"container": {"rank_logs": str(source / "rank{0..3}.log")}}
            result = M.preserve_glm_logs(c, p)
            archive = Path(result["archive"])
            self.assertEqual(result["files"], 4)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o700)
            self.assertEqual((archive / "rank0.log").stat().st_mode & 0o777, 0o600)
            self.assertTrue((source / "rank0.log").exists())

    def test_shell_wrappers_syntax(self):
        for name in ("start", "stop", "download"):
            path = Path("/home/tngai/data/vllm-deepseek") / f"{name}_sglang_hy4_flash.sh"
            if path.exists():
                subprocess.run(["bash", "-n", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
