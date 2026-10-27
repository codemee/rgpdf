# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Windows title-bar menu integration; native handles remain owned by Windows."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


ABOUT_COMMAND = 0x1000  # Custom system commands must be below 0xF000.
WM_SYSCOMMAND = 0x0112


class WindowsSystemMenu:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        signatures = {
            "GetSystemMenu": ([wintypes.HWND, wintypes.BOOL], wintypes.HMENU),
            "GetMenuState": ([wintypes.HMENU, wintypes.UINT, wintypes.UINT], wintypes.UINT),
            "InsertMenuW": ([wintypes.HMENU, wintypes.UINT, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR], wintypes.BOOL),
            "ModifyMenuW": ([wintypes.HMENU, wintypes.UINT, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

    def update(self, window_id: int, title: str) -> None:
        menu = self.api.GetSystemMenu(window_id, False)
        if not menu:
            return
        if self.api.GetMenuState(menu, ABOUT_COMMAND, 0) == 0xFFFFFFFF:
            if self.api.InsertMenuW(menu, 0xF060, 0, ABOUT_COMMAND, title):
                self.api.InsertMenuW(menu, 0xF060, 0x800, 0, None)
        else:
            self.api.ModifyMenuW(menu, ABOUT_COMMAND, 0, ABOUT_COMMAND, title)

    @staticmethod
    def is_about_message(message) -> bool:
        native = wintypes.MSG.from_address(int(message))
        return native.message == WM_SYSCOMMAND and native.wParam & 0xFFF0 == ABOUT_COMMAND
