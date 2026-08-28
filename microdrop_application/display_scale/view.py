# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Display Scale dialog: one slider, and a running account of what
it does to the screen it is being dragged on."""

# Enthought library imports.
from traitsui.api import Handler, Item, RangeEditor, VGroup, View

# Microdrop style imports.
from microdrop_style.text_styles import preferences_group_style_sheet

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import stretch_group_layouts_horizontally

# Local imports.
from .consts import SCALE_MAX_PERCENT, SCALE_MIN_PERCENT


class DisplayScaleHandler(Handler):
    """Widens the group box so the slider spans the dialog."""

    def init(self, info):
        stretch_group_layouts_horizontally(info.ui.control)
        return super().init(info)


display_scale_view = View(
    VGroup(
        Item(
            "scale_percent",
            label="Scale (%)",
            editor=RangeEditor(
                low=SCALE_MIN_PERCENT,
                high=SCALE_MAX_PERCENT,
                mode="slider",
                is_float=False,
            ),
        ),
        Item("_"),
        Item("summary", style="readonly", show_label=False),
        Item("relaunch_note", style="readonly", show_label=False),
        label="Interface Scale",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    ),
    handler=DisplayScaleHandler(),
    title="Display Scale",
    buttons=["OK", "Cancel"],
    kind="livemodal",
    resizable=True,
    width=480,
)


if __name__ == "__main__":
    # Standalone prototyping: the view against nothing but its model.
    from .model import DisplayScaleModel

    DisplayScaleModel(screen_width=1280, screen_height=800).configure_traits(
        view=display_scale_view
    )
