# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The magnet, pogo, home-all and per-motor handlers judge every reply the
driver's way: MAGNET_APPLIED only on a confirmed move, a FAULT / refusal /
timeout published as an error, every motion and Motor Stop outside the proxy
lock. Also the MOTOR_SNAPSHOT decode and its firmware gate (Home All and the
E-STOP: test_motion_safety). Hardware-free, no Redis."""

# Standard library imports.
import json
import struct
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, Dict, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller import portable_dropbot_controller_base
from portable_dropbot_controller.consts import (
    MAGNET_APPLIED,
    MECHANISM_STATE_FAULT,
    MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE,
    PMT_PRESET_PARK_MOTOR_FIRMWARE,
)
from portable_dropbot_controller.motion_replies import motor_snapshot_picture
from portable_dropbot_controller.portable_dropbot_controller_base import (
    PortableDropbotControllerBase,
)
from portable_dropbot_controller.services import (
    portable_dropbot_motors_mixin_service as motors_service,
)

#: What the driver's last_result says about a refused or unanswered request.
REFUSAL = "cmd 0x1122: FAIL RESP_FAIL (0.05 s)"


class _Result:
    """The driver's CommandResult: truthy only on OK."""

    def __init__(self, ok=False):
        self.ok = ok

    def __bool__(self):
        return self.ok

    def describe(self):
        return REFUSAL


class _Uart:
    def __init__(self, log, reply):
        self.log = log
        self.reply = reply

    def last_result(self, cmd):
        return _Result()

    def setPogo(self, state):
        self.log.append(("setPogo", state))
        return self.reply

    def motorAbsoluteMove(self, motor_id, value):
        self.log.append(("motorAbsoluteMove", motor_id, value))
        return self.reply

    def motorAction(self, motor_id, mode, value):
        self.log.append(("motorAction", motor_id, mode, value))
        return self.reply

    def motorStop(self, motor_id):
        self.log.append(("motorStop", motor_id))
        return self.reply

    def setMotorSpeed(self, motor_id, speed):
        self.log.append(("setMotorSpeed", motor_id, speed))
        return self.reply

    def motorHome(self, motor_id):
        self.log.append(("motorHome", motor_id))
        return self.reply


class _Motor:
    """The generated motor-board proxy's bool PMT_RESET."""

    def __init__(self, log, reply):
        self.log = log
        self.reply = reply

    def pmt_reset(self):
        self.log.append(("pmt_reset",))
        return self.reply


class _Session:
    def __init__(self, log, reply):
        self.log = log
        self.reply = reply
        self.uart = _Uart(log, reply)
        self.motor = _Motor(log, reply)

    def move_magnet(self, action):
        self.log.append(("move_magnet", action))
        return self.reply


class _Base(HasTraits):
    proxy = Any()
    log = List()
    errors = List()
    serialized = List()
    snapshots = List()
    #: Whether the fake motor firmware parks the PMT at `_dp_park`.
    pmt_presets = Bool(True)

    def _motor_firmware_at_least(self, version):
        assert version == PMT_PRESET_PARK_MOTOR_FIRMWARE
        return self.pmt_presets

    def _proxy_call(self, context, call, serialize=True):
        self.serialized.append(serialize)
        return True, call()

    def _publish_error(self, context, error):
        self.errors.append((context, error))

    def _publish_status_snapshot(self):
        self.snapshots.append(True)

    def _publish_motors(self, mechanisms=None, poll=True):
        self.snapshots.append(True)


class _Harness(motors_service.PortableDropbotMotorsMixinService, _Base):
    pass


@pytest.fixture
def acks(monkeypatch):
    """The topics the mixin publishes, in order."""
    published = []

    monkeypatch.setattr(
        motors_service,
        "publish_message",
        lambda topic, message: published.append((topic, message)),
    )

    return published


def _harness(reply):
    harness = _Harness()
    harness.proxy = _Session(harness.log, reply)

    return harness


def _protocol_magnet(on, height_mm=0.0):
    return json.dumps({"on": on, "height_mm": height_mm})


@pytest.mark.parametrize(("on", "reply"), [(True, b"\x01"), (False, b"\x00")])
def test_a_confirmed_magnet_move_is_acked(acks, on, reply):
    harness = _harness(reply)

    harness.on_protocol_set_magnet_request(_protocol_magnet(on))

    assert acks == [(MAGNET_APPLIED, str(int(on)))]
    assert harness.errors == []


@pytest.mark.parametrize(
    "reply",
    [bytes([MECHANISM_STATE_FAULT]), b"", False],
    ids=["fault", "refused", "timeout"],
)
def test_a_failed_magnet_move_is_published_and_never_acked(acks, reply):
    harness = _harness(reply)

    harness.on_protocol_set_magnet_request(_protocol_magnet(True))

    assert acks == []
    assert [context for context, _ in harness.errors] == ["protocol magnet engage"]
    assert harness.snapshots == [True]


def test_an_absolute_magnet_move_to_zero_is_acked(acks):
    harness = _harness(0)

    harness.on_protocol_set_magnet_request(_protocol_magnet(True, 2.5))

    assert harness.log == [("motorAbsoluteMove", 2, 2500)]
    assert acks == [(MAGNET_APPLIED, "1")]


@pytest.mark.parametrize(
    ("reply", "error"),
    [("Stall", "Stall"), (None, REFUSAL), (False, "motor board not connected")],
)
def test_a_failed_absolute_magnet_move_is_never_acked(acks, reply, error):
    harness = _harness(reply)

    harness.on_protocol_set_magnet_request(_protocol_magnet(True, 2.5))

    assert acks == []
    assert harness.errors == [("protocol magnet absolute 2500", error)]


