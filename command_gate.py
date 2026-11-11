"""Time- and generation-bound commands, invalidated on any control transition."""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from controller_config import MAX_COMMAND_AGE_SECONDS


@dataclass(frozen=True)
class Command:
    action: str
    created_at: float
    generation: int
    target: str


class CommandGate:
    def __init__(self):
        self.lock = threading.RLock()
        self.generation = 0
        self.enabled = False
        self.target = ''

    def invalidate(self, enabled: bool = False, target: str | None = None) -> None:
        with self.lock:
            self.generation += 1
            self.enabled = enabled
            if target is not None:
                self.target = target

    def issue(self, action: str, now: float | None = None) -> Command | None:
        with self.lock:
            if not self.enabled or not self.target:
                return None
            return Command(action, time.perf_counter() if now is None else now, self.generation, self.target)

    def valid(self, command: Command, now: float | None = None) -> bool:
        with self.lock:
            age = (time.perf_counter() if now is None else now) - command.created_at
            return bool(self.enabled and command.generation == self.generation
                        and command.target == self.target and 0 <= age <= MAX_COMMAND_AGE_SECONDS)
