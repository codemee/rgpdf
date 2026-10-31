# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Early DOCX text results; never supplies PDF page numbers or coordinates."""

from xml.etree import ElementTree as ET
from zipfile import ZipFile

from rgpdf.models import PreliminaryDocument, PreliminaryMatch
from rgpdf.word_screening import W, A, M, _content_part
from rgpdf.word_conversion import ConversionCancelled


def preliminary_document(path, options, cancel_event=None):
    from rgpdf.search import compile_pattern

    matches = []
    if path.suffix.casefold() == ".docx":
        try:
            paragraphs = []
            with ZipFile(path) as archive:
                for name in sorted(archive.namelist(), key=lambda n: (n != "word/document.xml", n)):
                    if not _content_part(name):
                        continue
                    stack = []
                    with archive.open(name) as stream:
                        for event, element in ET.iterparse(stream, events=("start", "end")):
                            if cancel_event is not None and cancel_event.is_set():
                                raise ConversionCancelled()
                            if event == "start":
                                if element.tag in {W + "p", A + "p"}:
                                    stack.append([])
                                continue
                            if stack:
                                if element.tag in {W + "t", A + "t", M + "t"} or element.tag.endswith("}v"):
                                    stack[-1].append(element.text or "")
                                elif element.tag == W + "tab":
                                    stack[-1].append("\t")
                                elif element.tag in {W + "br", W + "cr"}:
                                    stack[-1].append("" if options.ignore_line_wraps else "\n")
                                elif element.tag in {W + "p", A + "p"}:
                                    value = "".join(stack.pop())
                                    if value.strip():
                                        paragraphs.append(value)
                            element.clear()
            text = "\n\n".join(paragraphs)
            compiled = compile_pattern(options)
            for match in compiled.finditer(text, timeout=options.regex_timeout_seconds):
                if match.end() == match.start():
                    continue
                boundary = text.rfind("\n\n", 0, match.start())
                start = max(boundary + 2 if boundary >= 0 else 0, match.start() - 120)
                end = text.find("\n\n", match.end())
                end = min(end if end >= 0 else len(text), match.end() + 120)
                matches.append(PreliminaryMatch(match.group(), text[start:end].strip(), match.start(), match.end()))
        except ConversionCancelled:
            raise
        except Exception:
            # Unreadable/unsupported text is still verified through the PDF.
            matches = []
    return PreliminaryDocument(path, path.relative_to(options.root), tuple(matches))
