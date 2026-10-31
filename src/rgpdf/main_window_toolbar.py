# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QTabBar, QToolBar
from rgpdf.buttons import SettingsButton


class FolderTabBar(QTabBar):
    """Reserve the actual action-button height in QTabWidget style metrics."""

    def sizeHint(self):
        size = super().sizeHint()
        size.setHeight(max(size.height(), SettingsButton.BUTTON_SIZE + 2 * SettingsButton.PADDING))
        return size

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setHeight(max(size.height(), SettingsButton.BUTTON_SIZE + 2 * SettingsButton.PADDING))
        return size


class SettingsToolBar(QToolBar):
    """Keep control spacing and margins stable when Qt reapplies style metrics."""

    def event(self, event) -> bool:
        handled = super().event(event)
        if event.type() in (
            QEvent.Type.Polish,
            QEvent.Type.Show,
            QEvent.Type.StyleChange,
        ):
            layout = self.layout()
            if layout is not None:
                layout.setSpacing(SettingsButton.SPACING)
                padding = SettingsButton.PADDING
                layout.setContentsMargins(padding, padding, padding, padding)
        return handled
