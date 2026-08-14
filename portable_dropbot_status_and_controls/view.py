"""The Portable Dropbot status pane, laid out exactly like the
DropBot one (device photo + connection column on the left, a
readback/setter grid on the right) so users move between the two
without relearning anything — plus the portable's extras: the
COM-port picker, light intensity, temperatures, humidity,
mechanisms, and alarms."""
from traitsui.api import (
    EnumEditor, HGroup, Item, Spring, UItem, VGrid, VGroup, View,
)

from microdrop_utils.traitsui_qt_helpers import (
    InPlaceToggleEditor, StatusIconEditorFactory,
)

left = HGroup(
    Item("icon_path",
         editor=StatusIconEditorFactory(fire="tray_toggle_clicked"),
         show_label=False,
         tooltip="Click to eject the tray; click again to bring "
                 "it back in"),
    Spring("8"),
    VGroup(
        Spring("12"),
        VGroup(
            Item("connection_status_text", style="readonly",
                 label="Connection"),
            Item("chip_status_text", style="readonly",
                 label="Chip Status"),
        ),
        Spring("8"),
        HGroup(
            Item("selected_port", label="Port",
                 editor=EnumEditor(name="available_ports"),
                 enabled_when="not connected"),
            UItem("refresh_ports_button"),
            UItem("connect_button",
                  enabled_when="not connected and selected_port"),
        ),
        Spring("8"),
        UItem(
            "realtime_mode",
            style="custom",
            editor=InPlaceToggleEditor(on_label="Realtime On",
                                       off_label="Realtime Off"),
            enabled_when="connected and not protocol_running",
        ),
        Spring("10"),
    ),
    id="status_controls",
)

grid = VGrid(
    Item("voltage_readback_display", style="readonly", label="Voltage"),
    UItem("voltage",
          enabled_when="connected and free_mode and "
                       "not protocol_running"),
    Item("frequency_display", style="readonly", label="Frequency"),
    UItem("frequency",
          enabled_when="connected and free_mode and "
                       "not protocol_running"),
    Item("light_display", style="readonly", label="Light"),
    UItem("light_intensity", enabled_when="connected"),
    Item("capacitance_display", style="readonly", label="Capacitance"),
    UItem(""),
    Item("chip_temp_display", style="readonly", label="Chip Temp"),
    UItem(""),
    Item("device_temp_display", style="readonly", label="Device Temp"),
    UItem(""),
    Item("device_humidity_display", style="readonly",
         label="Device Humidity"),
    UItem(""),
    Item("mechanisms_display", style="readonly", label="Mechanisms"),
    UItem(""),
    Item("last_alarm", style="readonly", label="Last Alarm"),
    UItem(""),
    id="data_grid",
)

# The remaining signal-board STATUS fields, like the vendor UI's
# Connection/Status tab shows them.
board_grid = VGrid(
    Item("out_power_display", style="readonly", label="Heater Power"),
    Item("heater_on_display", style="readonly", label="Heater"),
    Item("fan_duty_display", style="readonly", label="Fan Duty"),
    Item("rgy_led_display", style="readonly", label="Status LED"),
    Item("flu_led_display", style="readonly", label="Fluor. LED"),
    Item("pmt_display", style="readonly", label="PMT"),
    Item("chip_short_display", style="readonly", label="Chip Short"),
    Item("chip_res_display", style="readonly", label="Chip Res."),
    Item("cap_match_display", style="readonly", label="Cap Match"),
    id="board_grid",
)

UnifiedView = View(
    HGroup(left, "15", grid, "15", board_grid),
    resizable=True,
    # Let the dock pane shrink below the grids' natural size — the
    # content then scrolls instead of pinning the pane width.
    scrollable=True,
)
