# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's type roles, in one place: which face, size and weight each
kind of text takes. Headings (the drawer title, section and News
sub-section headers) are in the brand's heading face, Orbitron; everything
else, card titles included, in its body face, Lato. Either falls back to
the application's font until its files are installed.

Sizes keep one hierarchy: drawer title > section > sub-section, and the
cards below them.
"""

# Standard library imports.
from collections import namedtuple

# Enthought library imports.
from pyface.qt import QtGui

# Microdrop style imports.
from microdrop_style.brand_fonts import HEADING_FONT_FAMILY, body_family, heading_family

#: Which face a role takes.
HEADING = "heading"
BODY = "body"

_WEIGHT = QtGui.QFont.Weight

#: A role: its face, size (points), weight, and the letter spacing (%) it
#: takes in the heading face itself (none in a fallback).
FontRole = namedtuple("FontRole", "face points weight spacing", defaults=(100,))

DRAWER_TITLE = FontRole(HEADING, 13, _WEIGHT.DemiBold, 104)
SECTION_TITLE = FontRole(HEADING, 11, _WEIGHT.DemiBold, 103)
SUBSECTION_TITLE = FontRole(HEADING, 10, _WEIGHT.Medium, 103)
CARD_TITLE = FontRole(BODY, 10.5, _WEIGHT.Bold)
BODY_TEXT = FontRole(BODY, 10, _WEIGHT.Normal)
META = FontRole(BODY, 9, _WEIGHT.Normal)
CHIP = FontRole(BODY, 9, _WEIGHT.DemiBold)
BUTTON = FontRole(BODY, 10, _WEIGHT.DemiBold)


def role_font(role, weight=None):
    """The QFont for ``role``, at ``weight`` instead of its own if given."""
    family = heading_family() if role.face == HEADING else body_family()
    font = QtGui.QFont(family)

    font.setPointSizeF(role.points)
    font.setWeight(weight if weight is not None else role.weight)

    if family == HEADING_FONT_FAMILY and role.spacing != 100:
        font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, role.spacing)

    return font
