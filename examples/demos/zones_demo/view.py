# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI view for the electrode zones demo: the device canvas (the one
custom-Qt widget, embedded via CustomEditor) beside the shipped zones
sidebar (device_viewer.views.zone_view.zones_sidebar.zones_view), embedded via
an InstanceEditor over the manager."""

# Enthought library imports.
from traitsui.api import (
    CustomEditor,
    EnumEditor,
    HGroup,
    InstanceEditor,
    UItem,
    VGroup,
    View,
)

# Microdrop package imports.
from device_viewer.consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from device_viewer.views.zone_view.zones_sidebar import zones_view

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import SafeCancelTableHandler

# Local imports.
from .canvas import zones_canvas_factory
from .consts import PAN_MODE, SIDEBAR_WIDTH

sidebar = VGroup(
    UItem("load_svg_button"),
    UItem(
        "mode",
        style="custom",
        editor=EnumEditor(
            values={
                PAN_MODE: "Pan",
                ZONE_DRAW_MODE: "Draw zones",
                ZONE_SELECT_MODE: "Select",
            },
            cols=3,
        ),
    ),
    HGroup(
        UItem("undo_button", enabled_when="can_undo"),
        UItem("redo_button", enabled_when="can_redo"),
    ),
    UItem(
        "manager",
        style="custom",
        editor=InstanceEditor(view=zones_view),
        width=SIDEBAR_WIDTH,
    ),
)

ZonesDemoView = View(
    HGroup(
        UItem("manager", editor=CustomEditor(zones_canvas_factory), springy=True),
        sidebar,
    ),
    title="Electrode Zones Demo",
    width=1100,
    height=650,
    resizable=True,
    handler=SafeCancelTableHandler(),
)
