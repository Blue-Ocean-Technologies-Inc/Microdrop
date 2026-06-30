import json

from traits.api import Instance

from template_status_and_controls.base_message_handler import BaseMessageHandler
from logger.logger_service import get_logger

from .consts import PWM_MIN, PWM_MAX
from .model import HeaterStatusModel
from .telemetry import resolve_selection, format_telemetry

logger = get_logger(__name__)

# ERR kinds that mean the board stopped driving the heater → reflect as halted.
HALTING_ERR_KINDS = ("overtemp", "task_crash", "sensor_fail")


class HeaterMessageHandler(BaseMessageHandler):
    """Dramatiq message handler for the heater UI.

    Inherits the common connected / disconnected handlers from BaseMessageHandler.
    Adds heater-specific handlers for the available-heaters list and telemetry.
    """

    model = Instance(HeaterStatusModel)

    def _on_heaters_available_triggered(self, body):
        try:
            heaters = json.loads(body)
        except Exception:
            return
        if not isinstance(heaters, list):
            return
        self.model.available_heaters = list(heaters)
        self.model.trait_set(**resolve_selection(self.model.selected_heater, heaters))

    def _on_telemetry_triggered(self, body):
        try:
            data = json.loads(body)
        except Exception:
            logger.error("Failed to parse telemetry", exc_info=True)
            return
        if not isinstance(data, dict):
            logger.debug("Failed to parse telemetry")
            return

        heater, updates = format_telemetry(data, pid_mode=self.model.mode == "Temp")
        if updates:
            if heater is None:
                self.model.trait_set(**updates)        # global readouts
            else:
                readout = self._readout_for(heater)    # per-heater row
                if readout is not None:
                    readout.trait_set(**updates)

        # In Temp mode the PID regulates the duty; mirror the selected heater's
        # live duty into the open-loop `pwm` setpoint so the "Set PWM" field
        # tracks the real value (and switching back to PWM mode resumes from it,
        # not a stale value). The pwm observer ignores writes while mode != "PWM",
        # so this publishes no command.
        if self.model.mode == "Temp" and heater == self.model.selected_heater:
            live_pwm = data.get("pwm_percentage")
            if isinstance(live_pwm, (int, float)):
                self.model.pwm = max(PWM_MIN, min(PWM_MAX, round(live_pwm)))

        if data.get("_frame") == "ERR" and data.get("kind") in HALTING_ERR_KINDS:
            self.model.halted = True

    def _readout_for(self, name):
        """The HeaterReadout row for ``name``, or None if not yet known (the
        heaters_available signal that creates the rows may lag the first frame)."""
        for readout in self.model.heater_readouts:
            if readout.name == name:
                return readout
        return None
