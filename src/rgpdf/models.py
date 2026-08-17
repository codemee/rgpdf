# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


RectTuple = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class SearchOptions:
    root: Path
    pattern: str
    use_regex: bool = False
    case_sensitive: bool = False
    recursive: bool = True
    regex_timeout_seconds: float = 1.0


@dataclass(frozen=True, slots=True)
class PageHighlight:
    page_index: int
    rectangles: tuple[RectTuple, ...]


@dataclass(frozen=True, slots=True)
class TextMatch:
    matched_text: str
    context: str
    start: int
    end: int
    start_page: int
    end_page: int
    highlights: tuple[PageHighlight, ...]


@dataclass(frozen=True, slots=True)
class DocumentMatch:
    path: Path
    relative_path: Path
    matches: tuple[TextMatch, ...]


@dataclass(frozen=True, slots=True)
class SearchWarning:
    path: Path
    message: str


@dataclass(slots=True)
class SearchReport:
    documents: list[DocumentMatch] = field(default_factory=list)
    warnings: list[SearchWarning] = field(default_factory=list)
    scanned_files: int = 0
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class CharacterRef:
    page_index: int
    rectangle: RectTuple | None


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    text: str
    character_refs: tuple[CharacterRef, ...]
    page_count: int
