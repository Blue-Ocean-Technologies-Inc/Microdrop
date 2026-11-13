# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from traits.api import Bool, Button, Enum, Float, Int, List, Str

# Microdrop package imports.
from microdrop_application.helpers import is_advanced_mode
from portable_dropbot_controller.consts import MOTOR_IDS
from template_status_and_controls.base_model import BaseStatusModel

# Local imports.
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
    #: toggle shows what was last asked for. (The fan toggle lives
    #: in the main status pane's mechanism quick controls.)
    buzzer_state = Bool(
        desc="power-system buzzer state as last requested, not read back"
    )

    # ---- Motor params ------------------------------------------------
    selected_motor = Enum(
        *MOTOR_IDS, desc="motor whose params are shown; switching re-reads them"
    )

    # ---- The param struct fields, named exactly as on the wire ------
    nl_pos = Float(desc="negative soft limit (µm)")
    pl_pos = Float(desc="positive soft limit (µm)")
    round_len = Float(desc="lead per motor revolution (µm)")
    origin_offset = Float(desc="home offset (µm)")
    origin_area = Float(desc="home flag length (µm)")
    step_len = Float(desc="distance per microstep (µm)")
    motor_polarity = Int(
        desc=(
            "direction polarity, 1 = as wired, 0 = mirrored; changing it "
            "alone can send homing away from the home flag"
        )
    )
    I_hold = Int(desc="hold current, 0–31")
    I_run = Int(desc="run current, 0–31")
    subdiv = Int(desc="microsteps per full step")
    run_sgt = Int(desc="StallGuard threshold while running")
    rst_sgt = Int(desc="StallGuard threshold while homing")
    bspd = Int(
        desc=(
            "homing speed as stored: µm/s on layout-2.0 motor firmware, "
            "1.398× the real µm/s on older"
        )
    )
    rspd = Int(
        desc=(
            "default run speed as stored: µm/s on layout-2.0 motor firmware, "
            "1.398× the real µm/s on older"
        )
    )
    acc_run = Int(desc="acceleration ramp factor while running (0 or less means 6)")
    acc_rst = Int(desc="acceleration ramp factor while homing (0 or less means 6)")

    #: The fields the last read actually returned (old firmware stops
    #: at rspd) — a write sends back exactly these, and Write stays
    #: disabled until a read has succeeded.
    loaded_fields = List(Str)
    params_loaded = Bool(False)

    read_button = Button("Read")
    write_button = Button("Write (RAM)")
    preset_button = Button("Preset to Flash")
    reboot_button = Button("Reboot Motor Board")
    params_status = Str("-", desc="Last read/write/preset/reboot outcome")
