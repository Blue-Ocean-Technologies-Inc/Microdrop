from traits.api import Bool, Instance, Int, List

from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase

from ..opendrop_serial_proxy import OpenDropSerialProxy
from ..preferences import OpenDropPreferences


class IOpenDropControllerBase(IDramatiqControllerBase):
    """
    Interface for OpenDrop controller service.
    """

    proxy = Instance(OpenDropSerialProxy, desc="Serial proxy for OpenDrop hardware.")
    dropbot_connection_active = Bool(
        desc=(
            "Kept for compatibility with existing services. True when OpenDrop connection is active."
        )
    )
    preferences = Instance(OpenDropPreferences, desc="OpenDrop controller preferences.")
    board_id = Int(desc="OpenDrop board id reported by firmware.")
    set_temperatures = List(Int, desc="Current temperature setpoints [t1, t2, t3].")

    def on_electrodes_state_change_request(self, message):
        """
        Set OpenDrop electrode state from serialized channel map.
        """
