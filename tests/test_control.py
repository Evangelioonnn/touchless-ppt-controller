from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from app_settings import Settings, SettingsStore
from command_gate import CommandGate
from gesture_engine import GestureEngine, detect_pose
from person_tracker import PresenterTracker, PoseSmoother
from pose_types import Person


def setUpModule():
    (Path(__file__).resolve().parents[1] / 'validation').mkdir(exist_ok=True)


def pose(kind='neutral'):
    points = np.zeros((17, 2), np.float32)
    points[5], points[6] = (400, 200), (600, 200)
    points[7], points[8] = (350, 280), (650, 280)
    points[9], points[10] = (340, 380), (660, 380)
    if kind in ('next', 'both'):
        points[9] = (380, 100)
    if kind in ('previous', 'both'):
        points[10] = (620, 100)
    if kind == 'cross':
        points[9], points[10] = (580, 280), (420, 280)
    return points, np.ones(17, np.float32)


class GestureTests(unittest.TestCase):
    def drive(self, engine, kind, start, duration, scores=None):
        points, confidence = pose(kind)
        if scores is not None:
            confidence = scores
        events = []
        for now in np.arange(start, start + duration, 0.05):
            frame = engine.update(points, confidence, round(float(now), 9))
            if frame.triggered:
                events.append(frame.triggered)
        return events

    def test_G01_held_hand_only_once(self):
        self.assertEqual(self.drive(GestureEngine(False), 'next', 0, 10), ['next'])

    def test_G02_G03_dropout_never_rearms(self):
        engine = GestureEngine(False)
        self.assertEqual(self.drive(engine, 'next', 0, 1), ['next'])
        now = 1.0
        for _ in range(20):
            for t in np.arange(now, now + 0.5, 0.05):
                engine.update(None, None, float(t))
            now += 0.5
            self.assertEqual(self.drive(engine, 'next', now, 1.0), [])
            now += 1.0

    def test_G04_neutral_rearms(self):
        engine = GestureEngine(False)
        self.assertEqual(self.drive(engine, 'next', 0, 1), ['next'])
        self.drive(engine, 'neutral', 1, 0.6)
        self.assertEqual(self.drive(engine, 'next', 1.6, 1.0), ['next'])

    def test_original_both_hands_no_command_rearms_and_brief_wrist_dropout_does_not(self):
        engine = GestureEngine(False)
        self.drive(engine, 'next', 0, 1)
        self.drive(engine, 'both', 1, 1)
        self.assertEqual(self.drive(engine, 'next', 2, 1), ['next'])
        scores = np.ones(17, np.float32)
        scores[9] = 0
        self.drive(engine, 'neutral', 3, 0.2, scores)
        self.assertEqual(self.drive(engine, 'next', 3.2, 1), [])

    def test_both_hands_below_desk_rearms_with_original_release_time(self):
        engine = GestureEngine(False)
        self.assertEqual(self.drive(engine, 'next', 0, 1.1), ['next'])
        hidden = np.ones(17, np.float32)
        hidden[[7, 8, 9, 10]] = 0
        self.assertEqual(self.drive(engine, 'neutral', 1.1, .45, hidden), [])
        self.assertTrue(engine.armed)
        # Bring only the active hand back, not the other wrist or elbows.
        hidden[9] = 1
        self.assertEqual(self.drive(engine, 'next', 1.6, 1.1, hidden), ['next'])

    def test_long_gap_cancels_pending_without_disarming_or_locking(self):
        engine = GestureEngine(False)
        self.drive(engine, 'next', 0, 0.4)
        self.assertIsNone(engine.update(*pose('next'), 5.0).triggered)
        self.assertTrue(engine.armed)
        self.assertFalse(engine.locked)
        self.assertEqual(self.drive(engine, 'next', 5.05, 1), ['next'])

    def test_absence_1_10_60_seconds_preserves_unlock_and_auto_resumes(self):
        for seconds in (1, 10, 60):
            with self.subTest(seconds=seconds):
                engine = GestureEngine(False)
                self.drive(engine, 'neutral', 0, 0.3)
                for t in np.arange(.3, .3 + seconds, .05):
                    frame = engine.update(None, None, float(t))
                    self.assertIsNone(frame.triggered)
                    self.assertFalse(frame.locked)
                self.assertEqual(self.drive(engine, 'next', .3 + seconds, 1.1), ['next'])

    def test_return_does_not_replay_incomplete_hold(self):
        engine = GestureEngine(False)
        self.drive(engine, 'next', 0, .5)
        engine.update(None, None, .5)
        engine.update(None, None, 60)
        frame = engine.update(*pose('next'), 60.05)
        self.assertIsNone(frame.triggered)
        self.assertEqual(frame.progress, 0)
        self.assertFalse(frame.locked)

    def test_partial_upper_body_both_elbows_and_resting_wrist_may_be_hidden(self):
        for kind, hidden_wrist, expected in (('next', 10, 'next'), ('previous', 9, 'previous')):
            with self.subTest(kind=kind):
                engine = GestureEngine(False)
                scores = np.ones(17, np.float32)
                scores[[7, 8, hidden_wrist]] = 0
                self.assertEqual(self.drive(engine, kind, 0, 1.1, scores), [expected])
                self.drive(engine, 'neutral', 1.1, .6, scores)
                self.assertEqual(self.drive(engine, kind, 1.7, 1.1, scores), [expected])

    def test_brief_dropout_pauses_hold_without_restarting_or_counting_missing_time(self):
        engine = GestureEngine(False)
        self.drive(engine, 'next', 0, .5)
        engine.update(None, None, .5)
        engine.update(None, None, .6)
        frame = engine.update(*pose('next'), .65)
        self.assertAlmostEqual(engine.candidate_elapsed, .45)
        self.assertIsNone(frame.triggered)
        self.assertEqual(self.drive(engine, 'next', .7, .4), ['next'])

    def test_manual_lock_survives_leaving_and_returning(self):
        engine = GestureEngine(False)
        engine.force_lock(0)
        for t in (0, 1, 10, 60):
            self.assertTrue(engine.update(None, None, t).locked)
        self.assertEqual(self.drive(engine, 'next', 60.1, 2), [])
        self.assertTrue(engine.locked)

    def test_suspension_preserves_unlocked_choice_and_one_shot_latch(self):
        engine = GestureEngine(False)
        self.drive(engine, 'next', 0, 1.1)
        engine.suspend(2)
        self.assertFalse(engine.locked)
        self.assertEqual(self.drive(engine, 'next', 10, 1.1), [])
        self.drive(engine, 'neutral', 11.1, .6)
        self.assertEqual(self.drive(engine, 'next', 11.7, 1.1), ['next'])

    def test_cross_lock_and_mapping_preserved(self):
        engine = GestureEngine()
        self.assertEqual(self.drive(engine, 'cross', 0, 1.3), ['toggle_lock'])
        self.assertFalse(engine.locked)
        self.drive(engine, 'neutral', 1.3, 0.6)
        self.assertEqual(self.drive(engine, 'previous', 1.9, 1.1), ['previous'])

    def test_crossed_arm_elbow_dropout_cannot_rearm_lock_toggle(self):
        engine = GestureEngine(True)
        self.assertEqual(self.drive(engine, 'cross', 0, 1.3), ['toggle_lock'])
        scores = np.ones(17, np.float32)
        scores[7:9] = 0
        self.assertEqual(self.drive(engine, 'cross', 1.3, .6, scores), [])
        self.assertEqual(self.drive(engine, 'cross', 1.9, 1.2), [])
        self.assertFalse(engine.locked)

    def test_thresholds_and_geometry_unchanged(self):
        import controller_config as cfg
        self.assertEqual((cfg.RAISE_HOLD_SECONDS, cfg.CROSS_HOLD_SECONDS,
                          cfg.NEUTRAL_REARM_SECONDS, cfg.ACTION_COOLDOWN_SECONDS), (.78, 1, .35, .75))
        for kind, expected in [('neutral', 'NEUTRAL'), ('cross', 'ARMS CROSSED'), ('both', 'BOTH HANDS - NO COMMAND')]:
            self.assertEqual(detect_pose(*pose(kind))[0], expected)


