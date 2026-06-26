from traits.api import Str, List, Bool

from template_status_and_controls.base_model import BaseStatusModel
from microdrop_utils.traitsui_qt_helpers import RangeWithSteppedSpinViewHint

from .consts import (
    disconnected_color, connected_color, halted_color,
    TEMPERATURE_MIN, TEMPERATURE_MAX, TEMPERATURE_DEFAULT,
    PWM_MIN, PWM_MAX, PWM_DEFAULT,
)

from logger.logger_service import get_logger
logger = get_logger(__name__)


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

    # ---- Setpoint controls (range + units, like voltage/frequency) ------
    temperature = RangeWithSteppedSpinViewHint(
        TEMPERATURE_MIN, TEMPERATURE_MAX, value=TEMPERATURE_DEFAULT, suffix=" °C",
        desc="PID setpoint to apply (°C)",
    )
    pwm = RangeWithSteppedSpinViewHint(
        PWM_MIN, PWM_MAX, value=PWM_DEFAULT, suffix=" %",
        desc="Open-loop duty to apply (%)",
    )

    # ---- Toggle controls (realtime-style buttons) -----------------------
    pid_active = Bool(False, desc="PID control enabled")
    stream_active = Bool(False, desc="Telemetry streaming active")

    # ---- Readback displays (written by the message handler) -------------
    temperature_display = Str("-")
    pwm_display = Str("-")
    board_id_text = Str("-")

    # ---- Optional per-sensor temperature snapshot (hidden by default) ----
    show_all_temps = Bool(False, desc="Reveal the per-sensor temperature snapshot")
    all_temps_display = Str("-")

    # ------------------------------------------------------------------ #
    # Neutralize dropbot realtime-mode coupling                            #
    # ------------------------------------------------------------------ #
    def _realtime_mode_updated(self, event=None):
        """The heater has no hardware realtime mode; don't touch the dropbot
        REALTIME_MODE_KEY app global that BaseStatusModel would otherwise write."""
        pass
