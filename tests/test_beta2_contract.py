"""UI revisions must not silently alter the approved beta.2 gesture behavior."""
import hashlib
from pathlib import Path
import unittest


class Beta2ContractTests(unittest.TestCase):
    def test_approved_recognition_files_are_byte_identical_to_beta2(self):
        root = Path(__file__).resolve().parents[1]
        expected = {
        "gesture_engine.py": "f15a57145918dbff02043a546dd3a1bdd92ce0870f57fefcb8e309b2d674f1ce",
        "person_tracker.py": "a3ecab4196046f059904fca37e2276b902fffeed65bbd2eaf32fcac89a049e7f",
        "inference_service.py": "d7bba5dc3120d1bfbc52070071caf36ad10e1ad6a588b877f2228b71c917af9f",
        "controller_config.py": "4360ca6eaae81286ec28ab3fbcc0552a5710f21f73809263d213c172aa242485",
        "pose_backends.py": "ac92b3b3675b9d43b36c8d0df22559be4286dab4a54d680bc45a6fe3bb1e80a8",
        "powerpoint_bridge.py": "e63ecfd07d27ff31ea533666046acd9a42ee2ea5c234ac867841a5491a11002d"
}
        for name, digest in expected.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest)
