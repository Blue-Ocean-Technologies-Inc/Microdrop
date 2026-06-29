from traits.api import Str, List, Bool, Event, Enum, HasTraits, Instance, observe

from template_status_and_controls.base_model import BaseStatusModel
from microdrop_utils.traitsui_qt_helpers import RangeWithSteppedSpinViewHint

from .consts import (
    disconnected_color, connected_color, halted_color,
    TEMPERATURE_MIN, TEMPERATURE_MAX, TEMPERATURE_DEFAULT,
    PWM_MIN, PWM_MAX, PWM_DEFAULT,
)
from .telemetry import reconcile_readouts

from logger.logger_service import get_logger
logger = get_logger(__name__)


class HeaterReadout(HasTraits):
    """Per-heater status row (one per board channel). Temperature is the PID
    sensor reading; pwm is the regulated duty in Temp mode or the commanded duty
    in PWM mode. Both display strings carry their own units, so the view shows
    them label-free."""
    name = Str()
    temperature_display = Str("-")
    pwm_display = Str("-")


class HeaterStatusModel(BaseStatusModel):
    """Model for heater status display and controls.

    Extends BaseStatusModel. The heater has no device picture and no chip / "no
    device" sub-state (connected maps straight to green), and no hardware
    realtime mode — so the inherited realtime-mode app-globals push is neutralized.
    """

    # ---- Class-level constants ----------------------------------------
    DEFAULT_ICON_PATH = ""          # no device picture for the heater pane
    CHIP_INSERTED_ICON_PATH = ""
    DISCONNECTED_COLOR = disconnected_color
    # No "connected but no chip" state — connected is green outright.
    CONNECTED_NO_DEVICE_COLOR = connected_color
    CONNECTED_COLOR = connected_color
    HALTED_COLOR = halted_color

    # ---- Heater channel selection (dropdown populated from the board) ---
    available_heaters = List(Str, desc="Channels reported by the board")
    selected_heater = Str(desc="Channel that commands target")

    # One status readout per available heater, kept in sync with available_heaters.
    heater_readouts = List(Instance(HeaterReadout))

    # ---- Setpoint controls (range + units, like voltage/frequency) ------
    temperature = RangeWithSteppedSpinViewHint(
        TEMPERATURE_MIN, TEMPERATURE_MAX, value=TEMPERATURE_DEFAULT, suffix=" °C",
        desc="PID setpoint to apply (°C)",
    )
    pwm = RangeWithSteppedSpinViewHint(
        PWM_MIN, PWM_MAX, value=PWM_DEFAULT, suffix=" %",
        desc="Open-loop duty to apply (%)",
    )

    # ---- Control mode + streaming gate ----------------------------------
    # "PWM": open-loop — the duty is driven directly. "Temp": closed-loop —
    # the backend's PID auto-drives the duty toward the temperature setpoint.
    mode = Enum("PWM", "Temp", desc="Open-loop PWM duty vs closed-loop temperature (PID)")
    # Master gate: while off, nothing streams from the board and we send it no
    # setpoint commands (edits are staged and applied when streaming starts).
    stream_active = Bool(False, desc="Telemetry streaming active")

    # ---- Readback displays (written by the message handler) -------------
    board_id_text = Str("-")

    # ---- Optional per-sensor temperature snapshot (hidden by default) ----
    show_all_temps = Bool(False, desc="Reveal the per-sensor temperature snapshot")
    all_temps_display = Str("-")

    # Fired by the controller when the user edits a setpoint while streaming is
    # off (the change is not sent to hardware until streaming starts). The dock
    # pane shows a one-time warning in response.
    stream_off_edit_warning = Event()

    # ------------------------------------------------------------------ #
    # Keep one readout row per available heater                            #
    # ------------------------------------------------------------------ #
    @observe("available_heaters")
    def _sync_heater_readouts(self, event):
        self.heater_readouts = reconcile_readouts(
            self.heater_readouts, self.available_heaters,
            lambda name: HeaterReadout(name=name),
        )

    # ------------------------------------------------------------------ #
    # Neutralize dropbot realtime-mode coupling                            #
    # ------------------------------------------------------------------ #
    def _realtime_mode_updated(self, event=None):
        """The heater has no hardware realtime mode; don't touch the dropbot
        REALTIME_MODE_KEY app global that BaseStatusModel would otherwise write."""
        pass
