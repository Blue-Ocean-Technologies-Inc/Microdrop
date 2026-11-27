# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json

# Enthought library imports.
from traits.api import HasTraits, Str, provides

# Local imports.
from ..interfaces.i_opendrop_control_mixin_service import IOpenDropControlMixinService

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


@provides(IOpenDropControlMixinService)
class OpenDropStatesSettingMixinService(HasTraits):
    id = Str("opendrop_states_setting_mixin_service")
    name = Str("OpenDrop States Setting Mixin")

    def on_set_realtime_mode_request(self, message):
        desired = str(message) == "True"

        # Realtime turns on only once the board has taken the state: a
        # failed write must not leave the key reading True.
        if desired:
            if self._push_state_to_device(force=True) is None:
                logger.warning("OpenDrop realtime mode stays off: no state reply")

                # Publish off so a pane that flipped its toggle on
                # optimistically reverts.
                self.realtime_mode = False
                self._publish_realtime_mode()

                return

            self.realtime_mode = True
            self._publish_realtime_mode()

        else:
            self.realtime_mode = False
            self._publish_realtime_mode()

            if self.proxy is not None:
                self.proxy.state_of_channels[:] = False
                self._push_state_to_device(force=True)

        logger.info(f"OpenDrop realtime mode set to {self.realtime_mode}")

    def on_set_feedback_request(self, message):
        self.feedback_enabled = str(message) == "True"
        if self.preferences is not None:
            self.preferences.feedback_enabled = self.feedback_enabled
        self._push_state_to_device(force=True)
        logger.info(f"OpenDrop feedback set to {self.feedback_enabled}")

    def on_set_temperatures_request(self, message):
        payload = json.loads(str(message))
        self.set_temperatures = [
            int(payload.get("t1", self.set_temperatures[0])),
            int(payload.get("t2", self.set_temperatures[1])),
            int(payload.get("t3", self.set_temperatures[2])),
        ]
        if self.preferences is not None:
            self.preferences.temperature_1 = self.set_temperatures[0]
            self.preferences.temperature_2 = self.set_temperatures[1]
            self.preferences.temperature_3 = self.set_temperatures[2]
        self._push_state_to_device(force=True)
        logger.info(f"OpenDrop temperatures updated: {self.set_temperatures}")

    def on_change_settings_request(self, message):
        payload = json.loads(str(message))
        if self.preferences is not None:
            self.preferences.trait_set(**payload)
            self.feedback_enabled = bool(self.preferences.feedback_enabled)
            self.set_temperatures = [
                int(self.preferences.temperature_1),
                int(self.preferences.temperature_2),
                int(self.preferences.temperature_3),
            ]
        self._push_state_to_device(force=True)
        logger.info(f"OpenDrop settings changed: {sorted(payload.keys())}")

    def on_set_temperature_1_request(self, message):
        self.on_set_temperatures_request(json.dumps({"t1": int(message)}))

    def on_set_temperature_2_request(self, message):
        self.on_set_temperatures_request(json.dumps({"t2": int(message)}))

    def on_set_temperature_3_request(self, message):
        self.on_set_temperatures_request(json.dumps({"t3": int(message)}))
