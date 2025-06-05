from traits.api import HasTraits, Instance, Dict, List, Str
import json
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from device_viewer.models.electrodes import Electrodes
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE

logger = get_logger(__name__)


class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class."""

    #: The electrodes model containing all electrode data
    electrodes_model = Instance(Electrodes)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    def handle_electrode_click(self, _electrode_id: Str):
        """Handle an electrode click event."""

        logger.debug(f"Electrode {_electrode_id} clicked")

        # get electrode model for current electrode clicked
        _clicked_electrode_channel = self.electrodes_model[_electrode_id].channel

        logger.debug(f"Channel {_clicked_electrode_channel} will be actuated")

        affected_electrode_ids = self.electrodes_model.channels_electrode_ids_map[_clicked_electrode_channel]

        logger.debug(f"Affected electrodes {affected_electrode_ids} with same channel as clicked electrode")

        # NOTE: performance is ok, sticking to serial for loop. If need be, we may have to multithread.
        for affected_electrode_id in affected_electrode_ids:
            # obtain affected electrode object
            _electrode = self.electrodes_model[affected_electrode_id]

            # update electrode model for electrode clicked and all electrodes with same channel affected by this click.
            _electrode.state = not _electrode.state

            # update electrode view for electrode clicked and all electrodes with same channel affected by this click.
            _electrode_view = self.electrode_view_layer.electrode_views[affected_electrode_id]
            _electrode_view.update_color(_electrode.state)

        updated_channels_states_map = self.electrodes_model.channels_states_map

        logger.info(f"New electrode channels states map: {updated_channels_states_map}")
        logger.info(f"Number of electrodes actuated now: {sum(self.electrodes_model.electrode_states)}")

        # publish event to all interested. Mainly to backend actors who need to know user has requested the electrode
        # to be actuated / unactuated.
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(updated_channels_states_map))