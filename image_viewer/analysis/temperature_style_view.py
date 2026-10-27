# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Temperature over time view's style panel: a table of the loaded
log's sensors over the bold line, capture-marker and legend settings.
A declarative View of a TemperaturePlotStyle — instantiable on its own
with ``TemperaturePlotStyle().edit_traits(view=temperature_style_view)``.
The plot pane shows it in place of the ROI table while that view is
up."""

# Enthought library imports.
from traitsui.api import HGroup, Item, Label, TableEditor, UItem, VGroup, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    ColorColumn,
    HexColorEditor,
    ObjectColumn,
    RangeColumn,
    VisibleColumn,
)

#: Width (px) of the small number boxes: line widths and marker sizes.
STYLE_NUMBER_W = -60

#: The sensor rows, editable in place like the ROI table's style
#: columns: the eye, the colour swatch (double-click for the picker),
#: line style, width and opacity.
SENSOR_STYLE_TABLE_EDITOR = TableEditor(
    columns=[
        VisibleColumn(
            name="visible", label="", editable=False, horizontal_alignment="center"
        ),
        ObjectColumn(name="sensor", label="Sensor", editable=False),
        ColorColumn(name="color", label="Color", editor=HexColorEditor()),
        ObjectColumn(name="line_style", label="Line"),
        ObjectColumn(name="line_width", label="Width"),
        RangeColumn(name="alpha", label="Alpha"),
    ],
    sortable=False,
)

temperature_style_view = View(
    VGroup(
        UItem("shown_sensors", editor=SENSOR_STYLE_TABLE_EDITOR),
        HGroup(
            Label("Bold line"),
            UItem("line_color", editor=HexColorEditor(), tooltip="Colour"),
            UItem("line_style", tooltip="Line style"),
            Item("line_width", label="width", width=STYLE_NUMBER_W),
            Item("line_alpha", label="alpha", tooltip="Opacity (%)"),
            Item(
                "show_legend",
                label="Legend",
                tooltip="Show the legend on the figure",
            ),
        ),
        HGroup(
            Label("Captures"),
            UItem("capture_marker", tooltip="Marker at each analysed capture"),
            Item("capture_size", label="size", width=STYLE_NUMBER_W),
            Item("capture_alpha", label="alpha", tooltip="Opacity (%)"),
            Item(
                "capture_color_follows_line",
                label="Line colour",
                tooltip="Draw the capture markers in the bold line's colour",
            ),
            UItem(
                "capture_color",
                editor=HexColorEditor(),
                enabled_when="not capture_color_follows_line",
                tooltip="The capture markers' own colour",
            ),
            Item(
                "excluded_size",
                label="Excluded size",
                width=STYLE_NUMBER_W,
                tooltip="Size of the hollow markers at excluded captures",
            ),
            Item(
                "excluded_alpha",
                label="alpha",
                tooltip="Opacity (%) of the hollow markers at excluded captures",
            ),
        ),
    ),
    resizable=True,
)
