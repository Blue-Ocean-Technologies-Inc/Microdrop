# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Motor roster, tray, magnet and motor-param constants, and their
message contracts."""

# Standard library imports.
from typing import Literal

# Third-party imports.
from pydantic import BaseModel, Field, field_validator

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# Local imports.
from .topics import (
    MAGNET_ENGAGE_UPDATED,
    MAGNET_ENGAGE_WRITE,
    MOTOR_PARAMS_WRITE,
    MOVE_TRAY,
)

#: Custom magnet height a protocol step may ask for: an absolute
#: position on the magnet Z motor (mm). The firmware's own motor
#: params (nl_pos/pl_pos) are the real travel limits; anything below
#: MIN is the column's "Default" sentinel = the firmware engage macro.
MAGNET_HEIGHT_MM_BOUNDS = (0.5, 1000.0)

#: The driver's fixed motor roster: name -> motor id.
MOTOR_IDS = {
    "tray": 0,
    "pmt": 1,
    "magnet": 2,
    "filter": 3,
    "pogo_left": 4,
    "pogo_right": 5,
}

#: CHIP_CABIN_CTRL action code the motor board takes per tray direction.
TRAY_ACTION_CODES = {"in": 0, "out": 1}
#: CHIP_CABIN_CTRL flags: the pogo pushpad macro, or tray-only. Either way
#: the firmware parks the PMT and makes the magnet tray-safe, or refuses.
CHIP_CABIN_WITH_POGOS_FLAG = 0
CHIP_CABIN_TRAY_ONLY_FLAG = 1
#: Tray / magnet / pogo / filter state byte of a mechanism in FAULT.
MECHANISM_STATE_FAULT = 0xFF
#: Motor firmware (DroDri) that answers MOTOR_SNAPSHOT.
MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE = (1, 0, 0, 25)
#: Motor-board command ids the driver's MotorBoard class does not name (its
#: generated proxy sends them): the coordinated magnet and tray resets and
#: the emergency stop.
MAG_RESET_CMD = 0x1134
TRAY_RESET_CMD = 0x1135
MOTOR_ESTOP_CMD = 0x11B6

#: Motor name -> the driver PARAMS friendly name whose EasyFlash blob
#: holds that motor's mechanical tuning struct.
MOTOR_PARAM_NAMES = {
    "tray": "tray_motor",
    "pmt": "pmt_motor",
    "magnet": "magnet_motor",
    "filter": "filter_motor",
    "pogo_left": "pogo_motor_left",
    "pogo_right": "pogo_motor_right",
}

#: The per-motor mechanical param struct's field names in WIRE ORDER, as
#: the driver's dropbot_portable.param_layout.MOTOR_FIELDS (which owns the
#: formats and the codec). Firmware generations serve a prefix of it: 14
#: fields (56 B), + acc_run/acc_rst (64 B), + stealthchop (68 B),
#: + home_dir (72 B, current). bspd/rspd travel in real µm/s.
MOTOR_PARAM_FIELDS = (
    "nl_pos",
    "pl_pos",
    "round_len",
    "origin_offset",
    "origin_area",
    "step_len",
    "motor_polarity",
    "I_hold",
    "I_run",
    "subdiv",
    "run_sgt",
    "rst_sgt",
    "bspd",
    "rspd",
    "acc_run",
    "acc_rst",
    "stealthchop",
    "home_dir",
)

#: The driver PARAMS friendly name of the magnet's device-defaults struct
#: (flash key _dp_magnet), and that struct's fields in WIRE ORDER: four
#: big-endian int32, all µm. z_up is the engage height; it must stay at or
#: below the magnet-Z motor's positive soft limit (its pl_pos), or the
#: firmware rejects every engage.
MAGNET_DEFAULTS_PARAM = "magnet_defaults"
MAGNET_DEFAULTS_FIELDS = ("z_up", "z_down", "y_0", "y_space")
MAGNET_DEFAULTS_FORMAT = ">4i"

# --------------------------------------------------------------------- #
# Mechanism message contracts (topic + schema, one importable unit)      #
# --------------------------------------------------------------------- #


class MoveTrayRequest(BaseModel):
    """A chip tray move; "toggle" moves it opposite to where the motor
    STATUS reports it."""

    direction: Literal["in", "out", "toggle"]
    #: True runs the firmware macro that releases the pogo pushpads before
    #: the move and presses them after; False moves the tray only.
    actuate_pogos: bool = True


move_tray_publisher = ValidatedTopicPublisher(
    topic=MOVE_TRAY, validator_class=MoveTrayRequest
)


# --------------------------------------------------------------------- #
# Magnet engage height message contracts (topic + schema, one unit)      #
# --------------------------------------------------------------------- #


class MagnetEngageWriteRequest(BaseModel):
    """The magnet engage height to write to the board's RAM device defaults."""

    engage_mm: float = Field(ge=0)


class MagnetEngageUpdated(BaseModel):
    """Outcome of a magnet engage request. `engage_mm` is the height a read
    returned or a write sent; `error` is set when the request failed."""

    action: Literal["read", "write", "preset"]
    engage_mm: float | None = None
    error: str = ""


magnet_engage_write_publisher = ValidatedTopicPublisher(
    topic=MAGNET_ENGAGE_WRITE, validator_class=MagnetEngageWriteRequest
)
magnet_engage_updated_publisher = ValidatedTopicPublisher(
    topic=MAGNET_ENGAGE_UPDATED, validator_class=MagnetEngageUpdated
)

# --------------------------------------------------------------------- #
# Motor mechanical params message contracts (topic + schema, one unit)   #
# --------------------------------------------------------------------- #


class MotorParamsWriteRequest(BaseModel):
    """Edited mechanical params for one motor's RAM write. `fields` names a
    subset of MOTOR_PARAM_FIELDS, speeds in real µm/s; the backend reads the
    board's blob and writes it back whole with these values in place."""

    motor: str
    fields: dict[str, float | int]

    @field_validator("motor")
    @classmethod
    def _motor_known(cls, value):
        if value not in MOTOR_PARAM_NAMES:
            raise ValueError(f"unknown motor {value!r}")

        return value

    @field_validator("fields")
    @classmethod
    def _fields_known(cls, value):
        unknown = sorted(set(value) - set(MOTOR_PARAM_FIELDS))

        if unknown:
            raise ValueError(f"unknown motor params: {', '.join(unknown)}")

        return value


motor_params_write_publisher = ValidatedTopicPublisher(
    topic=MOTOR_PARAMS_WRITE, validator_class=MotorParamsWriteRequest
)
