from traits.api import Instance, Bool

from dropbot_controller.services.global_proxy_state_manager import GlobalProxyStateManager
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase


class IDropbotControllerBase(IDramatiqControllerBase):
    """
    Interface for the Dropbot Controller Service.
    Provides methods for controlling and monitoring a Dropbot device.
    """

    proxy = Instance(DramatiqDropbotSerialProxy, desc="The DramatiqDropbotSerialProxy object")
    dropbot_connection_active = Bool(
        desc="Specifies if the controller is actively listening to commands or not. So if the dropbot "
             "connection is not there, no commands will be processed except searching for a dropbot "
             "connection"
    )

    proxy_state_manager = Instance(GlobalProxyStateManager, desc="Manager to use proxy instances safely")

    def _on_dropbot_proxy_connected(self):
        """
        Method that should be called once a dropbot proxy has been connected. There should be a routine here to setup
        the new connection. For instance, updating the states as needed, and hooking up the blinker signals emitted
        by the dropbot proxy to appropriate handlers (like the halted event for instance).
        """
