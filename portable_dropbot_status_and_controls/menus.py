# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The portable rig's Tools menu contributions."""

from pyface.action.api import Action
from pyface.qt.QtGui import QGuiApplication
from pyface.tasks.action.api import SGroup

from .consts import PKG
from .controllers.display_scale_controller import DisplayScaleController
from .models.display_scale_model import DisplayScaleModel, DisplayScalePreferences
from .screen_scale import live_scaling_available
from .views.display_scale_view import display_scale_view


class DisplayScaleAction(Action):
    """Open the live interface-scale slider."""

    id = f"{PKG}.display_scale"
    name = "&Display Scale..."

    def perform(self, event):
        percent = DisplayScalePreferences().scale_percent
        model = DisplayScaleModel(scale_percent=percent, **_native_panel_size(percent))
        DisplayScaleController(model=model).edit_traits(view=display_scale_view)


def display_scale_group_factory():
    """The Tools menu group; greyed out where the display server cannot
    rescale (anywhere but the rig's X session)."""
    return SGroup(
        DisplayScaleAction(enabled=live_scaling_available()),
        id=f"{PKG}.display_scale_group",
    )


def _native_panel_size(active_percent):
    """The panel's native pixels, undoing the scale currently applied —
    Qt reports the already-rescaled logical geometry."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return {}

    size = screen.geometry().size()

    return {
        "screen_width": round(size.width() * active_percent / 100),
        "screen_height": round(size.height() * active_percent / 100),
    }
