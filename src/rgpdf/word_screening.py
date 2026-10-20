# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

"""Conservative Word candidate screening; PDF remains the result authority."""

from pathlib import Path
from threading import Event
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from rgpdf.models import SearchOptions
from rgpdf.word_conversion import ConversionCancelled


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
# Ordinary pictures, formatting, and numbering do not make all text unknown.
UNSUPPORTED = {W + tag for tag in (
    "fldChar", "fldSimple", "instrText", "object", "altChunk", "subDoc", "contentPart",
)}
NUMBER_MARKERS = {W + tag for tag in (
    "numPr", "footnoteReference", "endnoteReference", "footnoteRef", "endnoteRef",
)}
NUMBER_CHARACTERS = set("0123456789ivxlcdm一二三四五六七八九十百千萬億零〇壹貳參肆伍陸柒捌玖拾佰仟第章节章節")
REGEX_META = frozenset(r". ^ $ * + ? { } [ ] \ | ( )".split())


def literal_query(options: SearchOptions) -> str | None:
    # Regex mode with no operators still has exactly literal semantics.
    if options.use_regex and any(char in REGEX_META for char in options.pattern):
        return None
    return options.pattern


def _content_part(name: str) -> bool:
    return name == "word/document.xml" or (
        name.startswith("word/") and name.endswith(".xml") and (
            name[5:].startswith(("header", "footer", "footnotes", "endnotes"))
            or name.startswith(("word/charts/", "word/diagrams/"))
        )
    )


def _screening_text(value: str) -> str:
    # A broader normalization than official PDF matching is intentional. Include
    # Unicode compatibility forms and Turkish I variants in candidate screening.
    value = unicodedata.normalize("NFKD", value.casefold()).replace("ı", "i")
    return "".join(c for c in value if not c.isspace() and c != "-"
                   and not unicodedata.combining(c))


def word_may_match(path: Path, options: SearchOptions, cancel_event: Event | None = None) -> bool:
    """Find a normalized literal sequence; PDF alone produces official results.

    Screen display-text parts, never style definitions or individual character
    presence. Unsupported content and genuine regex patterns fall back to PDF.
    """
    if cancel_event and cancel_event.is_set():
        raise ConversionCancelled("Search was cancelled.")
    literal = literal_query(options)
    if literal is None or path.suffix.casefold() != ".docx":
        return True
    query = _screening_text(literal)
    if not query:
        return True
    numbered = False
    number_characters = set(NUMBER_CHARACTERS)
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if "word/document.xml" not in names:
                return True
            for name in names:
                if name == "word/numbering.xml":
                    with archive.open(name) as stream:
                        for _, element in ET.iterparse(stream, events=("end",)):
                            if cancel_event and cancel_event.is_set():
                                raise ConversionCancelled("Search was cancelled.")
                            if element.tag == W + "lvlText":
                                number_characters.update(_screening_text(element.get(W + "val", "")))
                            element.clear()
                    continue
                if not _content_part(name):
                    continue
                tail = ""
                with archive.open(name) as stream:
                    for _, element in ET.iterparse(stream, events=("end",)):
                        if cancel_event and cancel_event.is_set():
                            raise ConversionCancelled("Search was cancelled.")
                        if element.tag in UNSUPPORTED:
                            return True
                        if element.tag in NUMBER_MARKERS:
                            numbered = True
                        if element.tag == W + "sym":
                            # Symbol-font character codes are not reliably Unicode.
                            # They cannot supply a multi-character CJK phrase; other
                            # queries retain the conservative renderer fallback.
                            if not all("\u3400" <= c <= "\u9fff" for c in query):
                                return True
                        if element.tag in {W + "t", A + "t", M + "t"} or element.tag.endswith("}v"):
                            value = _screening_text(element.text or "")
                            combined = tail + value
                            if query in combined:
                                return True
                            tail = combined[-(len(query) - 1):] if len(query) > 1 else ""
                        elif element.tag.rsplit("}", 1)[-1] in {"t", "char"}:
                            # Math and extension text require renderer interpretation.
                            return True
                        element.clear()
        # Numbering can generate counters absent from w:t, but a page number or
        # bullet does not make an unrelated phrase a candidate.
        return numbered and set(query) <= number_characters
    except ConversionCancelled:
        raise
    except Exception:
        return True
