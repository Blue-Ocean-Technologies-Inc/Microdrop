import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    HOME_ALL,
    MOTOR_HOME,
    MOTOR_MOVE,
    MOTOR_STOP,
    MOVE_MAGNET,
    MOVE_TRAY,
    SET_FILTER,
    SET_POGO,
)

logger = get_logger(__name__)


class MotorsController(Controller):
    """Buttons -> request topics, nothing else: the panel repaints
    from motors_updated signals, never from its own optimism."""

    @observe("model:tray_in_button")
    def _tray_in(self, event):
        publish_message(topic=MOVE_TRAY, message="in")

    @observe("model:tray_out_button")
    def _tray_out(self, event):
        publish_message(topic=MOVE_TRAY, message="out")

    @observe("model:magnet_engage_button")
    def _magnet_engage(self, event):
        publish_message(topic=MOVE_MAGNET, message="engage")

    @observe("model:magnet_disengage_button")
    def _magnet_disengage(self, event):
        publish_message(topic=MOVE_MAGNET, message="disengage")

    @observe("model:magnet_press_button")
    def _magnet_press(self, event):
        publish_message(topic=MOVE_MAGNET, message="press")

    @observe("model:magnet_release_button")
    def _magnet_release(self, event):
        publish_message(topic=MOVE_MAGNET, message="release")

    @observe("model:pogo_down_button")
    def _pogo_down(self, event):
        publish_message(topic=SET_POGO, message="True")

    @observe("model:pogo_up_button")
    def _pogo_up(self, event):
        publish_message(topic=SET_POGO, message="False")

    @observe("model:home_all_button")
    def _home_all(self, event):
        publish_message(topic=HOME_ALL, message="True")

    @observe("model:filter_position")
    def _filter_changed(self, event):
        publish_message(topic=SET_FILTER, message=str(int(event.new)))

    @observe("model:move_button")
    def _move(self, event):
        publish_message(topic=MOTOR_MOVE, message=json.dumps({
            "motor": self.model.selected_motor,
            "mode": self.model.move_mode,
            "value": int(self.model.move_steps),
        }))

    @observe("model:stop_button")
    def _stop(self, event):
        publish_message(topic=MOTOR_STOP,
                        message=self.model.selected_motor)

    @observe("model:home_button")
    def _home(self, event):
        publish_message(topic=MOTOR_HOME,
                        message=self.model.selected_motor)
