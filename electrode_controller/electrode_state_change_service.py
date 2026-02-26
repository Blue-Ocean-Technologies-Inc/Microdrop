# library imports
from traits.api import provides, HasTraits, Str, Int, Dict

# interface imports from microdrop plugins
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from dropbot.threshold import actuate_channels

from .models import ElectrodeChannelsRequest
# microdrop utils imports
from logger.logger_service import get_logger

logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()

from pydantic import (
    ValidationError
)


@provides(IDropbotControlMixinService)
class ElectrodeStateChangeMixinService(HasTraits):
    """
    A mixin Class that adds methods to change the electrode state in a dropbot.

    We assume that the base dropbot_controller plugin has been loaded with all of its services.
    So we should have access to the dropbot proxy object here, per the IDropbotControllerBase.
    """

    id = Str('electrode_state_change_mixin_service')
    name = Str('Electrode state change Mixin')
    message_context = Dict(Str, Int, desc="Context for message context. Max channels index for instance")

    ######################################## Methods to Expose #############################################

    def on_electrodes_state_change_request(self, message: str):
        try:
            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for electrode state change")
                return

            elif not self.realtime_mode:
                logger.warning("Cannot process actuations since realtime mode is disabled. Will process message when realtime mode on")
                return

            # Use safe proxy access for electrode state changes
            with self.proxy.transaction_lock:

                if not self.message_context:
                    self.message_context = {"max_channels": self.proxy.number_of_channels}

                # Validate message
                model = ElectrodeChannelsRequest.model_validate_json(
                    message,
                    context=self.message_context,
                )

                actuated_channels = actuate_channels(self.proxy, list(model.actuated_channels), timeout=5, allow_disabled=True)

                app_globals["last_channels_requested"] = message

                active_channels = self.proxy.state_of_channels.sum()
                logger.info(f"{active_channels} channels actuated: {actuated_channels}")
                logger.debug(f"{self.proxy.state_of_channels}")

        except TimeoutError:
            logger.error("Timeout waiting for proxy access for electrode state change", exc_info=True)
        except RuntimeError as e:
            logger.error(f"Proxy state error during electrode state change: {e}", exc_info=True)
        except ValidationError as e:
            logger.error(f"Actuated channels message should be list of int between 0 and {self.message_context["max_channels"]}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing electrode state change: {e}", exc_info=True)
