# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""TraitsUI editor for a live-updating pyqtgraph plot bound to a 1-D numpy
array trait (x is always the sample index). Generic — no domain knowledge
of any particular pane."""

# Third-party imports.
import numpy as np
import pyqtgraph as pg

# Enthought library imports.
from traits.api import Int, Str
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class _LivePlotEditor(QtEditor):
    """The Qt half: a pyqtgraph PlotWidget with one curve, redrawn from the
    trait's numpy array on every ``update_editor()``."""

    #: Synced (mode="from") from the factory's ``y_label`` extended trait
    #: name, so the left-axis label tracks another trait on the object.
    y_label_value = Str()

    def init(self, parent):
        self.control = pg.PlotWidget()
        self.control.setMinimumHeight(self.factory.min_height)
        self.control.setLabel("bottom", self.factory.x_label)
        self._curve = self.control.plot(pen="y")

        self.sync_value(self.factory.y_label, "y_label_value", mode="from")
        self.control.setLabel("left", self.y_label_value)

        self.update_editor()

    def _y_label_value_changed(self, new):
        if self.control is not None:
            self.control.setLabel("left", new)

    def update_editor(self):
        if self.control is None:
            return

        values = self.value

        if values is None or len(values) == 0:
            self._curve.setData([], [])
            return

        self._curve.setData(np.arange(len(values)), np.asarray(values))


class LivePlotEditor(BasicEditorFactory):
    """Factory for a live pyqtgraph plot bound to a 1-D numpy array trait::

        UItem("live_values", editor=LivePlotEditor(y_label="live_axis_label"))

    ``y_label`` names an extended trait on the edited object supplying the
    left-axis label, kept in sync as it changes; leave empty for no label.
    ``x_label`` is a plain string (x is always the sample index).
    """

    klass = _LivePlotEditor

    y_label = Str()
    x_label = Str("sample")
    min_height = Int(180)
