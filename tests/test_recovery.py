import time
import unittest
from unittest.mock import patch
import numpy as np
from camera_service import CameraService


class FakeCamera:
    def __init__(self, fails=False):
        self.fails = fails
        self.released = False
    def read(self):
        time.sleep(.005)
        return (False, None) if self.fails else (True, np.zeros((20, 30, 3), np.uint8))
    def release(self):
        self.released = True


def wait_until(predicate, timeout=2):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if predicate():
            return True
        time.sleep(.01)
    return False


class CameraTests(unittest.TestCase):
    def test_R01_single_read_failure_recovers_and_releases(self):
        first, second = FakeCamera(True), FakeCamera()
        cameras = iter([first, second])
        with patch('camera_service.CAMERA_RETRY_DELAYS', (.01, .02, .03)):
            service = CameraService(factory=lambda index: next(cameras))
            service.start()
            try:
                self.assertTrue(wait_until(lambda: service.snapshot()[1] == 'ready'))
                self.assertTrue(first.released)
                self.assertGreater(service.snapshot()[3], 0)
                self.assertEqual(service.snapshot()[0].image.shape, (20, 30, 3))
            finally:
                self.assertTrue(service.close())
        self.assertTrue(second.released)

    def test_R02_finite_retries_then_manual_recovery(self):
        attempts = []
        allowed = [False]
        camera = FakeCamera()
        def factory(index):
            attempts.append(index)
            if not allowed[0]:
                raise RuntimeError('simulated busy camera')
            return camera
        with patch('camera_service.CAMERA_RETRY_DELAYS', (.01, .02, .03)):
            service = CameraService(factory=factory); service.start()
            try:
                self.assertTrue(wait_until(lambda: service.snapshot()[1] == 'unavailable'))
                count = len(attempts)
                time.sleep(.1)
                self.assertEqual(len(attempts), count)
                self.assertEqual(count, 4)
                allowed[0] = True
                service.retry(2)
                self.assertTrue(wait_until(lambda: service.snapshot()[1] == 'ready'))
                self.assertEqual(attempts[-1], 2)
            finally:
                service.close()
