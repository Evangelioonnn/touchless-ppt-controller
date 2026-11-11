"""Upper-body gesture recognition and anti-misfire state management."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from controller_config import (
    ACTION_COOLDOWN_SECONDS,
    CROSS_HOLD_SECONDS,
    KEYPOINT_CONFIDENCE,
    NEUTRAL_REARM_SECONDS,
    RAISE_HOLD_SECONDS,
    GESTURE_DROPOUT_GRACE_SECONDS,
    MAX_OBSERVATION_GAP_SECONDS,
)


LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10


@dataclass
class GestureFrame:
    pose: str
    candidate: str | None
    progress: float
    triggered: str | None
    armed: bool
    locked: bool
    left_raised: bool
    right_raised: bool
    crossed: bool
    observation: str = 'known'


class GestureEngine:
    """Original gesture geometry, with recoverable single-presenter observations."""

    def __init__(self, locked: bool = True) -> None:
        self.locked = locked
        # The preview is mirrored like a selfie camera, so YOLO's semantic
        # left/right labels need to be exchanged to match the user's real hands.
        self.swap_hands = True
        self.candidate: str | None = None
        self.candidate_since = 0.0
        self.last_triggered_at = -10.0
        self.armed = True
        self.neutral_since: float | None = None
        self.last_update_at: float | None = None
        self.candidate_elapsed = 0.0
        self.missing_since: float | None = None
        self.previous_known = False
        self.cross_latched = False

    def reset(self, now: float | None = None, lock: bool = True) -> None:
        now = time.perf_counter() if now is None else now
        if lock:
            self.locked = True
        self._disarm(now)
        self.last_update_at = None
        self.missing_since = None
        self.previous_known = False

    def force_lock(self, now: float | None = None) -> None:
        self.reset(now, lock=True)

    def suspend(self, now: float | None = None) -> None:
        """Cancel unfinished timing, not the user's control choice or one-shot latch."""
        self._clear_candidate()
        self.neutral_since = None
        self.missing_since = None
        self.previous_known = False
        self.last_update_at = now

    def manual_toggle_lock(self) -> None:
        self.locked = not self.locked
        self._disarm(time.perf_counter())

    def toggle_hand_mapping(self) -> None:
        self.swap_hands = not self.swap_hands
        self._disarm(time.perf_counter())

    def _disarm(self, now: float) -> None:
        self.armed = False
        self._clear_candidate()
        self.candidate_since = now
        self.neutral_since = None
        self.last_triggered_at = now

    def _clear_candidate(self) -> None:
        self.candidate = None
        self.candidate_elapsed = 0.0

    def update(
        self,
        points: np.ndarray | None,
        scores: np.ndarray | None,
        now: float | None = None,
    ) -> GestureFrame:
        now = time.perf_counter() if now is None else now
        gap = 0.0 if self.last_update_at is None else now - self.last_update_at
        if gap < 0 or gap > MAX_OBSERVATION_GAP_SECONDS:
            self.suspend(now)
            gap = 0.0
        self.last_update_at = now
        pose, left_raised, right_raised, crossed = detect_pose(points, scores)
        # A normal page gesture needs shoulders and a visible wrist, NOT six
        # simultaneously reliable joints. Full arms are only for crossed arms.
        body_known = bool(
            point_valid(points, scores, LEFT_SHOULDER)
            and point_valid(points, scores, RIGHT_SHOULDER)
        )
        reliable = body_known and any(point_valid(points, scores, i) for i in (LEFT_WRIST, RIGHT_WRIST))
        # If the hand whose hold is in progress disappears, do not interpret the
        # remaining low wrist as a reliable release of that gesture.
        active_wrist = self._candidate_wrist()
        if active_wrist is not None and not point_valid(points, scores, active_wrist):
            reliable = False
        if not reliable:
            if self.missing_since is None:
                self.missing_since = now
            if now - self.missing_since > GESTURE_DROPOUT_GRACE_SECONDS:
                self._clear_candidate()
            # Restore the original desk-use release: when shoulders/body remain
            # visible and no raised hand is seen, wrists may be below the desk.
            # A missing BODY is different: it never rearms or emits a command.
            if body_known and not (left_raised or right_raised or crossed):
                if self.neutral_since is None:
                    self.neutral_since = now
                elif now - self.neutral_since >= NEUTRAL_REARM_SECONDS:
                    self.armed = True
            else:
                self.neutral_since = None
            self.previous_known = False
            return GestureFrame(pose=pose, candidate=None, progress=0.0, triggered=None,
                                armed=self.armed, locked=self.locked, left_raised=False,
                                right_raised=False, crossed=False, observation='unknown')
        if self.missing_since is not None and now - self.missing_since > GESTURE_DROPOUT_GRACE_SECONDS:
            self._clear_candidate()
        self.missing_since = None
        observed_interval = max(0.0, gap) if self.previous_known else 0.0
        self.previous_known = True

        # A separate cross-arm latch prevents an elbow dropout from toggling the
        # switch twice, without imposing elbows on ordinary page gestures.
        if self.cross_latched and cross_release_observed(points, scores, crossed):
            self.cross_latched = False

        if crossed:
            raw_candidate = None if self.cross_latched else "toggle_lock"
        elif self.locked:
            raw_candidate = None
        elif left_raised ^ right_raised:
            if self.swap_hands:
                raw_candidate = "next" if left_raised else "previous"
            else:
                raw_candidate = "previous" if left_raised else "next"
        else:
            raw_candidate = None

        if raw_candidate is None:
            self._clear_candidate()
            self.candidate_since = now
            # Original visible-body no-command rearm; no strict six-joint pose.
            is_neutral = not crossed
            if not is_neutral:
                self.neutral_since = None
            if not self.armed and is_neutral:
                if self.neutral_since is None:
                    self.neutral_since = now
                elif now - self.neutral_since >= NEUTRAL_REARM_SECONDS:
                    self.armed = True
            return GestureFrame(
                pose=pose,
                candidate=None,
                progress=0.0,
                triggered=None,
                armed=self.armed,
                locked=self.locked,
                left_raised=left_raised,
                right_raised=right_raised,
                crossed=crossed,
            )

        self.neutral_since = None
        if raw_candidate != self.candidate:
            self.candidate = raw_candidate
            self.candidate_since = now
            self.candidate_elapsed = 0.0
        else:
            self.candidate_elapsed += observed_interval

        hold_seconds = CROSS_HOLD_SECONDS if raw_candidate == "toggle_lock" else RAISE_HOLD_SECONDS
        progress = min(1.0, max(0.0, self.candidate_elapsed / hold_seconds))
        triggered = None

        if (
            self.armed
            and progress >= 1.0
            and now - self.last_triggered_at >= ACTION_COOLDOWN_SECONDS
        ):
            triggered = raw_candidate
            if triggered == "toggle_lock":
                self.locked = not self.locked
                self.cross_latched = True
            else:
                self.cross_latched = False
            self.last_triggered_at = now
            self.armed = False

        return GestureFrame(
            pose=pose,
            candidate=raw_candidate,
            progress=progress,
            triggered=triggered,
            armed=self.armed,
            locked=self.locked,
            left_raised=left_raised,
            right_raised=right_raised,
            crossed=crossed,
        )

    def _candidate_wrist(self) -> int | None:
        if self.candidate not in ('next', 'previous'):
            return None
        left_is_next = self.swap_hands
        return LEFT_WRIST if (self.candidate == 'next') == left_is_next else RIGHT_WRIST


