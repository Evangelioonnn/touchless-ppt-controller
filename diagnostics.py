"""Startup timing, bounded logs and newline-delimited local launcher messages."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import threading
import time

from app_paths import VERSION, user_data_dir


def configure_logging(directory: Path | None = None) -> logging.Logger:
    logger = logging.getLogger('touchless')
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    handler: logging.Handler
    try:
        folder = (directory if directory is not None else user_data_dir()) / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / 'controller.log', maxBytes=1024 * 1024,
                                      backupCount=3, encoding='utf-8')
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    logger.info('version=%s python=%s', VERSION, sys.version.split()[0])
    return logger


class Protocol:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.stream = sys.stdout

    def send(self, kind: str, **values) -> None:
        if not self.enabled or self.stream is None:
            return
        def convert(value):
            return asdict(value) if is_dataclass(value) else str(value)
        try:
            with self.lock:
                self.stream.write(json.dumps({'type': kind, **values}, default=convert, ensure_ascii=True) + '\n')
                self.stream.flush()
        except (OSError, ValueError):
            pass


class StartupTrace:
    def __init__(self, logger: logging.Logger, protocol: Protocol):
        self.start = time.perf_counter()
        self.events: dict[str, float] = {}
        self.lock = threading.Lock()
        self.logger, self.protocol = logger, protocol

    def mark(self, name: str) -> float:
        elapsed = time.perf_counter() - self.start
        with self.lock:
            self.events[name] = elapsed
        self.logger.info('startup stage=%s elapsed_s=%.4f', name, elapsed)
        self.protocol.send('stage', stage=name, elapsed_s=elapsed, version=VERSION)
        return elapsed

    def save(self, directory: Path | None = None) -> None:
        try:
            folder = directory if directory is not None else user_data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            with self.lock:
                snapshot = dict(self.events)
            (folder / 'last-startup.json').write_text(json.dumps({'version': VERSION,
                'measurement': 'process start, not OS cold start', 'stages_s': snapshot}, indent=2), encoding='utf-8')
        except OSError:
            self.logger.exception('Could not save startup timing')
