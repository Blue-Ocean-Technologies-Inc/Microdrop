from traits.api import Bool, Button, Range, Str

from portable_dropbot_controller.consts import (
    DEFAULT_PMT_GAIN, PMT_GAIN_BOUNDS, TEMP_CHANNEL_MAX,
    TEMP_PID_GAIN_BOUNDS, TEMP_PID_PERIOD_MS_BOUNDS,
    TEMP_TARGET_C_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

from ..consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotMoreControlsModel(BaseStatusModel):
    """Qt-free state for the More Controls pane, one chevron-collapsed
    group per subsystem: per-channel heater control with PID tuning,
    and the PMT (power, gain, acquire). The everyday lighting controls
    live in the status pane. Mutated only on the GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Chevron-collapsed group toggles -----------------------------
    show_temperature = Bool(True)
    show_pmt = Bool(False)

    # ---- Temperature control (per channel) ---------------------------
    temp_channel = Range(0, TEMP_CHANNEL_MAX, 0, mode="spinner",
                         desc="Heater channel")
    temp_target_c = Range(*TEMP_TARGET_C_BOUNDS, 37.0,
                          desc="Heater target temperature (°C)")
    set_target_button = Button("Set Target")
    #: Requested heater-control state for the selected channel; the
    #: board does not report a per-channel on/off, so the toggle shows
    #: what was last asked for.
    temp_control_on = Bool()
    read_info_button = Button("Read")
    temp_info_display = Str("-", desc="Last per-channel reading")

    # ---- PID tuning (chevron-collapsed) ------------------------------
    show_pid = Bool(False)
    pid_kp = Range(*TEMP_PID_GAIN_BOUNDS, 0.0)
    pid_ki = Range(*TEMP_PID_GAIN_BOUNDS, 0.0)
    pid_kd = Range(*TEMP_PID_GAIN_BOUNDS, 0.0)
    pid_period_ms = Range(*TEMP_PID_PERIOD_MS_BOUNDS, 1000,
                          mode="spinner")
    read_pid_button = Button("Read PID")
    apply_pid_button = Button("Apply PID")

    # ---- PMT ---------------------------------------------------------
    #: Mirrors the actual PMT power state the backend reports; a click
    #: that contradicts it is the user's request.
    pmt_power = Bool(False)
    pmt_gain = Range(*PMT_GAIN_BOUNDS, DEFAULT_PMT_GAIN,
                     mode="spinner",
                     desc="PMT gain (MCP41010 wiper position)")
    set_gain_button = Button("Set Gain")
    acquire_button = Button("Acquire")
    #: An acquire macro is running on the board (~10 s full buffer).
    acquiring = Bool(False)
    pmt_status_display = Str("-", desc="Last acquire outcome")
    #: Static help line, a trait so the view can word-wrap it.
    pmt_acquire_hint = Str(
        "Acquire runs the vendor macro: fluorescence LED off → "
        "power on → gain → sample (~10 s full buffer).")
