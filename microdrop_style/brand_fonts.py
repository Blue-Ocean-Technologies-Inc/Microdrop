# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots brand typefaces: Orbitron for headings, Lato for body text.

Every font file under ``fonts/`` is registered with Qt once, on first use;
``heading_family()`` and ``body_family()`` then name the brand family when
it is available (registered here, or installed on the system) and the
application's own font otherwise. Dropping the font files into ``fonts/``
switches to them with no code change.
"""

# Standard library imports.
from pathlib import Path

# Microdrop utils imports.
from microdrop_utils.font_helpers import load_font_family

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The brand families: headings, and body text.
HEADING_FONT_FAMILY = "Orbitron"
BODY_FONT_FAMILY = "Lato"

#: Where the shipped font files are.
FONTS_DIR = Path(__file__).parent / "fonts"

#: Font file suffixes registered.
FONT_SUFFIXES = (".ttf", ".otf")

#: Families registered from each folder, once per folder.
_registered = {}


def register_brand_fonts(directory=FONTS_DIR):
    """Register every font file under ``directory`` with Qt, once; return
    the families they hold. Needs a QGuiApplication."""
    directory = Path(directory)

    if directory in _registered:
        return _registered[directory]

    families = set()

    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() in FONT_SUFFIXES:
            family = load_font_family(path)

            if family:
                families.add(family)

    _registered[directory] = families

    brand = (HEADING_FONT_FAMILY, BODY_FONT_FAMILY)
    found = [name for name in brand if _is_available(name)]

    logger.info(
        f"Brand fonts available: {', '.join(found) or 'none'}"
        f" (registered from {directory.name}/: {', '.join(sorted(families)) or 'none'})"
    )

    return families


def heading_family():
    """Orbitron if available, else the application font's family."""
    return _family_or_default(HEADING_FONT_FAMILY)


def body_family():
    """Lato if available, else the application font's family."""
    return _family_or_default(BODY_FONT_FAMILY)


def _family_or_default(family):
    from pyface.qt import QtGui

    register_brand_fonts()

    if _is_available(family):
        return family

    return QtGui.QGuiApplication.font().family()


def _is_available(family):
    from pyface.qt import QtGui

    return family in QtGui.QFontDatabase.families()
