# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Progress labels with separate text colors over the track and filled area."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QProgressBar, QStyle, QStyleOptionProgressBar


class SearchProgressBar(QProgressBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTextVisible(False)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        label = self.text()
        if not label or self.maximum() <= self.minimum():
            return
        option = QStyleOptionProgressBar()
        self.initStyleOption(option)
        area = QRectF(self.style().subElementRect(QStyle.SubElement.SE_ProgressBarContents, option, self))
        fraction = max(0.0, min(1.0, (self.value() - self.minimum()) / (self.maximum() - self.minimum())))
        filled = QRectF(area)
        filled.setWidth(area.width() * fraction)
        if self.invertedAppearance() != (self.layoutDirection() == Qt.LayoutDirection.RightToLeft):
            filled.moveRight(area.right())
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(area, Qt.AlignmentFlag.AlignCenter, label)
        painter.setClipRect(filled)
        painter.setPen(self.palette().color(QPalette.ColorRole.HighlightedText))
        painter.drawText(area, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
