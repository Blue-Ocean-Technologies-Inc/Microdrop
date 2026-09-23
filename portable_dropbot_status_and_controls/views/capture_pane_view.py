# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""View builders shared by the capture panes (see capture_pane_model.py), so
the PMT and Fluorescence Capture panes lay out and behave alike: the row
table (a Capture tick column in manual mode, or Start/End tick columns while
a step is attached, switched with two TableEditors on the same `rows` since
TraitsUI cannot swap a table's columns in place), the run buttons and status
lines, and the Results group paging one capture run at a time.

Tick and number columns hug their contents; slider columns share the width
left over, so every slider gets room to be dragged. The row table's height
hugs its rows (see CapturePaneController.init)."""

# Enthought library imports.
from traitsui.api import HGroup, Item, Label, TableEditor, UItem, VGroup

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_CHEVRON_LEFT, ICON_CHEVRON_RIGHT

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    ActiveRowCheckboxColumn,
    ActiveRowObjectColumn,
    IconButtonEditor,
    IconToggleEditor,
    SteppedSliderEditor,
)

# Local imports.
from ..consts import CAPTURE_RESULTS_TABLE_MIN_HEIGHT

#: Idle, and never while a protocol runs (the tree refuses the pane's
#: set-cell then anyway, but the table locking too keeps the operator from
#: editing a frozen setup).
ROW_TABLE_ENABLED_WHEN = "connected and not busy and not protocol_running"


def key_column(name, label):
    """The read-only identity column, sized so its text is never elided."""
    return ActiveRowObjectColumn(
        name=name, label=label, editable=False, resize_mode="resize_to_contents"
    )


def tick_column(name, label):
    """A checkbox column as narrow as its header."""
    return ActiveRowCheckboxColumn(
        name=name, label=label, resize_mode="resize_to_contents"
    )


def number_column(name, label):
    """A plain editable number column sized to its contents."""
    return ActiveRowObjectColumn(
        name=name, label=label, resize_mode="resize_to_contents"
    )


def slider_column(name, label, low, high, step, value_format, span_name=""):
    """A slider-edited column sharing the table's spare width. `span_name`
    names the row trait holding the slider's run-time top end (the
    exposure range pick); the value itself is never clamped to it."""
    return ActiveRowObjectColumn(
        name=name,
        label=label,
        format=value_format,
        resize_mode="stretch",
        editor=SteppedSliderEditor(
            low=low, high=high, span_name=span_name, step=step, format=value_format
        ),
    )


def capture_row_tables(key, settings):
    """The manual- and attached-mode row tables: the key column, the mode's
    ticks, then the settings. `key` and `settings` are called once per table
    — the two tables must not share column instances."""

    def table(ticks):
        return TableEditor(
            columns=[key(), *ticks, *settings()],
            reorderable=True,
            show_toolbar=True,
            sortable=False,
            deletable=False,
            auto_size=False,
            selected="selected_row",
        )

    manual = table([tick_column("capture", "Capture")])
    attached = table([tick_column("at_start", "Start"), tick_column("at_end", "End")])

    return manual, attached


def capture_group(manual_table, attached_table, extra_buttons=()):
    """The mode line and exposure range, the row table for the current
    mode, the run buttons, and the status lines. Labelled rows live in
    their own sub-groups: a group with any labelled item lays out as a
    label/editor grid, which would push the unlabelled table into the
    editor column instead of full width."""
    return VGroup(
        VGroup(
            Item("attached_label", style="readonly", label="Mode"),
            Item(
                "step_capture_taken_note",
                style="readonly",
                show_label=False,
                visible_when="step_capture_taken",
            ),
            Item(
                "exposure_range",
                label="Exposure range",
                enabled_when=ROW_TABLE_ENABLED_WHEN,
            ),
        ),
        UItem(
            "rows",
            editor=manual_table,
            enabled_when=ROW_TABLE_ENABLED_WHEN,
            visible_when="not attached_step_id",
        ),
        UItem(
            "rows",
            editor=attached_table,
            enabled_when=f"{ROW_TABLE_ENABLED_WHEN} and not step_capture_taken",
            visible_when="attached_step_id",
        ),
        HGroup(
            UItem("start_button", enabled_when=f"{ROW_TABLE_ENABLED_WHEN} and rows"),
            UItem("abort_button", enabled_when="capturing"),
            *extra_buttons,
            Item(
                "park_motor",
                label="Park Motor",
                tooltip="Move the motor to its parking position when the capture ends",
                enabled_when=ROW_TABLE_ENABLED_WHEN,
            ),
        ),
        VGroup(
            Item("progress", style="readonly", label="Status"),
            Item("results_directory", style="readonly", label="Saved to"),
        ),
    )


def results_group(results_table):
    """The Results chevron group: arrows paging one capture run at a time
    over that run's results table."""
    return VGroup(
        HGroup(
            UItem("show_results", editor=IconToggleEditor()),
            Label("Results"),
        ),
        VGroup(
            HGroup(
                UItem(
                    "previous_frame_button",
                    editor=IconButtonEditor(
                        glyph=ICON_CHEVRON_LEFT, tooltip="Previous run"
                    ),
                    enabled_when="has_previous_frame",
                ),
                UItem("frame_label", style="readonly"),
                UItem(
                    "next_frame_button",
                    editor=IconButtonEditor(
                        glyph=ICON_CHEVRON_RIGHT, tooltip="Next run"
                    ),
                    enabled_when="has_next_frame",
                ),
            ),
            UItem(
                "results",
                editor=results_table,
                height=CAPTURE_RESULTS_TABLE_MIN_HEIGHT,
            ),
            visible_when="show_results",
        ),
    )
