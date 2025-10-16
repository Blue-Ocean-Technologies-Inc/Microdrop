from traits.api import Instance, Bool

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

    def _on_dropbot_proxy_connected(self):
        """
        Method that should be called once a dropbot proxy has been connected. There should be a routine here to setup
        the new connection. For instance, updating the states as needed, and hooking up the blinker signals emitted
        by the dropbot proxy to appropriate handlers (like the halted event for instance).
        """

    ################################### Exposed Methods ###############################

    def on_topic_request(self, message):
        """
        A method that is called when a dropbot topic request is received. This naming convention is to be followed
        for methods to be exposed. While calling it one would send a message to a topic that is
        something/dropbot/topic

        'on_chip_check_request' and 'on_detect_shorts_request' should be provided by default.
        """

    def on_chip_check_request(self, message):
        """
        Check if chip is inserted by reading **active low** `OUTPUT_ENABLE_PIN`.
        """

    def on_detect_shorts_request(self, message):
        """
        Detect any shorts on the chip.
        """

    ####################################################################################