"""Dramatiq listener that feeds the heater plot model from telemetry.

Runs as its own listener (see ``plot_listener_name``), subscribed only to the
telemetry topic, so the plot pane is independent of the status pane. It reuses
the shared telemetry parsing and only pushes numbers into the plot model.
"""
import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import BaseMessageHandler
from logger.logger_service import get_logger

from heater_controls_ui.telemetry import telemetry_samples
from .model import HeaterPlotModel

logger = get_logger(__name__)


class HeaterPlotMessageHandler(BaseMessageHandler):
    """Appends telemetry samples to the plot model. The inherited connected /
    disconnected / realtime handlers never fire here — this listener subscribes
    to the telemetry topic only."""

    model = Instance(HeaterPlotModel)

    def _on_telemetry_triggered(self, body):
        try:
            data = json.loads(body)
        except Exception:
            logger.debug("Plot: failed to parse telemetry frame", exc_info=True)
            return
        if isinstance(data, dict):
            self.model.apply(telemetry_samples(data))
