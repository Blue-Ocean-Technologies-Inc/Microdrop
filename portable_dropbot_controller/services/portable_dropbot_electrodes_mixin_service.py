from traits.api import Dict, HasTraits, Str, provides

from electrode_controller.models import ElectrodeChannelsRequest
from logger.logger_service import get_logger
from microdrop_application.helpers import get_microdrop_redis_globals_manager

from ..consts import DEFAULT_NUM_CHANNELS
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)

logger = get_logger(__name__)
app_globals = get_microdrop_redis_globals_manager()


@provides(IPortableDropbotControlMixinService)
class PortableDropbotElectrodesMixinService(HasTraits):
    id = Str("portable_dropbot_electrodes_mixin_service")
    name = Str("Portable Dropbot Electrodes Mixin")

    message_context = Dict

    def _board_channels(self):
        """The driver detects 120 vs 200 channels at login; before it
        has answered, validate against the larger board."""
        try:
            return int(self.proxy.uart.board_channels)
        except Exception:
            return DEFAULT_NUM_CHANNELS

    def on_electrodes_state_change_request(self, message):
        if self.proxy is None:
            logger.warning("Portable Dropbot not connected: ignoring "
                           "electrode state change request.")
            return

        if not self.realtime_mode:
            # Same hard gate as the regular DropBot backend: the
            # frontend already withholds clicks outside realtime mode,
            # but the hardware must not actuate on a stray request
            # either.
            logger.warning("Cannot process actuations since realtime "
                           "mode is disabled.")
            return

        model = ElectrodeChannelsRequest.model_validate_json(
            message,
            context={"max_channels": self._board_channels()},
        )
        channels = [int(channel) for channel in model.channels]
        logger.debug(f"Electrode state change requested: "
                     f"{len(channels)} active channel(s) {channels}")
        ok, _ = self._proxy_call(
            "electrode actuation",
            lambda: self.proxy.actuate_channels(channels))
        if ok:
            app_globals["last_channel_states_requested"] = str(message)
            logger.info(f"Portable Dropbot electrode update applied: "
                        f"{len(channels)} active")
        else:
            logger.warning(f"Portable Dropbot electrode update FAILED "
                           f"({len(channels)} active requested)")
