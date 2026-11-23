# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Third-party imports.
from dropbot_portable.portable_dropbot_service import CMD_ELECTRODE_STATE_CH

# Enthought library imports.
from traits.api import Dict, HasTraits, Str, provides

# Microdrop package imports.
from device_viewer.consts import user_disabled_channels_mirror
from electrode_controller.models import ElectrodeChannelsRequest
from microdrop_application.helpers import get_microdrop_redis_globals_manager

# Local imports.
from ..consts import DEFAULT_NUM_CHANNELS, LAST_CHANNEL_STATES_REQUESTED_KEY
from ..interfaces.i_portable_dropbot_control_mixin_service import (
    IPortableDropbotControlMixinService,
)
from ..motion_replies import describe_last_result

# Logger import.
from logger.logger_service import get_logger

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
            logger.warning(
                "Portable Dropbot not connected: ignoring "
                "electrode state change request."
            )
            return

        if not self.realtime_mode:
            # Same hard gate as the regular DropBot backend: the
            # frontend already withholds clicks outside realtime mode,
            # but the hardware must not actuate on a stray request
            # either.
            logger.warning("Cannot process actuations since realtime mode is disabled.")
            return

        model = ElectrodeChannelsRequest.model_validate_json(
            message,
            context={"max_channels": self._board_channels()},
        )
        channels = user_disabled_channels_mirror.drop_from(
            model.channels, "Portable Dropbot actuation"
        )
        logger.debug(
            f"Electrode state change requested: "
            f"{len(channels)} active channel(s) {channels}"
        )
        ok, applied = self._proxy_call(
            "electrode actuation", lambda: self._set_electrode_states(channels)
        )

        if ok and applied:
            app_globals[LAST_CHANNEL_STATES_REQUESTED_KEY] = str(message)
            logger.info(
                f"Portable Dropbot electrode update applied: {len(channels)} active"
            )
        elif ok:
            reason = describe_last_result(self.proxy.uart, CMD_ELECTRODE_STATE_CH)
            self._publish_error(
                "electrode actuation",
                f"not applied, {len(channels)} active requested: {reason} "
                f"(the board refuses electrodes while the 24 V rails are off)",
            )
        else:
            logger.warning(
                f"Portable Dropbot electrode update FAILED "
                f"({len(channels)} active requested)"
            )

    def _set_electrode_states(self, channels):
        """Turn on exactly these channels, as the vendor UI's Electrodes tab
        writes them; True only when the board applied the write. The
        session's ``actuate_channels`` drops ``setElectrodeStates``'s False,
        which since dropbot-portable 1.8.0 is a final refusal (0x1242 FAILs
        while the 24 V rails are off), no longer retried on the legacy
        protocol."""
        uart = self.proxy.uart
        states = [False] * uart.board_channels

        for channel in channels:
            if 0 <= channel < len(states):
                states[channel] = True

        return uart.setElectrodeStates(states)
