"""The More Controls pane: everything beyond the everyday status-pane
controls, one chevron-collapsed group per subsystem — per-channel
heater control (with nested PID tuning) and the PMT (power, gain, and
the acquire macro). Laid out like the status pane: one labeled row
per setter, action buttons on their own row below. The live PMT
reading shows in the status pane's Board Status group."""
from traitsui.api import HGroup, Item, Label, UItem, VGroup, View

from microdrop_style.icons.icons import ICON_CHECK, ICON_REFRESH
from microdrop_utils.traitsui_qt_helpers import (
    DoubleSpinBoxEditor, HtmlLabelEditor, IconButtonEditor,
    IconToggleEditor, InPlaceToggleEditor,
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
#: Muted, word-wrapped help text (wraps instead of forcing the pane
#: wide).
_hint_label = HtmlLabelEditor(
    template='<span style="color:#888; font-style:italic;">{}</span>')

temperature = VGroup(
    HGroup(
        UItem("show_temperature", editor=IconToggleEditor()),
        Label("Temperature Control (per channel)"),
    ),
    VGroup(
        Item("temp_channel", label="Channel"),
        HGroup(
            Item("temp_target_c", label="Target (°C)",
                 editor=_target_spin_box),
            UItem("set_target_button",
                  editor=IconButtonEditor(glyph=ICON_CHECK,
                                          tooltip="Set target")),
        ),
        HGroup(
            Item("temp_info_display", style="readonly",
                 label="Reading"),
            UItem("read_info_button",
                  editor=IconButtonEditor(glyph=ICON_REFRESH,
                                          tooltip="Read now")),
        ),
        HGroup(
            UItem("temp_control_on",
                  style="custom",
                  editor=InPlaceToggleEditor(
                      on_label="Stop Heating",
                      off_label="Start Heating")),
        ),
        VGroup(
            HGroup(
                UItem("show_pid", editor=IconToggleEditor()),
                Label("PID Tuning"),
            ),
            VGroup(
                Item("pid_kp", label="Kp", editor=_pid_spin_box),
                Item("pid_ki", label="Ki", editor=_pid_spin_box),
                Item("pid_kd", label="Kd", editor=_pid_spin_box),
                Item("pid_period_ms", label="Period (ms)"),
                HGroup(
                    UItem("read_pid_button"),
                    UItem("apply_pid_button"),
                ),
                visible_when="show_pid",
            ),
        ),
        visible_when="show_temperature",
        enabled_when="connected",
    ),
)

pmt = VGroup(
    HGroup(
        UItem("show_pmt", editor=IconToggleEditor()),
        Label("PMT"),
    ),
    VGroup(
        HGroup(
            Item("pmt_gain", label="Gain"),
            UItem("set_gain_button",
                  editor=IconButtonEditor(glyph=ICON_CHECK,
                                          tooltip="Set gain")),
        ),
        Item("pmt_status_display", style="readonly", label="Result"),
        HGroup(
            UItem("pmt_power",
                  style="custom",
                  editor=InPlaceToggleEditor(on_label="PMT On",
                                             off_label="PMT Off")),
            UItem("acquire_button",
                  enabled_when="connected and not acquiring"),
        ),
        UItem("pmt_acquire_hint", editor=_hint_label),
        visible_when="show_pmt",
        enabled_when="connected",
    ),
)

MoreControlsView = View(
    VGroup(temperature, pmt),
    resizable=True,
    scrollable=True,
)
