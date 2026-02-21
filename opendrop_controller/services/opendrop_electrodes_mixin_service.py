import json

import numpy as np
from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from ..consts import NUM_ELECTRODES
from ..interfaces.i_opendrop_control_mixin_service import IOpenDropControlMixinService

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


@provides(IOpenDropControlMixinService)
class OpenDropElectrodesMixinService(HasTraits):
    id = Str("opendrop_electrodes_mixin_service")
    name = Str("OpenDrop Electrodes Mixin")

    def on_electrodes_state_change_request(self, message):
        if self.proxy is None:
            logger.warning("OpenDrop not connected: ignoring electrode state change request.")
            return

        payload = json.loads(str(message))
        channel_mask = np.zeros(NUM_ELECTRODES, dtype=bool)

        for key, value in payload.items():
            idx = int(key)
            if 0 <= idx < NUM_ELECTRODES:
                channel_mask[idx] = bool(value)

        self.proxy.state_of_channels = channel_mask
        app_globals["last_channel_states_requested"] = str(message)
        telemetry = self._push_state_to_device(force=False)
        active_channels = int(channel_mask.sum())
        logger.info(
            f"OpenDrop electrode update applied: {active_channels}/{NUM_ELECTRODES} active "
            f"(telemetry={'ok' if telemetry is not None else 'skipped'})"
        )
