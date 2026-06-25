import json

import dramatiq
from traits.api import HasTraits, Instance, Str
from pyface.api import GUI

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    basic_listener_actor_routine,
    generate_class_method_dramatiq_listener_actor,
)

from .model import HeaterControlModel
from .consts import listener_name

logger = get_logger(__name__)

INVALID_TEMP_THRESHOLD = -40  # telemetry sends sentinels below this when no reading


class HeaterControlListener(HasTraits):
    """Listens to ``Heater/signals/...`` and pushes updates into the model.

    Handlers fire on dramatiq worker threads, so every model write is marshaled
    onto the GUI thread via ``GUI.invoke_later`` (TraitsUI editors must update on
    the UI thread, and telemetry streams quickly).
    """

    model = Instance(HeaterControlModel)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    name = Str(listener_name)

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine,
        )

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(
            self, message, topic,
            handler_name_pattern="_on_{topic}_triggered",
        )

    # -- helpers -------------------------------------------------------------
    def _set(self, **kw):
        """Apply model trait updates on the GUI thread."""
        if self.model is None:
            return
        GUI.invoke_later(self.model.trait_set, **kw)

    @staticmethod
    def _load(body):
        try:
            return json.loads(body.content)
        except Exception:
            return None

    # -- connection ----------------------------------------------------------
    def _on_connected_triggered(self, body):
        self._set(connected=True, status_text="Connected")

    def _on_disconnected_triggered(self, body):
        self._set(connected=False, status_text="Disconnected")

    # -- available heaters ---------------------------------------------------
    def _on_heaters_available_triggered(self, body):
        heaters = self._load(body)
        if not isinstance(heaters, list):
            return
        GUI.invoke_later(self._apply_heaters, heaters)

    def _apply_heaters(self, heaters):
        updates = {"available_heaters": list(heaters)}
        updates.update(resolve_selection(self.model.selected_heater, heaters))
        self.model.trait_set(**updates)

    # -- telemetry -----------------------------------------------------------
    def _on_telemetry_triggered(self, body):
        data = self._load(body)
        if isinstance(data, dict):
            GUI.invoke_later(self._apply_telemetry, data)

    def _apply_telemetry(self, data):
        self.model.trait_set(**format_telemetry(data))


# --- Pure formatting helpers (no Qt / model / broker — unit-testable) --------

def resolve_selection(current, heaters):
    """Return the selection update needed so ``selected_heater`` always points at
    a real channel: default to the first when unset or no longer present."""
    if heaters and current not in heaters:
        return {"selected_heater": heaters[0]}
    return {}


def format_telemetry(data):
    """Map a telemetry dict to the model status-field updates it should drive.

    Returns only the fields that the frame carries, so unrelated readouts keep
    their last value.
    """
    frame = data.get('_frame', '')

    if frame == 'WHOAMI':
        ident = data.get('device_id') or data.get('uid') or 'unknown'
        return {"board_id_text": f"Board: {ident}"}
    if frame == 'ERR':
        return {"status_text": f"Error ({data.get('heater', '?')}): {data.get('message', '')}"}
    if frame == 'INFO':
        return {}  # structured events aren't surfaced in the status panel yet

    # TEMP / PID_<HEATER> telemetry
    updates = {}
    pid_temp = data.get('pid_temperature')
    if isinstance(pid_temp, (int, float)) and pid_temp > INVALID_TEMP_THRESHOLD:
        updates["pid_temp_text"] = f"PID temp: {pid_temp:.2f} °C"

    pwm = data.get('pwm_percentage', data.get('pwm_tec1'))
    if isinstance(pwm, (int, float)):
        updates["pwm_text"] = f"PWM: {pwm}%"

    temps = data.get('temperatures') or {}
    if isinstance(temps, dict) and temps:
        updates["temps_text"] = "Temps: " + ", ".join(
            f"{name}={value:.1f}" for name, value in temps.items()
            if isinstance(value, (int, float))
        )
    return updates
