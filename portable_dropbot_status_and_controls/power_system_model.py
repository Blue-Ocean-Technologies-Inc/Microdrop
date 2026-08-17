from traits.api import Bool, Button

from microdrop_application.menus import is_advanced_mode
from template_status_and_controls.base_model import BaseStatusModel

from .consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotPowerSystemModel(BaseStatusModel):
    """Qt-free state for the power-system pane: fan and buzzer only
    (the rest of the vendor tab — power ctrl, resets, baud, CAN — is
    deliberately not exposed). Unlocked only in Advanced Mode."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    #: Follows the Edit-menu Advanced Mode toggle (via the message
    #: handler); the controls stay hidden without it.
    advanced_mode = Bool()

    def _advanced_mode_default(self):
        return is_advanced_mode()

    # Explicit On/Off buttons, exactly like the vendor UI — none of
    # these states are read back, so a toggle would just be optimism.
    buzzer_on_button = Button("Buzzer On")
    buzzer_off_button = Button("Buzzer Off")
    mcu_fan_on_button = Button("MCU Fan On")
    mcu_fan_off_button = Button("MCU Fan Off")
    motor_fan_on_button = Button("Motor Fan On")
    motor_fan_off_button = Button("Motor Fan Off")
