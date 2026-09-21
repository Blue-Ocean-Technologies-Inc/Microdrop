# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fluorescence Capture pane view: a header line naming the attached step
(or manual mode), the filter table (a Capture tick column in manual mode, or
Start/End tick columns while a step is attached, switched with two
TableEditors on the same `rows` since TraitsUI cannot swap a table's columns
in place — the same pattern as the PMT Capture pane's spot table), the run
buttons and status line, then the last capture's results as a table of file
links. Business logic lives in the model; this module is instantiable
standalone against just the model:

    PortableDropbotFluorescenceCaptureModel().edit_traits(
        view=FluorescenceCaptureView
    )
"""

# Enthought library imports.
from traitsui.api import HGroup, Item, ObjectColumn, TableEditor, UItem, VGroup, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    ActiveRowCheckboxColumn,
    ActiveRowObjectColumn,
    LinkColumn,
)

# Local imports.
from ..consts import PMT_RESULTS_TABLE_MIN_HEIGHT, PMT_SPOT_TABLE_MIN_HEIGHT

#: Manual mode: the pane's own Capture tick. Shown while unattached
#: (visible_when="not attached_step_id" on its UItem, below). Reorderable —
#: table order is capture order, independent of filter_position.
fluorescence_row_table_manual = TableEditor(
    columns=[
        ActiveRowObjectColumn(
            name="filter_position",
            label="Filter",
            editable=False,
            resize_mode="resize_to_contents",
        ),
        ActiveRowCheckboxColumn(name="capture", label="Capture"),
        ActiveRowObjectColumn(name="led_percent", label="LED %"),
        ActiveRowObjectColumn(name="exposure_ms", label="Exposure (ms)", format="%.1f"),
        ActiveRowCheckboxColumn(name="auto_focus", label="Auto focus"),
        ActiveRowObjectColumn(
            name="focus_distance",
            label="Focus",
            format="%.2f",
            resize_mode="stretch",
        ),
    ],
    reorderable=True,
    show_toolbar=True,
    sortable=False,
    deletable=False,
    auto_size=False,
    selected="selected_row",
)

#: Attached mode: Start/End ticks replace the single Capture tick, so a
#: filter position can be captured at the step's start, its end, or both.
#: Shown while a step is attached (visible_when="attached_step_id").
fluorescence_row_table_attached = TableEditor(
    columns=[
        ActiveRowObjectColumn(
            name="filter_position",
            label="Filter",
            editable=False,
            resize_mode="resize_to_contents",
        ),
        ActiveRowCheckboxColumn(name="at_start", label="Start"),
        ActiveRowCheckboxColumn(name="at_end", label="End"),
        ActiveRowObjectColumn(name="led_percent", label="LED %"),
        ActiveRowObjectColumn(name="exposure_ms", label="Exposure (ms)", format="%.1f"),
        ActiveRowCheckboxColumn(name="auto_focus", label="Auto focus"),
        ActiveRowObjectColumn(
            name="focus_distance",
            label="Focus",
            format="%.2f",
            resize_mode="stretch",
        ),
    ],
    reorderable=True,
    show_toolbar=True,
    sortable=False,
    deletable=False,
    auto_size=False,
    selected="selected_row",
)

#: The last capture's saved files, read-only, newest first.
fluorescence_results_table = TableEditor(
    columns=[
        ObjectColumn(name="path", label="Path", editable=False, resize_mode="stretch"),
        # Click to open the PNG in the system's default application.
        LinkColumn(name="file", label="File", fire="open_file"),
    ],
    sortable=False,
    editable=False,
    auto_size=False,
)

#: Idle, and never while a protocol runs (the tree refuses the pane's
#: set-cell then anyway, but the table locking too keeps the operator from
#: editing a frozen setup).
_row_table_enabled_when = "connected and not running and not protocol_running"

#: Labelled rows live in their own sub-group: a group with any labelled item
#: lays out as a label/editor grid, which would push the unlabelled table
#: into the editor column instead of full width (the #686 layout lesson).
capture = VGroup(
    Item("attached_label", style="readonly", label="Mode"),
    UItem(
        "rows",
        editor=fluorescence_row_table_manual,
        enabled_when=_row_table_enabled_when,
        height=PMT_SPOT_TABLE_MIN_HEIGHT,
        visible_when="not attached_step_id",
    ),
    UItem(
        "rows",
        editor=fluorescence_row_table_attached,
        enabled_when=_row_table_enabled_when,
        height=PMT_SPOT_TABLE_MIN_HEIGHT,
        visible_when="attached_step_id",
    ),
    HGroup(
        UItem(
            "start_button",
            enabled_when="connected and not running and not protocol_running and rows",
        ),
        UItem("abort_button", enabled_when="running"),
    ),
    VGroup(
        Item("status", style="readonly", label="Status"),
        Item("last_directory", style="readonly", label="Saved to"),
    ),
)

#: Only one small results table (unlike PMT's three collapsible groups), so
#: no chevron toggle — a labelled Item is enough, and safe to label directly
#: since no other control shares its row.
results = VGroup(
    Item(
        "result_rows",
        editor=fluorescence_results_table,
        label="Results",
        height=PMT_RESULTS_TABLE_MIN_HEIGHT,
    ),
)

FluorescenceCaptureView = View(
    VGroup(capture, results),
    resizable=True,
    scrollable=True,
)
