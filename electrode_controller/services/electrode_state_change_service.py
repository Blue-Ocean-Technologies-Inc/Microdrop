# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# library imports

# Third-party imports.
import numpy as np
from dropbot.threshold import actuate_channels
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Dict, HasTraits, Int, Str, provides

# Microdrop package imports.
from dropbot_controller.interfaces.i_dropbot_control_mixin_service import (
    IDropbotControlMixinService,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    ELECTRODES_STATE_APPLIED,
    LAST_CHANNELS_REQUESTED_KEY,
    disabled_channels_changed_publisher,
)
from ..models import ElectrodeChannelsRequest

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

app_globals = get_microdrop_redis_globals_manager()


@provides(IDropbotControlMixinService)
class ElectrodeStateChangeMixinService(HasTraits):
    """
    A mixin Class that adds methods to change the electrode state in a dropbot.

    We assume that the base dropbot_controller plugin has been loaded with
    all of its services. So we should have access to the dropbot proxy
    object here, per the IDropbotControllerBase.
    """

    id = Str("electrode_state_change_mixin_service")
    name = Str("Electrode state change Mixin")
    message_context = Dict(
        Str, Int, desc="Context for message context. Max channels index for instance"
    )

    ###################### Methods to Expose #########################

    def on_electrodes_state_change_request(self, message: str):
        try:
            if not hasattr(self, "proxy") or self.proxy is None:
                logger.error("Proxy not available for electrode state change")
                return

            elif not self.realtime_mode:
                logger.warning(
                    "Cannot process actuations since realtime mode is disabled. "
                    "Will process message when realtime mode on"
                )
                return

            # Use safe proxy access for electrode state changes
            with self.proxy.transaction_lock:
                if not self.message_context:
                    self.message_context = {
                        "max_channels": self.proxy.number_of_channels
                    }

                # Validate message
                model = ElectrodeChannelsRequest.model_validate_json(
                    message,
                    context=self.message_context,
                )

                actuated_channels = actuate_channels(
                    self.proxy, list(model.channels), timeout=5, allow_disabled=True
                )

                app_globals[LAST_CHANNELS_REQUESTED_KEY] = message

                active_channels = self.proxy.state_of_channels.sum()
                logger.info(f"{active_channels} channels actuated: {actuated_channels}")
                logger.debug(f"{self.proxy.state_of_channels}")

                # If requested vs actuated channel counts differ, some
                # channels were disabled by the hardware
                if len(model.channels) != len(actuated_channels):
                    logger.warning(
                        f"Actuation discrepancy: requested {len(model.channels)} "
                        f"channels, but only {len(actuated_channels)} were "
                        "actuated. Checking disabled channels mask."
                    )
                    mask = np.array(self.proxy.disabled_channels_mask)
                    disabled_indices = set(int(i) for i in np.where(mask != 0)[0])
                    disabled_channels_changed_publisher.publish(disabled_indices)

            # sending ack
            publish_message(str(len(actuated_channels)), topic=ELECTRODES_STATE_APPLIED)

        except TimeoutError:
            logger.error(
                "Timeout waiting for proxy access for electrode state change",
                exc_info=True,
            )
        except RuntimeError as e:
            logger.error(
                f"Proxy state error during electrode state change: {e}", exc_info=True
            )
        except ValidationError as e:
            logger.error(
                f"Actuated channels message should be list of int between 0 "
                f"and {self.message_context['max_channels']}: {e}",
                exc_info=True,
            )
        except Exception as e:
            logger.error(f"Error processing electrode state change: {e}", exc_info=True)
