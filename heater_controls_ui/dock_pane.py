import json

from traits.api import Instance, observe
from pyface.tasks.api import TraitsDockPane

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from logger.logger_service import get_logger

from heater_controller.consts import (
    SET_TEMPERATURE,
    SET_PWM,
    SET_PID_MODE,
    SET_STREAM,
    SET_FAN,
    ALL_OFF,
    START_DEVICE_MONITORING,
)

from .model import HeaterControlModel
from .view import heater_view
from .listener import HeaterControlListener
from .consts import PKG, PKG_name

logger = get_logger(__name__)


class HeaterControlDockPane(TraitsDockPane):
    """Controller: owns the model + connection/telemetry listener, and turns model
    button presses into published command topics."""

    id = PKG + ".pane"
    name = "Heater Controls"

    model = Instance(HeaterControlModel, ())
    traits_view = heater_view

    def __init__(self, **traits):
        super().__init__(**traits)
        # The listener writes connection/telemetry state into the same model.
        self._listener = HeaterControlListener(model=self.model)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _publish(topic, payload):
        msg = json.dumps(payload)
        logger.info(f"Publishing to {topic}: {msg}")
        publish_message(message=msg, topic=topic)

    def _heater_payload(self, **extra):
        """Payload including the selected heater (omitted when none selected, so
        the backend applies its tec1 default)."""
        payload = dict(extra)
        if self.model.selected_heater:
            payload["heater"] = self.model.selected_heater
        return payload

    # -- command observers ---------------------------------------------------
    @observe("model:apply_temperature")
    def _apply_temperature(self, event):
        self._publish(SET_TEMPERATURE, self._heater_payload(temperature=self.model.temperature))

    @observe("model:apply_pwm")
    def _apply_pwm(self, event):
        self._publish(SET_PWM, self._heater_payload(pwm=self.model.pwm))

    @observe("model:pid_enable")
    def _pid_enable(self, event):
        self._publish(SET_PID_MODE, self._heater_payload(mode="enable"))

    @observe("model:pid_disable")
    def _pid_disable(self, event):
        self._publish(SET_PID_MODE, self._heater_payload(mode="disable"))

    @observe("model:pid_stop")
    def _pid_stop(self, event):
        self._publish(SET_PID_MODE, self._heater_payload(mode="stop"))

    @observe("model:stream_start")
    def _stream_start(self, event):
        self._publish(SET_STREAM, {"group": self.model.stream_group})

    @observe("model:stream_stop")
    def _stream_stop(self, event):
        self._publish(SET_STREAM, {"group": "stop"})

    @observe("model:fan_on")
    def _fan_on(self, event):
        self._publish(SET_FAN, {"on": True})

    @observe("model:fan_off")
    def _fan_off(self, event):
        self._publish(SET_FAN, {"on": False})

    @observe("model:all_off")
    def _all_off(self, event):
        publish_message(message="", topic=ALL_OFF)

    @observe("model:connect")
    def _connect(self, event):
        logger.info("Requesting heater connection monitoring")
        publish_message(message="", topic=START_DEVICE_MONITORING)
