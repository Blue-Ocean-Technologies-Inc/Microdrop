"""The Portable Dropbot status pane, laid out exactly like the
DropBot one (device photo + connection column on the left, a
readback/setter grid on the right) so users move between the two
without relearning anything. The portable's many extra readouts are
folded into chevron-collapsed groups — Environment, Board Status —
so the pane shows only the actuation essentials until the user opens
them; deeper controls each have their own pane (calibration, temp &
lighting, PMT, and the advanced-mode power-system / motor-params
panes)."""

from traitsui.api import (
    EnumEditor,
    HGroup,
    Item,
    Label,
    Spring,
    UItem,
    VGrid,
    VGroup,
    View,
)

from microdrop_style.icons.icons import (
    ICON_ARROW_DOWNWARD,
    ICON_ARROW_UPWARD,
    ICON_EJECT,
    ICON_INPUT,
    ICON_LIGHT_OFF,
    ICON_LIGHTBULB,
    ICON_LINK,
    ICON_LINK_OFF,
    ICON_LOCK,
    ICON_LOCK_OPEN,
    ICON_MODE_FAN,
    ICON_MODE_FAN_OFF,
    ICON_REFRESH,
)
from microdrop_utils.traitsui_qt_helpers import (
    IconButtonEditor,
    IconToggleEditor,
    InPlaceToggleEditor,
    StatusIconEditorFactory,
)

# Mechanism quick controls: a glyph toolbar (fluorescence
# image-viewer style) sitting under the device picture. Each toggle
# shows the ACTION a click performs and mirrors the state the
# hardware reports.
mechanism_toolbar = HGroup(
    UItem(
        "chip_locked",
        editor=IconToggleEditor(
            on_glyph=ICON_LOCK_OPEN,
            off_glyph=ICON_LOCK,
            tooltip="Lock/unlock the chip (the pogo pads " "press/release it)",
        ),
    ),
    UItem(
        "tray_out",
        editor=IconToggleEditor(
            on_glyph=ICON_INPUT,
            off_glyph=ICON_EJECT,
            tooltip="Pull the chip tray out / push it back in",
        ),
    ),
    UItem(
        "magnet_engaged",
        editor=IconToggleEditor(
            on_glyph=ICON_ARROW_DOWNWARD,
            off_glyph=ICON_ARROW_UPWARD,
            tooltip="Magnet up (engage) / down (disengage)",
        ),
    ),
    UItem(
        "mcu_fan_state",
        editor=IconToggleEditor(
            on_glyph=ICON_MODE_FAN_OFF,
            off_glyph=ICON_MODE_FAN,
            tooltip="MCU fan on/off (state is not read back)",
        ),
    ),
    UItem(
        "light_on",
        editor=IconToggleEditor(
            on_glyph=ICON_LIGHT_OFF,
            off_glyph=ICON_LIGHTBULB,
            tooltip="Illumination light on/off (keeps the % " "setpoint)",
        ),
    ),
    enabled_when="connected",
)

left = HGroup(
    VGroup(
        HGroup(
            Item("12"),
            Item(
                "icon_path",
                editor=StatusIconEditorFactory(
                    fire="tray_toggle_clicked", min_size=160
                ),
                show_label=False,
                tooltip="Click to eject the tray; click again to bring it back in",
            ),
        ),
        Item("50"),
        mechanism_toolbar,
    ),
    VGroup(
        VGroup(
            Item("connection_status_text", style="readonly", label="Connection"),
            Item("chip_status_text", style="readonly", label="Chip Status"),
        ),
        HGroup(
            Item(
                "selected_port",
                label="Port",
                editor=EnumEditor(name="available_ports"),
                enabled_when="not connected",
            ),
            UItem(
                "refresh_ports_button",
                editor=IconButtonEditor(glyph=ICON_REFRESH, tooltip="Refresh ports"),
            ),
            UItem(
                "connect_toggle",
                editor=IconToggleEditor(
                    on_glyph=ICON_LINK_OFF,
                    off_glyph=ICON_LINK,
                    tooltip="Connect to the selected port / " "disconnect",
                ),
                enabled_when="connected or selected_port",
            ),
        ),
        HGroup(
            UItem(
                "realtime_mode",
                style="custom",
                editor=InPlaceToggleEditor(
                    on_label="Realtime On", off_label="Realtime Off"
                ),
                enabled_when="connected and not protocol_running",
                tooltip="Realtime mode is also the HV On/Off: on "
                "enables the HV output (pad-interlocked) for "
                "live actuation; off releases all electrodes "
                "and de-energizes HV",
            ),
        ),
    ),
    id="status_controls",
)

# The actuation essentials stay in sight; everything else lives in
# the chevron-collapsed groups below.
grid = VGrid(
    Item("voltage_readback_display", style="readonly", label="Voltage"),
    UItem(
        "voltage", enabled_when="connected and free_mode and " "not protocol_running"
    ),
    Item("frequency_display", style="readonly", label="Frequency"),
    UItem(
        "frequency", enabled_when="connected and free_mode and " "not protocol_running"
    ),
    Item("light_display", style="readonly", label="Light"),
    UItem("light_intensity", enabled_when="connected and light_on"),
    Item("capacitance_display", style="readonly", label="Capacitance"),
    UItem(""),
    Item("last_alarm", style="readonly", label="Last Alarm"),
    UItem(""),
    id="data_grid",
)

# Temperatures, humidity, and the heater/fan that regulate them.
environment = VGroup(
    HGroup(
        UItem("show_environment", editor=IconToggleEditor()),
        Label("Environment"),
    ),
    VGrid(
        Item("chip_temp_display", style="readonly", label="Chip Temp"),
        Item("device_temp_display", style="readonly", label="Device Temp"),
        Item("device_humidity_display", style="readonly", label="Device Humidity"),
        Item("out_power_display", style="readonly", label="Heater Power"),
        Item("heater_on_display", style="readonly", label="Heater"),
        Item("fan_duty_display", style="readonly", label="Fan Duty"),
        visible_when="show_environment",
    ),
)

# The remaining signal-board STATUS fields, like the vendor UI's
# Connection/Status tab shows them.
board_status = VGroup(
    HGroup(
        UItem("show_board_status", editor=IconToggleEditor()),
        Label("Board Status"),
    ),
    VGrid(
        Item("mechanisms_display", style="readonly", label="Mechanisms"),
        Item("illumination_display", style="readonly", label="Illumination"),
        Item("pmt_display", style="readonly", label="PMT"),
        Item("chip_short_display", style="readonly", label="Chip Short"),
        Item("chip_res_display", style="readonly", label="Chip Res."),
        Item("cap_match_display", style="readonly", label="Cap Match"),
        visible_when="show_board_status",
    ),
)

UnifiedView = View(
    HGroup(left, "15", VGroup(grid, environment, board_status)),
    resizable=True,
    # Let the dock pane shrink below the grids' natural size — the
    # content then scrolls instead of pinning the pane width.
    scrollable=True,
)
