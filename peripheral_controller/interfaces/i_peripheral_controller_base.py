from traits.api import Instance, Bool, Str

from microdrop_utils.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase

from ..preferences import PeripheralPreferences


class IPeripheralControllerBase(IDramatiqControllerBase):
    """
    Interface for peripheral controllers.
    Provides methods for controlling and monitoring a peripheral device.
    """

    _device_name = Str
    proxy = Instance(DramatiqPeripheralSerialProxy, desc="The DramatiqSerialProxy object")
    connection_active = Bool(
        desc="Specifies if the controller is actively listening to commands or not. So if the "
             "connection is not there, no commands will be processed except searching for s connection"
    )
    preferences = Instance(PeripheralPreferences,
                           desc="The preferences object for the dropbot controller service"
                           )

