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
from traitsui.api import EnumEditor, HGroup, Item, UItem, VGroup, View

# Local imports.
from .histogram_widget import LiveHistogramPlotEditor

plot = UItem("counts", editor=LiveHistogramPlotEditor())

controls = HGroup(
    UItem(
        "channel_mode",
        style="custom",
        # str keeps "RGB": the radio editor capitalizes labels otherwise.
        editor=EnumEditor(
            values={"luma": "1:Luma", "rgb": "2:RGB"}, cols=2, format_func=str
        ),
        tooltip="Plot brightness (luma), or the red, green, and blue channels",
    ),
    Item("log_y", label="Log", tooltip="Logarithmic count axis"),
    Item("paused", label="Pause", tooltip="Freeze the histogram"),
    Item("rate_hz", label="Hz", tooltip="Histogram updates per second"),
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
    VGroup(plot, controls, readouts),
    resizable=True,
)