def person(box):
    return Person(np.array(box, np.float32), *pose())


class TrackingTests(unittest.TestCase):
    def test_soft_continuity_reduces_target_jitter_without_identity_binding(self):
        tracker = PresenterTracker()
        a = person((300, 100, 700, 700))
        tracker.select([a]); self.assertTrue(tracker.bind())
        b = person((750, 0, 1500, 1000))
        self.assertIs(tracker.select([a, b]).person, a)

    def test_person_at_new_location_is_selected_automatically(self):
        tracker = PresenterTracker()
        tracker.select([person((300, 100, 700, 700))]); tracker.bind()
        returning = person((800, 0, 1500, 1000))
        self.assertIs(tracker.select([returning]).person, returning)
        self.assertFalse(tracker.suspended)

    def test_multiple_detections_do_not_require_manual_reselection(self):
        tracker = PresenterTracker()
        tracker.select([person((300, 100, 700, 700))]); tracker.bind()
        self.assertIsNotNone(tracker.select([person((310, 100, 710, 700)), person((290, 100, 690, 700))]).person)
        self.assertFalse(tracker.suspended)

    def test_single_miss_does_not_change_generation_and_return_is_automatic(self):
        tracker = PresenterTracker()
        presenter = person((300, 100, 700, 700))
        generation = tracker.select([presenter]).generation
        self.assertIsNone(tracker.select([]).person)
        self.assertEqual(tracker.generation, generation)
        self.assertIs(tracker.select([presenter]).person, presenter)
        self.assertEqual(tracker.generation, generation)

    def test_P04_reset_changes_generation(self):
        tracker = PresenterTracker()
        tracker.select([person((0, 0, 100, 200))]); tracker.bind()
        old = tracker.generation
        tracker.reset()
        self.assertGreater(tracker.generation, old)
        self.assertFalse(tracker.bound)

    def test_smoother_resets_and_ignores_invalid_points(self):
        smoother = PoseSmoother()
        a = person((0, 0, 100, 100))
        smoother.update(a)
        a.scores[9] = 0
        smoother.update(a)
        a.scores[9] = 1
        a.points[9] = (900, 100)
        self.assertEqual(smoother.update(a)[9, 0], 900)
        smoother.update(None)
        self.assertIsNone(smoother.points)


