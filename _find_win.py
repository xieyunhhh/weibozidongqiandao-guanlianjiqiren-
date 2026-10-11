# -*- coding: utf-8 -*-
"""枚举微信相关窗口，看主窗口是否可见。"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

results = []

def cb(hwnd, lparam):
    if not user32.IsWindowVisible(hwnd):
        return True
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return True
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    results.append((hwnd, pid.value, title))
    return True

user32.EnumWindows(EnumWindowsProc(cb), 0)

for hwnd, pid, title in results:
    if title:
        print(f"hwnd={hwnd} pid={pid} title={title!r}")
