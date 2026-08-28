# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Display Scale dialog: pick a scale with the slider, commit it
with Apply — nothing changes while dragging — and Reset returns the
panel to its native 100%."""

from traitsui.api import HGroup, Item, RangeEditor, UItem, VGroup, View

from ..consts import DISPLAY_SCALE_MAX_PERCENT, DISPLAY_SCALE_MIN_PERCENT

display_scale_view = View(
    VGroup(
        Item(
            "scale_percent",
            label="Scale (%)",
            editor=RangeEditor(
                low=DISPLAY_SCALE_MIN_PERCENT,
                high=DISPLAY_SCALE_MAX_PERCENT,
                mode="slider",
                is_float=False,
            ),
        ),
        Item("_"),
        Item("summary", style="readonly", show_label=False),
        HGroup(
            UItem("apply_button"),
            UItem("reset_button"),
        ),
        label="Interface Scale",
        show_border=True,
    ),
    title="Display Scale",
    buttons=["OK"],
    kind="livemodal",
    resizable=True,
    width=480,
)


if __name__ == "__main__":
    # Standalone prototyping: the view against nothing but its model.
    from portable_dropbot_status_and_controls.models.display_scale_model import (
        DisplayScaleModel,
    )

    DisplayScaleModel(screen_width=1280, screen_height=800).configure_traits(
        view=display_scale_view
    )
