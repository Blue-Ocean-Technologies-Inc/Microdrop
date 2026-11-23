# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the PMT spot -> motor location mapping on both motor firmware
generations, the position-table decode, and the move/park reply judges.
Pure functions, no driver session, no hardware."""

# Standard library imports.
import struct
from collections import namedtuple

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    MECHANISM_STATE_FAULT,
    PMT_LOCATION_MOVING,
    PMT_SPOT_SLOTS,
)
from portable_dropbot_controller.pmt_motion import (
    decode_pmt_positions,
    pmt_move_failure,
    pmt_park_failure,
    pmt_spot_count,
    pmt_spot_location,
    pmt_spot_positions,
)

_PmtCtrlReply = namedtuple("_PmtCtrlReply", "location")
_MotorControlReply = namedtuple("_MotorControlReply", "motor_id status position")


def test_preset_firmware_offers_every_location_as_a_spot():
    assert pmt_spot_count(True) == PMT_SPOT_SLOTS
    assert [pmt_spot_location(spot, True) for spot in range(1, 7)] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]


def test_older_firmware_skips_its_park_location():
    assert pmt_spot_count(False) == PMT_SPOT_SLOTS - 1
    assert [pmt_spot_location(spot, False) for spot in range(1, 6)] == [
        2,
        3,
        4,
        5,
        6,
    ]


@pytest.mark.parametrize(
    "spot, presets", [(0, True), (7, True), (0, False), (6, False), (-1, False)]
)
def test_spot_location_rejects_a_spot_the_firmware_lacks(spot, presets):
    with pytest.raises(ValueError):
        pmt_spot_location(spot, presets)


def test_decode_pmt_positions_keeps_every_location():
    blob = struct.pack(">6i", 0, 1000, 24500, 0, 61000, -5)

    assert decode_pmt_positions(b"_dp_pmt\x00" + blob + b"trailing") == [
        0,
        1000,
        24500,
        0,
        61000,
        -5,
    ]


def test_decode_pmt_positions_pads_a_legacy_five_location_table():
    blob = struct.pack(">5i", 0, 1000, 24500, 0, 61000)

    assert decode_pmt_positions(b"_dp_pmt\x00" + blob) == [0, 1000, 24500, 0, 61000, 0]

    with pytest.raises(ValueError):
        decode_pmt_positions(b"_dp_pmt\x00" + blob[:8])


def test_spot_positions_drop_the_park_location_on_older_firmware_only():
    locations = [7000, 1000, 24500, 0, 61000, -5]

    assert pmt_spot_positions(locations, True) == locations
    assert pmt_spot_positions(locations, False) == [1000, 24500, 0, 61000, -5]


def test_move_failure_judges_the_reply_location():
    assert pmt_move_failure(_PmtCtrlReply(3)) == ""
    assert "moving" in pmt_move_failure(_PmtCtrlReply(PMT_LOCATION_MOVING))
    assert "FAULT" in pmt_move_failure(_PmtCtrlReply(MECHANISM_STATE_FAULT))


def test_park_failure_judges_the_motor_status():
    assert pmt_park_failure(_MotorControlReply(1, 0, 0)) == ""
    assert "-1" in pmt_park_failure(_MotorControlReply(1, -1, 0))
