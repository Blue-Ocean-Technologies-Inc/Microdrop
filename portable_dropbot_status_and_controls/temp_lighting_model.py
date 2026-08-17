from traits.api import Bool, Button, Enum, Range, Str

from portable_dropbot_controller.consts import (
    FLUORESCENCE_LED_RAW_MAX, LIGHT_INTENSITY_RAW_MAX,
    RGB_LIGHT_STATES, TEMP_CHANNEL_MAX, TEMP_PID_GAIN_BOUNDS,
    TEMP_PID_PERIOD_MS_BOUNDS, TEMP_TARGET_C_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

from .consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotTempLightingModel(BaseStatusModel):
    """Qt-free state for the temp & lighting pane: per-channel heater
    control with PID tuning, and the vendor's raw lighting controls
    (the everyday Light %/on-off stays in the status pane). Mutated
    only on the GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- Temperature control (per channel) ---------------------------
    temp_channel = Range(0, TEMP_CHANNEL_MAX, 0, mode="spinner",
                         desc="Heater channel")
    temp_target_c = Range(*TEMP_TARGET_C_BOUNDS, 37.0,
                          desc="Heater target temperature (°C)")
    set_target_button = Button("Set Target")
    start_button = Button("Start")
    stop_button = Button("Stop")
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

    # ---- Lighting (vendor raw controls, exactly as the Temp/Lighting
    # tab sends them — no scaling anywhere in between) ------------------
    #: The message handler is writing board-reported values into the
    #: lighting traits below; the controller's observers stay quiet so
    #: the (lossily rescaled) seed is never echoed back as a set.
    seeding = Bool(False)

    rgb_light = Enum(*RGB_LIGHT_STATES,
                     desc="RGB indicator LED on the box")
    illumination_raw = Range(
        0, LIGHT_INTENSITY_RAW_MAX, 0, mode="spinner",
        desc="Illumination LED raw brightness byte (0-255)")
    fluorescence_led_raw = Range(
        0, FLUORESCENCE_LED_RAW_MAX, 0, mode="spinner",
        desc="Fluorescence LED raw 16-bit brightness (0-65535)")
    fluorescence_led_default_button = Button("Default (0)")