def test_a_pogo_fault_is_published():
    harness = _harness(bytes([MECHANISM_STATE_FAULT]))

    harness.on_set_pogo_request("True")

    assert harness.log == [("setPogo", 1)]
    assert [context for context, _ in harness.errors] == ["pogo press"]


def test_motor_stop_skips_the_proxy_lock():
    harness = _harness(1200)

    harness.on_motor_stop_request("tray")

    assert harness.log == [("motorStop", 0)]
    assert harness.serialized == [False]
    assert harness.errors == []


def test_motions_skip_the_proxy_lock():
    harness = _harness(b"\x01")

    harness.on_move_magnet_request("engage")
    harness.on_set_pogo_request("True")

    assert harness.serialized == [False, False]


def test_a_move_a_stop_interrupted_is_logged_not_published():
    harness = _harness("Unknown Error")
    move = '{"motor": "tray", "mode": "relative", "value": 5000}'

    harness._stopped_motor_ids.add(0)
    harness.on_motor_move_request(move)

    # A move clears the stop mark when it starts: only a stop sent while it
    # runs downgrades its failure.
    assert harness.errors == [("motor tray relative move 5000 um", "Unknown Error")]

    harness.errors = []
    harness.proxy.uart.motorAction = lambda *args: (
        harness._stopped_motor_ids.add(0) or "Unknown Error"
    )
    harness.on_motor_move_request(move)

    assert harness.errors == []


def test_an_unanswered_speed_write_is_published():
    harness = _harness(None)

    harness.on_motor_set_speed_request('{"motor": "pmt", "value": 20000}')

    assert harness.log == [("setMotorSpeed", 1, 20000)]
    assert harness.errors == [("motor pmt speed 20000 um/s", REFUSAL)]


def test_pmt_home_runs_pmt_reset_on_preset_firmware():
    harness = _harness(True)

    harness.on_motor_home_request("pmt")

    assert harness.log == [("pmt_reset",)]
    assert harness.errors == []
    assert harness.snapshots == [True]


def test_a_refused_pmt_reset_is_published():
    harness = _harness(False)

    harness.on_motor_home_request("pmt")

    assert harness.log == [("pmt_reset",)]
    assert harness.errors == [("motor pmt home (PMT_RESET, ends at park)", REFUSAL)]


@pytest.mark.parametrize(
    ("motor", "presets", "motor_id"),
    [("pmt", False, 1), ("tray", True, 0)],
    ids=["pmt-legacy-firmware", "other-motor"],
)
def test_other_homes_stay_the_raw_motor_home(motor, presets, motor_id):
    harness = _harness(0)
    harness.pmt_presets = presets

    harness.on_motor_home_request(motor)

    assert harness.log == [("motorHome", motor_id)]
    assert harness.errors == []


def _snapshot_reply(positions_10um, homed_bits):
    """The generated proxy's MotorBoardMOTOR_SNAPSHOTResponse."""
    return SimpleNamespace(
        positions=struct.pack(">6h", *positions_10um),
        homed_state_lo=homed_bits,
        sensors_state_hi=0,
        moving=0,
        faults=bytes(6),
    )


def test_the_snapshot_decodes_positions_in_um_and_homed_flags():
    reply = _snapshot_reply((100, -5, 0, 0, 40, 41), 0b000011)

    picture = motor_snapshot_picture(reply)

    assert picture["positions"] == {
        "tray": 1000,
        "pmt": -50,
        "magnet": 0,
        "filter": 0,
        "pogo_left": 400,
        "pogo_right": 410,
    }
    assert [name for name, flag in picture["homed"].items() if flag] == [
        "tray",
        "pmt",
    ]


def test_the_snapshot_names_moving_axes_and_faults():
    reply = _snapshot_reply((0,) * 6, 0)
    reply.moving = 0b000100
    reply.faults = bytes([0x10, 0, 0x05, 0, 0, 0])

    picture = motor_snapshot_picture(reply)

    assert [name for name, flag in picture["moving"].items() if flag] == ["magnet"]
    assert picture["faults"]["tray"] == ["estopped"]
    assert picture["faults"]["magnet"] == ["drv-err", "last-err"]
    assert picture["faults"]["pmt"] == []


class _BaseHarness(PortableDropbotControllerBase):
    #: Whether the fake motor firmware answers MOTOR_SNAPSHOT.
    snapshot_supported = Bool(True)
    replies = Dict()

    def traits_init(self):
        pass

    def _motor_firmware_at_least(self, version):
        assert version == MOTOR_SNAPSHOT_MIN_MOTOR_FIRMWARE
        return self.snapshot_supported

    def _proxy_call(self, context, call, serialize=True):
        return True, self.replies[context]


@pytest.mark.parametrize("poll", [True, False])
def test_supported_firmware_publishes_the_snapshot(monkeypatch, poll):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )
    harness = _BaseHarness(
        replies={"motor snapshot": _snapshot_reply((7, 0, 0, 0, 0, 0), 0b1)}
    )

    harness._publish_motors(poll=poll)

    assert published[0]["positions"]["tray"] == 70
    assert published[0]["homed"]["tray"] is True


def test_older_firmware_falls_back_to_the_position_and_homed_queries(monkeypatch):
    published = []
    monkeypatch.setattr(
        portable_dropbot_controller_base,
        "publish_message",
        lambda topic, message: published.append(json.loads(message)),
    )
    harness = _BaseHarness(
        snapshot_supported=False,
        replies={
            "motor positions": {"tray": 5},
            "motor homed flags": {"tray": False},
        },
    )

    harness._publish_motors()

    assert published[0]["positions"] == {"tray": 5}
    assert published[0]["homed"] == {"tray": False}
