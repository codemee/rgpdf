# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
"""Keep PyInstaller's Qt setup, but defer QtCore import until GUI ownership."""
def _install():
    import sys
    from _pyi_rth_utils import qt
    original = qt.create_embedded_qt_conf

    def defer(*args):
        sys._rgpdf_deferred_qt = (original, args)

    qt.create_embedded_qt_conf = defer


_install()
del _install
