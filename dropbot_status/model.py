import pint
from traits.api import HasTraits, Bool, Instance

from microdrop_utils.ureg_helpers import ureg


class DropBotStatusModel(HasTraits):
    """Represents the raw state of the DropBot hardware."""
    # Connection state
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    # Sensor readings — NaN magnitude means "no reading available"
    capacitance = Instance(pint.Quantity, desc="Raw capacitance (pF)")
    voltage = Instance(pint.Quantity, desc="Voltage set to device (V)")
    pressure = Instance(pint.Quantity, desc="Capacitance density / c_device (pF/mm^2)")
    force = Instance(pint.Quantity, desc="Calculated force (mN/m)")
    dielectric_thickness = Instance(pint.Quantity, desc="Calculated dielectric thickness (um)")

    def _capacitance_default(self):
        return ureg("nan pF")

    def _voltage_default(self):
        return ureg("nan V")

    def _pressure_default(self):
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
                "pressure",
                "force",
                "dielectric_thickness",
            ]
        )
