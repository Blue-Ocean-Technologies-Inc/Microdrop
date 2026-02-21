import json

from traits.api import HasTraits, Str, provides

from logger.logger_service import get_logger

from ..interfaces.i_opendrop_control_mixin_service import IOpenDropControlMixinService

logger = get_logger(__name__)


@provides(IOpenDropControlMixinService)
class OpenDropStatesSettingMixinService(HasTraits):
    id = Str("opendrop_states_setting_mixin_service")
    name = Str("OpenDrop States Setting Mixin")

    def on_set_realtime_mode_request(self, message):
        desired = str(message) == "True"
        self.realtime_mode = desired
        self._publish_realtime_mode()
        if not desired and self.proxy is not None:
            self.proxy.state_of_channels[:] = False
            self._push_state_to_device(force=True)
        elif desired:
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
