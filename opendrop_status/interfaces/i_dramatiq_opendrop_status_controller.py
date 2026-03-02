from traits.api import Instance

from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase
from opendrop_status.dramatiq_UI import DramatiqOpenDropStatusViewModel


class IDramatiqOpenDropStatusController(IDramatiqControllerBase):
    """
    Interface for the Dramatiq OpenDrop Status Controller.
    """

    ui = Instance(DramatiqOpenDropStatusViewModel)

    def controller_signal_handler(self):
        """Handle signals emitted to the OpenDrop status widget."""
