"""Backend-independent pose results. Importing this does not import a ML runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import numpy as np


@dataclass
class Person:
    box: 'np.ndarray'
    points: 'np.ndarray'
    scores: 'np.ndarray'
    confidence: float = 1.0


@dataclass
class PoseResult:
    people: list[Person]
    received_at: float
    completed_at: float
    sequence: int = 0
