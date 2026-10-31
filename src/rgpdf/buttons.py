# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QToolButton

from rgpdf.resources import pdf_logo


class SettingsButton(QToolButton):
    """Shared icon-only button with a palette-aware vector glyph."""

    ICON_SIZE = 20
    BUTTON_SIZE = 34
    PADDING = 4
    SPACING = 4
    STROKE_WIDTH = 1.0
    CORNER_RADIUS = 8.0
    DOCUMENT_ICON_SIZE = 16
    COMBINED_DOCUMENT_ICON_SIZE = 14

    def __init__(self, kind: str = "", *, checkable: bool = False) -> None:
        super().__init__()
        self.icon_kind = kind
        self.icon_foreground: QColor | None = None
        self.setCheckable(checkable)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)
        self.setContentsMargins(self.PADDING, self.PADDING, self.PADDING, self.PADDING)

    def set_icon_kind(self, kind: str) -> None:
        self.icon_kind = kind
        self.update()

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt API
        super().setToolTip(text)
        self.setAccessibleName(text)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        color = self.icon_foreground or self.palette().color(
            QPalette.ColorRole.PlaceholderText
        )
        if (self.icon_foreground is None and self.isChecked()
                and dark):
            color = self.palette().color(QPalette.ColorRole.Highlight)
        if not self.isEnabled():
            color = self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText)
        painter.setPen(QPen(color, self.STROKE_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = QPointF(self.width() / 2, self.height() / 2)
        # Center asymmetric glyphs by their visible bounds, not their path origin.
        vertical_offset = {
            "cache": 1.5,
            "moon": 1.0,
        }.get(self.icon_kind, 0.0)
        painter.translate(0, vertical_offset)

        if self.icon_kind in {"previous_page", "next_page"}:
            direction = -1 if self.icon_kind == "previous_page" else 1
            painter.translate(center)
            painter.drawPolyline([QPointF(-3 * direction, -6), QPointF(3 * direction, 0), QPointF(-3 * direction, 6)])
        elif self.icon_kind in {"zoom_in", "zoom_out", "search"}:
            painter.translate(center)
            painter.drawEllipse(QPointF(-2, -2), 5.5, 5.5)
            painter.drawLine(QLineF(2, 2, 8, 8))
            if self.icon_kind != "search":
                painter.drawLine(QLineF(-5, -2, 1, -2))
                if self.icon_kind == "zoom_in":
                    painter.drawLine(QLineF(-2, -5, -2, 1))
        elif self.icon_kind == "line_wrap":
            painter.translate(center)
            painter.drawLine(-8, -6, 8, -6)
            painter.drawLine(-8, -1, 3, -1)
            wrap = QPainterPath()
            wrap.moveTo(5, -1)
            wrap.lineTo(6, -1)
            wrap.cubicTo(10, -1, 10, 6, 6, 6)
            wrap.lineTo(-2, 6)
            painter.drawPath(wrap)
            painter.drawPolyline([QPointF(1, 3), QPointF(-2, 6), QPointF(1, 9)])
            painter.drawLine(-8, 6, -5, 6)
        elif self.icon_kind == "export_pdf":
            painter.translate(center)
            painter.save()
            if not self.isEnabled():
                painter.setOpacity(0.45)
            size = self.COMBINED_DOCUMENT_ICON_SIZE
            word_rect = QRectF(-12, -12, size, size)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2b579a"))
            painter.drawRoundedRect(word_rect, 1.5, 1.5)
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(9)
            painter.setFont(font)
            painter.drawText(word_rect, Qt.AlignmentFlag.AlignCenter, "W")
            pdf_logo().render(painter, QRectF(-2, -2, size, size))
            painter.restore()
            # Match scope_all's overlapping 14 px marks, reversing the order.
            # Route down from Word, then turn right into PDF's left edge through
            # the free lower-left corner without obscuring either logo.
            painter.drawPolyline([QPointF(-7.5, 2.5), QPointF(-7.5, 6.5), QPointF(-2.5, 6.5)])
            painter.drawPolyline([QPointF(-5, 4), QPointF(-2.5, 6.5), QPointF(-5, 9)])
        elif self.icon_kind == "copy_page":
            painter.translate(center)
            painter.drawPolyline([QPointF(-7, 4), QPointF(-9, 4), QPointF(-9, -9), QPointF(3, -9), QPointF(3, -7)])
            painter.drawRect(QRectF(-5, -5, 13, 14))
            painter.drawEllipse(QPointF(4, -1), 1.5, 1.5)
            painter.drawPolyline([QPointF(-5, 6), QPointF(-1, 1), QPointF(3, 6), QPointF(5, 4), QPointF(8, 7)])
        elif self.icon_kind == "select_text":
            painter.translate(center)
            painter.drawLine(-8, -7, 6, -7)
            painter.drawLine(-8, -4, 3, -4)
            painter.drawLine(-8, -1, -2, -1)
            painter.drawLine(-8, 2, -2, 2)
            painter.drawLine(3, -1, 3, 8)
            painter.drawLine(0, -1, 6, -1)
            painter.drawLine(0, 8, 6, 8)
        elif self.icon_kind == "close_tab":
            painter.translate(center)
            painter.drawLine(-3, -3, 3, 3)
            painter.drawLine(-3, 3, 3, -3)
        elif self.icon_kind == "cancel":
            painter.translate(center)
            painter.drawLine(-6, -6, 6, 6)
            painter.drawLine(-6, 6, 6, -6)
        elif self.icon_kind in {"browse", "add_folder"}:
            painter.translate(center)
            folder = QPainterPath()
            folder.moveTo(-8, 6)
            folder.lineTo(-8, -6)
            folder.lineTo(-2, -6)
            folder.lineTo(0, -3)
            folder.lineTo(8, -3)
            folder.lineTo(8, 6)
            folder.closeSubpath()
            painter.drawPath(folder)
            painter.drawLine(-8, -1, 8, -1)
            if self.icon_kind == "add_folder":
                painter.drawLine(0, 0, 0, 5)
                painter.drawLine(-2, 2, 2, 2)
        elif self.icon_kind in {"fit_width", "fit_page"}:
            painter.translate(center)
            if self.icon_kind == "fit_width":
                painter.drawLine(-9, -7, -9, 7)
                painter.drawLine(9, -7, 9, 7)
                painter.drawLine(-6, 0, 6, 0)
                for direction in (-1, 1):
                    painter.drawPolyline([QPointF(3 * direction, -3), QPointF(6 * direction, 0), QPointF(3 * direction, 3)])
            else:
                painter.drawRect(QRectF(-4, -6, 8, 12))
                for x, y in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    painter.drawPolyline([QPointF(x * 5, y * 9), QPointF(x * 8, y * 9), QPointF(x * 8, y * 6)])
        elif self.icon_kind == "custom_color":
            painter.translate(center)
            painter.drawEllipse(QPointF(0, 0), 8, 8)
            for x, y, shade in ((-3, -3, "#d93025"), (3, -3, "#2b579a"), (-3, 3, "#228b45"), (3, 3, "#e8bd62")):
                painter.setBrush(QColor(shade))
                painter.drawEllipse(QPointF(x, y), 1.7, 1.7)
        elif self.icon_kind == "help":
            # Align the ring's outer edges to device pixels. A centered 1 px
            # ellipse stroke otherwise spreads across two pixels at its axes.
            # deviceTransform also accounts for redirected high-DPI exports.
            transform = painter.deviceTransform()
            inverse, _ = transform.inverted()
            first = transform.map(center - QPointF(8, 8))
            last = transform.map(center + QPointF(8, 8))
            outer = inverse.mapRect(QRectF(
                round(first.x()), round(first.y()),
                round(last.x()) - round(first.x()),
                round(last.y()) - round(first.y()),
            ))
            ring = QPainterPath()
            ring.setFillRule(Qt.FillRule.OddEvenFill)
            ring.addEllipse(outer)
            ring.addEllipse(outer.adjusted(self.STROKE_WIDTH, self.STROKE_WIDTH,
                                           -self.STROKE_WIDTH, -self.STROKE_WIDTH))
            painter.fillPath(ring, color)
            painter.translate(center)
            question = QPainterPath()
            question.moveTo(-2.5, -3)
            question.cubicTo(-2.5, -7, 5, -6, 2, -1)
            question.lineTo(0, 1)
            painter.drawPath(question)
            painter.drawPoint(QPointF(0, 4.5))
        elif self.icon_kind == "check":
            painter.translate(center)
            painter.drawPolyline([QPointF(-5, 0), QPointF(-1, 4), QPointF(6, -4)])
        elif self.icon_kind == "language_system":
            painter.drawEllipse(center, 7, 7)
            painter.drawEllipse(QRectF(center.x() - 3.5, center.y() - 7, 7, 14))
            painter.drawLine(QLineF(center.x() - 6, center.y() - 2.5, center.x() + 6, center.y() - 2.5))
            painter.drawLine(QLineF(center.x() - 6, center.y() + 2.5, center.x() + 6, center.y() + 2.5))
        elif self.icon_kind == "theme_system":
            painter.setBrush(color)
            painter.drawPie(QRectF(center.x() - 7, center.y() - 7, 14, 14), 90 * 16, 180 * 16)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, 7, 7)
        elif self.icon_kind == "sun":
            painter.drawEllipse(center, 3.5, 3.5)
            for dx, dy in ((0, -7), (5, -5), (7, 0), (5, 5), (0, 7), (-5, 5), (-7, 0), (-5, -5)):
                painter.drawLine(
                    QLineF(
                        center.x() + dx * 0.7,
                        center.y() + dy * 0.7,
                        center.x() + dx,
                        center.y() + dy,
                    )
                )
        elif self.icon_kind == "moon":
            painter.save()
            painter.translate(center)
            painter.rotate(-45)
            moon = QPainterPath()
            moon.moveTo(3, -7)
            moon.cubicTo(
                -7,
                -5,
                -7,
                5,
                3,
                7,
            )
            moon.cubicTo(
                -1,
                3.5,
                -1,
                -3.5,
                3,
                -7,
            )
            painter.drawPath(moon)
            painter.restore()
        elif self.icon_kind == "recursive":
            parent = QPainterPath()
            parent.moveTo(center.x() - 10, center.y() - 8)
            parent.lineTo(center.x() - 5, center.y() - 8)
            parent.lineTo(center.x() - 3, center.y() - 6)
            parent.lineTo(center.x() + 4, center.y() - 6)
            parent.lineTo(center.x() + 4, center.y() + 2)
            parent.lineTo(center.x() - 10, center.y() + 2)
            parent.closeSubpath()
            child = parent.translated(6, 6)
            # Knock out the rear outline beneath the front folder without
            # adding a fill that would mismatch hover/theme backgrounds.
            outside = QPainterPath()
            outside.addRect(QRectF(self.rect()))
            painter.save()
            painter.setClipPath(outside.subtracted(child))
            painter.drawPath(parent)
            painter.restore()
            painter.drawPath(child)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif self.icon_kind == "highlighter":
            painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), self.STROKE_WIDTH))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(center.x() - 8, center.y() - 8, 16, 16), 2, 2)
        elif self.icon_kind == "cache":
            painter.drawRoundedRect(QRectF(center.x() - 6, center.y() - 5, 12, 11), 1, 1)
            painter.drawLine(QLineF(center.x() - 8, center.y() - 7, center.x() + 8, center.y() - 7))
            painter.drawLine(QLineF(center.x() - 3, center.y() - 9, center.x() + 3, center.y() - 9))
            painter.drawLine(QLineF(center.x() - 2, center.y() - 2, center.x() - 2, center.y() + 3))
            painter.drawLine(QLineF(center.x() + 2, center.y() - 2, center.x() + 2, center.y() + 3))
        elif self.icon_kind == "scope_pdf":
            painter.save()
            if not self.isEnabled():
                painter.setOpacity(0.45)
            size = self.DOCUMENT_ICON_SIZE
            pdf_logo().render(painter, QRectF(center.x() - size / 2, center.y() - size / 2, size, size))
            painter.restore()
        elif self.icon_kind == "scope_word":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2b579a"))
            size = self.DOCUMENT_ICON_SIZE
            painter.drawRoundedRect(QRectF(center.x() - size / 2, center.y() - size / 2, size, size), 2, 2)
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(11)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "W")
        elif self.icon_kind == "scope_all":
            painter.save()
            if not self.isEnabled():
                painter.setOpacity(0.45)
            size = self.COMBINED_DOCUMENT_ICON_SIZE
            pdf_logo().render(painter, QRectF(center.x() - 12, center.y() - 12, size, size))
            painter.restore()
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2b579a"))
            word_rect = QRectF(center.x() - 2, center.y() - 2, size, size)
            painter.drawRoundedRect(word_rect, 1.5, 1.5)
            painter.setPen(QColor("white"))
            font.setPixelSize(9)
            painter.setFont(font)
            painter.drawText(
                word_rect,
                Qt.AlignmentFlag.AlignCenter,
                "W",
            )
        else:
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(13 if self.icon_kind == "case" else 14)
            painter.setFont(font)
            labels = {
                "language_zh": "中",
                "language_en": "A",
                "case": "Aa",
                "regex": ".*",
                "about": "i",
            }
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, labels.get(self.icon_kind, ""))
        painter.end()
