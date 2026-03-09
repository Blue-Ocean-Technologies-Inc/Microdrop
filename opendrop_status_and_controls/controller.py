from opendrop_controller.consts import (
    SET_TEMPERATURE_1,
    SET_TEMPERATURE_2,
    SET_TEMPERATURE_3,
)
from template_status_and_controls.base_controller import BaseStatusController

from traits.api import observe

from logger.logger_service import get_logger
logger = get_logger(__name__)


class ControlsController(BaseStatusController):
    """OpenDrop controls controller.

    All logic (realtime-mode toggle, message queueing, debounced setattr)
    is inherited from BaseStatusController. OpenDrop has no additional
    hardware parameters to control from the UI.
    """

    # ------------------------------------------------------------------ #
    # Observers                                                            #
    # ------------------------------------------------------------------ #

    @observe("model:set_temperature_1")
    def _on_temperature_1_changed(self, event):
        if self._publish_or_queue(topic=SET_TEMPERATURE_1, message=str(event.new)):
            logger.info(f"Set temperature 1 to {event.new}")

    @observe("model:set_temperature_2")
    def _on_temperature_2_changed(self, event):
        if self._publish_or_queue(topic=SET_TEMPERATURE_2, message=str(event.new)):
            logger.info(f"Set temperature 2 to {event.new}")

    @observe("model:set_temperature_3")
    def _on_temperature_3_changed(self, event):
        if self._publish_or_queue(topic=SET_TEMPERATURE_3, message=str(event.new)):
            logger.info(f"Set temperature 3 to {event.new}")
