from traits.api import Any, Bool, Instance, Int

from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase

from ..preferences import PortableDropbotPreferences


class IPortableDropbotControllerBase(IDramatiqControllerBase):
    """
    Interface for the Portable Dropbot controller service.
    """

    # Any rather than an Instance of the driver class, so importing
    # the interface never drags in the vendored serial stack.
    proxy = Any(desc="DropletBotSession for the Portable Dropbot "
                     "hardware; None while disconnected.")
    portable_dropbot_connection_active = Bool(
        desc="True while the Portable Dropbot connection is active.")
    preferences = Instance(PortableDropbotPreferences,
                           desc="Portable Dropbot controller preferences.")
    voltage = Int(desc="HV amplitude setpoint (V).")
    frequency = Int(desc="HV frequency setpoint (Hz).")

    def on_electrodes_state_change_request(self, message):
        """
        Actuate the Portable Dropbot electrodes from a serialized
        channel list.
        """
