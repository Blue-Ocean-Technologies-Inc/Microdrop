# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test hub panel, after the vendor's self-test tab: the test
table and parameters, Run / Abort, the pre-flight check, progress, the
rendered report, the figures, and the two saves. Instantiable alone
against a SelfTestHubModel (``model.edit_traits(view=self_tests_view)``)."""

# Enthought library imports.
from traitsui.api import (
    HGroup,
    InstanceEditor,
    Item,
    Label,
    ListEditor,
    ProgressEditor,
    RangeEditor,
    Tabbed,
    TableEditor,
    UItem,
    VGroup,
    View,
)

# Microdrop style imports.
from microdrop_style.colors import ERROR_COLOR

# Microdrop utils imports.
from microdrop_utils.markdown_browser_editor import MarkdownBrowserEditor
from microdrop_utils.traitsui_qt_helpers import (
    CustomCheckboxColumn,
    DoubleSpinBoxEditor,
    ObjectColumn,
)

# Local imports.
from ..models.consts import (
    CALIBRATION_MAX_RAIL_PCT_BOUNDS,
    CALIBRATION_MIN_COUNTS_BOUNDS,
    CALIBRATION_REPLICATES_BOUNDS,
    CHANNELS_REPLICATES_BOUNDS,
    CHANNELS_THRESHOLD_PF_BOUNDS,
    VOLTAGE_POINTS_BOUNDS,
)
from .plot_view import plot_view
from .preflight_view import preflight_view

#: Height (px) of the report browser, which scrolls its own content.
REPORT_HEIGHT_PX = 380


class OutcomeColumn(ObjectColumn):
    """The last-result column: FAIL / ERROR in the error colour."""

    def get_text_color(self, object):
        return ERROR_COLOR if object.outcome_is_bad else super().get_text_color(object)


tests_table = TableEditor(
    columns=[
        CustomCheckboxColumn(
            name="selected",
            label="Run",
            editable=False,
            horizontal_alignment="center",
        ),
        ObjectColumn(name="title", label="Test", editable=False),
        ObjectColumn(name="pads", label="Pads", editable=False),
        OutcomeColumn(name="outcome", label="Last result", editable=False),
        ObjectColumn(name="duration", label="Duration", editable=False),
    ],
    editable=True,
    sortable=False,
    deletable=False,
    show_toolbar=False,
    auto_size=True,
)

parameters_group = HGroup(
    VGroup(
        Item(
            "object.parameters.voltage_points",
            label="Voltage: sweep points",
            editor=RangeEditor(
                mode="spinner",
                low=VOLTAGE_POINTS_BOUNDS[0],
                high=VOLTAGE_POINTS_BOUNDS[1],
            ),
            tooltip="Points of the 40-200 V sweep (n)",
        ),
        Item(
            "object.parameters.channels_replicates",
            label="Channels: repeats",
            editor=RangeEditor(
                mode="spinner",
                low=CHANNELS_REPLICATES_BOUNDS[0],
                high=CHANNELS_REPLICATES_BOUNDS[1],
            ),
            tooltip="Replicates of the per-channel sweep (n_reps)",
        ),
        Item(
            "object.parameters.channels_threshold_pf",
            label="Channels: active above (pF)",
            editor=DoubleSpinBoxEditor(
                low=CHANNELS_THRESHOLD_PF_BOUNDS[0],
                high=CHANNELS_THRESHOLD_PF_BOUNDS[1],
                decimals=1,
                step=0.5,
            ),
            tooltip="A channel passes when its capacitance with the all-off "
            "baseline removed is above this",
        ),
    ),
    VGroup(
        Item(
            "object.parameters.calibration_replicates",
            label="Feedback calibration: repeats",
            editor=RangeEditor(
                mode="spinner",
                low=CALIBRATION_REPLICATES_BOUNDS[0],
                high=CALIBRATION_REPLICATES_BOUNDS[1],
            ),
            tooltip="Replicates per matrix point (n_reps)",
        ),
        Item(
            "object.parameters.calibration_min_counts",
            label="Feedback calibration: valid above (counts)",
            editor=DoubleSpinBoxEditor(
                low=CALIBRATION_MIN_COUNTS_BOUNDS[0],
                high=CALIBRATION_MIN_COUNTS_BOUNDS[1],
                decimals=0,
                step=5.0,
            ),
            tooltip="Low limit: a point whose expected signal (IQR) is below "
            "this many ADC counts is too small to resolve and is not judged",
        ),
        Item(
            "object.parameters.calibration_max_rail_pct",
            label="Feedback calibration: rail below (%)",
            editor=DoubleSpinBoxEditor(
                low=CALIBRATION_MAX_RAIL_PCT_BOUNDS[0],
                high=CALIBRATION_MAX_RAIL_PCT_BOUNDS[1],
                decimals=1,
                step=0.5,
            ),
            tooltip="High limit: a point with more than this % of its samples "
            "on an ADC rail is clipped and not judged",
        ),
    ),
    label="Parameters",
    show_border=True,
    enabled_when="idle",
)

run_buttons = HGroup(
    UItem("run_selected_button", enabled_when="idle"),
    UItem("run_all_button", enabled_when="idle"),
    UItem(
        "abort_button",
        enabled_when="running and not aborting",
        tooltip="Abort between steps: HV off, pads back to where they were",
    ),
)

run_state = VGroup(
    UItem("summary", style="readonly", resizable=True),
    UItem(
        "progress",
        editor=ProgressEditor(min=0, max=100),
        visible_when="running",
    ),
    UItem("step_text", style="readonly", resizable=True),
)

outputs_tabs = Tabbed(
    VGroup(
        UItem(
            "object.outputs.report_markdown",
            editor=MarkdownBrowserEditor(min_height=REPORT_HEIGHT_PX),
            resizable=True,
        ),
        HGroup(
            UItem(
                "save_report_button",
                enabled_when="can_save_report",
                tooltip="HTML report (figures embedded, raw-data JSON beside "
                "it), or Markdown for a .md name",
            ),
            UItem("object.outputs.report_status", style="readonly", resizable=True),
        ),
        label="Report",
    ),
    VGroup(
        UItem(
            "object.outputs.plots",
            resizable=True,
            style="custom",
            editor=ListEditor(
                use_notebook=True,
                page_name=".title",
                selected="selected_plot",
                view=plot_view,
                deletable=False,
            ),
        ),
        label="Plots",
    ),
)

calibration = HGroup(
    UItem(
        "save_calibration_button",
        enabled_when="can_save_calibration",
        tooltip="Save what the last run left in RAM to the signal board's "
        "flash: the feedback-cap calibration and the electrode tare. Until "
        "then both last until reboot.",
    ),
    VGroup(
        UItem("unsaved_text", style="readonly", resizable=True),
        UItem("calibration_status", style="readonly", resizable=True),
    ),
)

self_tests_view = View(
    VGroup(
        Label(
            "Load the capacitor test board, tick the tests and run. A pre-flight\n"
            "check comes first; the run presses / lifts the pogo pads per test\n"
            "(HV off before every move), never moves the tray, and puts the pads\n"
            "back afterwards with the HV off."
        ),
        UItem("rows", editor=tests_table, enabled_when="idle"),
        parameters_group,
        run_buttons,
        UItem(
            "preflight",
            style="custom",
            editor=InstanceEditor(view=preflight_view),
            visible_when="preflight_pending",
        ),
        run_state,
        outputs_tabs,
        calibration,
    ),
    title="Portable DropBot Self Tests",
    resizable=True,
    scrollable=True,
    width=900,
    height=900,
)
