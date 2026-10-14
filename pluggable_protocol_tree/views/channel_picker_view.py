# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The channel picker dialog: the Fill Pattern's channel entries on the
left (one per step), the device picture on the right showing and editing
the selected entry — click an electrode to toggle its channel."""

# Enthought library imports.
from traitsui.api import (
    HGroup,
    ListStrEditor,
    OKCancelButtons,
    UItem,
    VGroup,
    View,
    spring,
)

# Microdrop style imports.
from microdrop_style.icons.icons import (
    ICON_ADD,
    ICON_DESELECT,
    ICON_FIT_SCREEN,
    ICON_PLAYLIST_REMOVE,
    ICON_ROTATE_90_CW,
    ICON_ZOOM_IN,
    ICON_ZOOM_OUT,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import IconButtonEditor

# Local imports.
from .channel_picker_canvas import ChannelPickerCanvasEditor

#: The dialog's opening size.
START_WIDTH_PX = 900
START_HEIGHT_PX = 600

#: Fixed width of the entry list column (negative: fixed, not a minimum).
ENTRY_LIST_WIDTH_PX = -220

entries_column = VGroup(
    UItem(
        "entry_labels",
        editor=ListStrEditor(
            title="Entries (one per step)",
            editable=False,
            selected="current_label",
            selected_index="current_index",
        ),
        width=ENTRY_LIST_WIDTH_PX,
    ),
    HGroup(
        UItem(
            "add_entry",
            editor=IconButtonEditor(glyph=ICON_ADD, tooltip="Add an entry"),
        ),
        UItem(
            "remove_entry",
            editor=IconButtonEditor(
                glyph=ICON_PLAYLIST_REMOVE, tooltip="Remove the selected entry"
            ),
            enabled_when="current_index >= 0",
        ),
        UItem(
            "clear_entry",
            editor=IconButtonEditor(
                glyph=ICON_DESELECT,
                tooltip="Unselect every channel of the selected entry",
            ),
            enabled_when="current_index >= 0",
        ),
        spring,
    ),
)

device_column = VGroup(
    HGroup(
        UItem(
            "zoom_in", editor=IconButtonEditor(glyph=ICON_ZOOM_IN, tooltip="Zoom in")
        ),
        UItem(
            "zoom_out", editor=IconButtonEditor(glyph=ICON_ZOOM_OUT, tooltip="Zoom out")
        ),
        UItem(
            "fit_view",
            editor=IconButtonEditor(
                glyph=ICON_FIT_SCREEN, tooltip="Fit the device in the view"
            ),
        ),
        UItem(
            "rotate",
            editor=IconButtonEditor(
                glyph=ICON_ROTATE_90_CW, tooltip="Rotate a quarter turn clockwise"
            ),
        ),
        spring,
    ),
    UItem("electrode_paths", editor=ChannelPickerCanvasEditor(), springy=True),
    springy=True,
)

channel_picker_view = View(
    HGroup(entries_column, device_column),
    title="Pick channels on device",
    buttons=OKCancelButtons,
    kind="livemodal",
    resizable=True,
    width=START_WIDTH_PX,
    height=START_HEIGHT_PX,
)


if __name__ == "__main__":
    # Standalone prototyping: the view against a synthetic 4 x 3 device.
    import numpy as np

    from pluggable_protocol_tree.models.channel_picker_model import (
        ChannelPickerModel,
    )

    square = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    paths = {
        f"e{row}{col}": square + [col * 1.1, row * 1.1]
        for row in range(3)
        for col in range(4)
    }

    # Two electrodes share channel 0; the last one has no channel.
    channels = {electrode_id: index for index, electrode_id in enumerate(paths)}
    channels["e01"] = 0
    channels["e23"] = None

    ChannelPickerModel(
        electrode_paths=paths,
        electrode_channels=channels,
        entries=[[0, 2], [5]],
    ).configure_traits(view=channel_picker_view)
