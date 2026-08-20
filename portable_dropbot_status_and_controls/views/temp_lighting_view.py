"""The temp & lighting pane, mirroring the vendor UI's Temp/Lighting
tab: per-channel heater control (target / start / stop / read) with a
chevron-collapsed PID tuning group, and the raw lighting controls.
The everyday Light %/on-off lives in the status pane."""
from traitsui.api import HGroup, Item, Label, UItem, VGroup, View

from microdrop_utils.traitsui_qt_helpers import (
    DoubleSpinBoxEditor, IconToggleEditor,
)
from portable_dropbot_controller.consts import (
    TEMP_PID_GAIN_BOUNDS, TEMP_TARGET_C_BOUNDS,
)

_target_spin_box = DoubleSpinBoxEditor(
    low=TEMP_TARGET_C_BOUNDS[0], high=TEMP_TARGET_C_BOUNDS[1],
    decimals=1, step=0.5,
)
_pid_spin_box = DoubleSpinBoxEditor(
    low=TEMP_PID_GAIN_BOUNDS[0], high=TEMP_PID_GAIN_BOUNDS[1],
    decimals=3, step=0.1,
)

temperature = VGroup(
    HGroup(
        Item("temp_channel", label="Channel"),
        Item("temp_target_c", label="Target (°C)",
             editor=_target_spin_box),
        UItem("set_target_button"),
        UItem("start_button"),
        UItem("stop_button"),
        UItem("read_info_button"),
    ),
    Item("temp_info_display", style="readonly", label="Reading"),
    VGroup(
        HGroup(
            UItem("show_pid", editor=IconToggleEditor()),
            Label("PID Tuning"),
        ),
        HGroup(
            Item("pid_kp", label="Kp", editor=_pid_spin_box),
            Item("pid_ki", label="Ki", editor=_pid_spin_box),
            Item("pid_kd", label="Kd", editor=_pid_spin_box),
            Item("pid_period_ms", label="Period (ms)"),
            UItem("read_pid_button"),
            UItem("apply_pid_button"),
            visible_when="show_pid",
        ),
    ),
    label="Temperature Control (per channel)",
    show_border=True,
    enabled_when="connected",
)

lighting = VGroup(
    Item("rgb_light", label="RGB LED",
         tooltip="Manual override; the status pane re-syncs this LED "
                 "to the device status (yellow = no chip, green = "
                 "chip, red = halted) on every state change"),
    Item("illumination_raw", label="Illumination (raw 0-255)"),
    HGroup(
        Item("fluorescence_led_raw", label="Fluorescence LED (16-bit)"),
        UItem("fluorescence_led_default_button"),
    ),
    label="Lighting",
    show_border=True,
    enabled_when="connected",
)

TempLightingView = View(
    VGroup(temperature, lighting),
    resizable=True,
    scrollable=True,
)
