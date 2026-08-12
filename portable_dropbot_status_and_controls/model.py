from traits.api import Int, Str

from template_status_and_controls.base_model import BaseStatusModel

from .consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotStatusAndControlsModel(BaseStatusModel):
    """Model for the Portable Dropbot status display and controls.

    Connection/mode/icon traits and their observers are inherited;
    this adds the HV setpoints and the portable-specific readouts.
    """

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    # ---- HV setpoints (Int end-to-end, published by the controller) --
    voltage = Int(100, desc="HV amplitude setpoint (V)")
    frequency = Int(10_000, desc="HV frequency setpoint (Hz)")

    # ---- Readouts written by the message handler ---------------------
    chip_status_text = Str("No Chip Detected")
    hv_readback_display = Str("-", desc="HV amplitude/frequency the "
                                        "board reports")
    capacitance_display = Str("-", desc="Chip capacitance reading")
    temperature_display = Str("-", desc="Heater current/target (°C)")
    mechanisms_display = Str("-", desc="Tray/magnet/filter/pogo states")
    last_alarm = Str("-", desc="Most recent decoded alarm or error")

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = ("Chip Detected" if inserted
                                 else "No Chip Detected")
