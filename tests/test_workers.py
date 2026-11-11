import threading
import time
import unittest
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from app_settings import Settings
from camera_service import CameraFrame
from command_gate import CommandGate
from inference_service import InferenceService, result_is_fresh
from pose_types import PoseResult
from powerpoint_bridge import OperationResult, PowerPointStatus
from ppt_service import PowerPointService
from test_recovery import wait_until


class Camera:
    def __init__(self):
        self.sequence = 0
    def snapshot(self):
        self.sequence += 1
        return CameraFrame(np.zeros((20,30,3), np.uint8), time.perf_counter(), self.sequence, 0), 'ready', '', 0


class Backend:
    def __init__(self, *args):
        self.name = 'test GPU'
        self.recovered = False
    def predict(self, image, received, sequence):
        if not self.recovered:
            raise RuntimeError('simulated device loss')
        time.sleep(.005)
        return PoseResult([], received, time.perf_counter(), sequence)
    def recover_cpu(self):
        if self.recovered:
            return False
        self.recovered = True
        self.name = 'test CPU'
        return True


class WorkerTests(unittest.TestCase):
    def test_R05_gpu_initialization_failure_uses_cpu(self):
        from pose_backends import TorchBackend
        def fail():
            raise RuntimeError('simulated CUDA driver initialization failure')
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=fail))
        fake_ultralytics = SimpleNamespace(YOLO=lambda *args, **kwargs: object())
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'validation') as directory:
            root = Path(directory)
            model = root / 'model.pt'; model.touch()
            with patch.dict(sys.modules, {'torch': fake_torch, 'ultralytics': fake_ultralytics}), patch('app_paths.user_data_dir', return_value=root):
                backend = TorchBackend(model)
                self.assertEqual(backend.device, 'cpu')
                self.assertIn('recovery', backend.name)

    def test_R05_gpu_recovery_invalidates_old_inference(self):
        with patch('pose_backends.TorchBackend', Backend):
            service = InferenceService(Camera(), Settings())
            service.start()
            try:
                self.assertTrue(wait_until(lambda: service.snapshot()[2] == 'ready'))
                snapshot = service.snapshot()
                self.assertEqual(snapshot[4], 'test CPU')
                self.assertEqual(snapshot[5], 1)
                self.assertIsNotNone(snapshot[0])
            finally:
                self.assertTrue(service.close())

    def test_normal_cpu_inference_over_half_second_remains_usable(self):
        class SlowBackend(Backend):
            def predict(self, image, received, sequence):
                time.sleep(.55)
                return PoseResult([], received, time.perf_counter(), sequence)
        with patch('pose_backends.TorchBackend', SlowBackend):
            service = InferenceService(Camera(), Settings()); service.start()
            try:
                self.assertTrue(wait_until(lambda: service.snapshot()[2] == 'ready'))
                snapshot = service.snapshot()
                self.assertIsNotNone(snapshot[0])
                self.assertEqual(snapshot[5], 0)
                self.assertTrue(result_is_fresh(snapshot[0], time.perf_counter()))
            finally:
                self.assertTrue(service.close())

    def test_result_freshness_adapts_to_cpu_latency_but_stale_results_expire(self):
        result = PoseResult([], 10, 10.6, 1)
        self.assertTrue(result_is_fresh(result, 10.61))
        self.assertTrue(result_is_fresh(result, 11.2))
        self.assertFalse(result_is_fresh(result, 13.1))
        self.assertFalse(result_is_fresh(None, 11))

    def test_truly_expired_inference_is_reported_and_automatically_recovers(self):
        class FirstExpired(Backend):
            def __init__(self, *args):
                super().__init__(*args)
                self.calls = 0
            def predict(self, image, received, sequence):
                self.calls += 1
                if self.calls == 1:
                    return PoseResult([], received - 10, time.perf_counter(), sequence)
                time.sleep(.005)
                return PoseResult([], received, time.perf_counter(), sequence)
        seen = []
        with patch('pose_backends.TorchBackend', FirstExpired):
            service = InferenceService(Camera(), Settings())
            original_snapshot = service.snapshot
            def snapshot():
                value = original_snapshot()
                seen.append(value[2])
                return value
            service.snapshot = snapshot
            service.start()
            try:
                self.assertTrue(wait_until(lambda: service.snapshot()[2] == 'ready'))
                self.assertEqual(service.snapshot()[5], 1)
                self.assertIsNotNone(service.snapshot()[0])
            finally:
                self.assertTrue(service.close())

    def test_L07_lock_does_not_block_on_inflight_ppt_and_drops_old_queue(self):
        started, release = threading.Event(), threading.Event()
        calls = []
        class Bridge:
            def __init__(self, **kwargs): pass
            def refresh_if_needed(self, now):
                return PowerPointStatus(True, 'test', True, '1')
            def execute(self, action):
                calls.append(action); started.set(); release.wait(1)
                return OperationResult('accepted', 'test', action, '1')
        gate = CommandGate(); gate.invalidate(True, '1')
        service = PowerPointService(gate, bridge_factory=Bridge)
        service.start()
        try:
            command = gate.issue('next')
            self.assertTrue(service.submit(command))
            self.assertTrue(started.wait(1))
            self.assertTrue(service.submit(command))
            before = time.perf_counter(); gate.invalidate()
            self.assertLess(time.perf_counter() - before, .05)
            self.assertIsNone(gate.issue('next'))
            release.set()
            self.assertTrue(wait_until(lambda: not service.busy))
            time.sleep(.1)
            self.assertEqual(calls, ['next'])
        finally:
            release.set(); service.close()
