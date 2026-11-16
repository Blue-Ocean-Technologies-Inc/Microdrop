# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The ways into and out of Help mode: a checkable menu action and the
finger-sized ? toggle for the status bar, all kept in step."""

# Enthought library imports.
from pyface.action.api import Action
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import QToolButton
from traits.api import Instance, observe

# Microdrop package imports.
from microdrop_status_bar.consts import ICON_PRIORITY_LEFTMOST

# Microdrop style imports.
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.colors import ACCENT_COLOR, WHITE
from microdrop_style.icons.icons import ICON_HELP
from microdrop_style.touch_style import (
    TOUCH_DENSE_ROW_PX,
    TOUCH_RADIUS_PX,
    TOUCH_TARGET_PX,
)

# Local imports.
from .consts import HELP_TOGGLE_TOOLTIP, PKG
from .help_mode import HelpModeController, help_mode_controller

#: Pixel size of the ? glyph.
_GLYPH_PX = 24

_TOGGLE_STYLE = f"""
QToolButton {{
    border: none;
    border-radius: {TOUCH_RADIUS_PX}px;
}}
QToolButton:checked {{
    background-color: {ACCENT_COLOR};
    color: {WHITE};
}}
"""


class HelpModeAction(Action):
    """Help mode as a checkable menu entry."""

    style = "toggle"
    name = "&Help Mode"
    tooltip = HELP_TOGGLE_TOOLTIP

    #: The controller the entry turns on and off and follows.
    controller = Instance(HelpModeController)

    def perform(self, event):
        self.controller.active = self.checked

    @observe("controller:active")
    def _follow_active(self, event):
        self.checked = event.new


def help_mode_action():
    """A Help mode menu entry; one per menu, pyface binds actions to the
    window rendering them."""
    return HelpModeAction(
        id=f"{PKG}.help_mode",
        controller=help_mode_controller,
        checked=help_mode_controller.active,
    )


def make_help_toggle_button():
    """The ? toggle for the status bar: full finger width, and as tall as a
    dense row so the bar grows as little as possible at the screen edge."""
    button = QToolButton()
    button.setText(ICON_HELP)
    button.setToolTip(HELP_TOGGLE_TOOLTIP)
    button.setCheckable(True)
    button.setFixedSize(TOUCH_TARGET_PX, TOUCH_DENSE_ROW_PX)
    button.setStyleSheet(_TOGGLE_STYLE)

    font = QFont(ICON_FONT_FAMILY)
    font.setPixelSize(_GLYPH_PX)
    button.setFont(font)

    # Read by the status bar plugin to order its icons.
    button.status_bar_icon_priority = ICON_PRIORITY_LEFTMOST

    help_mode_controller.register_toggle_button(button)

    return button
