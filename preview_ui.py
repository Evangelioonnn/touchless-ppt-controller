"""Real-time touchless PowerPoint controller powered by YOLO26 Pose.

Controls:
    Q / Esc  Quit
    S        Start the open PowerPoint presentation
    R        Rescan for a slideshow
    L        Manually lock or unlock gesture control
    M        Swap left/right hand mapping
    O        Toggle compact always-on-top overlay mode
    F        Toggle fullscreen preview
"""

from __future__ import annotations

import ctypes
import time
import traceback

import cv2
import numpy as np

from controller_config import (
    CAMERA_HEIGHT,
    CAMERA_INDEX,
    CAMERA_WIDTH,
    DETECTION_CONFIDENCE,
    IMAGE_SIZE,
    MODEL_PATH,
    PROJECT_ROOT,
)
from gesture_engine import (
    LEFT_ELBOW,
    LEFT_SHOULDER,
    LEFT_WRIST,
    RIGHT_ELBOW,
    RIGHT_SHOULDER,
    RIGHT_WRIST,
    GestureEngine,
    GestureFrame,
    valid,
)
from powerpoint_bridge import PowerPointBridge, PowerPointStatus


WINDOW_NAME = "Touchless PowerPoint Controller"
APP_USER_MODEL_ID = "TouchlessPPTController.YOLO26"
from app_paths import resource_path
APP_ICON_PATH = resource_path("windows_launcher/TouchlessPPTController.ico")
NOSE = 0
UPPER_BODY_EDGES = (
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW),
    (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW),
    (RIGHT_ELBOW, RIGHT_WRIST),
    (NOSE, LEFT_SHOULDER),
    (NOSE, RIGHT_SHOULDER),
)

GREEN = (70, 240, 100)
CYAN = (255, 220, 50)
BLUE = (255, 120, 30)
ORANGE = (20, 160, 255)
RED = (60, 60, 255)
WHITE = (245, 245, 245)
GRAY = (150, 155, 165)
DARK = (18, 22, 32)


ENABLE_GLOW = True

def set_windows_app_identity() -> None:
    """Give the Python window its own taskbar identity instead of pythonw.exe's."""
    shell32 = ctypes.windll.shell32
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def apply_windows_window_icon() -> tuple[int, ...]:
    """Apply the project icon to OpenCV's title bar and taskbar window."""
    if not APP_ICON_PATH.is_file():
        print(f"Window icon not found: {APP_ICON_PATH}")
        return ()

    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t

    hwnd = user32.FindWindowW(None, WINDOW_NAME)
    if not hwnd:
        return ()

    image_icon = 1
    load_from_file = 0x0010
    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    icon_small_2 = 2

    big_handle = user32.LoadImageW(None, str(APP_ICON_PATH), image_icon, 32, 32, load_from_file)
    small_handle = user32.LoadImageW(None, str(APP_ICON_PATH), image_icon, 16, 16, load_from_file)
    handles = tuple(int(handle) for handle in (big_handle, small_handle) if handle)
    if not handles:
        print(f"Windows could not load the window icon: {APP_ICON_PATH}")
        return ()

    if big_handle:
        user32.SendMessageW(hwnd, wm_seticon, icon_big, int(big_handle))
    if small_handle:
        user32.SendMessageW(hwnd, wm_seticon, icon_small, int(small_handle))
        user32.SendMessageW(hwnd, wm_seticon, icon_small_2, int(small_handle))
    return handles


def release_windows_icons(handles: tuple[int, ...]) -> None:
    """Release icon resources after the OpenCV window has closed."""
    user32 = ctypes.windll.user32
    user32.DestroyIcon.argtypes = [ctypes.c_void_p]
    user32.DestroyIcon.restype = ctypes.c_bool
    for handle in handles:
        user32.DestroyIcon(ctypes.c_void_p(handle))


def point(points: np.ndarray, index: int) -> tuple[int, int]:
    return int(points[index, 0]), int(points[index, 1])


