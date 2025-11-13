from traits.api import Instance

from ..dramatiq_view_model import DramatiqStatusViewModel
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase


class IDramatiqPeripheralStatusController(IDramatiqControllerBase):
    """
    Interface for the Dramatiq  Status Controller.
    Provides a dramatiq listener which recieved messages that request changes to the dropbot status widget.
    """

    ui = Instance(DramatiqStatusViewModel)

    def controller_signal_handler(self):
        """The view should have a controller_signal. This handler will be connected to that signal"""
