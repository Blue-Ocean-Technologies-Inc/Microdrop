# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Live Histogram pane: the plot on top, its display controls, and the
exposure readouts below. Instantiable standalone against the model:
``LiveHistogramModel().edit_traits(view=LiveHistogramView)``."""

# Enthought library imports.
from traitsui.api import HGroup, Item, Label, Spring, UItem, VGroup, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    InPlaceToggleEditor,
    SlidingToggleEditor,
    SteppedSliderEditor,
)

# Local imports.
from ...consts import LIVE_HISTOGRAM_PLOT_STYLES, LIVE_HISTOGRAM_RATE_BOUNDS_HZ
from .histogram_widget import LiveHistogramPlotEditor

plot = UItem("counts", editor=LiveHistogramPlotEditor())

#: Fixed width of a sliding switch (the Toggle's own size hint); stretched,
#: it pushes the state name on its right away from it.
SWITCH_WIDTH = -58

# Each two-state choice is a sliding switch with its off state named on the
# left and its on state on the right.
switches = HGroup(
    HGroup(
        Label("Luma"),
        UItem(
            "channel_mode",
            editor=SlidingToggleEditor(on_value="rgb", off_value="luma"),
            width=SWITCH_WIDTH,
            tooltip="Plot brightness (luma), or the red, green, and blue channels",
        ),
        Label("RGB"),
    ),
    Spring(width=24, springy=False),
    HGroup(
        Label("Bars"),
        UItem(
            "plot_style",
            editor=SlidingToggleEditor(
                on_value=LIVE_HISTOGRAM_PLOT_STYLES[1],
                off_value=LIVE_HISTOGRAM_PLOT_STYLES[0],
            ),
            width=SWITCH_WIDTH,
            tooltip=(
                "Filled bars per level, or just the density curve (cheaper to draw)"
            ),
        ),
        Label("Curve"),
    ),
    Spring(),
)

feed_controls = HGroup(
    UItem(
        "log_y",
        editor=InPlaceToggleEditor(on_label="Log Y", off_label="Linear Y"),
        tooltip="Logarithmic count axis",
    ),
    UItem(
        "paused",
        editor=InPlaceToggleEditor(on_label="Paused", off_label="Live"),
        tooltip="Freeze the histogram",
    ),
    UItem(
        "rate_hz",
        editor=SteppedSliderEditor(
            low=LIVE_HISTOGRAM_RATE_BOUNDS_HZ[0],
            high=LIVE_HISTOGRAM_RATE_BOUNDS_HZ[1],
            step=1,
            integer=True,
            format="%d Hz",
        ),
        tooltip="Histogram updates per second",
        springy=True,
    ),
)

readouts = VGroup(
    Item("status_text", style="readonly", label="Feed"),
    Item(
        "clipping_text",
        style="readonly",
        label="Clipped",
        tooltip="Share of pixels at the darkest and the brightest level",
    ),
    Item("mean_text", style="readonly", label="Mean"),
    Item(
        "range_text",
        style="readonly",
        label="1–99 %",
        tooltip="Levels below which 1 % and 99 % of the pixels fall",
    ),
)

LiveHistogramView = View(
    VGroup(plot, switches, feed_controls, readouts),
    resizable=True,
)