class GateTests(unittest.TestCase):
    def test_stale_and_generation_commands_rejected(self):
        gate = CommandGate(); gate.invalidate(True, 'a')
        command = gate.issue('next', 1.0)
        self.assertTrue(gate.valid(command, 1.2))
        self.assertFalse(gate.valid(command, 1.6))
        gate.invalidate(True, 'a')
        self.assertFalse(gate.valid(command, 1.2))
        self.assertIsNotNone(gate.issue('next', 2))
        gate.invalidate(False)
        self.assertIsNone(gate.issue('next', 2))


class SettingsTests(unittest.TestCase):
    def test_U01_U02_roundtrip_and_corrupt_recovery(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'validation') as folder:
            store = SettingsStore(Path(folder))
            settings = Settings(camera_index=3, glow=False)
            self.assertTrue(store.save(settings))
            self.assertEqual(store.load(), settings)
            store.path.write_text('{broken', encoding='utf-8')
            self.assertEqual(store.load(), Settings())
            self.assertTrue(list(Path(folder).glob('settings.broken-*')))

    def test_invalid_types_and_unknown_versions_rejected(self):
        for values in ({'camera_index': True}, {'glow': 'false'}, {'schema_version': 99}, {'device': 'magic'}):
            with self.assertRaises(ValueError):
                Settings.from_dict(values)

    def test_unwritable_store_reports_failure(self):
        store = SettingsStore(Path('unused'))
        with patch('pathlib.Path.mkdir', side_effect=PermissionError('test')):
            self.assertFalse(store.save(Settings()))
        self.assertTrue(store.warnings)


if __name__ == '__main__':
    unittest.main()
