"""Serial model worker over the camera's latest frame, with no frame queue."""
from __future__ import annotations

import logging
import threading
import time

from app_settings import Settings
from controller_config import MAX_FRAME_AGE_SECONDS, MAX_INFERENCE_AGE_SECONDS, MODEL_PATH, ONNX_MODEL_PATH


def result_is_fresh(result, now: float) -> bool:
    """Allow a normal CPU cadence, but never reuse an old result indefinitely."""
    if result is None:
        return False
    latency = max(0.0, result.completed_at - result.received_at)
    budget = min(MAX_INFERENCE_AGE_SECONDS, max(MAX_FRAME_AGE_SECONDS, latency * 2.5 + .25))
    return bool(0 <= now - result.received_at <= budget)


class InferenceService:
    def __init__(self, camera, settings: Settings, stage=lambda name: None):
        self.camera, self.settings, self.stage = camera, settings, stage
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.retry_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name='inference', daemon=True)
        self.result = None
        self.image = None
        self.camera_generation = -1
        self.generation = 0
        self.state = 'loading'
        self.message = 'Loading local model'
        self.device_name = 'Initializing'
        self.latency_ms = 0.0
        self.fps = 0.0
        self.logger = logging.getLogger('touchless')

    def start(self):
        self.thread.start()

    def retry(self, settings: Settings | None = None):
        with self.lock:
            if settings is not None:
                self.settings = settings
            self.result, self.image = None, None
            self.generation += 1
            self.state = 'loading'
        self.retry_event.set()

    def snapshot(self):
        with self.lock:
            return (self.result, self.image, self.state, self.message, self.device_name,
                    self.generation, self.camera_generation, self.fps, self.latency_ms)

    def _run(self):
        from pose_backends import OnnxBackend, TorchBackend
        backend = None
        last_sequence = -1
        last_completed = None
        while not self.stop_event.is_set():
            if self.retry_event.is_set():
                self.retry_event.clear()
                backend = None
                last_sequence = -1
                last_completed = None
            if backend is None:
                try:
                    backend = (OnnxBackend(ONNX_MODEL_PATH, self.settings.device, self.stage)
                               if self.settings.backend == 'onnx' else TorchBackend(MODEL_PATH, self.settings.device, self.stage))
                    with self.lock:
                        self.state = 'waiting_camera'
                        self.message = 'Model loaded; waiting for a camera frame'
                        self.device_name = backend.name
                except Exception as error:
                    self.logger.exception('Model initialization failed')
                    with self.lock:
                        self.state = 'unavailable'
                        self.message = str(error)
                    while not self.stop_event.wait(.1) and not self.retry_event.is_set():
                        pass
                    continue
            frame, camera_state, _, generation = self.camera.snapshot()
            now = time.perf_counter()
            if camera_state != 'ready' or frame is None or frame.sequence == last_sequence or now - frame.received_at > MAX_FRAME_AGE_SECONDS:
                self.stop_event.wait(.005)
                continue
            last_sequence = frame.sequence
            requested_generation = self.generation
            try:
                import cv2
                image = cv2.flip(frame.image, 1)
                result = backend.predict(image, frame.received_at, frame.sequence)
                current_camera_generation = self.camera.snapshot()[3]
                if current_camera_generation != generation:
                    continue
                if time.perf_counter() - result.received_at > MAX_INFERENCE_AGE_SECONDS:
                    with self.lock:
                        if self.state != 'slow':
                            self.generation += 1
                        self.state = 'slow'
                        self.message = 'Frame expired: inference exceeded 3 s; waiting for a fresh result. Unlock state preserved.'
                        self.result, self.image = None, None
                        self.device_name = backend.name
                        self.latency_ms = (result.completed_at - result.received_at) * 1000
                    continue
                with self.lock:
                    if requested_generation != self.generation or self.retry_event.is_set():
                        continue
                    self.result, self.image = result, image
                    self.camera_generation = generation
                    self.state, self.message = 'ready', 'Ready'
                    self.device_name = backend.name
                    self.latency_ms = (result.completed_at - result.received_at) * 1000
                    if last_completed is not None:
                        value = 1 / max(.000001, result.completed_at - last_completed)
                        self.fps = value if self.fps == 0 else .9 * self.fps + .1 * value
                if last_completed is None:
                    self.stage('first_inference')
                last_completed = result.completed_at
            except Exception as error:
                self.logger.exception('Inference failed')
                with self.lock:
                    self.result, self.image = None, None
                    self.generation += 1
                    self.state = 'recovering'
                    self.message = str(error)
                try:
                    recovered = backend.recover_cpu()
                except Exception:
                    self.logger.exception('CPU recovery failed')
                    recovered = False
                if not recovered:
                    with self.lock:
                        self.state = 'unavailable'
                        self.message = 'Inference unavailable. Select a backend/device and Retry. ' + str(error)
                    while not self.stop_event.wait(.1) and not self.retry_event.is_set():
                        pass

    def close(self) -> bool:
        self.stop_event.set()
        self.thread.join(2)
        return not self.thread.is_alive()
