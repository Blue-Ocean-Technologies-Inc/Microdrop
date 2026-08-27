from traits.api import Bool, Button, Enum, Float, Int, List, Str

from microdrop_application.menus import is_advanced_mode
from portable_dropbot_controller.consts import MOTOR_IDS
from template_status_and_controls.base_model import BaseStatusModel

from ..consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotAdvancedControlsModel(BaseStatusModel):
    """Qt-free state for the Advanced Controls pane: the power-system
    buzzer plus one motor's mechanical tuning struct
    (MOTOR_PARAM_FIELDS wire order), read from the board into the
    field traits below, written back to RAM, presetted to flash, and
    made effective by a motor-board reboot. Unlocked only in Advanced
    Mode."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    #: Follows the Edit-menu Advanced Mode toggle (via the message
    #: handler); the controls stay hidden without it.
    advanced_mode = Bool()

    def _advanced_mode_default(self):
        return is_advanced_mode()

    # ---- Power system ------------------------------------------------
    #: Requested buzzer state, not read back from the device — the
    #: toggle shows what was last asked for. (The MCU fan toggle lives
    #: in the main status pane's mechanism quick controls.)
    buzzer_state = Bool()

    # ---- Motor params ------------------------------------------------
    selected_motor = Enum(*MOTOR_IDS)

    # ---- The param struct fields, named exactly as on the wire ------
    nl_pos = Float()
    pl_pos = Float()
    round_len = Float()
    origin_offset = Float()
    origin_area = Float()
    step_len = Float()
    motor_polarity = Int()
    I_hold = Int()
    I_run = Int()
    subdiv = Int()
    run_sgt = Int()
    rst_sgt = Int()
    bspd = Int()
    rspd = Int()
    acc_run = Int()
    acc_rst = Int()

    #: The fields the last read actually returned (old firmware stops
    #: at rspd) — a write sends back exactly these, and Write stays
    #: disabled until a read has succeeded.
    loaded_fields = List(Str)
    params_loaded = Bool(False)

    read_button = Button("Read")
    write_button = Button("Write (RAM)")
    preset_button = Button("Preset to Flash")
    reboot_button = Button("Reboot Motor Board")
    params_status = Str("-", desc="Last read/write/preset/reboot "
                                  "outcome")
