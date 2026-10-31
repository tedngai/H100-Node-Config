import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

TOOLS = Path(__file__).resolve().parents[1] / "scripts/glm_candidate"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    # Modules under scripts are not installed packages.
    sys.path.insert(0, str(TOOLS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class DevicePatchTests(unittest.TestCase):
    def setUp(self):
        self.patch = load("device_patch")

    def test_patch_is_idempotent(self):
        original = "import os\n" + self.patch.OLD
        once = self.patch.adapt(original)
        self.assertIn(self.patch.NEW, once)
        self.assertEqual(self.patch.adapt(once), once)

    def test_unknown_or_duplicate_source_refused(self):
        for text in ("pass", "import os\n" + self.patch.OLD * 2,
                     "import os\n" + self.patch.OLD + self.patch.NEW):
            with self.assertRaises(ValueError):
                self.patch.adapt(text)

    def test_missing_os_import_refused(self):
        with self.assertRaises(ValueError):
            self.patch.adapt(self.patch.OLD)


class PatchContextTests(unittest.TestCase):
    def test_only_context_changes_not_patch_operations(self):
        module = load("apply_patches")
        text = module.HEADER + "\n-before\n+after\n" + module.CONTEXT
        result = module.refresh_reply_context(text)
        operations = lambda src: [line for line in src.splitlines() if line.startswith(("-", "+"))]
        self.assertEqual(operations(text), operations(result))
        self.assertIn("rejected=rejected", result)
        self.assertIn("@@ -607,17 +617,17 @@", result)

    def test_unknown_context_is_refused(self):
        module = load("apply_patches")
        with self.assertRaises(ValueError):
            module.refresh_reply_context("unexpected patch")

    def test_chat_context_preserves_exit_on_broken_and_operations(self):
        module = load("apply_patches")
        text = ("@@ -562,6 +600,8 @@ class MultiDecoder:\n+new\n"
                "         self.idle = True\n         self.broken: Exception | None = None\n")
        result = module.refresh_chat_context(text)
        self.assertIn("         self.exit_on_broken = exit_on_broken()", result)
        self.assertEqual([s for s in text.splitlines() if s.startswith(("-", "+"))],
                         [s for s in result.splitlines() if s.startswith(("-", "+"))])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.prepare = load("prepare")

    def test_patch_hash_covers_order_content_and_extras(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "0002.patch").write_text("second")
            (root / "0001.patch").write_text("first")
            expected = hashlib.sha256(("firstsecond" + self.prepare.EXTRAS + "\n").encode()).hexdigest()[:12]
            self.assertEqual(self.prepare.patch_hash(root), expected)

    def test_build_paths_cannot_be_inside_repo(self):
        for path in (self.prepare.ROOT, self.prepare.ROOT / ".local/build"):
            with self.assertRaises(ValueError):
                self.prepare.outside_repo(path)

    def test_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            self.prepare.write_evidence(path, {"ok": True})
            with self.assertRaises(FileExistsError):
                self.prepare.write_evidence(path, {"ok": False})

    def test_entrypoint_does_not_modify_engine_source(self):
        text = (TOOLS / "entrypoint.sh").read_text()
        self.assertNotIn("write_text", text)
        self.assertNotIn("docker rm", text)
        self.assertIn("wait -n", text)

    def test_build_dry_run_has_no_external_actions(self):
        with patch.object(sys, "argv", ["prepare.py", "--recipe-repo", "/unused", "--workspace", "/unused-build"]), \
                patch.object(self.prepare.subprocess, "run") as run, \
                patch.object(self.prepare.subprocess, "check_output") as output:
            self.assertEqual(self.prepare.main(), 0)
            run.assert_not_called()
            output.assert_not_called()


class CPUValidationTests(unittest.TestCase):
    def setUp(self):
        self.validate = load("validate")

    def test_containers_have_no_gpu_or_host_network(self):
        args = self.validate.cpu_command("sha256:test", "test", "test_get_bodies.py", Path("/unused"))
        self.assertNotIn("--gpus", args)
        self.assertNotIn("--privileged", args)
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertEqual(args[args.index("--runtime") + 1], "runc")
        self.assertIn("--read-only", args)
        self.assertIn("CUDA_VISIBLE_DEVICES=", args)
        self.assertNotIn("--mount", args)

    def test_tokenizer_mounts_never_include_model_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("tokenizer.json", "tokenizer_config.json", "weights.safetensors"):
                (root / name).write_text("{}")
            args = self.validate.cpu_command("sha256:test", "test", "literal_tokens_check.py", root)
            mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
            self.assertEqual(len(mounts), 2)
            self.assertTrue(all(m.endswith(",readonly") for m in mounts))
            self.assertFalse(any("weights" in m for m in mounts))

    def test_unknown_check_refused(self):
        with self.assertRaises(ValueError):
            self.validate.cpu_command("image", "name", "serve.py", Path("/unused"))

    def test_build_identity_must_match(self):
        build = {"success": True, "deployed": False, "recipe_commit": self.validate.RECIPE_COMMIT,
                 "tensorfold_commit": self.validate.TF_COMMIT, "image": self.validate.IMAGE,
                 "upstream_patch_hash": self.validate.PATCHES_HASH, "image_id": "sha256:expected"}
        image = {"Id": "sha256:expected", "Architecture": "amd64", "Config": {"Labels": {
            "tf.patches": self.validate.PATCHES_HASH, "h100.recipe.commit": self.validate.RECIPE_COMMIT}}}
        self.assertEqual(self.validate.verify_build(build, image), "sha256:expected")
        image["Id"] = "sha256:other"
        with self.assertRaises(ValueError):
            self.validate.verify_build(build, image)


if __name__ == "__main__":
    unittest.main()
