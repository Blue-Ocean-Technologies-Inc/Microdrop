# library imports
from traits.api import provides, HasTraits, Str, Instance

# interface imports from microdrop plugins
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from dropbot_controller.models.dropbot_channels_properties_model import DropbotChannelsPropertiesModelFromJSON

# microdrop utils imports
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


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
            with self.proxy_state_manager.safe_proxy_access("electrode_state_change", timeout=3.0):
                
                # Create and validate message model
                channel_states_map_model = DropbotChannelsPropertiesModelFromJSON(
                    num_available_channels=self.proxy.number_of_channels,
                    property_dtype=bool,
                    channels_properties_json=message,
                ).model

                # Validate boolean mask size
                expected_channels = self.proxy.number_of_channels
                mask_size = len(channel_states_map_model.channels_properties_mask)
                
                if mask_size != expected_channels:
                    logger.error(f"Boolean mask size mismatch: expected {expected_channels}, got {mask_size}")
                    return

                # Set electrode state safely
                with self.proxy.transaction_lock:
                    self.proxy.state_of_channels = channel_states_map_model.channels_properties_mask
                
                active_channels = self.proxy.state_of_channels.sum()
                logger.info(f"{active_channels} channels actuated")
                logger.debug(f"{self.proxy.state_of_channels}")
                
        except TimeoutError:
            logger.error("Timeout waiting for proxy access for electrode state change")
        except RuntimeError as e:
            logger.error(f"Proxy state error during electrode state change: {e}")
        except Exception as e:
            logger.error(f"Error processing electrode state change: {e}")
