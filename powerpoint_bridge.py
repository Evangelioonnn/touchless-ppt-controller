"""Target-bound PowerPoint control; sending a message never proves a slide changed."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import time


@dataclass(frozen=True)
class PowerPointTarget:
    id: str
    title: str
    hwnd: int
    process_id: int
    slideshow: bool


@dataclass
class PowerPointStatus:
    connected: bool
    title: str
    main_window_found: bool
    target_id: str = ''
    targets: list[PowerPointTarget] = field(default_factory=list)
    backend: str = 'keys'
    message: str = ''


@dataclass
class OperationResult:
    state: str
    message: str
    action: str
    target_id: str

    def __bool__(self) -> bool:
        return self.state in ('observed', 'accepted')


class NativeWindows:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Microsoft PowerPoint control requires Windows.')
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        u, k = self.user32, self.kernel32
        for name, args, result in (
            ('IsWindowVisible', [wintypes.HWND], wintypes.BOOL),
            ('IsWindow', [wintypes.HWND], wintypes.BOOL),
            ('GetWindowTextLengthW', [wintypes.HWND], ctypes.c_int),
            ('GetWindowTextW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            ('GetClassNameW', [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            ('GetWindowThreadProcessId', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            ('PostMessageW', [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
        ):
            function = getattr(u, name)
            function.argtypes, function.restype = args, result
        self.enum_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u.EnumWindows.argtypes = [self.enum_type, wintypes.LPARAM]
        u.EnumWindows.restype = wintypes.BOOL
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL

    def _is_powerpoint(self, pid: int) -> bool:
        if pid == os.getpid():
            return False
        handle = self.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            return bool(self.kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
                        and Path(path.value).name.upper() == 'POWERPNT.EXE')
        finally:
            self.kernel32.CloseHandle(handle)

    def targets(self) -> list[PowerPointTarget]:
        targets = []
        process_cache = {}

        @self.enum_type
        def callback(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            class_name = ctypes.create_unicode_buffer(256)
            self.user32.GetClassNameW(hwnd, class_name, len(class_name))
            if class_name.value not in ('screenClass', 'PPTFrameClass'):
                return True
            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in process_cache:
                process_cache[pid.value] = self._is_powerpoint(pid.value)
            if not process_cache[pid.value]:
                return True
            title = ctypes.create_unicode_buffer(max(1, self.user32.GetWindowTextLengthW(hwnd) + 1))
            self.user32.GetWindowTextW(hwnd, title, len(title))
            # Office 16 windowed shows can use PPTFrameClass too. This title
            # check is only applied AFTER validating the actual POWERPNT.EXE PID.
            caption = title.value.casefold()
            windowed_show = any(caption.startswith(prefix) for prefix in (
                'powerpoint 幻灯片放映', 'powerpoint 放映', 'powerpoint slide show', 'powerpoint slideshow'))
            targets.append(PowerPointTarget(str(int(hwnd)), title.value or 'Microsoft PowerPoint',
                                            int(hwnd), pid.value, class_name.value == 'screenClass' or windowed_show))
            return True
        self.user32.EnumWindows(callback, 0)
        return targets

    def is_window(self, hwnd: int) -> bool:
        return bool(self.user32.IsWindow(hwnd))

    def is_target_valid(self, target: PowerPointTarget) -> bool:
        if not self.is_window(target.hwnd):
            return False
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(target.hwnd, ctypes.byref(pid))
        return pid.value == target.process_id and self._is_powerpoint(pid.value)

    def post_key(self, hwnd: int, key: int) -> bool:
        # Only target this window. Never steal focus or inject a global key.
        if not self.is_window(hwnd):
            return False
        first = self.user32.PostMessageW(hwnd, 0x100, key, 1)
        second = self.user32.PostMessageW(hwnd, 0x101, key, 0xC0000001)
        return bool(first and second)


def active_powerpoint():
    import win32com.client
    return win32com.client.GetActiveObject('PowerPoint.Application')


def com_int(value) -> int:
    """Office late-bound HWND can be exposed as a zero-argument method."""
    return int(value() if callable(value) else value)


def com_matches_window(obj, target: PowerPointTarget) -> bool:
    """Use HWND when available, otherwise a unique document-name match.

    Office PowerPoint versions do not consistently expose HWND on automation
    objects. The caller MUST reject zero or multiple matches. Native discovery
    has already checked the window class and actual POWERPNT.EXE process.
    """
    try:
        return com_int(obj.HWND) == target.hwnd
    except Exception:
        try:
            presentation = obj.Presentation
            name = str(presentation.Name)
        except Exception:
            try:
                name = str(obj.Name)
            except Exception:
                return False
        stem = Path(name).stem.strip().casefold()
        title = target.title.casefold()
        if name and re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)', title):
            return True
        if re.search(r'\.(?:pptx|pptm|ppt|ppsx|ppsm|pps|potx|potm|pot)(?!\w)', title):
            return False
        return bool(stem and re.search(r'(?<!\w)' + re.escape(stem) + r'(?!\w)', title))


class PowerPointBridge:
    def __init__(self, backend: str = 'keys', windows=None, com_factory=active_powerpoint, clock=time.perf_counter):
        self.windows = windows if windows is not None else NativeWindows()
        self.backend, self.com_factory, self.clock = backend, com_factory, clock
        self.selected_id: str | None = None
        self.available: list[PowerPointTarget] = []
        self.pending_start: tuple[int, set[str], float] | None = None
        self.last_scan_at = -float('inf')
        self.refresh()

    def refresh(self) -> PowerPointStatus:
        self.available = self.windows.targets()
        if self.selected_id is None:
            slides = [target for target in self.available if target.slideshow]
            choices = slides if slides else self.available
            if len(choices) == 1:
                self.selected_id = choices[0].id
        if self.pending_start is not None:
            pid, existing_shows, requested = self.pending_start
            created = [item for item in self.available if item.slideshow and item.process_id == pid and item.id not in existing_shows]
            if len(created) == 1:
                self.selected_id = created[0].id
                self.pending_start = None
            elif self.clock() - requested > 5:
                self.pending_start = None
        self.last_scan_at = self.clock()
        return self.status()

    def select_target(self, target_id: str) -> PowerPointStatus:
        self.selected_id = target_id
        return self.refresh()

    def target(self) -> PowerPointTarget | None:
        return next((target for target in self.available if target.id == self.selected_id
                     and self.windows.is_window(target.hwnd)), None)

    def status(self) -> PowerPointStatus:
        target = self.target()
        return PowerPointStatus(bool(target and target.slideshow), target.title if target else 'Select an active presentation',
            any(not item.slideshow for item in self.available), target.id if target else '', list(self.available), self.backend,
            'Multiple targets: select one' if self.selected_id is None and len(self.available) > 1 else '')

    def refresh_if_needed(self, now: float, interval: float = 1.0) -> PowerPointStatus:
        if now - self.last_scan_at >= interval:
            return self.refresh()
        return self.status()

    def next_slide(self) -> OperationResult:
        return self.execute('next')

    def previous_slide(self) -> OperationResult:
        return self.execute('previous')

    def start_slideshow(self) -> OperationResult:
        return self.execute('start')

    def execute(self, action: str) -> OperationResult:
        target = self.target()
        target_id = target.id if target else ''
        if target is None or (action != 'start' and not target.slideshow):
            return OperationResult('failed', 'No selected active slideshow', action, target_id)
        if not getattr(self.windows, 'is_target_valid', lambda item: True)(target):
            return OperationResult('failed', 'Target identity changed; reconnect first', action, target_id)
        if action not in ('next', 'previous', 'start'):
            return OperationResult('failed', 'Unknown action', action, target_id)
        if action == 'start' and target.slideshow:
            return OperationResult('accepted', 'SELECTED SLIDESHOW IS ALREADY RUNNING', action, target.id)
        if action == 'start':
            self.pending_start = (target.process_id, {item.id for item in self.available if item.slideshow}, self.clock())
        if self.backend == 'com':
            if len({item.process_id for item in self.available}) > 1:
                return OperationResult('failed', 'Multiple PowerPoint processes: COM target cannot be proven unique', action, target.id)
            result = self._com_execute(target, action)
            if action == 'start' and result.state == 'failed':
                self.pending_start = None
            return result
        key = {'next': 0x27, 'previous': 0x25, 'start': 0x74}[action]
        sent = self.windows.post_key(target.hwnd, key)
        if action == 'start' and not sent:
            self.pending_start = None
        return OperationResult('sent' if sent else 'failed',
            'COMMAND SENT - EXECUTION NOT VERIFIED' if sent else 'WINDOW REJECTED COMMAND', action, target.id)

    def _com_execute(self, target: PowerPointTarget, action: str) -> OperationResult:
        invoked = False
        try:
            app = self.com_factory()
            if action == 'start':
                matches = []
                for index in range(1, int(app.Presentations.Count) + 1):
                    presentation = app.Presentations.Item(index)
                    if com_matches_window(presentation, target):
                        matches.append(presentation)
                if len(matches) != 1:
                    return OperationResult('failed', 'Select the document in PowerPoint and start it manually', action, target.id)
                invoked = True
                matches[0].SlideShowSettings.Run()
                return OperationResult('accepted', 'START REQUEST ACCEPTED', action, target.id)
            matches = [app.SlideShowWindows.Item(i) for i in range(1, int(app.SlideShowWindows.Count) + 1)
                       if com_matches_window(app.SlideShowWindows.Item(i), target)]
            if len(matches) != 1:
                return OperationResult('failed', 'Cannot uniquely match the selected slideshow; use distinct document names', action, target.id)
            show = matches[0]
            before = int(show.View.Slide.SlideIndex)
            invoked = True
            if action == 'next':
                show.View.Next()
            else:
                show.View.Previous()
            after = int(show.View.Slide.SlideIndex)
            return OperationResult('observed' if before != after else 'accepted',
                'SLIDE %d' % after if before != after else 'COMMAND ACCEPTED - ANIMATION OR BOUNDARY POSSIBLE', action, target.id)
        except Exception as error:
            # The action might already have happened. Never automatically send again.
            return OperationResult('unknown' if invoked else 'failed',
                                   ('RESULT UNKNOWN: ' if invoked else 'COM UNAVAILABLE: ') + str(error), action, target.id)

