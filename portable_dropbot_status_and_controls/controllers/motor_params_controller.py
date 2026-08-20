import json

from pyface.api import YES
from traits.api import observe
from traitsui.api import Controller

from logger.logger_service import get_logger
from microdrop_application.dialogs.pyface_wrapper import confirm
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from portable_dropbot_controller.consts import (
    MOTOR_PARAMS_PRESET, MOTOR_PARAMS_READ, MOTOR_PARAMS_WRITE,
    REBOOT_MOTOR_BOARD,
)

logger = get_logger(__name__)


class MotorParamsController(Controller):
    """Buttons -> request topics. Flash persistence and the reboot are
    behind confirms — both outlive the session."""

    @observe("model:selected_motor")
    def _on_motor_changed(self, event):
        # The fields on screen belong to the previous motor now:
        # require a fresh read before they can be written anywhere.
        self.model.params_loaded = False
        self.model.loaded_fields = []
        self.model.params_status = "-"
        if self.model.connected:
            publish_message(topic=MOTOR_PARAMS_READ,
                            message=self.model.selected_motor)

    @observe("model:read_button")
    def _read(self, event):
        publish_message(topic=MOTOR_PARAMS_READ,
                        message=self.model.selected_motor)

    @observe("model:write_button")
    def _write(self, event):
        publish_message(topic=MOTOR_PARAMS_WRITE, message=json.dumps({
            "motor": self.model.selected_motor,
            "fields": {name: getattr(self.model, name)
                       for name in self.model.loaded_fields},
        }))
        logger.info(f"Requested {self.model.selected_motor} params "
                    f"write ({len(self.model.loaded_fields)} fields)")

    @observe("model:preset_button")
    def _preset(self, event):
        motor = self.model.selected_motor
        if confirm(
                None,
                f"Persist the {motor} motor's CURRENT on-device params "
                f"to flash (survives reboot)? Write first if you have "
                f"unsaved edits.",
                title="Preset to Flash") != YES:
            return
        publish_message(topic=MOTOR_PARAMS_PRESET, message=motor)

    @observe("model:reboot_button")
    def _reboot(self, event):
        if confirm(
                None,
                "Reboot the motor board so flashed params take effect? "
                "All motors stop and lose their homing — run Home All "
                "from the motor panel afterwards.",
                title="Reboot Motor Board") != YES:
            return
        self.model.params_status = "rebooting motor board..."
        publish_message(topic=REBOOT_MOTOR_BOARD, message="")
