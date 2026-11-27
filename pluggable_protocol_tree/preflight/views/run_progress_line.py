# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The run-progress line along the status bar's top edge (#1211): filled in
the accent colour with the run's completed steps, empty while idle."""

# Enthought library imports.
from pyface.qt import QtGui, QtWidgets
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_status_bar.consts import STATUS_BAR_SIDE_TOP_EDGE

# Microdrop style imports.
from microdrop_style.colors import ACCENT_COLOR

# Local imports.
from ..models import RunInfo
from .view_consts import RUN_PROGRESS_LINE_PX


class RunProgressLine(QtWidgets.QWidget):
    """A thin line filled to ``fraction`` of its width; draws nothing while
    no run is ``active``."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.status_bar_side = STATUS_BAR_SIDE_TOP_EDGE
        self.setFixedHeight(RUN_PROGRESS_LINE_PX)

        self._active = False
        self._fraction = 0.0

    def show_progress(self, active, fraction):
        """Fill ``fraction`` (0-1) of the line while ``active``."""
        self._active = active
        self._fraction = fraction
        self.update()

    def paintEvent(self, event):
        if not self._active:
            return

        painter = QtGui.QPainter(self)
        painter.fillRect(
            0,
            0,
            round(self.width() * self._fraction),
            self.height(),
            QtGui.QColor(ACCENT_COLOR),
        )
        painter.end()


class RunProgressController(HasTraits):
    """Keeps a progress line in step with the run."""

    #: The run in progress, if any.
    run_info = Instance(RunInfo)

    #: The line drawn.
    line = Instance(RunProgressLine)

    @observe("run_info.[active, completed_fraction], line", dispatch="ui")
    def _update_line(self, event):
        if None in (self.line, self.run_info):
            return

        self.line.show_progress(self.run_info.active, self.run_info.completed_fraction)
