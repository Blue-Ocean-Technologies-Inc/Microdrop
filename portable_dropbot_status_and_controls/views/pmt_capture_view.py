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
idle), the run buttons and status line, then three chevron-collapsed
groups — the last capture's per-spot Results table, the Live stream &
acquire controls (shared gain/avg/osr/Rf), and the Conversion settings.
Business logic lives in the model; this module is instantiable standalone
against just the model:

    PortableDropbotPmtCaptureModel(rows=[...]).edit_traits(view=PmtCaptureView)
"""

# Enthought library imports.
from traitsui.api import (
    EnumEditor,
    HGroup,
    Item,
    Label,
    ObjectColumn,
    TableEditor,
    UItem,
    VGroup,
    View,
)
from traitsui.extras.checkbox_column import CheckboxColumn

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    PMT_RF_OHMS_BOUNDS,
    PMT_STREAM_AVG_CHOICES,
    PMT_STREAM_OSR_CHOICES,
)

# Microdrop utils imports.
from microdrop_utils.pyqtgraph_editors import LivePlotEditor
from microdrop_utils.traitsui_qt_helpers import (
    DoubleSpinBoxEditor,
    HtmlLabelEditor,
    IconToggleEditor,
)

# Local imports.
from ..consts import PMT_RESULTS_TABLE_MIN_HEIGHT, PMT_SPOT_TABLE_MIN_HEIGHT

#: Boxcar averaging choices as "N (rate Hz)" — the value rate is the
#: firmware's raw 1 kHz stream divided by N. The "i:" prefix keeps
#: EnumEditor in numeric rather than alphabetical order.
_stream_avg_labels = {
    n: f"{i}:{n} ({1000 // n} Hz)" for i, n in enumerate(PMT_STREAM_AVG_CHOICES)
}

#: ADS70x6 on-chip oversampling index labels: 0 = off, n = 2**n samples.
_stream_osr_labels = {
    n: f"{n}:{'Off' if n == 0 else f'{2**n}x'}" for n in PMT_STREAM_OSR_CHOICES
}

_rf_spin_box = DoubleSpinBoxEditor(
    low=PMT_RF_OHMS_BOUNDS[0], high=PMT_RF_OHMS_BOUNDS[1], decimals=0, step=1000.0
)

#: Muted, word-wrapped help text (wraps instead of forcing the pane wide).
_hint_label = HtmlLabelEditor(
    template='<span style="color:#888; font-style:italic;">{}</span>'
)

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

#: The last capture's per-spot outcomes, read-only.
pmt_results_table = TableEditor(
    columns=[
        ObjectColumn(name="slot", label="Spot", editable=False),
        ObjectColumn(name="gain", label="Gain", editable=False),
        ObjectColumn(
            name="exposure_s", label="Exposure (s)", format="%.1f", editable=False
        ),
        ObjectColumn(name="n_samples", label="N", editable=False),
        ObjectColumn(
            name="mean_counts", label="Mean (counts)", format="%.1f", editable=False
        ),
        ObjectColumn(
            name="sd_counts", label="SD (counts)", format="%.1f", editable=False
        ),
        ObjectColumn(name="mean_current", label="Mean current", editable=False),
        ObjectColumn(name="file", label="File", editable=False),
        ObjectColumn(name="error", label="Error", editable=False),
    ],
    sortable=False,
    editable=False,
    auto_size=False,
)

capture = VGroup(
    UItem(
        "rows",
        editor=pmt_spot_table,
        enabled_when="connected and not busy",
        height=PMT_SPOT_TABLE_MIN_HEIGHT,
    ),
    HGroup(
        UItem("start_button", enabled_when="connected and not busy and rows"),
        UItem("abort_button", enabled_when="capturing"),
        UItem("refresh_button", enabled_when="connected and not busy"),
    ),
    Item("progress", style="readonly", label="Status"),
    Item("results_directory", style="readonly", label="Saved to"),
)

results = VGroup(
    HGroup(
        UItem("show_results", editor=IconToggleEditor()),
        Label("Results"),
    ),
    VGroup(
        UItem(
            "results",
            editor=pmt_results_table,
            height=PMT_RESULTS_TABLE_MIN_HEIGHT,
        ),
        visible_when="show_results",
    ),
)

live = VGroup(
    HGroup(
        UItem("show_live", editor=IconToggleEditor()),
        Label("Live stream & acquire"),
    ),
    VGroup(
        HGroup(
            Item("gain", enabled_when="connected and not capturing and not acquiring"),
            Item(
                "stream_avg",
                label="Avg",
                editor=EnumEditor(values=_stream_avg_labels),
                enabled_when="connected and not capturing and not acquiring",
            ),
            Item(
                "stream_osr",
                label="OSR",
                editor=EnumEditor(values=_stream_osr_labels),
                enabled_when="connected and not capturing and not acquiring",
            ),
        ),
        HGroup(
            UItem("stream_start_button", enabled_when="connected and not busy"),
            UItem("stream_stop_button", enabled_when="streaming"),
            UItem("acquire_button", enabled_when="connected and not busy"),
        ),
        Item("live_units", label="Units"),
        Item("live_summary", style="readonly", label="Live"),
        UItem("live_values", editor=LivePlotEditor(y_label="live_axis_label")),
        Item("acquire_summary", style="readonly", label="Acquire"),
        visible_when="show_live",
    ),
)

conversion = VGroup(
    HGroup(
        UItem("show_conversion", editor=IconToggleEditor()),
        Label("Conversion"),
    ),
    VGroup(
        Item("rf_ohms", label="Rf (Ω)", editor=_rf_spin_box),
        Item("adc_display", style="readonly", label="ADC"),
        Item("vref_display", style="readonly", label="Vref"),
        UItem("conversion_note", editor=_hint_label),
        visible_when="show_conversion",
    ),
)

PmtCaptureView = View(
    VGroup(capture, results, live, conversion),
    resizable=True,
    scrollable=True,
)
