# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Chip-on-pad contact bits, chip-detect rules, chip engage modes,
PAD_ENGAGE, and the chip lock failure contract."""

# Standard library imports.
from typing import Literal

# Third-party imports.
from pydantic import BaseModel

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .topics import CHIP_LOCK_FAILED

#: chip_on_pad status bits: bit0 debounced presence, bit1/bit2 raw left/right
#: pogo contact. The vendor documents bits 1-2 as diagnostic only (sampled
#: undebounced, never to be gated on; only bit0 drives the HV interlock).
#: Under the both-pogos rule a chip counts as on the pad only with all three
#: set.
CHIP_ON_PAD_SEATED_MASK = 0b111
#: The debounced presence bit every chip-detect rule requires — the vendor's
#: whole rule.
CHIP_ON_PAD_PRESENCE_BIT = 0b001
#: The left/right pogo contact bits; the any-pogo rule needs one of them.
CHIP_ON_PAD_POGO_BITS = 0b110

#: Chip-detect rules (Portable DropBot Settings preference): which contact
#: masks the backend reports as a chip on the pad. Presence (the default)
#: follows the vendor and the HV interlock; the pogo rules are stricter
#: opt-ins that also require the raw pad contacts.
CHIP_DETECT_RULE_PRESENCE = "presence"
CHIP_DETECT_RULE_BOTH_POGOS = "both_pogos"
CHIP_DETECT_RULE_ANY_POGO = "any_pogo"
CHIP_DETECT_RULES = (
    CHIP_DETECT_RULE_PRESENCE,
    CHIP_DETECT_RULE_BOTH_POGOS,
    CHIP_DETECT_RULE_ANY_POGO,
)
DEFAULT_CHIP_DETECT_RULE = CHIP_DETECT_RULE_PRESENCE

#: Chip engage modes (Portable DropBot Settings preference): how a chip lock
#: presses the pogo pads. Classic is the motor board's fixed-position press;
#: smart is the signal board's PAD_ENGAGE, where each pad descends until its
#: own contact sensor trips, then overdrives (both pads must be homed).
CHIP_ENGAGE_MODE_CLASSIC = "classic"
CHIP_ENGAGE_MODE_SMART = "smart"
CHIP_ENGAGE_MODES = (CHIP_ENGAGE_MODE_CLASSIC, CHIP_ENGAGE_MODE_SMART)
DEFAULT_CHIP_ENGAGE_MODE = CHIP_ENGAGE_MODE_CLASSIC

#: PAD_ENGAGE (signal board, 0x1250) arguments. Retract is the vendor UI's
#: way out of any engage: action 0 with mode 0.
PAD_ENGAGE_CMD = 0x1250
PAD_ENGAGE_ACTION_ENGAGE = 1
PAD_ENGAGE_ACTION_RETRACT = 0
PAD_ENGAGE_MODE_SMART = 1
PAD_ENGAGE_MODE_CLASSIC = 0
#: Smart descent at the vendor UI's defaults: step (µm, signed, the sign is
#: the descent direction), the most steps before giving up, and the press
#: past contact (µm).
PAD_ENGAGE_STEP_UM = 200
PAD_ENGAGE_MAX_STEPS = 18
PAD_ENGAGE_OVERDRIVE_UM = 300
#: PAD_ENGAGE reply status: 0 is done; every other status is a failure.
#: A motor error is also how an engage with unhomed pads can end. Statuses
#: 4 and 5 may leave the pads pressing the chip.
PAD_ENGAGE_STATUS_OK = 0
PAD_ENGAGE_STATUS_MOTOR_ERROR = 2
PAD_ENGAGE_FAILURES = {
    1: "no contact: the pads found no chip and retracted",
    PAD_ENGAGE_STATUS_MOTOR_ERROR: "motor error: the pads retracted",
    3: "busy: a pad engage is already running",
    4: "the retract after a failed engage also failed",
    5: "a motor E-STOP stopped it and nothing was retracted",
}
PAD_ENGAGE_PADS_MAY_BE_PRESSED = (4, 5)
#: Smart engage's prerequisite (vendor UI), added to its refusals.
SMART_ENGAGE_NEEDS = "smart engage needs both pads homed (Home All)"


class ChipLockFailed(BaseModel):
    """A chip lock or unlock through PAD_ENGAGE that did not finish, and why.
    `pads_may_be_pressed` is set when the pads may still press the chip."""

    action: Literal["lock", "unlock"]
    error: str
    pads_may_be_pressed: bool = False


chip_lock_failed_publisher = ValidatedTopicPublisher(
    topic=CHIP_LOCK_FAILED, validator_class=ChipLockFailed
)
