# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT Capture pane view: the spot table (reorderable, editable while
idle), the run buttons, and the status line. Business logic lives in the
model; this module is instantiable standalone against just the model:

    PortableDropbotPmtCaptureModel(rows=[...]).edit_traits(view=PmtCaptureView)
"""

# Enthought library imports.
from traitsui.api import (
    HGroup,
    Item,
    ObjectColumn,
    TableEditor,
    UItem,
    VGroup,
    View,
)
from traitsui.extras.checkbox_column import CheckboxColumn

#: One row per configured spot; the toolbar's move up/down buttons act on
#: the selected row and define capture order.
pmt_spot_table = TableEditor(
    columns=[
        ObjectColumn(name="label", label="Spot", editable=False),
        CheckboxColumn(name="capture", label="Capture"),
        ObjectColumn(name="gain", label="Gain"),
        ObjectColumn(name="exposure_s", label="Exposure (s)", format="%.1f"),
    ],
    reorderable=True,
    show_toolbar=True,
    sortable=False,
    deletable=False,
    auto_size=False,
    selected="selected_row",
)

PmtCaptureView = View(
    VGroup(
        UItem(
            "rows",
            editor=pmt_spot_table,
            enabled_when="connected and not capturing",
        ),
        HGroup(
            UItem("start_button", enabled_when="connected and not capturing and rows"),
            UItem("abort_button", enabled_when="capturing"),
            UItem("refresh_button", enabled_when="connected and not capturing"),
        ),
        Item("progress", style="readonly", label="Status"),
        Item("results_directory", style="readonly", label="Saved to"),
    ),
    resizable=True,
)
