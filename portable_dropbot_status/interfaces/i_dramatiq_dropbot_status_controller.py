from traits.api import Instance

from dropbot_status.dramatiq_UI import DramatiqDropBotStatusViewModel
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase


class IDramatiqDropbotStatusController(IDramatiqControllerBase):
    """
    Interface for the Dramatiq Dropbot Status Controller.
    Provides a dramatiq listener which recieved messages that request changes to the dropbot status widget.
    """

    ui = Instance(DramatiqDropBotStatusViewModel)

    def controller_signal_handler(self):
        """The view should have a controller_signal. This handler will be connected to that signal"""
