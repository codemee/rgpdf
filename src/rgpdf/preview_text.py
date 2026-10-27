# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Immutable page text geometry and mouse selection over the rendered page."""

from dataclasses import dataclass
import sys

import pymupdf as fitz
from PySide6.QtCore import QPointF, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QMenu

from rgpdf.i18n import translate
from rgpdf.models import RectTuple


@dataclass(frozen=True)
class PageGlyph:
    start: int
    end: int
    rectangle: RectTuple


@dataclass(frozen=True)
class PageLine:
    start: int
    end: int
    rectangle: RectTuple
    direction: tuple[float, float]


@dataclass(frozen=True)
class PageText:
    text: str
    glyphs: tuple[PageGlyph, ...]
    lines: tuple[PageLine, ...]


def extract_page_text(page: fitz.Page) -> PageText:
    raw = page.get_text("rawdict", flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES, sort=True)
    rotation = page.rotation_matrix
    parts, glyphs, lines = [], [], []
    offset = 0
    previous_block = None
    for block_index, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            chars = [char for span in line.get("spans", []) for char in span.get("chars", [])
                     if char.get("c")]
            if not any(not char["c"].isspace() for char in chars):
                continue
            if parts:
                separator = "\n" if previous_block == block_index else "\n\n"
                parts.append(separator)
                offset += len(separator)
            start = len(glyphs)
            for char in chars:
                value = char["c"]
                box = fitz.Rect(char["bbox"]) * rotation
                glyphs.append(PageGlyph(offset, offset + len(value), tuple(box)))
                parts.append(value)
                offset += len(value)
            first, last = glyphs[start].rectangle, glyphs[-1].rectangle
            dx, dy = last[0] + last[2] - first[0] - first[2], last[1] + last[3] - first[1] - first[3]
            if abs(dx) + abs(dy) < 0.001:
                origin = fitz.Point(0, 0) * rotation
                vector = fitz.Point(line.get("dir", (1, 0))) * rotation - origin
                dx, dy = vector.x, vector.y
            lines.append(PageLine(start, len(glyphs), tuple(fitz.Rect(line["bbox"]) * rotation), (dx, dy)))
            previous_block = block_index
    return PageText("".join(parts), tuple(glyphs), tuple(lines))


def _distance(box: RectTuple, point: QPointF) -> float:
    dx = max(box[0] - point.x(), 0, point.x() - box[2])
    dy = max(box[1] - point.y(), 0, point.y() - box[3])
    return dx * dx + dy * dy


class SelectablePageLabel(QLabel):
    selection_dragged = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._page_text: PageText | None = None
        self._zoom = 1.0
        self._anchor: int | None = None
        self._focus: int | None = None
        self._dragging = False
        self._selection_mode = True
        self._language = "en"
        self._pending_copy: str | None = None
        self._copy_attempts = 0
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._write_clipboard)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_language(self, language: str) -> None:
        self._language = language

    def has_text(self) -> bool:
        return self._page_text is not None and bool(self._page_text.glyphs)

    def set_page_text(self, text: PageText | None, zoom: float = 1.0) -> None:
        self._page_text, self._zoom = text, zoom
        self.clear_selection(cancel_copy=False)
        self._update_cursor()

    def set_selection_mode(self, enabled: bool) -> None:
        self._selection_mode = enabled
        if not enabled:
            self.clear_selection()
        self._update_cursor()

    def _update_cursor(self) -> None:
        self.setCursor(Qt.CursorShape.IBeamCursor if self._selection_mode and self.has_text()
                       else Qt.CursorShape.ArrowCursor)

    def clear_selection(self, *, cancel_copy: bool = True) -> None:
        if cancel_copy:
            self._copy_timer.stop()
            self._pending_copy = None
        self._anchor = self._focus = None
        self._dragging = False
        self.update()

    def clear(self) -> None:
        self.clear_selection()
        self.set_page_text(None)
        super().clear()

    def selected_text(self) -> str:
        if self._page_text is None or self._anchor is None or self._focus is None:
            return ""
        start, end = sorted((self._anchor, self._focus))
        return self._page_text.text[start:end]

    def copy_selected(self) -> None:
        text = self.selected_text()
        if text:
            self._copy_timer.stop()
            self._pending_copy, self._copy_attempts = text, 0
            self._write_clipboard()

    def _write_clipboard(self) -> None:
        if self._pending_copy is None:
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self._pending_copy)
        self._copy_attempts += 1
        success = clipboard.text() == self._pending_copy
        if sys.platform == "win32":
            success = success and clipboard.ownsClipboard()
        if not success and self._copy_attempts < 10:
            self._copy_timer.start(100)
        else:
            self._pending_copy = None

    def select_all(self) -> None:
        if self._selection_mode and self.has_text():
            self._anchor, self._focus = 0, len(self._page_text.text)
            self.update()
            self.copy_selected()

    def _image_origin(self) -> QPointF:
        pixmap = self.pixmap()
        if pixmap.isNull():
            return QPointF()
        size = pixmap.deviceIndependentSize()
        area = self.contentsRect()
        return QPointF(area.left() + (area.width() - size.width()) / 2,
                       area.top() + (area.height() - size.height()) / 2)

    def _hit_test(self, position: QPointF) -> int:
        point = (position - self._image_origin()) / self._zoom
        data = self._page_text
        line = min(data.lines, key=lambda item: _distance(item.rectangle, point))
        glyph = min(data.glyphs[line.start:line.end], key=lambda item: _distance(item.rectangle, point))
        box = glyph.rectangle
        forward = ((point.x() - (box[0] + box[2]) / 2) * line.direction[0]
                   + (point.y() - (box[1] + box[3]) / 2) * line.direction[1]) >= 0
        return glyph.end if forward else glyph.start

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._selection_mode and self.has_text():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.clear_selection()
            self._anchor = self._focus = self._hit_test(event.position())
            self._dragging = True
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging and self.has_text():
            self._focus = self._hit_test(event.position())
            self.update()
            self.selection_dragged.emit(round(event.position().x()), round(event.position().y()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging and self.has_text():
            self._focus = self._hit_test(event.position())
            self._dragging = False
            self.update()
            self.copy_selected()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._selection_mode and event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
            event.accept()
        elif self._selection_mode and event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        if not self._selection_mode or not self.has_text():
            return
        menu = QMenu(self)
        copy = menu.addAction(translate(self._language, "copy_selection"), self.copy_selected)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setEnabled(bool(self.selected_text()))
        select_all = menu.addAction(translate(self._language, "select_all_page"), self.select_all)
        select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self.selected_text():
            return
        start, end = sorted((self._anchor, self._focus))
        origin = self._image_origin()
        painter = QPainter(self)
        color = QColor(self.palette().color(QPalette.ColorRole.Highlight))
        color.setAlpha(95)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for glyph in self._page_text.glyphs:
            if glyph.end > start and glyph.start < end:
                x0, y0, x1, y1 = glyph.rectangle
                painter.drawRect(QRectF(origin.x() + x0 * self._zoom, origin.y() + y0 * self._zoom,
                                       (x1 - x0) * self._zoom, (y1 - y0) * self._zoom))
        painter.end()
