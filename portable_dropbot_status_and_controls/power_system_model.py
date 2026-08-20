from traits.api import Bool

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

    # Requested states, not read back from the device — the toggles
    # show what was last asked for.
    buzzer_state = Bool()
    mcu_fan_state = Bool()
