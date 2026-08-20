import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import SET_BUZZER, SET_FAN

logger = get_logger(__name__)


class PowerSystemController(Controller):
    """Toggles -> request topics, nothing else."""

    @observe("model:buzzer_state")
    def _buzzer_state_change(self, event):
        publish_message(topic=SET_BUZZER, message=str(event.new))
        logger.debug(f"Buzzer state change to {event.new} requested: "
                     f"published to {SET_BUZZER}")

    @observe("model:mcu_fan_state")
    def _mcu_fan_state_change(self, event):
        publish_message(topic=SET_FAN,
                        message=json.dumps({"board": "signal",
                                            "on": event.new}))
        logger.debug(f"MCU fan state change to {event.new} requested: "
                     f"published to {SET_FAN}")