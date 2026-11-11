"""Model restoration security/integrity tests use tiny fixtures, never network/camera."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.restore_models import check_existing, expected_models, restore_archive


class ModelRestoreTests(unittest.TestCase):
    def temporary(self):
        parent = Path(__file__).resolve().parents[1] / "validation/model-restore-fixtures"
        parent.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=parent)

    def fixture(self, root, *, corrupt=False, extra=False):
        data = {"yolo26s-pose.pt": b"checkpoint fixture", "yolo26s-pose.onnx": b"onnx fixture"}
        manifest = {"source": "yolo26s-pose.pt", "onnx": "yolo26s-pose.onnx",
                    "source_sha256": hashlib.sha256(data["yolo26s-pose.pt"]).hexdigest(),
                    "onnx_sha256": hashlib.sha256(data["yolo26s-pose.onnx"]).hexdigest()}
        (root / "models").mkdir()
        (root / "models/manifest.json").write_text(json.dumps(manifest))
        archive = root / "fixture.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("models/manifest.json", json.dumps(manifest))
            for name, content in data.items():
                bundle.writestr("models/" + name, b"damaged" if corrupt and name.endswith(".onnx") else content)
            if extra:
                bundle.writestr("../outside.txt", "not allowed")
        return archive, data

    def test_restore_and_idempotent_verified_models(self):
        with self.temporary() as directory:
            root = Path(directory)
            archive, data = self.fixture(root)
            self.assertEqual(len(restore_archive(archive, root)), 2)
            for name, content in data.items():
                self.assertEqual((root / "models" / name).read_bytes(), content)
            self.assertEqual(restore_archive(archive, root), [])

    def test_bad_existing_file_is_never_overwritten(self):
        with self.temporary() as directory:
            root = Path(directory)
            archive, _ = self.fixture(root)
            (root / "models/yolo26s-pose.pt").write_bytes(b"local file")
            with self.assertRaises(RuntimeError):
                restore_archive(archive, root)
            self.assertEqual((root / "models/yolo26s-pose.pt").read_bytes(), b"local file")

    def test_corrupt_archive_installs_neither_model(self):
        with self.temporary() as directory:
            root = Path(directory)
            archive, _ = self.fixture(root, corrupt=True)
            with self.assertRaises(ValueError):
                restore_archive(archive, root)
            self.assertEqual(len(check_existing(root, expected_models(root)[1])), 2)

    def test_unexpected_or_traversal_archive_is_rejected(self):
        with self.temporary() as directory:
            root = Path(directory)
            archive, _ = self.fixture(root, extra=True)
            with self.assertRaises(ValueError):
                restore_archive(archive, root)
            self.assertFalse((root.parent / "outside.txt").exists())
