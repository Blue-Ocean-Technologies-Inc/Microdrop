# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The heater auto-tune live plot's canvas, shown once a run has a
reading; standalone-instantiable as
``HeaterTunePlot().edit_traits(view=HeaterTunePlotView)``."""

# Enthought library imports.
from traitsui.api import UItem, VGroup, View

# Microdrop utils imports.
from microdrop_utils.matplotlib_editors import MatplotlibFigureEditor

# Local imports.
from ..consts import HEATER_TUNE_PLOT_HEIGHT

HeaterTunePlotView = View(
    VGroup(
        UItem(
            "figure",
            resizable=True,
            editor=MatplotlibFigureEditor(
                min_height=HEATER_TUNE_PLOT_HEIGHT, follow_dark_theme=True
            ),
            visible_when="figure is not None",
        ),
    ),
)
