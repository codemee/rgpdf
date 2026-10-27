import ctypes
from ctypes import wintypes
import sys

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from rgpdf.main_window import MainWindow


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native system menu")
def test_native_about_menu_and_language(qtbot, tmp_path, monkeypatch):
    if QApplication.platformName() != "windows":
        pytest.skip("Requires the native Windows Qt platform")
    from rgpdf.system_menu import ABOUT_COMMAND, WM_SYSCOMMAND

    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/language", "en")
    window = MainWindow(lambda _: None, settings=settings)
    qtbot.addWidget(window)
    window.show()
    api = window._system_menu.api
    api.GetMenuItemCount.argtypes = [wintypes.HMENU]
    api.GetMenuItemCount.restype = ctypes.c_int
    api.GetMenuStringW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.LPWSTR, ctypes.c_int, wintypes.UINT]
    api.GetMenuStringW.restype = ctypes.c_int
    api.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    api.SendMessageW.restype = ctypes.c_ssize_t
    menu = api.GetSystemMenu(int(window.winId()), False)

    def title():
        text = ctypes.create_unicode_buffer(128)
        assert api.GetMenuStringW(menu, ABOUT_COMMAND, text, len(text), 0)
        return text.value

    assert title() == "About rgPDF"
    count = api.GetMenuItemCount(menu)
    window.hide()
    window.show()
    assert api.GetMenuItemCount(menu) == count
    window.language_preference = "zh_TW"
    window.language = "zh_TW"
    window.retranslate_ui()
    assert title() == "關於 rgPDF"
    assert api.GetMenuItemCount(menu) == count
    calls = []
    monkeypatch.setattr("rgpdf.main_window.QMessageBox.about", lambda *args: calls.append(args))
    api.SendMessageW(int(window.winId()), WM_SYSCOMMAND, ABOUT_COMMAND, 0)
    qtbot.waitUntil(lambda: len(calls) == 1)
    assert calls[0][1] == "關於 rgPDF"
    # Standard Minimize remains handled by Qt/Windows.
    api.SendMessageW(int(window.winId()), WM_SYSCOMMAND, 0xF020, 0)
    qtbot.waitUntil(window.isMinimized)
