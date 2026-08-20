import json

from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    SET_FLUORESCENCE_LED_RAW, SET_ILLUMINATION_RAW, SET_RGB_LIGHT,
    TEMP_CONTROL, TEMP_READ_INFO, TEMP_READ_PID, TEMP_SET_PID,
    TEMP_SET_TARGET,
)

logger = get_logger(__name__)


class TempLightingController(Controller):
    """Buttons and lighting edits -> request topics. Lighting is not
    actuation, so nothing here queues behind realtime mode."""

    # ------------------------------------------------------------------ #
    # Temperature control                                                  #
    # ------------------------------------------------------------------ #
    @observe("model:set_target_button")
    def _set_target(self, event):
        publish_message(topic=TEMP_SET_TARGET, message=json.dumps({
            "channel": int(self.model.temp_channel),
            "target_c": float(self.model.temp_target_c),
        }))

    def _temp_control(self, on):
        publish_message(topic=TEMP_CONTROL, message=json.dumps({
            "channel": int(self.model.temp_channel),
            "on": on,
        }))
        logger.info(f"Temp control ch{self.model.temp_channel} --> "
                    f"{'on' if on else 'off'}")

    @observe("model:start_button")
    def _start(self, event):
        self._temp_control(True)

    @observe("model:stop_button")
    def _stop(self, event):
        self._temp_control(False)

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
    # Lighting                                                             #
    # ------------------------------------------------------------------ #
    # Each lighting observer stays quiet while the handler is seeding
    # board-reported values into the model — the seed is a lossy
    # rescale (% and ‰ back to raw), so echoing it as a set would
    # actually nudge the hardware.
    @observe("model:rgb_light")
    def _on_rgb_light_changed(self, event):
        if self.model.seeding:
            return
        publish_message(topic=SET_RGB_LIGHT, message=str(event.new))
        logger.debug(f"RGB light --> {event.new}")

    @debounce(wait_seconds=0.3)
    def illumination_raw_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:illumination_raw")
    def _on_illumination_raw_changed(self, event):
        if self.model.seeding:
            return
        publish_message(topic=SET_ILLUMINATION_RAW,
                        message=str(int(event.new)))
        logger.debug(f"Illumination raw --> {event.new}")

    @debounce(wait_seconds=0.3)
    def fluorescence_led_raw_setattr(self, info, obj, traitname,
                                     value):
        return super().setattr(info, obj, traitname, value)

    @observe("model:fluorescence_led_raw")
    def _on_fluorescence_led_raw_changed(self, event):
        if self.model.seeding:
            return
        publish_message(topic=SET_FLUORESCENCE_LED_RAW,
                        message=str(int(event.new)))
        logger.debug(f"Fluorescence LED raw --> {event.new}")

    @observe("model:fluorescence_led_default_button")
    def _on_fluorescence_led_default(self, event):
        # The vendor tab's "Default (0)": zero the spinner and send it
        # regardless (the trait observer stays quiet when already 0).
        self.model.fluorescence_led_raw = 0
        publish_message(topic=SET_FLUORESCENCE_LED_RAW, message="0")
