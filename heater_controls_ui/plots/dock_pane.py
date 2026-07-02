"""Heater Plots dock pane.

A lean pyface DockPane hosting the matplotlib canvas. It owns the plot model
and its own telemetry listener, so it needs nothing from the status pane.
"""
from traits.api import Any, Instance
from pyface.tasks.dock_pane import DockPane
from PySide6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from logger.logger_service import get_logger

from .consts import PLOT_DOCK_PANE_ID, PLOT_DOCK_PANE_NAME, plot_listener_name
from .model import HeaterPlotModel
from .message_handler import HeaterPlotMessageHandler
from .canvas import HeaterPlotCanvas

logger = get_logger(__name__)


class HeaterPlotDockPane(DockPane):
    """Live temperature / PWM plots for the heater."""

    id = PLOT_DOCK_PANE_ID
    name = PLOT_DOCK_PANE_NAME

    #: Qt-free buffers, shared between the telemetry listener (writer) and the
    #: canvas (reader).
    model = Instance(HeaterPlotModel, ())
    message_handler = Instance(HeaterPlotMessageHandler)
    _canvas = Any()

    def traits_init(self):
        # Start the telemetry listener up front so samples accumulate even
        # before the pane is first shown.
        self.message_handler = HeaterPlotMessageHandler(
            model=self.model, name=plot_listener_name)

    def create_contents(self, parent):
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._canvas = HeaterPlotCanvas(self.model, parent=container)
        # Pan / zoom / save-image toolbar, handy for inspecting a run.
        layout.addWidget(NavigationToolbar2QT(self._canvas, container))
        layout.addWidget(self._canvas)
        return container

    def destroy(self):
        if self._canvas is not None:
            self._canvas.stop()
            self._canvas = None
        super().destroy()
