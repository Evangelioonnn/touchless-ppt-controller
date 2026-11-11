"""Small Windows helpers that load before any ML imports."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


class SingleInstance:
    def __init__(self):
        self.handle = None
        self.already_running = False
        if os.name != 'nt':
            raise RuntimeError('This application requires Windows.')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\TouchlessPPTController_YOLO26')
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.already_running = ctypes.get_last_error() == 183

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def activate_existing():
    if os.name != 'nt':
        return
    user32 = ctypes.WinDLL('user32')
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    for title in ('Touchless PPT Controller', 'Touchless PowerPoint Controller'):
        hwnd = user32.FindWindowW(None, title)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)


def error_dialog(message: str):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, message, 'Touchless PPT Controller', 0x10)
