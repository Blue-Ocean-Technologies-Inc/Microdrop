# library imports
import numpy as np
from traits.api import provides, HasTraits, Str, Int, Dict

# interface imports from microdrop plugins
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService

from .models import ElectrodeChannelsRequest

# microdrop utils imports
from logger.logger_service import get_logger

logger = get_logger(__name__)

from pydantic import ValidationError


@provides(IDropbotControlMixinService)
class ElectrodeDisableMixinService(HasTraits):
    """
    A mixin class that adds methods to disable/enable electrode channels on a dropbot.

    When channels are disabled, the dropbot will refuse to actuate them. This is useful
    for marking bad electrodes that should never be actuated.

    We assume that the base dropbot_controller plugin has been loaded with all of its services.
    So we should have access to the dropbot proxy object here, per the IDropbotControllerBase.
    """

    id = Str('electrode_disable_mixin_service')
    name = Str('Electrode disable Mixin')
    message_context = Dict(Str, Int, desc="Context for message validation. Max channels index for instance")

    ######################################## Methods to Expose #############################################

    def on_electrodes_disable_request(self, message: str):
        try:
            if not hasattr(self, 'proxy') or self.proxy is None:
                logger.error("Proxy not available for electrode disable request")
                return

            with self.proxy.transaction_lock:

                if not self.message_context:
                    self.message_context = {"max_channels": self.proxy.number_of_channels}

                # Validate message
                model = ElectrodeChannelsRequest.model_validate_json(
                    message,
                    context=self.message_context,
                )

                disabled_channels = list(model.actuated_channels)

                # Build the disabled channels mask as a numpy array matching the proxy's channel count
                num_channels = self.proxy.number_of_channels
                mask = np.zeros(num_channels, dtype=int)
                mask[disabled_channels] = 1

                self.proxy.disabled_channels_mask = mask

                logger.info(f"Disabled channels mask updated: {len(disabled_channels)} channels disabled: {disabled_channels}")

        except ValidationError as e:
            logger.error(f"Disabled channels message should be list of int between 0 and {self.message_context.get('max_channels', '?')}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing electrode disable request: {e}", exc_info=True)