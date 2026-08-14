from traits.api import Button, Event, List, Range, Str

from microdrop_utils.traitsui_qt_helpers import (
    RangeWithSteppedSpinViewHint,
)
from portable_dropbot_controller.consts import (
    DEFAULT_FREQUENCY, DEFAULT_LIGHT_INTENSITY, DEFAULT_VOLTAGE,
    FREQUENCY_BOUNDS, LIGHT_INTENSITY_BOUNDS, VOLTAGE_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

from .consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotStatusAndControlsModel(BaseStatusModel):
    """Model for the Portable Dropbot status display and controls.

    Connection/mode/icon traits and their observers are inherited;
    this adds the HV setpoints and the portable-specific readouts.
    """

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- HV setpoints (Int end-to-end, published by the controller;
    # stepped spin boxes exactly like the DropBot pane's) -------------
    voltage = RangeWithSteppedSpinViewHint(
        *VOLTAGE_BOUNDS, value=DEFAULT_VOLTAGE, suffix=" V",
        desc="HV amplitude setpoint (V)")
    frequency = RangeWithSteppedSpinViewHint(
        *FREQUENCY_BOUNDS, value=DEFAULT_FREQUENCY, step=100,
        suffix=" Hz", desc="HV frequency setpoint (Hz)")
    light_intensity = Range(*LIGHT_INTENSITY_BOUNDS,
                            DEFAULT_LIGHT_INTENSITY, mode="spinner",
                            desc="Illumination LED brightness (%)")

    #: Fired by clicking the device picture: eject the tray, click
    #: again to bring it back in (the original pane's gesture).
    tray_toggle_clicked = Event()

    # ---- Explicit COM-port connect -----------------------------------
    # The backend owns port enumeration (it may sit on another
    # machine); the handler fills available_ports from PORTS_UPDATED.
    available_ports = List(Str, desc="Serial ports the backend reported")
    selected_port = Str(desc="Port chosen for an explicit connect")
    refresh_ports_button = Button("Refresh Ports")
    connect_button = Button("Connect")

    # ---- Readouts written by the message handler ---------------------
    # Named like the DropBot pane's displays so the two panes read the
    # same; each sits beside its setter in the view's grid.
    chip_status_text = Str("No Chip Detected")
    voltage_readback_display = Str("-", desc="HV amplitude the board "
                                             "reports")
    frequency_display = Str("-", desc="HV frequency the board reports")
    light_display = Str("-", desc="Illumination LED brightness the "
                                  "board reports")
    capacitance_display = Str("-", desc="Chip capacitance reading")
    chip_temp_display = Str("-", desc="Heater current/target (°C)")
    device_temp_display = Str("-", desc="Instrument internal "
                                        "temperature")
    device_humidity_display = Str("-", desc="Instrument internal "
                                            "relative humidity")
    mechanisms_display = Str("-", desc="Tray/magnet/filter/pogo states")
    last_alarm = Str("-", desc="Most recent decoded alarm or error")

    # ---- The rest of the signal board's STATUS fields, mirroring
    # the vendor UI's Connection/Status tab -----------------------------
    out_power_display = Str("-", desc="Heater output power (%)")
    heater_on_display = Str("-", desc="Heater enable flag (temp_onoff)")
    fan_duty_display = Str("-", desc="Cooling fan duty (%)")
    rgy_led_display = Str("-", desc="Status LED state "
                                    "(off/red/green/yellow)")
    flu_led_display = Str("-", desc="Fluorescence LED brightness (‰)")
    pmt_display = Str("-", desc="PMT reading")
    chip_short_display = Str("-", desc="Chip short-circuit flag")
    chip_res_display = Str("-", desc="Chip resistance reading")
    cap_match_display = Str("-", desc="Capacitance-match flag")

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = ("Chip Detected" if inserted
                                 else "No Chip Detected")
