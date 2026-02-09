from traits.api import HasTraits, Bool, Str


class DropBotStatusModel(HasTraits):
    """Represents the raw state of the DropBot hardware."""
    # Connection state
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    # Sensor readings
    capacitance = Str("-", desc="Raw capacitance in pF")
    zstage_position = Str("-", desc="Zstage height in mm")
    voltage = Str("-", desc="Voltage set to device in V")

    frequency = Str("-", desc="Frequency of chip in Hz")
    chip_temp = Str("-", desc="Chip temperature in C")
    device_temp = Str("-", desc="Device temperature in C")
    device_humidity = Str("-", desc="Humidity in %")


    def reset_readings(self):
        """Reset the readings reading counter."""
        self.capacitance = self.voltage = self.frequency = self.chip_temp = self.device_temp = self.device_humidity = "-"

