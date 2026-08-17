import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import SET_BUZZER, SET_FAN

logger = get_logger(__name__)


class PowerSystemController(Controller):
    """Buttons -> request topics, nothing else."""

    @observe("model:buzzer_on_button")
    def _buzzer_on(self, event):
        publish_message(topic=SET_BUZZER, message="True")

    @observe("model:buzzer_off_button")
    def _buzzer_off(self, event):
        publish_message(topic=SET_BUZZER, message="False")

    def _fan(self, board, on):
        publish_message(topic=SET_FAN,
                        message=json.dumps({"board": board, "on": on}))
        logger.info(f"{board} fan --> {'on' if on else 'off'}")

    @observe("model:mcu_fan_on_button")
    def _mcu_fan_on(self, event):
        self._fan("signal", True)

    @observe("model:mcu_fan_off_button")
    def _mcu_fan_off(self, event):
        self._fan("signal", False)

    @observe("model:motor_fan_on_button")
    def _motor_fan_on(self, event):
        self._fan("motor", True)

    @observe("model:motor_fan_off_button")
    def _motor_fan_off(self, event):
        self._fan("motor", False)
