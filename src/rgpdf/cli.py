# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Argument parsing without importing Qt, PDF libraries or filesystem scans."""
import argparse


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(prog="rgpdf", description="Search PDF and Word documents with rgPDF.")
    integration = parser.add_mutually_exclusive_group()
    integration.add_argument("--install-context-menu", action="store_true", help="Install the per-user Explorer/Finder context menu")
    integration.add_argument("--remove-context-menu", action="store_true", help="Remove the per-user Explorer/Finder context menu")
    parser.add_argument("--new-window", action="store_true", help="Open an independent window instead of reusing the running app")
    parser.add_argument("paths", nargs="*", help="Folders to open (files use their parent folder)")
    return parser.parse_args(argv)
