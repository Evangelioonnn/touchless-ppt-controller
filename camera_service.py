"""Latest-frame camera capture with finite retries and explicit recovery state."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable

from controller_config import CAMERA_HEIGHT, CAMERA_WIDTH, CAMERA_RETRY_DELAYS


@dataclass
class CameraFrame:
    image: object
    received_at: float
    sequence: int
    generation: int


def open_camera(index: int):
    import cv2
    for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
        camera = cv2.VideoCapture(index, backend)
        if camera.isOpened():
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return camera
        camera.release()
    raise RuntimeError('Cannot open camera. Check permissions, connection, or another application.')


class CameraService:
    def __init__(self, index: int = 0, factory: Callable = open_camera):
        self.index, self.factory = index, factory
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.retry_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.frame: CameraFrame | None = None
        self.state = 'opening'
        self.message = 'Opening camera'
        self.generation = 0
        self.sequence = 0
        self.camera = None
        self.actual_size = (0, 0)
        self.logger = logging.getLogger('touchless')

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name='camera', daemon=True)
        self.thread.start()

    def retry(self, index: int | None = None) -> None:
        with self.lock:
            if index is not None:
                self.index = index
            self.frame = None
            self.state = 'opening'
            self.generation += 1
        self.retry_event.set()

    def snapshot(self) -> tuple[CameraFrame | None, str, str, int]:
        with self.lock:
            return self.frame, self.state, self.message, self.generation

    def _state(self, state: str, message: str, invalidate: bool = False) -> None:
        with self.lock:
            if invalidate:
                self.generation += 1
            self.state, self.message = state, message
            if state != 'ready':
                self.frame = None

    def _run(self) -> None:
        failures = 0
        try:
            while not self.stop_event.is_set():
                if self.retry_event.is_set():
                    self.retry_event.clear()
                    self._release()
                    failures = 0
                if self.camera is None:
                    try:
                        self._state('opening', 'Opening camera')
                        self.camera = self.factory(self.index)
                        self.logger.info('camera opened index=%s', self.index)
                    except Exception as error:
                        self.logger.warning('camera open failed: %s', error)
                        if not self._retry_wait(failures, str(error)):
                            failures = 0
                        else:
                            failures += 1
                        continue
                try:
                    read_generation = self.generation
                    ok, image = self.camera.read()
                except Exception as error:
                    ok, image = False, None
                    self.logger.warning('camera read failed: %s', error)
                if not ok or image is None:
                    self._state('retrying', 'No fresh camera frame', invalidate=True)
                    self._release()
                    if not self._retry_wait(failures, 'Camera did not return a frame'):
                        failures = 0
                    else:
                        failures += 1
                    continue
                failures = 0
                now = time.perf_counter()
                self.actual_size = (image.shape[1], image.shape[0])
                with self.lock:
                    if read_generation != self.generation or self.retry_event.is_set():
                        continue
                    self.sequence += 1
                    self.frame = CameraFrame(image, now, self.sequence, self.generation)
                    self.state = 'ready'
                    self.message = 'Camera %d: %dx%d' % (self.index, *self.actual_size)
        finally:
            self._release()
            self._state('stopped', 'Camera stopped', invalidate=True)

    def _retry_wait(self, failures: int, message: str) -> bool:
        if failures < len(CAMERA_RETRY_DELAYS):
            self._state('retrying', message + '; retry %d/3' % (failures + 1))
            # Manual retry interrupts the backoff too.
            until = time.perf_counter() + CAMERA_RETRY_DELAYS[failures]
            while time.perf_counter() < until:
                if self.stop_event.wait(0.05) or self.retry_event.is_set():
                    return False
            return True
        self._state('unavailable', message + '; select a camera and press Retry')
        while not self.stop_event.wait(0.1):
            if self.retry_event.is_set():
                return False
        return False

    def _release(self) -> None:
        camera, self.camera = self.camera, None
        if camera is not None:
            try:
                camera.release()
            except Exception:
                self.logger.exception('camera release failed')

    def close(self) -> bool:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(2.0)
            return not self.thread.is_alive()
        return True
