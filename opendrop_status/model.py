from traits.api import Bool, HasTraits, Str


class OpenDropStatusModel(HasTraits):
    """Represents the raw state of the OpenDrop hardware."""

    connected = Bool(False, desc="True if OpenDrop is connected")
    board_id = Str("-", desc="OpenDrop board identifier")
    temperature_1 = Str("-", desc="Temperature channel 1 in C")
    temperature_2 = Str("-", desc="Temperature channel 2 in C")
    temperature_3 = Str("-", desc="Temperature channel 3 in C")
    feedback_active_channels = Str("-", desc="Number of active feedback channels")

    def reset_readings(self):
        self.temperature_1 = "-"
        self.temperature_2 = "-"
        self.temperature_3 = "-"
        self.feedback_active_channels = "-"
        self.board_id = "-"
