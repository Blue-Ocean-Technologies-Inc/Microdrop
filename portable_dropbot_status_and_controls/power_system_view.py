"""The power-system pane: buzzer and fans, unlocked only in Advanced
Mode (Edit menu). The MCU fan is the signal board's; the motor fan is
where the chassis fans are wired on current benches."""
from traitsui.api import HGroup, Label, UItem, VGroup, View

locked_hint = VGroup(
    Label("Enable Advanced Mode (Edit menu) to use the power-system "
          "controls."),
    visible_when="not advanced_mode",
)

controls = VGroup(
    HGroup(
        UItem("buzzer_on_button"),
        UItem("buzzer_off_button"),
        label="Buzzer",
        show_border=True,
    ),
    HGroup(
        UItem("mcu_fan_on_button"),
        UItem("mcu_fan_off_button"),
        UItem("motor_fan_on_button"),
        UItem("motor_fan_off_button"),
        label="Fans",
        show_border=True,
    ),
    visible_when="advanced_mode",
    enabled_when="connected",
)

PowerSystemView = View(
    VGroup(locked_hint, controls),
    resizable=True,
    scrollable=True,
)
