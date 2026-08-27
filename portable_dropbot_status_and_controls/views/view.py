# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Portable Dropbot status pane, laid out exactly like the
DropBot one (device photo + connection column on the left, a
readback/setter grid on the right) so users move between the two
without relearning anything. The portable's many extra readouts are
folded into chevron-collapsed groups — Environment, Board Status —
so the pane shows only the actuation essentials until the user opens
them; deeper controls each have their own pane (calibration, temp &
lighting, PMT, and the advanced-mode power-system / motor-params
panes)."""
from microdrop_style.fonts.fontnames import MDI_ICON_FONT_FAMILY
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
    MDI_ICON_MAGNET_ON,
    MDI_ICON_MAGNET
)
from microdrop_utils.traitsui_qt_helpers import (
    IconButtonEditor,
    IconToggleEditor,
    InPlaceToggleEditor,
    StatusIconEditorFactory,
)

# Mechanism quick controls: a glyph toolbar (fluorescence
# image-viewer style) sitting under the device picture. Each toggle's
# glyph reads as the STATE the hardware reports — a closed padlock
# means the chip IS locked — never as the action a click performs;
# the tooltip says what clicking does. The button relief reads as
# on/off: popped-out while the mechanism is ON (light/fan on, magnet
# up, pogo down, tray in), sunken/grey while it is off — hence
# invert_checked on every toggle whose True state is the ON state
# (tray_out's True is the OFF state, so it maps directly).
#
# enabled_when sits on each item, not the group: a group-level
# condition makes TraitsUI wrap the row in its own QWidget whose
# layout keeps Qt's default 9px margins, indenting the row ~9px
# relative to the flattened single-item rows above/below it.
mechanism_toolbar = HGroup(
    UItem(
        "chip_locked",
        editor=IconToggleEditor(
            on_glyph=ICON_LOCK,
            off_glyph=ICON_LOCK_OPEN,
            tooltip="Lock/unlock the chip (the pogo pads " "press/release it)",
        ),
        enabled_when="connected",
    ),
    UItem(
        "tray_out",
        editor=IconToggleEditor(
            on_glyph=ICON_EJECT,
            off_glyph=ICON_INPUT,
            invert_checked=True,
            tooltip="Pull the chip tray out / push it back in",
        ),
        enabled_when="connected",
    ),
    UItem(
        "magnet_engaged",
        editor=IconToggleEditor(
            on_glyph=MDI_ICON_MAGNET_ON,
            off_glyph=MDI_ICON_MAGNET,
            font_family=MDI_ICON_FONT_FAMILY,
            tooltip="Magnet up (engage) / down (disengage)",
        ),
        enabled_when="connected",
    ),
    UItem(
        "mcu_fan_state",
        editor=IconToggleEditor(
            on_glyph=ICON_MODE_FAN,
            off_glyph=ICON_MODE_FAN_OFF,
            tooltip="MCU fan on/off (state is not read back)",
        ),
        enabled_when="connected",
    ),
    UItem(
        "light_on",
        editor=IconToggleEditor(
            on_glyph=ICON_LIGHTBULB,
            off_glyph=ICON_LIGHT_OFF,
            tooltip="Illumination light on/off (keeps the % " "setpoint)",
        ),
        enabled_when="connected",
    ),
)

# A single column: device picture, the mechanism toolbar, the
# realtime/HV master toggle, and — in Advanced Mode only — the
# explicit COM-port connect row (the device normally auto-connects;
# the connect toggle's glyph already shows the link state, so the
# old readonly Connection/Chip Status lines are gone).
left = VGroup(
    HGroup(
        Item(
            "icon_path",
            editor=StatusIconEditorFactory(
                fire="tray_toggle_clicked",
                min_size=160,
                # Nothing else in this single column drives the row
                # height — unpinned, the image row collapses and the
                # picture paints over the toolbar.
                fixed_size=True,
            ),
            show_label=False,
            tooltip="Click to eject the tray; click again to bring it back in",
        ),
    ),
    mechanism_toolbar,
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
    # visible_when per item, not on the group — same 9px-margin
    # wrapper-widget indent as the mechanism toolbar (see above).
    HGroup(
        UItem(
            "selected_port",
            editor=EnumEditor(name="available_ports"),
            enabled_when="not connected",
            visible_when="advanced_mode",
        ),
        UItem(
            "refresh_ports_button",
            editor=IconButtonEditor(glyph=ICON_REFRESH, tooltip="Refresh ports"),
            visible_when="advanced_mode",
        ),
        UItem(
            "connect_toggle",
            editor=IconToggleEditor(
                on_glyph=ICON_LINK,
                off_glyph=ICON_LINK_OFF,
                tooltip="Connect to the selected port / " "disconnect",
            ),
            enabled_when="connected or selected_port",
            visible_when="advanced_mode",
        ),
    ),
    # Absorb the column's extra height (the right column is taller) at
    # the bottom — without this the box layout spreads it equally
    # between the rows, blowing the gaps out to ~50px each.
    Spring(),
    id="status_controls",
)

# The actuation essentials stay in sight; everything else lives in
# the chevron-collapsed groups below.
grid = VGrid(
    # Realtime mode is the HV master enable: with it off the reported
    # amplitude still wanders, but none of it reaches the pogo pins,
    # so grey the readback out rather than show a misleading live number.
    Item(
        "voltage_readback_display",
        style="readonly",
        label="Voltage",
        enabled_when="realtime_mode",
    ),
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
    HGroup(left, "12", VGroup(grid, environment, board_status)),
    resizable=True,
    # Let the dock pane shrink below the grids' natural size — the
    # content then scrolls instead of pinning the pane width.
    scrollable=True,
)


if __name__ == "__main__":
    # Layout preview without the app (no Redis/hardware; the toggles
    # publish nothing here). Run from the src directory:
    #   ..\.pixi\envs\default\python.exe -m portable_dropbot_status_and_controls.views.view
    from portable_dropbot_status_and_controls.models.model import (
        PortableDropbotStatusAndControlsModel,
    )
    from pyface.qt.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from microdrop_style.helpers import style_app

    style_app(app)

    model = PortableDropbotStatusAndControlsModel()
    # Set (not defaulted) so nothing consults the running app, and the
    # connected/advanced-gated rows all show for inspection.
    model.connected = True
    model.advanced_mode = True
    model.configure_traits(view=UnifiedView)
