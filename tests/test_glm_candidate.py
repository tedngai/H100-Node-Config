import importlib.util
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "scripts/glm_candidate"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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


if __name__ == "__main__":
    unittest.main()
