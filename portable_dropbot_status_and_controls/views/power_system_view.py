"""The power-system pane: buzzer and fans, unlocked only in Advanced
Mode (Edit menu). The MCU fan is the signal board's; the motor fan is
where the chassis fans are wired on current benches."""
from traitsui.api import HGroup, Label, UItem, VGroup, View

from microdrop_utils.traitsui_qt_helpers import InPlaceToggleEditor

locked_hint = VGroup(
    Label("Enable Advanced Mode (Edit menu) to use the power-system "
          "controls."),
    visible_when="not advanced_mode",
)

controls = VGroup(
    HGroup(
        UItem("buzzer_state",
              editor=InPlaceToggleEditor(on_label="Buzzer On",
                                         off_label="Buzzer Off")),
        label="Buzzer",
        show_border=True,
    ),
    HGroup(
        UItem("mcu_fan_state",
              editor=InPlaceToggleEditor(on_label="MCU Fan On",
                                         off_label="MCU Fan Off")),
        label="Fans",
        show_border=True,
    ),
    visible_when="advanced_mode",
    enabled_when="connected",
)

PowerSystemView = View(
    VGroup(locked_hint, controls),
)
