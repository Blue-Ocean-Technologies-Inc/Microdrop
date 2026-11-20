# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT motion for the portable PMT mixin: the spot -> motor location
mapping, the position-table decode, and the moves themselves (spot presets
and park), on both motor firmware generations.

From motor firmware PMT_PRESET_PARK_MOTOR_FIRMWARE (DroDri_1.0.0.25) all
six PMT locations are measurement presets and spot n is location n; park is
the axis's `_dp_park` position, reached with MOTOR_CONTROL action
MOTOR_ACTION_PARK (the driver bench UI's Park button). Older firmware
treats location 1 as park, so spot n is location n + 1 and park is
``pmt_ctrl(1)``. While the motor firmware version is unknown (re-read
once first) every PMT move and spot read is refused rather than guessed: the
two mappings put the PMT on different spots.

A board upgraded to .25 keeps its taught table, whose location 1 was park:
location 1 reading 0 or the park position is reported once per connection
so the table and saved PMT protocol steps get re-checked.

The firmware refuses a PMT move with BUSY while the tray is moving or a
home is running. The driver returns None for that, exactly as for a
timeout or a FAIL; its per-thread ``last_result`` record says which, and
that account is the failure reason reported.
"""

# Standard library imports.
import struct

# Third-party imports.
from dropbot_portable import MotorBoard
from dropbot_portable.param_layout import unpack_park

# Enthought library imports.
from traits.api import Any, HasTraits

# Local imports.
from .consts import (
    MECHANISM_STATE_FAULT,
    MOTOR_ACTION_PARK,
    MOTOR_IDS,
    PMT_LEGACY_PARK_LOCATION,
    PMT_LOCATION_MOVING,
    PMT_PRESET_PARK_MOTOR_FIRMWARE,
    PMT_SPOT_SLOTS,
)
from .motion_replies import describe_last_result

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: One big-endian int32 Y-axis position per motor location
#: (PMTPositionParams.pos).
_POSITIONS = struct.Struct(f">{PMT_SPOT_SLOTS}i")
#: Firmware from before the park extension serves five locations.
_LEGACY_POSITIONS_BYTES = 5 * 4

#: Why a PMT move or spot read is refused while the motor firmware is unknown.
PMT_FIRMWARE_UNKNOWN = (
    "the motor firmware version is unknown, so the PMT spot numbering "
    "cannot be told (it changed in DroDri_1.0.0.25); reconnect, or check "
    "that the motor board answers"
)


def pmt_spot_count(presets):
    """How many spots the motor firmware offers; ``presets`` is whether
    every location is a measurement preset."""

    if presets:
        return PMT_SPOT_SLOTS

    return PMT_SPOT_SLOTS - PMT_LEGACY_PARK_LOCATION


def pmt_spot_location(spot, presets):
    """Return the motor location of spot 1..``pmt_spot_count(presets)``.

    Raises
    ------
    ValueError
        When the spot does not exist on this firmware generation.
    """
    count = pmt_spot_count(presets)

    if not 1 <= spot <= count:
        raise ValueError(f"PMT spot {spot} is not one of 1..{count} on this firmware")

    return spot if presets else spot + PMT_LEGACY_PARK_LOCATION


def decode_pmt_positions(reply):
    """Decode a ``GET_PARAMS`` reply for ``pmt_defaults`` into one position
    per motor location; index 0 is location 1.

    The reply echoes the flash key, a NUL, then the raw struct: big-endian
    int32 Y-axis positions in µm (the driver's ``PMTPositionParams``). A
    five-location table from older firmware is zero-padded, as the driver
    itself does, so its missing last location reads as unused.
    """
    raw = bytes(reply)
    blob = raw.split(b"\x00", 1)[1] if b"\x00" in raw else raw

    if len(blob) < _LEGACY_POSITIONS_BYTES:
        raise ValueError(
            f"PMT position table is {len(blob)} bytes, "
            f"expected at least {_LEGACY_POSITIONS_BYTES}"
        )

    return list(_POSITIONS.unpack_from(blob.ljust(_POSITIONS.size, b"\x00")))


def pmt_spot_positions(location_positions, presets):
    """Map per-location positions onto spots; index 0 is spot 1. Older
    firmware's park location is not a spot and is dropped."""

    if presets:
        return list(location_positions)

    return list(location_positions[PMT_LEGACY_PARK_LOCATION:])


def pmt_park_position(park_reply, location_positions):
    """The PMT park position in µm from a ``GET_PARAMS`` reply for
    ``_dp_park``: its PMT entry's absolute value (source 0), or the
    location it follows (source n). None when it cannot be told."""
    raw = bytes(park_reply)
    blob = raw.split(b"\x00", 1)[1] if b"\x00" in raw else raw
    source, value_um = unpack_park(blob)[MOTOR_IDS["pmt"]]

    if source == 0:
        return value_um

    if 1 <= source <= len(location_positions):
        return location_positions[source - 1]

    return None


def pmt_location_one_left_over(location_positions, park_um):
    """Why location 1 looks like the park slot of the firmware before
    PMT_PRESET_PARK_MOTOR_FIRMWARE, never re-taught as a spot: it reads 0
    (home) or the park position. Empty when it does not."""
    first = location_positions[0]

    if first == 0:
        return "PMT location 1 is 0 µm (home)"

    if park_um is not None and first == park_um:
        return f"PMT location 1 is the park position ({park_um} µm)"

    return ""


def pmt_move_failure(reply):
    """Why a PMT_CTRL reply is not a landed move; empty when it is. A
    missing reply is the caller's to explain (see ``_move_pmt``)."""

    if reply.location == PMT_LOCATION_MOVING:
        return "still moving"

    if reply.location == MECHANISM_STATE_FAULT:
        return "FAULT: the PMT axis is not homed, home it first"

    return ""


def pmt_park_failure(reply):
    """Why a MOTOR_CONTROL park reply is not a landed park; empty when it
    is. A non-zero status is the firmware's MTE_* code."""

    if reply.status != 0:
        return f"motor status {reply.status}"

    return ""


class PmtMotionMixin(HasTraits):
    """PMT moves for the PMT mixin service. Composes into the controller,
    which provides ``proxy``, ``_proxy_call``, ``_publish_error`` and the
    board firmware mixin's ``_motor_firmware_known`` /
    ``_motor_firmware_at_least``."""

    #: The session the location-1 warning was given for: once per connection.
    _pmt_location_one_warned_for = Any()

    def _pmt_presets_supported(self):
        """True when every PMT location is a preset and park is
        `_dp_park`, False on older motor firmware, None while the version
        stays unknown after a re-read."""

        if not self._motor_firmware_known():
            return None

        return self._motor_firmware_at_least(PMT_PRESET_PARK_MOTOR_FIRMWARE)

    def _pmt_spot_location(self, spot):
        return pmt_spot_location(spot, self._pmt_presets_supported())

    def _pmt_spot_table(self, reply):
        """Decode a ``pmt_defaults`` reply into one position per spot;
        index 0 is spot 1.

        Raises
        ------
        ValueError
            When the table is malformed or the motor firmware is unknown.
        """
        presets = self._pmt_presets_supported()

        if presets is None:
            raise ValueError(PMT_FIRMWARE_UNKNOWN)

        locations = decode_pmt_positions(reply)

        if presets:
            self._warn_pmt_location_one_left_over(locations)

        return pmt_spot_positions(locations, presets)

    def _warn_pmt_location_one_left_over(self, locations):
        """Report, once per connection, a location 1 still holding the old
        park slot (see pmt_location_one_left_over)."""

        if self._pmt_location_one_warned_for is self.proxy:
            return

        ok, park_reply = self._proxy_call(
            "PMT park read",
            lambda: self.proxy.uart.getBoardParameter("motor", "park"),
        )

        try:
            park_um = pmt_park_position(park_reply, locations) if ok else None
        except (TypeError, ValueError) as error:
            logger.warning(f"Portable Dropbot PMT park position unreadable: {error}")
            park_um = None

        why = pmt_location_one_left_over(locations, park_um)

        if not why:
            return

        self._pmt_location_one_warned_for = self.proxy
        self._publish_error(
            "PMT spot table check",
            f"{why}. From motor firmware DroDri_1.0.0.25 location 1 is spot 1, "
            f"a measurement spot, and park is separate; a board upgraded from "
            f"older firmware keeps its old table. Re-teach the PMT positions "
            f"and re-check saved PMT protocol steps (spot n was location n + 1).",
        )

    def _move_pmt(self, context, spot):
        """Move the PMT to a spot (0 = park); return why it failed, or an
        empty string when it landed. Never raises.

        A missing reply (BUSY while the tray moves, FAIL, or a timeout) is
        explained by the driver's record of this thread's request, read
        right after the call on the same thread.
        """
        presets = self._pmt_presets_supported()

        if presets is None:
            return PMT_FIRMWARE_UNKNOWN

        if spot == 0 and presets:
            cmd, judge = MotorBoard.MOTOR_CONTROL, pmt_park_failure

            def command():
                return self.proxy.motor.motor_control(
                    MOTOR_IDS["pmt"], MOTOR_ACTION_PARK, 0
                )

        else:
            try:
                location = (
                    PMT_LEGACY_PARK_LOCATION
                    if spot == 0
                    else pmt_spot_location(spot, presets)
                )
            except ValueError as error:
                return str(error)

            cmd, judge = MotorBoard.PMT_CTRL, pmt_move_failure

            def command():
                return self.proxy.motor.pmt_ctrl(location)

        # Unserialized like every motion (see the base's _proxy_lock): the
        # firmware answers a conflicting move BUSY, and a long PMT travel
        # must not park the status poll or other workers on the lock.
        ok, reply = self._proxy_call(context, command, serialize=False)

        if not ok:
            return str(reply) if reply is not None else "not connected"

        if reply is None:
            return describe_last_result(getattr(self.proxy, "uart", None), cmd)

        return judge(reply)
