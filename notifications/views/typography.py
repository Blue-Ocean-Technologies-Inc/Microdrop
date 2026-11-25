# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's type roles, in one place: the size and weight each kind of
text takes, all in the application's own font. Sizes keep one hierarchy:
drawer title > section > sub-section, and the cards below them."""

# Standard library imports.
from collections import namedtuple

# Enthought library imports.
from pyface.qt import QtGui

_WEIGHT = QtGui.QFont.Weight

#: A role: its size (points) and weight.
FontRole = namedtuple("FontRole", "points weight")

DRAWER_TITLE = FontRole(13, _WEIGHT.DemiBold)
SECTION_TITLE = FontRole(11.5, _WEIGHT.DemiBold)
SUBSECTION_TITLE = FontRole(10.5, _WEIGHT.DemiBold)
CARD_TITLE = FontRole(10.5, _WEIGHT.Bold)
BODY_TEXT = FontRole(10, _WEIGHT.Normal)
META = FontRole(9, _WEIGHT.Normal)
CHIP = FontRole(9, _WEIGHT.DemiBold)
BUTTON = FontRole(10, _WEIGHT.DemiBold)


def role_font(role, weight=None):
    """The application's font for ``role``, at ``weight`` instead of its
    own if given."""
    font = QtGui.QFont(QtGui.QGuiApplication.font())

    font.setPointSizeF(role.points)
    font.setWeight(weight if weight is not None else role.weight)

    return font
