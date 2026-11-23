# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""MOVE_TRAY: the payload parse (validated model or legacy bare string), the
one CHIP_CABIN_CTRL both paths send (the pogo pushpad macro, or tray-only),
the toggle's cabin-state decode, and the reply judged like the driver's
setTray — the 1-byte state of current firmware and the legacy 12-byte
shape; FAULT, a refusal and a timeout all fail and are published.
Hardware-free, no Redis."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Enthought library imports.
from traits.api import Any, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    CHIP_CABIN_TRAY_ONLY_FLAG,
    CHIP_CABIN_WITH_POGOS_FLAG,
    MECHANISM_STATE_FAULT,
    MoveTrayRequest,
)
from portable_dropbot_controller.services.portable_dropbot_motors_mixin_service import (
    PortableDropbotMotorsMixinService,
    parse_move_tray_request,
)

#: What the driver's last_result says about a refused or unanswered request.
REFUSAL = "cmd 0x1120: FAIL RESP_FAIL (0.05 s)"
FAULT = "the mechanism reports FAULT (not homed, or the move failed)"


class _Reply:
    """The generated proxy's MotorBoardCHIP_CABIN_CTRLResponse."""

    def __init__(self, status_data):
        self.status_data = status_data


class _Result:
    def describe(self):
        return REFUSAL


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

    def last_result(self, cmd):
        return _Result()


class _Session:
    def __init__(self, log, reply=None, cabin_state=0):
        self.motor = _Motor(log, reply)
        self.uart = _Uart(cabin_state)


class _Base(HasTraits):
    proxy = Any()
    log = List()
    snapshots = List()
    errors = List()

    def _proxy_call(self, context, call, serialize=True):
        return True, call()

    def _publish_error(self, context, error):
        self.errors.append((context, error))

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


@pytest.mark.parametrize(
    ("actuate_pogos", "flags"),
    [(True, CHIP_CABIN_WITH_POGOS_FLAG), (False, CHIP_CABIN_TRAY_ONLY_FLAG)],
)
def test_both_paths_send_one_chip_cabin_ctrl(actuate_pogos, flags):
    harness = _harness(reply=_Reply(b"\x01"))
    request = MoveTrayRequest(direction="out", actuate_pogos=actuate_pogos)

    harness.on_move_tray_request(request.model_dump_json())

    assert harness.log == [("chip_cabin_ctrl", 1, flags)]
    assert harness.errors == []
    assert harness.snapshots == [True]


@pytest.mark.parametrize(("cabin_state", "action"), [(0, 1), (1, 0)])
def test_toggle_moves_opposite_to_the_reported_cabin_state(cabin_state, action):
    harness = _harness(reply=_Reply(bytes([action])), cabin_state=cabin_state)

    harness.on_move_tray_request('{"direction": "toggle", "actuate_pogos": false}')

    assert harness.log == [("chip_cabin_ctrl", action, CHIP_CABIN_TRAY_ONLY_FLAG)]


@pytest.mark.parametrize("cabin_state", [2, 0xF2, MECHANISM_STATE_FAULT])
def test_toggle_ignores_a_state_without_a_single_opposite(cabin_state):
    harness = _harness(reply=_Reply(b"\x00"), cabin_state=cabin_state)

    harness.on_move_tray_request("toggle")

    assert harness.log == []
    assert harness.snapshots == []


@pytest.mark.parametrize(
    "status_data",
    [b"\x00", b"\x01", bytes(11) + b"\x01"],
    ids=["in", "out", "legacy-12-byte"],
)
def test_a_reported_position_is_success(status_data):
    harness = _harness(reply=_Reply(status_data))

    harness.on_move_tray_request("in")

    assert harness.errors == []


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        (_Reply(bytes([MECHANISM_STATE_FAULT])), FAULT),
        (_Reply(bytes(11) + bytes([MECHANISM_STATE_FAULT])), FAULT),
        (_Reply(b""), REFUSAL),
        (None, REFUSAL),
    ],
    ids=["fault", "legacy-fault", "refused", "timeout"],
)
def test_a_fault_a_refusal_or_a_timeout_fails_and_is_published(reply, error):
    harness = _harness(reply=reply)

    harness.on_move_tray_request('{"direction": "in", "actuate_pogos": false}')

    assert harness.errors == [("tray in (tray only)", error)]
    assert harness.snapshots == [True]
