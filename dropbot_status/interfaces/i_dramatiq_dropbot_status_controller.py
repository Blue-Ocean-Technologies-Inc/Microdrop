from traits.api import Instance
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
from dropbot_status.dramatiq_viewcontroller import DramatiqDropBotStatusWidget


class IDramatiqDropbotStatusController(IDramatiqControllerBase):
    """
    Interface for the Dramatiq Dropbot Status Controller.
    Provides a dramatiq listener which recieved messages that request changes to the dropbot status widget.
    """

    view = Instance(DramatiqDropBotStatusWidget, desc="The DropbotStatusWidget object")

    def controller_signal_handler(self):
        """The view should have a controller_signal. This handler will be connected to that signal"""
