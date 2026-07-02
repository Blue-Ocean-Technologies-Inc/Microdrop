"""Heater Plots dock pane.

A lean pyface DockPane hosting the matplotlib canvas. It owns the plot model
and its own telemetry listener, so it needs nothing from the status pane. The
Pause / Stop buttons only flip model traits (paused / enabled) — the canvas
reads those on its timer, keeping the model/view separation intact.
"""
from traits.api import Any, Instance
from pyface.tasks.dock_pane import DockPane
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_PAUSE, ICON_STOP
from logger.logger_service import get_logger

from heater_controls_ui.consts import plot_listener_name

from .consts import (
    PLOT_DOCK_PANE_ID, PLOT_DOCK_PANE_NAME,
    PAUSE_PLOT_TOOLTIP, STOP_PLOT_TOOLTIP,
)
from .model import HeaterPlotModel
from .message_handler import HeaterPlotMessageHandler
from .canvas import HeaterPlotCanvas

logger = get_logger(__name__)


class HeaterPlotDockPane(DockPane):
    """Live temperature / PWM plots for the heater."""

    id = PLOT_DOCK_PANE_ID
    name = PLOT_DOCK_PANE_NAME

    #: Qt-free buffers + plot run state, shared between the telemetry listener
    #: (writer) and the canvas (reader).
    model = Instance(HeaterPlotModel, ())
    message_handler = Instance(HeaterPlotMessageHandler)
    _canvas = Any()
    _pause_button = Any()
    _stop_button = Any()

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

        # Pan / zoom / save-image toolbar plus the pause / stop toggles.
        toolbar_row = QHBoxLayout()
        toolbar_row.addWidget(NavigationToolbar2QT(self._canvas, container))
        toolbar_row.addStretch(1)
        self._pause_button = self._make_toggle_button(
            container, ICON_PAUSE, PAUSE_PLOT_TOOLTIP, self._on_pause_toggled)
        toolbar_row.addWidget(self._pause_button)
        self._stop_button = self._make_toggle_button(
            container, ICON_STOP, STOP_PLOT_TOOLTIP, self._on_stop_toggled)
        toolbar_row.addWidget(self._stop_button)

        layout.addLayout(toolbar_row)
        layout.addWidget(self._canvas)
        return container

    def destroy(self):
        if self._canvas is not None:
            self._canvas.stop()
            self._canvas = None
        # Release the plot listener's Dramatiq actor name so a re-mounted
        # pane can register fresh (runtime hot unload/reload).
        if self.message_handler is not None:
            self.message_handler.teardown()
            self.message_handler = None
        super().destroy()

    # ------------------------------------------------------------------ #
    # Pause / Stop (view -> model traits; the canvas polls them)           #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_toggle_button(parent, glyph, tooltip, on_toggled):
        button = QToolButton(parent)
        button.setCheckable(True)
        button.setText(glyph)
        button.setFont(QFont(ICON_FONT_FAMILY))
        button.setToolTip(tooltip)
        button.toggled.connect(on_toggled)
        return button

    def _on_pause_toggled(self, checked):
        self.model.paused = checked

    def _on_stop_toggled(self, checked):
        self.model.enabled = not checked
        # Pausing a stopped plot is meaningless — grey the button out.
        self._pause_button.setEnabled(not checked)
