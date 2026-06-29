import json

from traits.api import observe

from template_status_and_controls.base_controller import BaseStatusController
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from heater_controller.consts import (
    SET_TEMPERATURE, SET_PWM, SET_PID_MODE, SET_STREAM, ALL_OFF,
)

logger = get_logger(__name__)


class HeaterControlsController(BaseStatusController):
    """Heater controls controller.

    Translates model changes into published command topics. The heater has no
    realtime-queue concept (the backend rejects commands while disconnected and
    the view disables controls then), so commands publish directly rather than
    going through the base realtime queue.
    """

    # ------------------------------------------------------------------ #
    # Debounced setattr (prevents flooding while dragging the spinboxes)   #
    # ------------------------------------------------------------------ #
    @debounce(wait_seconds=0.3)
    def temperature_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    @debounce(wait_seconds=0.3)
    def pwm_setattr(self, info, obj, traitname, value):
        return super().setattr(info, obj, traitname, value)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #
    def _heater_payload(self, **extra):
        """Payload including the selected heater (omitted when none selected, so
        the backend applies its tec1 default)."""
        payload = dict(extra)
        if self.model.selected_heater:
            payload["heater"] = self.model.selected_heater
        return payload

    @staticmethod
    def _publish(topic, payload):
        publish_message(message=json.dumps(payload), topic=topic)

    def _apply_mode(self):
        """Drive the board to the current mode's state. Called only while
        streaming is on (the master gate). Temp runs closed-loop PID toward the
        temperature setpoint; PWM disables PID and drives the open-loop duty."""
        if self.model.mode == "Temp":
            self._publish(SET_PID_MODE, self._heater_payload(mode="enable"))
            self._publish(SET_TEMPERATURE, self._heater_payload(temperature=self.model.temperature))
        else:
            self._publish(SET_PID_MODE, self._heater_payload(mode="disable"))
            self._publish(SET_PWM, self._heater_payload(pwm=self.model.pwm))

    # ------------------------------------------------------------------ #
    # Observers → published commands                                       #
    # ------------------------------------------------------------------ #
    # Setpoint edits only reach the board while streaming (the master gate) and
    # only for the active mode; otherwise they are staged and pushed by
    # _apply_mode when streaming starts.
    @observe("model:temperature")
    def _on_temperature_changed(self, event):
        if self.model.mode != "Temp":
            return
        if self.model.stream_active:
            self._publish(SET_TEMPERATURE, self._heater_payload(temperature=event.new))
            logger.debug(f"Temperature → {event.new} °C")
        else:
            logger.debug(f"Temperature setpoint {event.new} °C staged (stream off)")
            self.model.stream_off_edit_warning = True

    @observe("model:pwm")
    def _on_pwm_changed(self, event):
        if self.model.mode != "PWM":
            return
        if self.model.stream_active:
            self._publish(SET_PWM, self._heater_payload(pwm=event.new))
            logger.debug(f"PWM → {event.new} %")
        else:
            logger.debug(f"PWM duty {event.new} % staged (stream off)")
            self.model.stream_off_edit_warning = True

    @observe("model:mode")
    def _on_mode_changed(self, event):
        # Switching mode re-applies the board state for the new mode, but only
        # while streaming. While stream is off the mode is staged (applied by
        # _apply_mode when streaming starts).
        if self.model.stream_active:
            self._apply_mode()
            logger.debug(f"Mode → {event.new}")

    @observe("model:stream_active")
    def _on_stream_active_changed(self, event):
        if event.new:
            # Start telemetry, then drive the board to the UI's current state.
            self._publish(SET_STREAM, {"group": "all"})
            self._apply_mode()
        else:
            # Master-gate off: idle the board and stop telemetry, so nothing is
            # driven and no data flows while streaming is off.
            self._publish(ALL_OFF, {})
            self._publish(SET_STREAM, {"group": "stop"})
