"""Exercise the actual loop with virtual time/devices; never open UI/camera/Office."""
from contextlib import ExitStack
from dataclasses import replace
import logging
import queue
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from app_settings import Settings
from camera_service import CameraFrame
from controller_runtime import run
from pose_types import Person, PoseResult
from powerpoint_bridge import PowerPointStatus
from test_control import pose


class LectureRuntimeTests(unittest.TestCase):
    def exercise(self, manual_lock=False, native=False):
        clock = SimpleNamespace(now=0.0)
        draws, calls, keys = [], [], set()
        image = np.zeros((720, 1280, 3), np.uint8)
        controls = queue.Queue(maxsize=32)
        if native:
            controls.put({'action': 'unlock'})
            controls.put({'action': 'preview_visibility', 'visible': False})

        class Publisher:
            closed = False
            def publish(self, frame, now): pass
            def close(self): self.closed = True
        publisher = Publisher() if native else None

        class Event:
            def __init__(self): self.flag = False
            def set(self): self.flag = True
            def clear(self): self.flag = False
            def is_set(self): return self.flag
            def wait(self, seconds):
                clock.now = round(clock.now + .05, 9)
                if native and clock.now == 63.8:
                    controls.put({'action': 'preview_visibility', 'visible': True})
                return self.flag

        class Camera:
            def __init__(self, *args): pass
            def start(self): pass
            def retry(self, *args): pass
            def close(self): return True
            def snapshot(self):
                if 8 <= clock.now < 10:
                    return None, 'retrying', 'test camera recovery', 1
                generation = int(clock.now >= 8)
                return CameraFrame(image, clock.now, int(clock.now * 100) + 1, generation), 'ready', '', generation

        class Inference:
            def __init__(self, *args): pass
            def start(self): pass
            def retry(self, *args): pass
            def close(self): return True
            def snapshot(self):
                generation = int(clock.now >= 14)
                if 14 <= clock.now < 16:
                    return None, None, 'recovering', 'test GPU recovery', 'test CPU', generation, 1, 20, 50
                visible = clock.now < 2 or clock.now >= 62
                raised = .6 <= clock.now < 2 or 62.6 <= clock.now
                points, scores = pose('next' if raised else 'neutral')
                # The resting wrist and both elbows are below a desk.
                scores[[7, 8, 10]] = 0
                if not raised:
                    scores[9] = 0  # Both hands rest below the desk between pages.
                box = np.array((300, 100, 700, 700) if clock.now < 2 else (700, 100, 1100, 700), np.float32)
                people = [Person(box, points, scores)] if visible else []
                result = PoseResult(people, clock.now, clock.now, int(clock.now * 100) + 1)
                return result, image, 'ready', '', 'test CPU', generation, int(clock.now >= 8), 20, 50

        class PowerPoint:
            busy = False
            def __init__(self, *args): self.results = queue.Queue()
            def start(self): pass
            def close(self): return True
            def control(self, *args): pass
            def status(self):
                connected = not 20 <= clock.now < 22
                return PowerPointStatus(connected, 'fixture', connected, 'fixture' if connected else '')
            def submit(self, command):
                calls.append((clock.now, command.action))
                return True

        def render(frame, gesture, *args):
            draws.append((clock.now, replace(gesture)))

        initial_wait = [True]
        def wait_key(*args):
            if initial_wait[0]:
                initial_wait[0] = False
                return -1
            scheduled = [(0, 'l'), (63.8, 'c')]
            if manual_lock:
                scheduled.append((5, 'l'))
            for when, key in sorted(scheduled):
                if clock.now >= when and (when, key) not in keys:
                    keys.add((when, key))
                    return ord(key)
            return -1

        noop = lambda *args, **kwargs: None
        ui = SimpleNamespace(WINDOW_NAME='virtual preview', ORANGE=(0, 0, 0), GREEN=(0, 0, 0),
            WHITE=(0, 0, 0), CYAN=(0, 0, 0), ENABLE_GLOW=False,
            set_windows_app_identity=noop, put_text=noop, apply_windows_window_icon=lambda: (),
            release_windows_icons=noop, set_overlay_mode=noop, render_ui=render)
        cv2 = SimpleNamespace(WINDOW_NORMAL=0, WINDOW_FULLSCREEN=1, WND_PROP_FULLSCREEN=0,
            WND_PROP_TOPMOST=1, WND_PROP_VISIBLE=2, namedWindow=noop, resizeWindow=noop,
            imshow=noop, waitKey=wait_key, setWindowProperty=noop, getWindowProperty=lambda *args: 1,
            flip=lambda frame, *args: frame, mean=lambda frame: (50, 50, 50, 0), destroyAllWindows=noop)
        trace = SimpleNamespace(events={}, mark=noop, save=noop)
        def mark(name): trace.events[name] = clock.now
        trace.mark = mark
        protocol = SimpleNamespace(enabled=False, send=noop)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {'cv2': cv2, 'preview_ui': ui}))
            stack.enter_context(patch('controller_runtime.threading.Event', Event))
            stack.enter_context(patch('controller_runtime.time.perf_counter', lambda: clock.now))
            stack.enter_context(patch('camera_service.CameraService', Camera))
            stack.enter_context(patch('inference_service.InferenceService', Inference))
            stack.enter_context(patch('ppt_service.PowerPointService', PowerPoint))
            run(Settings(), SimpleNamespace(save=lambda settings: True), protocol, trace,
                logging.getLogger('test'), duration=65, headless=native, native_preview=publisher,
                control_queue=controls if native else None)
        if native:
            self.assertTrue(publisher.closed)
        return draws, calls

    def test_actual_loop_leaving_for_a_minute_and_resource_recovery_preserves_unlock(self):
        draws, calls = self.exercise()
        self.assertTrue(all(not gesture.locked for now, gesture in draws if now >= .1))
        self.assertEqual([action for _, action in calls], ['next', 'next'])
        self.assertFalse(any(2 <= now < 62.6 for now, _ in calls))
        self.assertGreaterEqual(calls[1][0], 62.6 + .78)

    def test_actual_loop_manual_lock_is_not_undone_by_reentry_or_refresh(self):
        draws, calls = self.exercise(manual_lock=True)
        self.assertTrue(all(gesture.locked for now, gesture in draws if now >= 5.1))
        self.assertEqual([action for _, action in calls], ['next'])

    def test_hidden_native_preview_does_not_interrupt_background_gestures_or_repaint(self):
        draws, calls = self.exercise(native=True)
        self.assertEqual([action for _, action in calls], ['next', 'next'])
        self.assertTrue(draws)
        self.assertTrue(all(now >= 63.8 for now, gesture in draws))
        self.assertTrue(all(not gesture.locked for now, gesture in draws))


if __name__ == '__main__':
    unittest.main()
