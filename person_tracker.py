"""Automatic main-person selection for a single-presenter lecture."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from pose_types import Person


def overlap(a: np.ndarray, b: np.ndarray) -> float:
    lo, hi = np.maximum(a[:2], b[:2]), np.minimum(a[2:], b[2:])
    intersection = float(np.prod(np.maximum(0, hi - lo)))
    union = float(np.prod(np.maximum(0, a[2:] - a[:2])) + np.prod(np.maximum(0, b[2:] - b[:2])) - intersection)
    return intersection / union if union > 0 else 0.0


@dataclass
class Selection:
    person: Person | None
    status: str
    generation: int


class PresenterTracker:
    def __init__(self):
        self.bound = False
        self.box: np.ndarray | None = None
        self.candidate: Person | None = None
        self.generation = 0
        self.suspended = False

    def reset(self) -> None:
        self.bound = False
        self.box = None
        self.candidate = None
        self.suspended = False
        self.generation += 1

    def bind(self) -> bool:
        if self.candidate is None:
            return False
        self.box = self.candidate.box.copy()
        self.bound = True
        return True

    def select(self, people: list[Person]) -> Selection:
        people = [p for p in people if np.isfinite(p.box).all() and np.all(p.box[2:] > p.box[:2])]
        if not people:
            # Keep the last box as a soft hint only. A one-frame miss must not
            # cancel all gesture timing or create a permanent suspended state.
            self.candidate = None
            self.bound = False
            return Selection(None, 'WAITING FOR PRESENTER - AUTO RESUME', self.generation)
        largest = max(people, key=lambda p: float(np.prod(p.box[2:] - p.box[:2])))
        person = largest
        best_overlap = 0.0
        if self.box is not None:
            matches = sorted(((overlap(self.box, p.box), p) for p in people), key=lambda x: x[0], reverse=True)
            best_overlap, closest = matches[0]
            # Continuity reduces jitter if someone briefly appears in the back,
            # but never rejects the only person or requires manual reselection.
            if best_overlap >= .25:
                person = closest
        if self.box is None or best_overlap < .15:
            self.generation += 1
        self.candidate = person
        self.box = person.box.copy()
        self.bound = True
        self.suspended = False
        return Selection(person, 'PRESENTER FOUND - SINGLE-PERSON MODE', self.generation)


class PoseSmoother:
    def __init__(self, responsiveness: float = 0.42):
        self.responsiveness = responsiveness
        self.points: np.ndarray | None = None

    def reset(self) -> None:
        self.points = None

    def update(self, person: Person | None) -> np.ndarray | None:
        if person is None:
            self.reset()
            return None
        points = person.points.astype(np.float32).copy()
        from controller_config import KEYPOINT_CONFIDENCE
        valid = np.isfinite(points).all(axis=1) & (person.scores >= KEYPOINT_CONFIDENCE)
        if self.points is not None and self.points.shape == points.shape:
            previous_valid = np.isfinite(self.points).all(axis=1)
            mask = valid & previous_valid
            points[mask] = (1 - self.responsiveness) * self.points[mask] + self.responsiveness * points[mask]
        self.points = points.copy()
        self.points[~valid] = np.nan
        return points
