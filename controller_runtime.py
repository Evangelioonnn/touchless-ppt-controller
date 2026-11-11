"""Responsive preview/control loop. Capture, inference and PowerPoint run separately."""
from __future__ import annotations

from dataclasses import asdict
import json
import queue
import sys
import threading
import time

from app_settings import Settings
from command_gate import CommandGate
from gesture_engine import GestureEngine
from person_tracker import PoseSmoother, PresenterTracker


def run(settings, store, protocol, trace, logger, headless=False, observe_only=False, duration=0, metrics_path=None,
        native_preview=None, control_queue=None):
    trace.mark('loading_preview')
    import cv2
    import numpy as np
    import preview_ui as ui
    from camera_service import CameraService
    from inference_service import InferenceService, result_is_fresh
    from ppt_service import PowerPointService

    trace.mark('preview_dependencies_loaded')
    stop = threading.Event()
    urgent_lock = threading.Event()
    controls: queue.Queue = queue.Queue(maxsize=32) if control_queue is None else control_queue
    gate = CommandGate()
    camera = CameraService(settings.camera_index)
    inference = InferenceService(camera, settings, trace.mark)
    ppt = PowerPointService(gate, settings.ppt_backend)
    tracker, smoother = PresenterTracker(), PoseSmoother()
    engine = GestureEngine(locked=True)
    engine.swap_hands = settings.swap_hands
    gesture = engine.update(None, None)
    tracker_status = 'WAITING FOR PRESENTER'
    diagnostic_started = time.perf_counter()
    metrics = None
    if metrics_path is not None:
        from runtime_metrics import RuntimeMetrics
        metrics = RuntimeMetrics(metrics_path)

    def input_reader():
        try:
            for line in sys.stdin:
                try:
                    command = json.loads(line)
                    if not isinstance(command, dict) or 'action' not in command:
                        continue
                    if command['action'] in ('quit', 'lock', 'toggle_lock', 'reselect', 'target', 'settings', 'retry'):
                        gate.invalidate()
                    if command['action'] == 'lock':
                        urgent_lock.set()
                    if command['action'] == 'quit':
                        stop.set()
                    controls.put_nowait(command)
                except (ValueError, queue.Full):
                    logger.warning('Ignored malformed or excess control message')
        except (OSError, ValueError):
            pass
        finally:
            stop.set()  # A closed launcher must not leave a camera worker orphaned.

    if protocol.enabled:
        threading.Thread(target=input_reader, name='launcher-input', daemon=True).start()
    icon_handles = ()
    camera_started = inference_started = ppt_started = False
    flash_text, flash_color, flash_until = 'START LOCKED - CROSS ARMS TO UNLOCK', ui.ORANGE, time.perf_counter() + 3
    last_seq = -1
    last_resource = None
    last_presenter_generation = tracker.generation
    last_ppt = None
    last_status_at = 0.0
    points = scores = box = None
    dark_frames = 0
    preview_mode = None
    preview_visible = True
    last_preview_publish = -1.0
    last_preview_sequence = -1
    preview_published_frames = 0
    preview_error_at = -10.0

    def pause(reselect=False, lock=False):
        nonlocal gesture, points, scores, box, last_presenter_generation
        gate.invalidate()
        if lock:
            engine.force_lock()
        else:
            engine.suspend(time.perf_counter())
        gesture = engine.update(None, None)
        smoother.reset()
        points = scores = box = None
        if reselect:
            tracker.reset()
            last_presenter_generation = tracker.generation

    def toggle_lock():
        nonlocal flash_text, flash_color, flash_until, gesture
        if engine.locked:
            engine.manual_toggle_lock()
            flash_text, flash_color = 'CONTROL ACTIVE - AUTO RESUME WHEN VISIBLE', ui.GREEN
        else:
            pause(lock=True)
            flash_text, flash_color = 'LOCKING - WAIT FOR IN-FLIGHT COMMAND' if ppt.busy else 'CONTROL LOCKED', ui.ORANGE
        flash_until = time.perf_counter() + 1.5

    def persist():
        if not store.save(settings):
            protocol.send('warning', message=store.warnings[-1])

    try:
        ui.set_windows_app_identity()
        if not headless:
            cv2.namedWindow(ui.WINDOW_NAME, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(ui.WINDOW_NAME, 1120, 700)
            initial = np.zeros((720, 1280, 3), np.uint8)
            ui.put_text(initial, 'LOADING LOCAL MODEL - CONTROLS ARE LOCKED', (60, 350), .9, ui.WHITE)
            cv2.imshow(ui.WINDOW_NAME, initial)
            cv2.waitKey(1)
            icon_handles = ui.apply_windows_window_icon()
        trace.mark('preview_visible' if not headless else 'headless_loop')
        camera.start(); camera_started = True
        ppt.start(); ppt_started = True
        inference.start(); inference_started = True
        while not stop.is_set():
            now = time.perf_counter()
            if duration > 0 and now - diagnostic_started >= duration:
                stop.set()
                break
            if urgent_lock.is_set():
                urgent_lock.clear()
                pause(lock=True)
            for _ in range(32):
                try:
                    control = controls.get_nowait()
                except queue.Empty:
                    break
                action = control.get('action')
                if action == 'quit':
                    stop.set()
                elif action == 'lock':
                    pause(lock=True)
                elif action in ('toggle_lock', 'unlock'):
                    if action != 'unlock' or engine.locked:
                        toggle_lock()
                    last_presenter_generation = tracker.generation
                elif action == 'reselect':
                    pause(reselect=True)
                elif action == 'target':
                    pause()
                    ppt.control('target', control.get('value', ''))
                elif action == 'start':
                    pause()
                    if not observe_only:
                        ppt.control('start')
                elif action == 'refresh':
                    ppt.control('refresh')
                elif action == 'retry':
                    pause(reselect=True)
                    camera.retry(settings.camera_index)
                    inference.retry(settings)
                elif action == 'settings':
                    try:
                        updated = Settings.from_dict({**asdict(settings), **control.get('values', {})})
                    except (ValueError, TypeError) as error:
                        protocol.send('warning', message=str(error))
                        continue
                    pause(reselect=True)
                    if updated.camera_index != settings.camera_index:
                        camera.retry(updated.camera_index)
                    if updated.backend != settings.backend or updated.device != settings.device:
                        inference.retry(updated)
                    if updated.ppt_backend != settings.ppt_backend:
                        ppt.control('backend', updated.ppt_backend)
                    settings = updated
                    engine.swap_hands = settings.swap_hands
                    persist()
                elif action == 'preview':
                    if control.get('value') in ('normal', 'overlay', 'fullscreen'):
                        settings.preview_mode = control['value']
                        persist()
                elif action == 'preview_visibility':
                    if type(control.get('visible')) is bool:
                        preview_visible = control['visible']

            camera_frame, camera_state, camera_message, camera_generation = camera.snapshot()
            result, result_image, infer_state, infer_message, device, infer_generation, result_camera_generation, fps, latency = inference.snapshot()
            status = ppt.status()
            resource = (camera_generation, infer_generation)
            if last_resource is not None and resource != last_resource:
                pause(reselect=True)
            last_resource = resource
            ppt_identity = (status.connected, status.target_id)
            if last_ppt is not None and ppt_identity != last_ppt:
                pause()
            last_ppt = ppt_identity
            fresh = bool(camera_state == 'ready' and infer_state == 'ready' and result is not None
                         and result_camera_generation == camera_generation
                         and result_is_fresh(result, now))
            if fresh and result.sequence != last_seq:
                last_seq = result.sequence
                selection = tracker.select(result.people)
                tracker_status = selection.status
                if selection.generation != last_presenter_generation:
                    pause()
                    last_presenter_generation = selection.generation
                person = selection.person
                points = smoother.update(person)
                scores = person.scores if person is not None else None
                box = person.box if person is not None else None
                gesture = engine.update(points, scores, now)
                if gesture.triggered == 'toggle_lock':
                    gate.invalidate()
                    last_presenter_generation = tracker.generation
                    flash_text = 'CONTROL LOCKED' if engine.locked else 'CONTROL ACTIVE'
                    flash_color = ui.ORANGE if engine.locked else ui.GREEN
                    flash_until = now + 1.5
                allowed = bool(not observe_only and not engine.locked and person is not None
                               and gesture.observation == 'known' and status.connected)
                if gate.enabled != allowed or gate.target != status.target_id:
                    gate.invalidate(allowed, status.target_id)
                if gesture.triggered in ('next', 'previous') and allowed:
                    command = gate.issue(gesture.triggered, now)
                    if command is not None:
                        if ppt.submit(command):
                            flash_text, flash_color = 'COMMAND QUEUED', ui.CYAN
                        else:
                            flash_text, flash_color = 'BUSY - LOWER HAND AND RETRY', ui.ORANGE
                        flash_until = now + 1.2
                        logger.info('gesture=%s target=%s', gesture.triggered, status.target_id)
            elif not fresh:
                if gate.enabled:
                    gate.invalidate()
                points = scores = box = None
                smoother.reset()
                gesture = engine.update(None, None, now)
                if infer_state != 'ready':
                    tracker_status = infer_message
                else:
                    tracker_status = 'WAITING FOR FRESH FRAME - AUTO RESUME'

            while True:
                try:
                    operation = ppt.results.get_nowait()
                except queue.Empty:
                    break
                flash_text = operation.message[:85]
                flash_color = ui.GREEN if operation.state == 'observed' else ui.CYAN if operation.state in ('accepted', 'sent') else ui.ORANGE
                flash_until = now + 2
                logger.info('ppt action=%s result=%s target=%s message=%s', operation.action, operation.state, operation.target_id, operation.message)
                protocol.send('operation', result=asdict(operation))

            if fresh and 'ready' not in trace.events:
                trace.mark('ready')
                trace.save()
            if metrics is not None:
                metrics.sample(fps, latency, camera_state, infer_state)
            if protocol.enabled and now - last_status_at >= .25:
                protocol.send('status', locked=engine.locked, locking=engine.locked and ppt.busy,
                              presenter_visible=bool(fresh and box is not None),
                              preview_published_frames=preview_published_frames,
                              camera_state=camera_state, camera_message=camera_message,
                              inference_state=infer_state, inference_message=infer_message, device=device,
                              presenter=tracker_status, fps=round(fps, 1), latency_ms=round(latency, 1),
                              ppt=asdict(status), settings=asdict(settings), ready=fresh)
                last_status_at = now
            publish_native = bool(native_preview is not None and preview_visible and camera_frame is not None
                                  and camera_state == 'ready' and now - last_preview_publish >= 1 / 15
                                  and camera_frame.sequence != last_preview_sequence)
            if not headless or publish_native:
                if not headless and settings.preview_mode != preview_mode:
                    mode = settings.preview_mode
                    cv2.setWindowProperty(ui.WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN if mode == 'fullscreen' else cv2.WINDOW_NORMAL)
                    if mode != 'fullscreen':
                        ui.set_overlay_mode(mode == 'overlay')
                    else:
                        cv2.setWindowProperty(ui.WINDOW_NAME, cv2.WND_PROP_TOPMOST, 0)
                    preview_mode = mode
                if camera_frame is not None and camera_state == 'ready':
                    frame = cv2.flip(camera_frame.image, 1)
                    dark_frames = dark_frames + 1 if sum(cv2.mean(frame)[:3]) / 3 < 1 else 0
                else:
                    frame = np.zeros((720, 1280, 3), np.uint8)
                if frame.shape[1] < 960 or frame.shape[0] < 600:
                    # Draw UI at its established layout size; scale keypoints consistently.
                    old_h, old_w = frame.shape[:2]
                    frame = cv2.resize(frame, (1280, 720))
                    draw_points = points * np.array([1280 / old_w, 720 / old_h]) if points is not None else None
                    draw_box = box * np.array([1280 / old_w, 720 / old_h] * 2) if box is not None else None
                else:
                    draw_points, draw_box = points, box
                ui.ENABLE_GLOW = settings.glow
                ui.render_ui(frame, gesture, status, draw_points, scores, draw_box,
                             len(result.people) if fresh else 0, fps, device, engine.swap_hands,
                             flash_text, flash_color, now < flash_until, dark_frames)
                ui.put_text(frame, tracker_status[:80], (30, frame.shape[0] - 103), .5, ui.CYAN, 1)
                if not fresh:
                    message = camera_message if camera_state != 'ready' else infer_message
                    ui.put_text(frame, message[:85], (30, frame.shape[0] // 2 + 90), .5, ui.ORANGE, 1)
                if publish_native:
                    try:
                        native_preview.publish(frame, now)
                        preview_published_frames += 1
                        last_preview_sequence = camera_frame.sequence
                    except Exception as error:
                        if now - preview_error_at >= 5:
                            logger.warning('Native preview frame unavailable: %s', error)
                            protocol.send('warning', message='Preview unavailable; recognition continues. ' + str(error))
                            preview_error_at = now
                    last_preview_publish = now
                if not headless:
                    cv2.imshow(ui.WINDOW_NAME, frame)
                    if not icon_handles:
                        icon_handles = ui.apply_windows_window_icon()
                    if cv2.getWindowProperty(ui.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        stop.set()
                        continue
                    key = cv2.waitKey(1) & 0xFF
                    shortcuts = {ord('q'): 'quit', 27: 'quit', ord('l'): 'toggle_lock', ord('s'): 'start',
                                 ord('r'): 'refresh', ord('c'): 'reselect'}
                    if 65 <= key <= 90:
                        key += 32
                    if key in shortcuts:
                        controls.put_nowait({'action': shortcuts[key]})
                    elif key == ord('m'):
                        controls.put_nowait({'action': 'settings', 'values': {'swap_hands': not settings.swap_hands}})
                    elif key in (ord('o'), ord('f')):
                        requested = ('normal' if settings.preview_mode == 'overlay' else 'overlay') if key == ord('o') else ('normal' if settings.preview_mode == 'fullscreen' else 'fullscreen')
                        controls.put_nowait({'action': 'preview', 'value': requested})
            stop.wait(.008 if not headless else .02)
    finally:
        gate.invalidate()
        stop.set()
        if inference_started and not inference.close():
            logger.warning('Inference still stopping; launcher supervises process lifetime')
        if camera_started and not camera.close():
            logger.warning('Camera still stopping; launcher supervises process lifetime')
        if ppt_started and not ppt.close():
            logger.warning('PPT still stopping; launcher supervises process lifetime')
        if not headless:
            cv2.destroyAllWindows()
        if native_preview is not None:
            native_preview.close()
        ui.release_windows_icons(icon_handles)
        protocol.send('stopped')
        trace.mark('stopped')
        if metrics is not None:
            metrics.save(True)
    return 0
