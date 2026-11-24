# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's colours resolve for the theme of the palette they are
asked with: a light palette gets the light values, a dark one the dark."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtGui import QColor, QPalette
from pyface.qt.QtWidgets import QApplication

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_cards import accent_color
from examples.demos.notifications_pane.sci_bots_feed_groups import FEED_GROUPS
from examples.demos.notifications_ux import colour_roles as roles
from examples.demos.notifications_ux.view_styles import link_color, role_color

WINDOWS = {roles.LIGHT: "#F3F3F3", roles.DARK: "#1E1E1E"}


def _palette(theme):
    QApplication.instance() or QApplication([])
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(WINDOWS[theme]))
    palette.setColor(QPalette.ColorRole.Base, QColor(WINDOWS[theme]))

    return palette


@pytest.mark.parametrize("theme", [roles.LIGHT, roles.DARK])
def test_roles_resolve_for_the_palette_theme(theme):
    palette = _palette(theme)

    assert link_color(palette).name().upper() == roles.LINK[theme]

    for severity, pair in roles.SEVERITY.items():
        assert role_color(palette, pair).name().upper() == pair[theme], severity


@pytest.mark.parametrize("theme", [roles.LIGHT, roles.DARK])
def test_sub_section_accents_resolve_for_the_palette_theme(theme):
    palette = _palette(theme)

    for spec in FEED_GROUPS:
        assert accent_color(spec, palette).name().upper() == spec.accent[theme].upper()
