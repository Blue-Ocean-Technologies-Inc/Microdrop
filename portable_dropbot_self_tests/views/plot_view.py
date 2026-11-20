# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One figure tab of the hub: the view choice and the canvas. Instantiable
alone against a SelfTestPlot."""

# Enthought library imports.
from traitsui.api import EnumEditor, UItem, VGroup, View

# Microdrop utils imports.
from microdrop_utils.matplotlib_editors import MatplotlibFigureEditor

#: Canvas height (px) of a figure tab.
PLOT_CANVAS_HEIGHT_PX = 340

plot_view = View(
    VGroup(
        UItem(
            "view",
            editor=EnumEditor(name="view_labels"),
            visible_when="view_labels",
            enabled_when="has_views",
            tooltip="Which values the figure shows",
        ),
        UItem(
            "figure",
            resizable=True,
            editor=MatplotlibFigureEditor(min_height=PLOT_CANVAS_HEIGHT_PX),
            visible_when="figure is not None",
        ),
        UItem(
            "plot_error", style="readonly", resizable=True, visible_when="plot_error"
        ),
    ),
)
