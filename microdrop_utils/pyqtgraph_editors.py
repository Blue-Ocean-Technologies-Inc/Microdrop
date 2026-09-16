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
from pyface.qt import QtGui, QtWidgets
from traits.api import Int, Str
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor as QtEditor

# Microdrop style imports.
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_FIT_SCREEN

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
        self._plot = pg.PlotWidget()
        self._plot.setMinimumHeight(self.factory.min_height)
        self._plot.setLabel("bottom", self.factory.x_label)
        self._curve = self._plot.plot(pen="y")

        # A pan or zoom turns pyqtgraph's auto-range off for good; this
        # button turns it back on so the view follows the data again.
        reset_button = QtWidgets.QToolButton()
        reset_button.setFont(QtGui.QFont(ICON_FONT_FAMILY))
        reset_button.setText(ICON_FIT_SCREEN)
        reset_button.setToolTip("Reset view: rescale to the data")
        reset_button.clicked.connect(self._reset_view)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addStretch()
        toolbar.addWidget(reset_button)

        self.control = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self._plot)

        self.sync_value(self.factory.y_label, "y_label_value", mode="from")
        self._plot.setLabel("left", self.y_label_value)

        self.update_editor()

    def _reset_view(self):
        self._plot.enableAutoRange()

    def _y_label_value_changed(self, new):
        if self.control is not None:
            self._plot.setLabel("left", new)

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
