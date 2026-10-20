# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Join likely physical line wraps while retaining exact character locations."""

from dataclasses import dataclass

import pymupdf as fitz

from rgpdf.models import CharacterRef, ExtractedDocument


@dataclass
class _Line:
    text: str
    refs: list[CharacterRef]
    block: int
    box: fitz.Rect
    direction: tuple[float, float]
    cell: tuple[int, int] | None
    edge_space: tuple[bool, bool]


def _cjk(char: str) -> bool:
    return any(start <= ord(char) <= end for start, end in (
        (0x2E80, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
        (0x20000, 0x323AF),
    ))


def _lines(page: fitz.Page) -> list[_Line]:
    flags = fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES
    raw = page.get_text("rawdict", flags=flags, sort=True)
    try:
        paths = page.get_drawings()
        # Text-only and image-only pages have no ruled grid. Avoid the much
        # more expensive table analysis there; geometry still guards columns.
        cells = [(table_index, cell_index, fitz.Rect(box))
                 for table_index, table in enumerate(page.find_tables(paths=paths).tables)
                 for cell_index, box in enumerate(table.cells) if box is not None] if paths else []
        table_detection_ok = True
    except Exception:
        cells = []
        table_detection_ok = False
    lines = []
    for block_index, block in enumerate(raw["blocks"]):
        if block.get("type") != 0:
            continue
        for raw_line in block.get("lines", []):
            chars = [char for span in raw_line.get("spans", []) for char in span.get("chars", [])
                     if char.get("c")]
            if not chars:
                continue
            text, refs = [], []
            pending_space = False
            for char in chars:
                value = char["c"]
                if value.isspace():
                    pending_space = bool(text)
                    continue
                if pending_space:
                    text.append(" ")
                    refs.append(CharacterRef(page.number, None))
                    pending_space = False
                text.extend(value)
                refs.extend(CharacterRef(page.number, tuple(char["bbox"])) for _ in value)
            if not text:
                continue
            box = fitz.Rect(raw_line["bbox"])
            middle = (box.tl + box.br) / 2
            cell = next(((t, c) for t, c, rect in cells if middle in rect), None)
            # Failed table detection disables joins rather than guessing across cells.
            if not table_detection_ok:
                cell = (-1, len(lines))
            lines.append(_Line("".join(text), refs, block_index, box,
                               tuple(raw_line.get("dir", (1, 0))), cell,
                               (chars[0]["c"].isspace(), chars[-1]["c"].isspace())))
    return lines


def _wrap(previous: _Line, following: _Line) -> bool:
    if previous.block != following.block or previous.cell != following.cell:
        return False
    if previous.direction != (1, 0) or following.direction != (1, 0):
        return False
    height = max(previous.box.height, following.box.height)
    advance = following.box.y0 - previous.box.y0
    return (
        height > 0 and 0.5 * height <= advance <= 1.8 * height
        and abs(previous.box.x0 - following.box.x0) <= 2.2 * height
        and min(previous.box.x1, following.box.x1) > max(previous.box.x0, following.box.x0)
    )


def extract_layout_document(document: fitz.Document) -> ExtractedDocument:
    text: list[str] = []
    refs: list[CharacterRef] = []
    previous: _Line | None = None
    for page in document:
        for line in _lines(page):
            if previous is not None:
                same_page = previous.refs[-1].page_index == page.number
                soft_wrap = same_page and _wrap(previous, line)
                separator = "\n\n" if same_page else " "
                if soft_wrap:
                    left, right = previous.text[-1], line.text[0]
                    separator = " "
                    if not previous.edge_space[1] and not line.edge_space[0]:
                        if (left == "-" and len(previous.text) > 1
                                and previous.text[-2].isascii() and previous.text[-2].isalpha()
                                and right.isascii() and right.isalpha()):
                            text.pop()
                            refs.pop()
                            separator = ""
                        elif _cjk(left) or _cjk(right):
                            separator = ""
                text.extend(separator)
                refs.extend(CharacterRef(page.number, None) for _ in separator)
            text.extend(line.text)
            refs.extend(line.refs)
            previous = line
    result = "".join(text)
    assert len(result) == len(refs)
    return ExtractedDocument(result, tuple(refs), document.page_count)
