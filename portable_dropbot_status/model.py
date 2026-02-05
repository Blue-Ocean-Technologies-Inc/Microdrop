from traits.api import HasTraits, Bool, Str


class DropBotStatusModel(HasTraits):
    """Represents the raw state of the DropBot hardware."""
    # Connection state
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    # Sensor readings
    capacitance = Str("-", desc="Raw capacitance in pF")
    voltage = Str("-", desc="Voltage set to device in V")
    pressure = Str("-", desc="Pressure reading in pF/mm^2 ")
    force = Str("-", desc="Calculated force in N")

    def reset_readings(self):
        """Reset the readings reading counter."""
        self.capacitance = "-"
        self.voltage = "-"
        self.pressure = "-"
        self.force = "-"