def put_text(
    frame: np.ndarray,
    text: str,
    origin: tuple[int, int],
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    x, y = origin
    cv2.putText(frame, text, (x + 2, y + 2), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 3, cv2.LINE_AA)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def translucent_rect(
    frame: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    overlay = frame.copy()
    cv2.rectangle(overlay, top_left, bottom_right, color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0.0, dst=frame)


def draw_corner_box(frame: np.ndarray, box: np.ndarray | None, color: tuple[int, int, int]) -> None:
    if box is None:
        return
    x1, y1, x2, y2 = (int(value) for value in box)
    length = max(20, min(x2 - x1, y2 - y1) // 10)
    segments = (
        ((x1, y1 + length), (x1, y1), (x1 + length, y1)),
        ((x2 - length, y1), (x2, y1), (x2, y1 + length)),
        ((x1, y2 - length), (x1, y2), (x1 + length, y2)),
        ((x2 - length, y2), (x2, y2), (x2, y2 - length)),
    )
    for first, middle, last in segments:
        cv2.line(frame, first, middle, color, 3, cv2.LINE_AA)
        cv2.line(frame, middle, last, color, 3, cv2.LINE_AA)


def draw_pose(
    frame: np.ndarray,
    points: np.ndarray | None,
    scores: np.ndarray | None,
    box: np.ndarray | None,
    locked: bool,
) -> None:
    if points is None or scores is None:
        return
    color = GRAY if locked else GREEN
    if not ENABLE_GLOW:
        draw_corner_box(frame, box, color)
        for first, second in UPPER_BODY_EDGES:
            if valid(scores, first) and valid(scores, second) and np.isfinite(points[[first, second]]).all():
                cv2.line(frame, point(points, first), point(points, second), color, 2, cv2.LINE_AA)
        for index in (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST):
            if valid(scores, index) and np.isfinite(points[index]).all():
                cv2.circle(frame, point(points, index), 4, WHITE, -1, cv2.LINE_AA)
        return
    glow = np.zeros_like(frame)
    core = np.zeros_like(frame)
    draw_corner_box(frame, box, color)

    for start_index, end_index in UPPER_BODY_EDGES:
        if not (valid(scores, start_index) and valid(scores, end_index) and np.isfinite(points[[start_index, end_index]]).all()):
            continue
        start = point(points, start_index)
        end = point(points, end_index)
        cv2.line(glow, start, end, color, 11, cv2.LINE_AA)
        cv2.line(core, start, end, WHITE, 2, cv2.LINE_AA)

    for index in (NOSE, LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST):
        if not valid(scores, index) or not np.isfinite(points[index]).all():
            continue
        center = point(points, index)
        cv2.circle(glow, center, 13, color, -1, cv2.LINE_AA)
        cv2.circle(core, center, 4, WHITE, -1, cv2.LINE_AA)

    blurred = cv2.GaussianBlur(glow, (0, 0), 10)
    cv2.addWeighted(frame, 1.0, blurred, 0.45, 0.0, dst=frame)
    cv2.add(frame, core, dst=frame)


def draw_progress_ring(
    frame: np.ndarray,
    center: tuple[int, int],
    progress: float,
    color: tuple[int, int, int],
) -> None:
    cv2.circle(frame, center, 31, (45, 48, 55), 6, cv2.LINE_AA)
    cv2.ellipse(frame, center, (31, 31), -90, 0, progress * 360.0, color, 7, cv2.LINE_AA)


def action_label(action: str | None) -> str:
    return {
        "next": "NEXT SLIDE",
        "previous": "PREVIOUS SLIDE",
        "toggle_lock": "TOGGLE CONTROL LOCK",
    }.get(action, "WAITING FOR GESTURE")


def render_ui(
    frame: np.ndarray,
    gesture: GestureFrame,
    ppt_status: PowerPointStatus,
    points: np.ndarray | None,
    scores: np.ndarray | None,
    box: np.ndarray | None,
    people: int,
    fps: float,
    device_name: str,
    swap_hands: bool,
    flash_text: str,
    flash_color: tuple[int, int, int],
    flash_active: bool,
    black_frames: int,
) -> None:
    height, width = frame.shape[:2]
    draw_pose(frame, points, scores, box, gesture.locked)

    translucent_rect(frame, (12, 12), (width - 12, 126), DARK, 0.72)
    connection_color = GREEN if ppt_status.connected else RED
    lock_color = ORANGE if gesture.locked else GREEN
    put_text(frame, "TOUCHLESS PPT CONTROLLER", (30, 48), 0.88, CYAN, 2)
    put_text(
        frame,
        "POWERPOINT CONNECTED" if ppt_status.connected else "NO ACTIVE SLIDESHOW - OPEN PPT AND PRESS F5",
        (30, 82),
        0.56,
        connection_color,
        2,
    )
    put_text(
        frame,
        "LOCKED" if gesture.locked else "CONTROL ACTIVE",
        (30, 111),
        0.55,
        lock_color,
        2,
    )
    put_text(frame, f"FPS {fps:.1f}   PEOPLE {people}   DEVICE {device_name}", (width - 470, 48), 0.40, WHITE, 1)
    put_text(frame, f"POSE: {gesture.pose}", (width - 470, 78), 0.48, WHITE, 1)
    mapping = "MIRROR MAPPING CORRECTED" if swap_hands else "RAW MODEL MAPPING"
    put_text(frame, mapping, (width - 470, 108), 0.43, CYAN, 1)

    panel_top = 150
    panel_bottom = min(height - 86, 290)
    left_active = gesture.candidate == "previous"
    right_active = gesture.candidate == "next"
    translucent_rect(frame, (14, panel_top), (255, panel_bottom), BLUE if left_active else DARK, 0.62)
    translucent_rect(frame, (width - 255, panel_top), (width - 14, panel_bottom), GREEN if right_active else DARK, 0.62)
    put_text(frame, "LEFT HAND", (34, panel_top + 39), 0.58, WHITE, 2)
    put_text(frame, "PREVIOUS", (34, panel_top + 82), 0.75, BLUE if left_active else GRAY, 2)
    put_text(frame, "RIGHT HAND", (width - 226, panel_top + 39), 0.58, WHITE, 2)
    put_text(frame, "NEXT", (width - 226, panel_top + 82), 0.75, GREEN if right_active else GRAY, 2)

    if gesture.candidate and points is not None and scores is not None:
        if gesture.candidate == "next":
            wrist_index = LEFT_WRIST if swap_hands else RIGHT_WRIST
            if valid(scores, wrist_index):
                draw_progress_ring(frame, point(points, wrist_index), gesture.progress, GREEN)
        elif gesture.candidate == "previous":
            wrist_index = RIGHT_WRIST if swap_hands else LEFT_WRIST
            if valid(scores, wrist_index):
                draw_progress_ring(frame, point(points, wrist_index), gesture.progress, BLUE)

    bar_left, bar_right = 280, width - 280
    bar_y = height - 70
    cv2.rectangle(frame, (bar_left, bar_y), (bar_right, bar_y + 18), (40, 43, 52), -1)
    if gesture.candidate:
        progress_right = int(bar_left + (bar_right - bar_left) * gesture.progress)
        bar_color = ORANGE if gesture.candidate == "toggle_lock" else GREEN
        cv2.rectangle(frame, (bar_left, bar_y), (progress_right, bar_y + 18), bar_color, -1)
    put_text(frame, action_label(gesture.candidate), (bar_left, bar_y - 12), 0.52, WHITE, 1)

    translucent_rect(frame, (12, height - 44), (width - 12, height - 10), DARK, 0.75)
    put_text(
        frame,
        "Cross arms: lock/unlock   S: start slideshow   R: reconnect   O: overlay   M: swap hands   Q: quit",
        (24, height - 20),
        0.42,
        WHITE,
        1,
    )

    if flash_active:
        translucent_rect(frame, (width // 2 - 285, height // 2 - 58), (width // 2 + 285, height // 2 + 58), DARK, 0.80)
        text_size = cv2.getTextSize(flash_text, cv2.FONT_HERSHEY_SIMPLEX, 0.95, 2)[0]
        put_text(frame, flash_text, ((width - text_size[0]) // 2, height // 2 + 10), 0.95, flash_color, 2)

    if black_frames > 20:
        put_text(frame, "CAMERA IMAGE IS VERY DARK - CHECK LIGHTING / CAMERA", (35, height // 2 + 95), 0.60, RED, 2)


def set_overlay_mode(enabled: bool) -> None:
    if enabled:
        screen_width = int(ctypes.windll.user32.GetSystemMetrics(0))
        cv2.resizeWindow(WINDOW_NAME, 520, 330)
        cv2.moveWindow(WINDOW_NAME, max(0, screen_width - 540), 20)
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
    else:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 0)
        cv2.resizeWindow(WINDOW_NAME, 1120, 700)
        cv2.moveWindow(WINDOW_NAME, 70, 50)
