from traits.api import (
    Bool,
    Button,
    Event,
    List,
    Range,
    Str,
    observe,
)

from microdrop_utils.traitsui_qt_helpers import (
    RangeWithSteppedSpinViewHint,
)
from portable_dropbot_controller.consts import (
    DEFAULT_FREQUENCY,
    DEFAULT_LIGHT_INTENSITY,
    DEFAULT_VOLTAGE,
    FREQUENCY_BOUNDS,
    LIGHT_INTENSITY_BOUNDS,
    VOLTAGE_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

from ..consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotStatusAndControlsModel(BaseStatusModel):
    """Model for the Portable Dropbot status display and controls.

    Connection/mode/icon traits and their observers are inherited;
    this adds the HV setpoints and the portable-specific readouts.
    """

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- HV setpoints (Int end-to-end, published by the controller;
    # stepped spin boxes exactly like the DropBot pane's) -------------
    voltage = RangeWithSteppedSpinViewHint(
        *VOLTAGE_BOUNDS,
        value=DEFAULT_VOLTAGE,
        suffix=" V",
        desc="HV amplitude setpoint (V)"
    )
    frequency = RangeWithSteppedSpinViewHint(
        *FREQUENCY_BOUNDS,
        value=DEFAULT_FREQUENCY,
        step=100,
        suffix=" Hz",
        desc="HV frequency setpoint (Hz)"
    )
    light_intensity = Range(
        *LIGHT_INTENSITY_BOUNDS,
        DEFAULT_LIGHT_INTENSITY,
        mode="spinner",
        desc="Light brightness (%), driving the "
        "fluorescence LED — the LED that "
        "lights this instrument"
    )
    light_on = Bool(
        True, desc="Light switch; off drives the LED to " "0 keeping the % setpoint"
    )

    # ---- Chevron-collapsed group toggles: only the actuation
    # essentials stay visible; the rest opens on demand (the raw
    # lighting controls live in the Temp & Lighting pane) --------------
    show_environment = Bool(False)
    show_board_status = Bool(False)

    #: Fired by clicking the device picture: eject the tray, click
    #: again to bring it back in (the original pane's gesture).
    tray_toggle_clicked = Event()

    # ---- Explicit COM-port connect -----------------------------------
    # The backend owns port enumeration (it may sit on another
    # machine); the handler fills available_ports from PORTS_UPDATED.
    available_ports = List(Str, desc="Serial ports the backend reported")
    selected_port = Str(desc="Port chosen for an explicit connect")
    refresh_ports_button = Button("Refresh Ports")
    #: Connect/Disconnect toggle: mirrors the actual connection state
    #: (see _sync_connect_toggle); a click that contradicts it is the
    #: user's request, which the controller publishes.
    connect_toggle = Bool(False)

    @observe("connected")
    def _sync_connect_toggle(self, event):
        self.connect_toggle = bool(event.new)

    # ---- Mechanism quick controls ------------------------------------
    #: Requested MCU fan state; the board does not read it back.
    mcu_fan_state = Bool()
    # The mechanism toggles mirror what the motor snapshot reports
    # (the *_reported traits, written by the message handler); a click
    # CONTRADICTING the reported state is the user's request, which
    # the controller publishes — same scheme as connect_toggle.
    chip_locked = Bool()
    chip_locked_reported = Bool()
    tray_out = Bool()
    tray_out_reported = Bool()
    magnet_engaged = Bool()
    magnet_engaged_reported = Bool()

    @observe("chip_locked_reported")
    def _sync_chip_locked_toggle(self, event):
        self.chip_locked = bool(event.new)

    @observe("tray_out_reported")
    def _sync_tray_out_toggle(self, event):
        self.tray_out = bool(event.new)

    @observe("magnet_engaged_reported")
    def _sync_magnet_toggle(self, event):
        self.magnet_engaged = bool(event.new)

    # ---- Readouts written by the message handler ---------------------
    # Named like the DropBot pane's displays so the two panes read the
    # same; each sits beside its setter in the view's grid.
    chip_status_text = Str("No Chip Detected")
    voltage_readback_display = Str("-", desc="HV amplitude the board " "reports")
    frequency_display = Str("-", desc="HV frequency the board reports")
    light_display = Str(
        "-",
        desc="Light brightness the board reports "
        "(the fluorescence LED, as % of its "
        "16-bit range)",
    )
    capacitance_display = Str("-", desc="Chip capacitance reading")
    chip_temp_display = Str("-", desc="Heater current/target (°C)")
    device_temp_display = Str("-", desc="Instrument internal " "temperature")
    device_humidity_display = Str("-", desc="Instrument internal " "relative humidity")
    mechanisms_display = Str("-", desc="Tray/magnet/filter/pogo states")
    last_alarm = Str("-", desc="Most recent decoded alarm or error")

    # ---- The rest of the signal board's STATUS fields, mirroring
    # the vendor UI's Connection/Status tab -----------------------------
    out_power_display = Str("-", desc="Heater output power (%)")
    heater_on_display = Str("-", desc="Heater enable flag (temp_onoff)")
    fan_duty_display = Str("-", desc="Cooling fan duty (%)")
    illumination_display = Str(
        "-", desc="Illumination LED brightness " "the board reports"
    )
    pmt_display = Str("-", desc="PMT reading")
    chip_short_display = Str("-", desc="Chip short-circuit flag")
    chip_res_display = Str("-", desc="Chip resistance reading")
    cap_match_display = Str("-", desc="Capacitance-match flag")

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = "Chip Detected" if inserted else "No Chip Detected"
