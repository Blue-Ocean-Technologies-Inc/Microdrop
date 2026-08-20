import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    PMT_ACQUIRE, PMT_POWER, PMT_SET_GAIN,
    TEMP_CONTROL, TEMP_READ_INFO, TEMP_READ_PID, TEMP_SET_PID,
    TEMP_SET_TARGET,
)

logger = get_logger(__name__)


class MoreControlsController(Controller):
    """Toggles and buttons -> request topics. PMT results come back
    through the message handler on PMT_UPDATED."""

    # ------------------------------------------------------------------ #
    # Temperature control                                                  #
    # ------------------------------------------------------------------ #
    @observe("model:set_target_button")
    def _set_target(self, event):
        publish_message(topic=TEMP_SET_TARGET, message=json.dumps({
            "channel": int(self.model.temp_channel),
            "target_c": float(self.model.temp_target_c),
        }))

    @observe("model:temp_control_on")
    def _on_temp_control_changed(self, event):
        publish_message(topic=TEMP_CONTROL, message=json.dumps({
            "channel": int(self.model.temp_channel),
            "on": bool(event.new),
        }))
        logger.info(f"Temp control ch{self.model.temp_channel} --> "
                    f"{'on' if event.new else 'off'}")

    @observe("model:read_info_button")
    def _read_info(self, event):
        publish_message(topic=TEMP_READ_INFO,
                        message=str(int(self.model.temp_channel)))

    @observe("model:read_pid_button")
    def _read_pid(self, event):
        publish_message(topic=TEMP_READ_PID,
                        message=str(int(self.model.temp_channel)))

    @observe("model:apply_pid_button")
    def _apply_pid(self, event):
        publish_message(topic=TEMP_SET_PID, message=json.dumps({
            "channel": int(self.model.temp_channel),
            "kp": float(self.model.pid_kp),
            "ki": float(self.model.pid_ki),
            "kd": float(self.model.pid_kd),
            "period_ms": int(self.model.pid_period_ms),
        }))

    # ------------------------------------------------------------------ #
    # PMT                                                                  #
    # ------------------------------------------------------------------ #
    @observe("model:pmt_power")
    def _on_pmt_power_changed(self, event):
        publish_message(topic=PMT_POWER, message=str(bool(event.new)))
        logger.info(f"PMT power --> {'on' if event.new else 'off'}")

    @observe("model:set_gain_button")
    def _set_gain(self, event):
        publish_message(topic=PMT_SET_GAIN,
                        message=str(int(self.model.pmt_gain)))

    @observe("model:acquire_button")
    def _acquire(self, event):
        self.model.pmt_status_display = "acquiring..."
        publish_message(topic=PMT_ACQUIRE, message=json.dumps(
            {"gain": int(self.model.pmt_gain)}))
        logger.info("Requested PMT acquire macro")
