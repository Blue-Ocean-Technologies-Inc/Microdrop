# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""MOVE_TRAY: the payload parse (validated model or legacy bare string) and
the two backend paths — the pogo pushpad macro through move_tray, and the
tray-only move through the motor proxy's chip_cabin_ctrl. Hardware-free, no
Redis."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    CHIP_CABIN_STATUS_ERROR,
    MoveTrayRequest,
)
from portable_dropbot_controller.services.portable_dropbot_motors_mixin_service import (
    PortableDropbotMotorsMixinService,
    parse_move_tray_request,
)


class _Reply:
    def __init__(self, status_byte):
        self.status_data = bytes(11) + bytes([status_byte])


class _Motor:
    def __init__(self, log, reply):
        self.log = log
        self.reply = reply

    def chip_cabin_ctrl(self, action, flags=0):
        self.log.append(("chip_cabin_ctrl", action, flags))
        return self.reply


class _Uart:
    def __init__(self, cabin_state):
        self.cabin_state = cabin_state

    def GetBoardStatus(self, board):
        return bytes([0, self.cabin_state])


class _Session:
    def __init__(self, log, reply=None, cabin_state=0):
        self.log = log
        self.motor = _Motor(log, reply)
        self.uart = _Uart(cabin_state)

    def move_tray(self, direction):
        self.log.append(("move_tray", direction))
        return False


class _Base(HasTraits):
    proxy = Any()
    log = List()
    snapshots = List()

    def _proxy_call(self, context, call):
        return True, call()

    def _publish_status_snapshot(self):
        self.snapshots.append(True)


class _Harness(PortableDropbotMotorsMixinService, _Base):
    pass


def _harness(**session_kwargs):
    harness = _Harness()
    harness.proxy = _Session(harness.log, **session_kwargs)

    return harness


@pytest.mark.parametrize("message", ["in", " OUT ", "toggle"])
def test_a_legacy_bare_direction_runs_the_pogo_macro(message):
    request = parse_move_tray_request(message)

    assert request.direction == message.strip().lower()
    assert request.actuate_pogos is True


def test_a_validated_payload_carries_the_pogo_flag():
    message = MoveTrayRequest(direction="out", actuate_pogos=False).model_dump_json()

    assert parse_move_tray_request(message) == MoveTrayRequest(
        direction="out", actuate_pogos=False
    )


@pytest.mark.parametrize("message", ["sideways", '{"direction": "up"}'])
def test_an_unknown_direction_is_rejected(message):
    with pytest.raises(ValidationError):
        parse_move_tray_request(message)


def test_an_unknown_direction_moves_nothing():
    harness = _harness()

    harness.on_move_tray_request("sideways")

    assert harness.log == []
    assert harness.snapshots == []


def test_the_pogo_macro_still_moves_through_move_tray():
    harness = _harness()

    harness.on_move_tray_request('{"direction": "out", "actuate_pogos": true}')

    assert harness.log == [("move_tray", "out")]
    assert harness.snapshots == [True]


def test_tray_only_moves_through_chip_cabin_ctrl_with_the_tray_only_flag():
    harness = _harness(reply=_Reply(0x00))

    harness.on_move_tray_request('{"direction": "out", "actuate_pogos": false}')

    assert harness.log == [("chip_cabin_ctrl", 1, 1)]
    assert harness.snapshots == [True]


def test_tray_only_toggle_moves_opposite_to_the_reported_cabin_state():
    harness = _harness(reply=_Reply(0x00), cabin_state=1)

    harness.on_move_tray_request('{"direction": "toggle", "actuate_pogos": false}')

    assert harness.log == [("chip_cabin_ctrl", 0, 1)]


@pytest.mark.parametrize(
    ("reply", "ok"),
    [(_Reply(0x00), True), (_Reply(CHIP_CABIN_STATUS_ERROR), False), (None, False)],
)
def test_tray_only_reads_success_from_the_status_byte(reply, ok):
    harness = _harness(reply=reply)

    assert harness._move_tray_only("out") is ok
