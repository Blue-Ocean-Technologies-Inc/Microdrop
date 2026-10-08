# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Register font files with Qt's font database."""

# Standard library imports.
from pathlib import Path


def load_font_family(font_path):
    """Register ``font_path`` with Qt; return its first family, or None."""
    # Qt is imported here, not at module level, so importing the font
    # registry does not load Qt for tools that never draw (tutorial --check).
    from pyface.qt.QtGui import QFontDatabase

    if not Path(font_path).exists():
        return None

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    families = QFontDatabase.applicationFontFamilies(font_id)

    return families[0] if families else None
