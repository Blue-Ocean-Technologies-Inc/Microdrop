# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Logo pictures shipped with the style package, by name."""

# Standard library imports.
from pathlib import Path

#: Where the logo pictures are.
ICONS_DIR = Path(__file__).parent

#: Blue Ocean Technologies and Sci-Bots side by side: a wide lockup (about
#: 1.8:1) of two overlapping rings with white-filled discs, on transparency.
BLUE_OCEAN_SCI_BOTS_LOGO = ICONS_DIR / "Blue_Ocean_Sci_Bots_Logo.png"

#: MicroDrop's mark alone: the dark grey mu, square, on transparency.
MICRODROP_MARK = ICONS_DIR / "Microdrop_Icon_Trans.png"
