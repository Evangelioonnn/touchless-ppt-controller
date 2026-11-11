"""Local resource samples only: no images, keypoints, document titles or uploads."""
from __future__ import annotations
import json
from pathlib import Path
import time


class RuntimeMetrics:
    def __init__(self, path: Path):
        import psutil
        self.path = path
        self.process = psutil.Process()
        self.start = time.perf_counter()
        self.last_sample = 0.0
        self.samples = []

    def sample(self, fps: float, latency: float, camera_state: str, inference_state: str):
        now = time.perf_counter()
        if now - self.last_sample < 1:
            return
        self.last_sample = now
        sample = {'elapsed_s': now - self.start, 'rss_bytes': self.process.memory_info().rss,
                  'handles': self.process.num_handles(), 'threads': self.process.num_threads(),
                  'fps': fps, 'latency_ms': latency, 'camera': camera_state, 'inference': inference_state}
        self.samples.append(sample)
        if len(self.samples) % 10 == 0:
            self.save(False)

    def save(self, finished: bool):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({'measurement': 'observe-only controller; PPT commands disabled',
            'duration_s': time.perf_counter() - self.start, 'finished': finished,
            'samples': self.samples}, indent=2), encoding='utf-8')
