# library imports
from traits.api import provides, HasTraits, Str, Instance
from numpy import where

# interface imports from microdrop plugins
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from dropbot_controller.models.dropbot_channels_properties_model import DropbotChannelsPropertiesModelFromJSON

from dropbot.threshold import actuate_channels

# microdrop utils imports
from logger.logger_service import get_logger
logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()


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
        try:
            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for electrode state change")
                return

            # Use safe proxy access for electrode state changes
            with self.proxy.transaction_lock:
                
                # Create and validate message model
                channel_states_map_model = DropbotChannelsPropertiesModelFromJSON(
                    num_available_channels=self.proxy.number_of_channels,
                    property_dtype=bool,
                    channels_properties_json=message,
                ).model

                # Validate boolean mask size
                expected_channels = self.proxy.number_of_channels
                mask_size = len(channel_states_map_model.channels_properties_array)
                
                if mask_size != expected_channels:
                    logger.error(f"Boolean mask size mismatch: expected {expected_channels}, got {mask_size}")
                    return

                # self.proxy.state_of_channels = channel_states_map_model.channels_properties_array

                channels_to_actuate = list(where(channel_states_map_model.channels_properties_array == True)[0])

                actuated_channels = actuate_channels(self.proxy, channels_to_actuate, timeout=5, allow_disabled=True)

                app_globals["last_channel_states_requested"] = message

                active_channels = self.proxy.state_of_channels.sum()
                logger.info(f"{active_channels} channels actuated: {actuated_channels}")
                logger.debug(f"{self.proxy.state_of_channels}")
                
        except TimeoutError:
            logger.error("Timeout waiting for proxy access for electrode state change")
        except RuntimeError as e:
            logger.error(f"Proxy state error during electrode state change: {e}")
        except Exception as e:
            logger.error(f"Error processing electrode state change: {e}")
