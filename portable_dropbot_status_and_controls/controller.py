from traits.api import observe

from logger.logger_service import get_logger
from microdrop_utils.decorators import debounce
from portable_dropbot_controller.consts import SET_FREQUENCY, SET_VOLTAGE
from template_status_and_controls.base_controller import (
    BaseStatusController,
)

logger = get_logger(__name__)


class ControlsController(BaseStatusController):
    """Portable Dropbot controls controller: voltage and frequency
    edits publish to the portable backend (queued while realtime mode
    is off, exactly as the DropBot pane does)."""

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:voltage")
    def _on_voltage_changed(self, event):
        if self._publish_or_queue(topic=SET_VOLTAGE,
                                  message=str(int(event.new))):
            logger.debug(f"Voltage --> {event.new} V")

    @observe("model:frequency")
    def _on_frequency_changed(self, event):
        if self._publish_or_queue(topic=SET_FREQUENCY,
                                  message=str(int(event.new))):
            logger.debug(f"Frequency --> {event.new} Hz")
