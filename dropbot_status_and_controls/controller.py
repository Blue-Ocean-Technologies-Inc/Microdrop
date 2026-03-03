from traits.api import observe

from dropbot_controller.consts import SET_VOLTAGE, SET_FREQUENCY
from microdrop_utils.decorators import debounce
from logger.logger_service import get_logger

from template_status_and_controls.base_controller import BaseStatusController

logger = get_logger(__name__)


class ControlsController(BaseStatusController):
    """DropBot controls controller.

    Extends BaseStatusController with voltage and frequency control:
      - Debounced setattr methods prevent hardware flooding during slider drags.
      - Observers publish hardware commands, queuing them when not in realtime mode.

    Inherited from BaseStatusController:
      - message_dict, _publish_or_queue(), publish_queued_messages()
      - realtime_mode_setattr(), _on_realtime_mode_changed()
    """

    # ------------------------------------------------------------------ #
    # Debounced setattr                                                    #
    # ------------------------------------------------------------------ #

    @debounce(wait_seconds=0.3)
    def voltage_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def frequency_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    # ------------------------------------------------------------------ #
    # Observers                                                            #
    # ------------------------------------------------------------------ #

    @observe("model:voltage")
    def _on_voltage_changed(self, event):
        if self._publish_or_queue(topic=SET_VOLTAGE, message=str(event.new)):
            logger.debug(f"Voltage → {event.new} V")

    @observe("model:frequency")
    def _on_frequency_changed(self, event):
        if self._publish_or_queue(topic=SET_FREQUENCY, message=str(event.new)):
            logger.debug(f"Frequency → {event.new} Hz")
