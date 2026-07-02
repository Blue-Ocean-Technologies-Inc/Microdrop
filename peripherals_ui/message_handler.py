"""Dramatiq message handler for the peripherals (Z-Stage) UI.

Replaces the old DramatiqStatusController + DramatiqStatusViewModel pair with
the shared BaseMessageHandler (reflection dispatch, timestamped dedup guards,
and teardown() for runtime hot unload). Handlers write to PeripheralModel,
whose ``status`` trait is the Z-Stage's connected flag.
"""
import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import BaseMessageHandler
from microdrop_utils.decorators import timestamped_value
from logger.logger_service import get_logger

from .model import PeripheralModel

logger = get_logger(__name__)


class PeripheralMessageHandler(BaseMessageHandler):
    """Updates the Z-Stage model from ZStage/signals/# plus the realtime-mode
    and start-monitoring request topics the pane also listens to."""

    model = Instance(PeripheralModel)

    # PeripheralModel exposes the connection flag as ``status`` (the z_stage
    # view-model observes it), so the shared connected/disconnected handlers
    # are overridden to write that trait. Dedup guards stay.
    @timestamped_value("connected_message")
    def _on_connected_triggered(self, body):
        logger.info(f"{self.model.device_name} connected: {body}")
        self.model.status = True

    @timestamped_value("connected_message")
    def _on_disconnected_triggered(self, body):
        logger.info(f"{self.model.device_name} disconnected: {body}")
        self.model.status = False
        self.model.realtime_mode = False

    @timestamped_value("realtime_mode_message")
    def _on_set_realtime_mode_triggered(self, body):
        # The pane subscribes to the SET_REALTIME_MODE request topic (last
        # segment "set_realtime_mode"), not the dropbot's realtime_mode_updated.
        self.model.realtime_mode = body == "True"

    def _on_position_updated_triggered(self, body):
        self.model.position = float(body)

    def _on_start_device_monitoring_triggered(self, body):
        self.model.search_requested = True

    def _on_searching_triggered(self, body):
        """Backend connection-scan state (JSON bool). Mirrored to the model so
        the pane can disable the status-icon 'search connection' click while a
        scan is already running."""
        try:
            self.model.searching = bool(json.loads(body))
        except Exception:
            logger.error("Failed to parse searching signal", exc_info=True)
