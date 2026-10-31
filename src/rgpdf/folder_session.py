# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Per-folder settings, with application appearance shared across tabs."""

from dataclasses import dataclass, field


TAB_DEFAULTS = {
    "search/folder": "", "search/pattern": "", "search/stem_glob": "",
    "search/scope": "pdf", "search/use_regex": True,
    "search/case_sensitive": False, "search/recursive": True,
    "search/ignore_line_wraps": False, "export/folder": "",
    "window/main_splitter": None, "window/result_splitter": None,
}


@dataclass
class FolderTabState:
    values: dict = field(default_factory=dict)


class FolderSettings:
    def __init__(self, root, state=None):
        self.root = root
        self.state = state or FolderTabState({
            key: root.value(key, default) for key, default in TAB_DEFAULTS.items()
        })

    def value(self, key, default=None, type=None):
        value = self.state.values.get(key, default) if key in TAB_DEFAULTS else self.root.value(key, default)
        if value is None:
            return default
        if type is bool and isinstance(value, str):
            return value.lower() in {"true", "1"}
        return type(value) if type is not None else value

    def setValue(self, key, value):
        if key in TAB_DEFAULTS:
            self.state.values[key] = value
        # Keep legacy last-used defaults for upgrades and new empty sessions.
        self.root.setValue(key, value)

    def sync(self):
        self.root.sync()