def valid(scores: np.ndarray | None, index: int) -> bool:
    return bool(scores is not None and len(scores) > index
                and np.isfinite(scores[index]) and scores[index] >= KEYPOINT_CONFIDENCE)


def point_valid(points, scores, index: int) -> bool:
    return bool(points is not None and points.ndim == 2 and points.shape[0] > index
                and points.shape[1] >= 2 and valid(scores, index)
                and np.isfinite(points[index, :2]).all())


def cross_release_observed(points, scores, crossed: bool) -> bool:
    if crossed:
        return False
    arms = (LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST)
    if all(point_valid(points, scores, i) for i in arms):
        return True
    if not all(point_valid(points, scores, i) for i in (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_WRIST, RIGHT_WRIST)):
        return False
    width = max(distance(points[LEFT_SHOULDER], points[RIGHT_SHOULDER]), 40.0)
    midpoint_y = float((points[LEFT_WRIST, 1] + points[RIGHT_WRIST, 1]) / 2)
    shoulder_y = float((points[LEFT_SHOULDER, 1] + points[RIGHT_SHOULDER, 1]) / 2)
    return bool(distance(points[LEFT_WRIST], points[RIGHT_WRIST]) >= 1.05 * width
                or not shoulder_y - .25 * width < midpoint_y < shoulder_y + 1.25 * width)


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def segments_cross(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    def orientation(p: np.ndarray, q: np.ndarray, r: np.ndarray) -> float:
        return float((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))

    first = orientation(a, b, c)
    second = orientation(a, b, d)
    third = orientation(c, d, a)
    fourth = orientation(c, d, b)
    return first * second <= 0.0 and third * fourth <= 0.0


def detect_pose(
    points: np.ndarray | None,
    scores: np.ndarray | None,
) -> tuple[str, bool, bool, bool]:
    if points is None or scores is None:
        return "NO PERSON", False, False, False

    if points.ndim != 2 or points.shape[0] <= RIGHT_WRIST or points.shape[1] < 2:
        return "INVALID POSE", False, False, False

    if not (point_valid(points, scores, LEFT_SHOULDER) and point_valid(points, scores, RIGHT_SHOULDER)):
        return "SHOW BOTH SHOULDERS", False, False, False

    left_shoulder = points[LEFT_SHOULDER]
    right_shoulder = points[RIGHT_SHOULDER]
    shoulder_width = max(distance(left_shoulder, right_shoulder), 40.0)

    left_raised = bool(
        point_valid(points, scores, LEFT_WRIST)
        and points[LEFT_WRIST, 1] < left_shoulder[1] - 0.06 * shoulder_width
    )
    right_raised = bool(
        point_valid(points, scores, RIGHT_WRIST)
        and points[RIGHT_WRIST, 1] < right_shoulder[1] - 0.06 * shoulder_width
    )

    crossed = False
    arm_indices = (LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST)
    if all(point_valid(points, scores, index) for index in arm_indices):
        left_elbow = points[LEFT_ELBOW]
        right_elbow = points[RIGHT_ELBOW]
        left_wrist = points[LEFT_WRIST]
        right_wrist = points[RIGHT_WRIST]
        forearms_intersect = segments_cross(left_elbow, left_wrist, right_elbow, right_wrist)
        wrist_order_reversed = (
            (left_elbow[0] - right_elbow[0]) * (left_wrist[0] - right_wrist[0]) < 0.0
        )
        wrist_midpoint = (left_wrist + right_wrist) / 2.0
        shoulder_y = float((left_shoulder[1] + right_shoulder[1]) / 2.0)
        wrists_on_chest = (
            shoulder_y - 0.25 * shoulder_width
            < wrist_midpoint[1]
            < shoulder_y + 1.25 * shoulder_width
        )
        crossed = bool(
            (forearms_intersect or wrist_order_reversed)
            and wrists_on_chest
            and distance(left_wrist, right_wrist) < 1.05 * shoulder_width
        )

    if crossed:
        pose = "ARMS CROSSED"
    elif left_raised and right_raised:
        pose = "BOTH HANDS - NO COMMAND"
    elif left_raised:
        pose = "LEFT HAND RAISED"
    elif right_raised:
        pose = "RIGHT HAND RAISED"
    else:
        pose = "NEUTRAL"
    return pose, left_raised, right_raised, crossed
