# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Decoders for the motor board's motion replies, judged the way the
dropbot-portable driver judges them: the coordinated tray / magnet / pogo
(and filter) state byte, a raw per-motor command's result, and the
one-frame MOTOR_SNAPSHOT. The byte-level decoding is the driver's own
(``param_layout.unpack_motor_snapshot``, and a copy of its private
``_motor_status_byte``); this module only turns it into the success /
reason pairs the motors mixin reports. No Qt, no proxy state:
unit-testable without hardware."""

# Third-party imports.
from dropbot_portable import param_layout

# Local imports.
from .consts import MECHANISM_STATE_FAULT, MOTOR_IDS

#: Motor id -> the driver's motor name, the keys of every motor picture.
_MOTOR_NAMES = {motor_id: name for name, motor_id in MOTOR_IDS.items()}
#: State byte of a mechanism still moving when it answered (the driver
#: UI's MECH_STATE_MOVING, shared by every mechanism's state byte).
_MECHANISM_STATE_MOVING = 0xF2
#: Offset of a motor reply's status byte inside a whole frame
#: (the driver's MOTOR_STATUS_INDEX).
_MOTOR_STATUS_INDEX = 11
#: Per-axis fault bits of a MOTOR_SNAPSHOT / MOTOR_HOMED_QUERY fault byte,
#: named as the driver UI's MOTOR_FAULT_BITS (``ui/common.py``, a Qt module).
_MOTOR_FAULT_BITS = (
    (0x01, "drv-err"),
    (0x02, "chip-bad"),
    (0x04, "last-err"),
    (0x08, "busy"),
    (0x10, "estopped"),
    (0x20, "drv-off"),
)


def _motor_status_byte(response):
    """Status byte of a motor *_READ / coordinated-CTRL reply, or None.

    A copy of the driver's private
    ``portable_dropbot_service._motor_status_byte``, so a driver bump cannot
    break this import: the reply is the payload (one byte on current
    firmware) or, from older firmware, a whole frame.
    """

    if not response:
        return None

    if len(response) > _MOTOR_STATUS_INDEX:
        return response[_MOTOR_STATUS_INDEX]

    return response[0]


def mechanism_state(reply):
    """The state byte of a coordinated mechanism reply, or None.

    Takes the generated proxy's response (``status_data``) or the uart
    facade's raw payload (False on no reply). Current firmware answers one
    byte, older firmware twelve; the driver's decoder reads both. None is
    no state at all: a timeout, a BUSY, or a refusal's empty reply.
    """
    return _motor_status_byte(getattr(reply, "status_data", reply))


def describe_last_result(uart, cmd):
    """The driver's account of this thread's last ``cmd`` request (FAIL,
    BUSY or TIMEOUT, with timing), or "no reply" when it kept none."""
    result = uart.last_result(cmd) if uart is not None else None

    return result.describe() if result is not None else "no reply"


def mechanism_failure(reply, uart, cmd):
    """Why a coordinated mechanism command failed, or None when it moved.

    Judged like the driver's ``setTray``: no state byte fails (a timeout
    or a refusal — interlocks, un-homed axes and a busy board all refuse),
    0xFF is a FAULT, and any other state is where the command left the
    mechanism.
    """
    state = mechanism_state(reply)

    if state == MECHANISM_STATE_FAULT:
        return "the mechanism reports FAULT (not homed, or the move failed)"

    if state is not None:
        return None

    return describe_last_result(uart, cmd)


def filter_move_failure(reply, uart, cmd):
    """Why a FLUORESCENCE_CTRL filter move failed, or None when it landed.

    ``mechanism_failure`` plus a wheel that answered while still turning:
    the driver's UI reads 0xF2 as moving, not as a landed position.
    """

    if mechanism_state(reply) == _MECHANISM_STATE_MOVING:
        return "the filter wheel is still moving"

    return mechanism_failure(reply, uart, cmd)


def acknowledged_failure(acknowledged, uart, cmd):
    """Why a driver call that answers only True / False failed, or None.

    The generated proxy's bool commands (PMT_RESET, the signal board's
    FLUORESCENCE_CTRL) answer False on a FAIL, a BUSY or a timeout alike;
    the driver's ``last_result`` record says which.
    """

    if acknowledged:
        return None

    return describe_last_result(uart, cmd)


def proxy_call_failure(ok, reply, uart, cmd, failure):
    """Why a ``_proxy_call`` (ok, reply) pair failed, or None.

    A raised call's reason is its exception (already published by
    ``_proxy_call``); an answered one is judged by ``failure``, one of
    this module's judges.
    """

    if not ok:
        return str(reply) if reply is not None else "not connected"

    return failure(reply, uart, cmd)


def motor_command_failure(result, uart, cmd):
    """Why a raw per-motor command failed, or None when it succeeded.

    The uart facade answers an int on success (``motorAction``'s final
    position for a move / home / stop, ``setMotorSpeed``'s accepted
    speed), the motor's status or error text on a failed motion, None on
    no reply and False when the motor board is not logged in.
    """

    if isinstance(result, int) and not isinstance(result, bool):
        return None

    if result is False:
        return "motor board not connected"

    if result is None:
        return describe_last_result(uart, cmd)

    return str(result)


def motor_snapshot_picture(reply):
    """The motor picture of a MOTOR_SNAPSHOT reply, or None.

    A dict keyed by motor name: ``positions`` in µm (10 µm resolution),
    ``homed`` and ``moving`` flags, and ``faults``, the names of each
    axis's set fault bits. The generated proxy splits the 21-byte frame
    into fields; they are reassembled for the driver's one decoder, as its
    UI's motor poll does.
    """

    if reply is None:
        return None

    raw = (
        bytes(reply.positions)
        + bytes(
            [
                reply.homed_state_lo & 0xFF,
                reply.sensors_state_hi & 0xFF,
                reply.moving & 0xFF,
            ]
        )
        + bytes(reply.faults)
    )

    try:
        snapshot = param_layout.unpack_motor_snapshot(raw)
    except ValueError:
        return None

    def by_motor(values):
        return {_MOTOR_NAMES[axis]: value for axis, value in enumerate(values)}

    faults = [
        [name for bit, name in _MOTOR_FAULT_BITS if fault & bit]
        for fault in snapshot.faults
    ]

    return {
        "positions": by_motor(snapshot.positions_um),
        "homed": by_motor(snapshot.homed),
        "moving": by_motor(snapshot.moving),
        "faults": by_motor(faults),
    }
