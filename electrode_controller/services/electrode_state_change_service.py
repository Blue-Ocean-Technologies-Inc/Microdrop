# library imports
from traits.api import provides, HasTraits, Str

# interface imports from microdrop plugins
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

# microdrop utils imports
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

# local imports
from ..models import ElectrodeStateChangeRequestMessageModel


@provides(IDropbotControlMixinService)
class ElectrodeStateChangeMixinService(HasTraits):
    """
    A mixin Class that adds methods to change the electrode state in a dropbot.

    We assume that the base dropbot_controller plugin has been loaded with all of its services.
    So we should have access to the dropbot proxy object here, per the IDropbotControllerBase.
    """

    id = Str('electrode_state_change_mixin_service')
    name = Str('Electrode state change Mixin')

    ######################################## Methods to Expose #############################################
    def on_electrodes_state_change_request(self, message):
        """
        Method following the simple example in examples/tests/test_dropbot_methods to actuate electrodes on dropbot
        given the states and channels pairs in the JSON message as per ElectrodeStateChangeRequestMessageModel.
        """
        channel_states_map_model = ElectrodeStateChangeRequestMessageModel(json_message=message,
                                                                           num_available_channels=self.proxy.number_of_channels)

        # do actuation
        self.proxy.state_of_channels = channel_states_map_model.channels_states_boolean_mask

        logger.info(f"{self.proxy.state_of_channels.sum()} number of channels actuated now")
