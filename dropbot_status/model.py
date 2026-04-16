import math

import pint
from traits.api import HasTraits, Bool, Instance, Enum, observe

from microdrop_utils.ureg_helpers import ureg

from logger.logger_service import get_logger
logger = get_logger(__name__)

# Dielectric materials and their relative permittivity values.
# Used to calculate dielectric thickness from device capacitance via:
#   d = epsilon * epsilon_0 / C_device
DIELECTRIC_MATERIALS = {
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


class DropBotStatusModel(HasTraits):
    """Represents the raw state of the DropBot hardware."""
    # Connection state
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    # Sensor readings — NaN magnitude means "no reading available"
    capacitance = Instance(pint.Quantity, desc="Raw capacitance (pF)")
    voltage = Instance(pint.Quantity, desc="Voltage set to device (V)")
    c_device = Instance(pint.Quantity, desc="Capacitance density / c_device (pF/mm^2)")
    force = Instance(pint.Quantity, desc="Calculated force (mN/m)")

    # Dielectric thickness calculation state
    selected_dielectric_material = Enum(*DIELECTRIC_MATERIALS.keys(), desc="Selected dielectric material")
    dielectric_thickness = Instance(pint.Quantity, desc="Calculated dielectric thickness (um)")

    def _capacitance_default(self):
        return ureg("nan pF")

    def _voltage_default(self):
        return ureg("nan V")

    def _c_device_default(self):
        return ureg("nan pF/mm^2")

    def _force_default(self):
        return ureg("nan mN/m")

    def _dielectric_thickness_default(self):
        return ureg("nan um")

    def reset_readings(self):
        """Reset all sensor readings to NaN."""
        self.reset_traits(
            [
                "capacitance",
                "voltage",
                "c_device",
                "force",
                "dielectric_thickness",
            ]
        )

    @observe("selected_dielectric_material, c_device")
    def _recalculate_dielectric_thickness(self, event):
        """Recalculate dielectric thickness: d = epsilon_r * epsilon_0 / C_device.

        Triggered automatically when ``selected_dielectric_material`` or
        ``c_device`` changes.  Uses pint's built-in ``vacuum_permittivity``
        for epsilon_0 and converts the result to micrometres.
        """
        if not self.selected_dielectric_material:
            self.reset_traits("dielectric_thickness")
            return

        epsilon_r = DIELECTRIC_MATERIALS.get(self.selected_dielectric_material)
        if epsilon_r is None:
            self.reset_traits("dielectric_thickness")
            return

        if self.c_device is None or math.isnan(self.c_device.magnitude) or self.c_device.magnitude <= 0:
            self.reset_traits("dielectric_thickness")
            return

        # d = epsilon_r * epsilon_0 / C_device
        # Convert to micrometres

        self.dielectric_thickness = (epsilon_r * ureg.vacuum_permittivity / self.c_device).to("um")
        logger.info(
            f"Dielectric thickness calculated: {self.dielectric_thickness:.3f} um "
            f"(material={self.selected_dielectric_material}, "
            f"epsilon_r={epsilon_r}, c_device={self.c_device} pF/mm^2)"
        )
