# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traitsui.api import HGroup, Item, Label, Spring, UItem, VGroup, View

# Microdrop package imports.
from dropbot_status_and_controls.consts import DIELECTRIC_MATERIALS, DROPLET_READOUTS

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_OPEN_IN_NEW

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    HoverScrollEnumEditor,
    HtmlLabelEditor,
    IconButtonEditor,
    InPlaceToggleEditor,
    StatusIconEditorFactory,
)

# 1. Add label, id, and dock='tab' to the left group
left = HGroup(
    Item(
        "icon_path",
        editor=StatusIconEditorFactory(),
        show_label=False,
    ),
    Spring("8"),
    VGroup(
        Spring("12"),
        VGroup(
            Item("connection_status_text", style="readonly", label="Connection"),
            Item("chip_status_text", style="readonly", label="Chip Status"),
        ),
        Spring("22"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=InPlaceToggleEditor(
                on_label="Realtime On", off_label="Realtime Off"
            ),
            enabled_when="connected and not halted and not protocol_running",
        ),
        Spring("10"),
    ),
    id="status_controls",  # Unique identifier for layout saving
)

# 2. Readings grid: label | value | control. Labels are Label items, not
# Item labels, so the droplet readout row can put a dropdown in the label
# column.
grid = VGroup(
    Label("Voltage", show_label=False),
    UItem("voltage_readback_display", style="readonly"),
    UItem("voltage", enabled_when="free_mode and not protocol_running and not halted"),
    Label("Frequency", show_label=False),
    UItem("frequency_display", style="readonly"),
    UItem(
        "frequency", enabled_when="free_mode and not protocol_running and not halted"
    ),
    Label("Capacitance", show_label=False),
    UItem("capacitance_display", style="readonly"),
    UItem(""),
    UItem(
        "droplet_readout",
        editor=HoverScrollEnumEditor(values=DROPLET_READOUTS),
        width=120,
        tooltip="Droplet readout to show; hover the value for all of them",
    ),
    UItem(
        "droplet_readout_display",
        editor=HtmlLabelEditor(
            word_wrap=False, tooltip_name="droplet_readouts_tooltip"
        ),
    ),
    UItem(
        "show_droplet_readouts",
        editor=IconButtonEditor(
            glyph=ICON_OPEN_IN_NEW, tooltip="Show all droplet readouts"
        ),
    ),
    Label("Force", show_label=False),
    UItem("force_display", style="readonly"),
    UItem(""),
    Label("Dielectric", show_label=False, visible_when="show_dielectric_info"),
    UItem(
        "dielectric_thickness_display",
        style="readonly",
        visible_when="show_dielectric_info",
    ),
    UItem(
        "dielectric_material",
        editor=HoverScrollEnumEditor(
            values=list(DIELECTRIC_MATERIALS.keys()),
        ),
        visible_when="show_dielectric_info",
    ),
    columns=3,
    id="data_grid",  # Unique identifier for layout saving
)

# Non-modal dialog with every droplet readout, plus c_device.
droplet_readouts_view = View(
    VGroup(
        Item("volume_display", style="readonly", label="Volume"),
        Item("fill_display", style="readonly", label="Fill"),
        Item("covered_area_display", style="readonly", label="Covered area"),
        Item("c_device_display", style="readonly", label="c_device"),
        UItem(
            "volume_status_message",
            style="readonly",
            visible_when="volume_status_message",
        ),
    ),
    title="Droplet Readouts",
    resizable=True,
)

# 3. Wrap in a split layout and set a View ID
UnifiedView = View(
    HGroup(
        left,
        "15",
        grid,
    ),
    resizable=True,
)
