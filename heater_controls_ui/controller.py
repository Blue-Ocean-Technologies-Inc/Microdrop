import json

from traits.api import observe

from template_status_and_controls.base_controller import BaseStatusController
from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from heater_controller.consts import (
    SET_TEMPERATURE, SET_PWM, SET_PID_MODE, SET_STREAM,
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

    # ------------------------------------------------------------------ #
    # Observers → published commands                                       #
    # ------------------------------------------------------------------ #
    @observe("model:temperature")
    def _on_temperature_changed(self, event):
        self._publish(SET_TEMPERATURE, self._heater_payload(temperature=event.new))
        logger.debug(f"Temperature → {event.new} °C")

    @observe("model:pwm")
    def _on_pwm_changed(self, event):
        self._publish(SET_PWM, self._heater_payload(pwm=event.new))
        logger.debug(f"PWM → {event.new} %")

    @observe("model:pid_active")
    def _on_pid_active_changed(self, event):
        mode = "enable" if event.new else "disable"
        self._publish(SET_PID_MODE, self._heater_payload(mode=mode))
        if event.new:
            # Push the current setpoint so PID has a target to regulate to, and
            # auto-start streaming so the PID temperature is reported. Setting the
            # trait drives the stream toggle + its publish (no-op if already on).
            self._publish(SET_TEMPERATURE, self._heater_payload(temperature=self.model.temperature))
            self.model.stream_active = True

    @observe("model:stream_active")
    def _on_stream_active_changed(self, event):
        self._publish(SET_STREAM, {"group": "all" if event.new else "stop"})
