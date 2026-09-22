# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Fluorescence Capture pane view, built from the capture-pane layout shared
with the PMT pane (see capture_pane_view.py): the filter table (Filter,
ticks, Auto focus, LED %, then the exposure and focus sliders), the run
controls, the collapsible Manual controls (wheel, LED and camera applied
live, a one-frame grab, the camera's readback), and the saved frames paged
per capture run. Business logic lives
in the model; this module is instantiable standalone against just the
model:

    PortableDropbotFluorescenceCaptureModel().edit_traits(
        view=FluorescenceCaptureView
    )
"""

# Enthought library imports.
from traitsui.api import (
    HGroup,
    Item,
    Label,
    ObjectColumn,
    TableEditor,
    UItem,
    VGroup,
    View,
)

# Microdrop package imports.
from portable_dropbot_controller.consts import FLUORESCENCE_EXPOSURE_MS_BOUNDS

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    IconToggleEditor,
    LinkColumn,
    SteppedSliderEditor,
)

# Local imports.
from ..consts import FLUORESCENCE_EXPOSURE_MS_STEP
from .capture_pane_view import (
    ROW_TABLE_ENABLED_WHEN,
    capture_group,
    capture_row_tables,
    key_column,
    number_column,
    results_group,
    slider_column,
    tick_column,
)


def _filter_column():
    return key_column("filter_position", "Filter")


def _setting_columns():
    return [
        tick_column("auto_focus", "Auto focus"),
        number_column("led_percent", "LED %"),
        slider_column(
            "exposure_ms",
            "Exposure (ms)",
            *FLUORESCENCE_EXPOSURE_MS_BOUNDS,
            step=FLUORESCENCE_EXPOSURE_MS_STEP,
            value_format="%.1f",
            high_name="exposure_max",
        ),
        slider_column(
            "focus_distance",
            "Focus",
            0.0,
            1.0,
            step=0.05,
            value_format="%.2f",
        ),
    ]


fluorescence_row_table_manual, fluorescence_row_table_attached = capture_row_tables(
    _filter_column, _setting_columns
)

#: One capture run's saved frames, read-only, in capture order: the filter
#: each frame was taken through and its file.
fluorescence_results_table = TableEditor(
    columns=[
        ObjectColumn(
            name="filter_position",
            label="Filter",
            editable=False,
            resize_mode="resize_to_contents",
        ),
        # Click to open the PNG in the system's default application; takes
        # all the width the Filter column leaves.
        LinkColumn(name="file", label="File", fire="open_file", resize_mode="stretch"),
    ],
    sortable=False,
    editable=False,
    auto_size=False,
)

#: Everything set directly, applied the moment it changes; the camera line
#: reads back what the camera actually took (for table captures too).
manual_controls = VGroup(
    HGroup(
        UItem("show_manual", editor=IconToggleEditor()),
        Label("Manual controls"),
    ),
    VGroup(
        VGroup(
            Item("manual_filter_position", label="Filter"),
            Item("manual_led_on", label="LED on"),
            Item(
                "manual_led_percent",
                label="LED %",
                enabled_when="manual_led_on",
            ),
            Item("manual_auto_exposure", label="Auto exposure"),
            Item(
                "manual_exposure_ms",
                label="Exposure (ms)",
                editor=SteppedSliderEditor(
                    low=FLUORESCENCE_EXPOSURE_MS_BOUNDS[0],
                    high_name="manual_exposure_max",
                    step=FLUORESCENCE_EXPOSURE_MS_STEP,
                    format="%.1f",
                ),
                enabled_when="not manual_auto_exposure",
            ),
            Item("manual_auto_focus", label="Auto focus"),
            Item(
                "manual_focus_distance",
                label="Focus",
                editor=SteppedSliderEditor(low=0.0, high=1.0, step=0.05, format="%.2f"),
                enabled_when="not manual_auto_focus",
            ),
            Item("camera_readback", style="readonly", label="Camera"),
        ),
        HGroup(
            UItem(
                "manual_capture_button",
                enabled_when="connected and not manual_capture_request_id",
            ),
        ),
        enabled_when=ROW_TABLE_ENABLED_WHEN,
        visible_when="show_manual",
    ),
)

FluorescenceCaptureView = View(
    VGroup(
        capture_group(fluorescence_row_table_manual, fluorescence_row_table_attached),
        manual_controls,
        results_group(fluorescence_results_table),
    ),
    resizable=True,
    scrollable=True,
)
