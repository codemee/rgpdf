# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget


class BusyIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)

    def _tick(self):
        self.angle = (self.angle + 18) % 360
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 2,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(6, 6, 28, 28), -self.angle * 16, 250 * 16)
