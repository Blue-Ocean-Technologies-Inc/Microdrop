import math

import pint
from traits.api import Str, Enum, Instance, observe

from dropbot_controller.preferences import DropbotPreferences
from logger.logger_service import get_logger
from microdrop_utils.ureg_helpers import ureg
from protocol_grid.services.force_calculation_service import ForceCalculationService

from template_status_and_controls.base_model import BaseStatusModel

from .consts import (
    DROPBOT_IMAGE, DROPBOT_CHIP_INSERTED_IMAGE,
    disconnected_color, connected_no_device_color, connected_color, halted_color,
)
from .view_helpers import RangeWithCustomViewHints

logger = get_logger(__name__)

N_DISPLAY_DIGITS = 3

# Dielectric materials and their relative permittivity values.
# Used to calculate dielectric thickness from device capacitance via:
#   d = epsilon * epsilon_0 / C_device
DIELECTRIC_MATERIALS = {
    "Choose Dielectric": float('nan'),
    "Parylene C": 3.1,
    "CYTOP": 2.1,
    "Teflon AF": 1.93,
    "SiO2": 3.9,
    "SU-8": 3.2,
    "Parylene N": 2.65,
    "Parylene D": 2.84,
    "PDMS": 2.7,
    "Si3N4": 7.5,
}


class DropbotStatusAndControlsModel(BaseStatusModel):
    """Model for DropBot status display and controls.

    Extends BaseStatusModel with DropBot-specific controls and sensor readings.
    Connection/mode/icon traits and their observers are inherited.
    """

    # ---- Class-level constants ----------------------------------------
    DEFAULT_ICON_PATH = DROPBOT_IMAGE
    CHIP_INSERTED_ICON_PATH = DROPBOT_CHIP_INSERTED_IMAGE
    DISCONNECTED_COLOR = disconnected_color
    CONNECTED_NO_DEVICE_COLOR = connected_no_device_color
    CONNECTED_COLOR = connected_color
    HALTED_COLOR = halted_color

    # ---- Hardware controls (user-writable via UI) ----------------------
    voltage = RangeWithCustomViewHints(
        30, 140, value=DropbotPreferences().default_voltage, suffix=" V",
        desc="Voltage to set on the DropBot device (V)",
    )
    frequency = RangeWithCustomViewHints(
        100, 20000, value=DropbotPreferences().default_frequency, step=100, suffix=" Hz",
        desc="Frequency to set on the DropBot device (Hz)",
    )

    # ---- Device-specific status ----------------------------------------
    chip_status_text = Str("Not Inserted")

    # ---- Dielectric material selection ----------------------------------
    dielectric_material = Enum(*list(DIELECTRIC_MATERIALS.keys()),
                               desc="Dielectric material for thickness calculation")

    # ---- Sensor readings (raw values set by message handler) -----------
    # NaN magnitude means "no reading available"
    capacitance = Instance(pint.Quantity, desc="Raw capacitance (pF)")
    voltage_readback = Instance(pint.Quantity, desc="Voltage readback from device (V)")
    c_device = Instance(pint.Quantity, desc="Capacitance density / c_device (pF/mm²)")
    force = Instance(pint.Quantity, desc="Calculated force (mN/m)")
    dielectric_thickness = Instance(pint.Quantity, desc="Calculated dielectric thickness (um)")

    def _capacitance_default(self):
        return ureg("nan pF")

    def _voltage_readback_default(self):
        return ureg("nan V")

    def _c_device_default(self):
        return ureg("nan pF/mm^2")

    def _force_default(self):
        return ureg("nan mN/m")

    def _dielectric_thickness_default(self):
        return ureg("nan um")

    def _dielectric_material_default(self):
        return "Choose Dielectric"

    # ---- Formatted sensor readings for display -------------------------
    capacitance_display = Str("-")
    voltage_readback_display = Str("-")
    frequency_display = Str("-")
    c_device_display = Str("-")
    force_display = Str("-")
    dielectric_thickness_display = Str("-")

    # ------------------------------------------------------------------ #
    # BaseStatusModel hook                                                 #
    # ------------------------------------------------------------------ #

    def _update_chip_display(self, inserted: bool) -> None:
        self.chip_status_text = "Inserted" if inserted else "Not Inserted"

    # ------------------------------------------------------------------ #
    # Observers                                                            #
    # ------------------------------------------------------------------ #

    @observe("realtime_mode")
    def _reset_readings_on_realtime_off(self, event):
        """Clear sensor displays when realtime mode is disabled."""
        if not event.new:
            self.reset_traits([
                "capacitance", "voltage_readback", "c_device",
                "force", "dielectric_thickness",
            ])
            self.frequency_display = "-"

    @observe("capacitance")
    def _update_capacitance_display(self, event):
        self.capacitance_display = self._format_reading(event.new)

    @observe("voltage_readback")
    def _update_voltage_readback_display(self, event):
        self.voltage_readback_display = self._format_reading(event.new)

    @observe("frequency,realtime_mode")
    def _update_frequency_display(self, event):
        if self.realtime_mode:
            self.frequency_display = self._format_reading(self.frequency * ureg.Hz)

    @observe("c_device")
    def _update_c_device_display(self, event):
        self.c_device_display = self._format_reading(event.new)

    @observe("force")
    def _update_force_display(self, event):
        self.force_display = self._format_reading(event.new)

    @observe("dielectric_thickness")
    def _update_dielectric_thickness_display(self, event):
        self.dielectric_thickness_display = self._format_reading(event.new)

    @observe("voltage_readback, c_device")
    def _recalculate_force(self, event):
        """Recalculate force when voltage_readback or c_device changes."""
        if math.isnan(self.voltage_readback.magnitude) or math.isnan(self.c_device.magnitude):
            self.force = ureg("nan mN/m")
            return
        force = ForceCalculationService.calculate_force_for_step(
            self.voltage_readback.magnitude, self.c_device.magnitude
        )
        self.force = ureg(f"{force:.4f} mN/m") if force is not None else ureg("nan mN/m")

    @observe("dielectric_material, c_device")
    def _recalculate_dielectric_thickness(self, event):
        """Recalculate dielectric thickness: d = epsilon_r * epsilon_0 / C_device.

        Triggered automatically when ``dielectric_material`` or ``c_device``
        changes.  Uses pint's built-in ``vacuum_permittivity`` for epsilon_0
        and converts the result to micrometres.
        """
        if not self.dielectric_material:
            self.reset_traits("dielectric_thickness")
            return

        epsilon_r = DIELECTRIC_MATERIALS.get(self.dielectric_material)
        if epsilon_r is None:
            self.reset_traits("dielectric_thickness")
            return

        if self.c_device is None or self.c_device.magnitude <= 0:
            self.reset_traits("dielectric_thickness")
            return

        # d = epsilon_r * epsilon_0 / C_device
        # Convert to micrometres

        self.dielectric_thickness = (epsilon_r * ureg.vacuum_permittivity / self.c_device).to("um")
        logger.info(
            f"Dielectric thickness calculated: {self.dielectric_thickness:.3f} um "
            f"(material={self.dielectric_material}, "
            f"epsilon_r={epsilon_r}, c_device={self.c_device} pF/mm^2)"
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_reading(value):
        if value is None or math.isnan(value.magnitude):
            return "-"
        return f"{value.to_compact():.{N_DISPLAY_DIGITS}g~H}"