# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Home All as the vendor UI's host plan (its order, its per-step checks,
realtime mode off first, a failure never cancelling the later steps, an
E-STOP ending it) and the motor E-STOP outside the proxy lock.
Hardware-free, no Redis."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest
from dropbot_portable import param_layout
from dropbot_portable.portable_dropbot_service import _is_urgent_thread
from dropbot_portable.proxy import (
    MotorBoardMOTOR_CONTROLResponse,
    MotorBoardMOTOR_ESTOPResponse,
)

# Enthought library imports.
from traits.api import Any, Bool, Dict, HasTraits, Int, List

# Microdrop package imports.
from portable_dropbot_controller.motion_safety import (
    home_all_block_reason,
    home_all_plan,
)
from portable_dropbot_controller.services import (
    portable_dropbot_motors_mixin_service as motors_service,
)

#: The vendor's plan for the firmware's default table.
DEFAULT_PLAN = ["pmt_reset", "mag_reset", "pushpad_reset", "tray_reset", "flu_reset"]
#: What the driver's last_result says about a refused or unanswered request.
REFUSAL = "cmd 0x1131: FAIL RESP_FAIL (0.05 s)"


class _Result:
    def describe(self):
        return REFUSAL


class _Uart:
    def __init__(self):
        self.last_error_ftype = {}

    def last_result(self, cmd):
        return _Result()


class _Motor:
    """The generated motor proxy: every reset answers what ``replies``
    says (default: success), logged in call order."""

    def __init__(self, log, replies, home_seq=None):
        self.log = log
        self.replies = replies
        self.home_seq = home_seq
        self.on_call = {}

    def _answer(self, name, default):
        self.log.append(name)
        self.on_call.get(name, lambda: None)()

        return self.replies.get(name, default)

    def get_params(self, name):
        assert name == param_layout.HOME_SEQ_KEY
        self.log.append("get_params")

        if self.home_seq is None:
            return None

        return SimpleNamespace(value=param_layout.pack_home_seq(self.home_seq))

    def pmt_reset(self):
        return self._answer("pmt_reset", True)

    def mag_reset(self):
        return self._answer("mag_reset", SimpleNamespace(status_data=b"\x00"))

    def pushpad_reset(self):
        return self._answer("pushpad_reset", True)

    def tray_reset(self):
        return self._answer("tray_reset", SimpleNamespace(status_data=b"\x00"))

    def flu_reset(self):
        return self._answer("flu_reset", True)

    def motor_control(self, motor_id, action, distance):
        return self._answer(
            f"park_{motor_id}", MotorBoardMOTOR_CONTROLResponse(motor_id, 0, 0)
        )

    def motor_estop(self):
        self.log.append("motor_estop")

        return MotorBoardMOTOR_ESTOPResponse(moving_bitmap=0b1)


class _Base(HasTraits):
    proxy = Any()
    log = List()
    errors = List()
    #: Context -> the serialize flag each driver call ran with.
    serialized = Dict()
    snapshots = Int()
    #: Calls of the base's E-STOP hook (the self-test run's halt).
    estop_hooks = Int()
    realtime_mode = Bool(True)
    pads_smart_engaged = Bool(True)

    def _proxy_call(self, context, call, serialize=True):
        self.serialized[context] = serialize

        return True, call()

    def _on_motor_estop(self):
        self.estop_hooks += 1

    def _leave_realtime_mode(self):
        self.log.append("realtime off")
        self.realtime_mode = False

    def _publish_error(self, context, error):
        self.errors.append((context, error))

    def _publish_status_snapshot(self):
        self.snapshots += 1

    def _publish_motors(self, mechanisms=None, poll=True):
        self.snapshots += 1


class _Harness(motors_service.PortableDropbotMotorsMixinService, _Base):
    pass


def _harness(replies=None, home_seq=None):
    harness = _Harness()
    harness.proxy = SimpleNamespace(
        motor=_Motor(harness.log, replies or {}, home_seq), uart=_Uart()
    )

    return harness


def test_the_default_table_plans_the_vendor_order():
    assert home_all_plan(param_layout.HOME_SEQ_DEFAULT) == DEFAULT_PLAN
    assert home_all_plan([]) == DEFAULT_PLAN


def test_a_home_and_park_of_the_magnet_adds_its_park():
    rows = [
        param_layout.HomeSeqRow(param_layout.HS_UNIT_PMT),
        param_layout.HomeSeqRow(param_layout.HS_UNIT_MAGNET),
    ]

    assert home_all_plan(rows)[:3] == ["pmt_reset", "mag_reset", "park_2"]


def test_an_unsafe_table_is_blocked():
    rows = [param_layout.HomeSeqRow(param_layout.HS_UNIT_TRAY)]

    assert home_all_block_reason(rows).startswith("home sequence order unsafe")
    assert home_all_block_reason(param_layout.HOME_SEQ_DEFAULT) == ""


def test_an_empty_stored_table_runs_the_compiled_default():
    empty = param_layout.unpack_home_seq(bytes(param_layout.HOME_SEQ_SIZE))

    assert param_layout.home_seq_problems(empty) == [
        param_layout.HOME_SEQ_EMPTY_PROBLEM
    ]
    assert home_all_block_reason(empty) == ""

    harness = _harness(home_seq=empty)

    harness.on_home_all_request("")

    assert harness.log == ["realtime off", "get_params", *DEFAULT_PLAN]
    assert harness.errors == []


def test_home_all_turns_realtime_off_then_runs_the_plan_outside_the_lock():
    harness = _harness()

    harness.on_home_all_request("")

    assert harness.log == ["realtime off", "get_params", *DEFAULT_PLAN]
    assert harness.errors == []
    assert all(
        serialize is False
        for context, serialize in harness.serialized.items()
        if context.startswith("home all:")
    )
    assert harness.snapshots == 1


def test_the_boards_table_drives_the_plan():
    rows = [
        param_layout.HomeSeqRow(param_layout.HS_UNIT_PMT),
        param_layout.HomeSeqRow(param_layout.HS_UNIT_MAGNET),
        param_layout.HomeSeqRow(param_layout.HS_UNIT_TRAY),
    ]
    harness = _harness(home_seq=rows)

    harness.on_home_all_request("")

    assert harness.log[2:5] == ["pmt_reset", "mag_reset", "park_2"]


def test_a_successful_pad_reset_clears_the_smart_engage():
    harness = _harness()

    harness.on_home_all_request("")

    assert harness.pads_smart_engaged is False


@pytest.mark.parametrize(
    ("replies", "error"),
    [
        ({"pmt_reset": False}, REFUSAL),
        ({"mag_reset": None}, REFUSAL),
    ],
    ids=["refused", "no-reply"],
)
def test_a_failed_step_is_published_and_the_plan_goes_on(replies, error):
    harness = _harness(replies)
    step = next(iter(replies))

    harness.on_home_all_request("")

    # The vendor queues every step up front: a failure cancels nothing.
    assert harness.log[2:] == DEFAULT_PLAN
    assert harness.errors == [(f"home all: {step}", error)]


def test_a_park_error_status_is_published():
    rows = [
        param_layout.HomeSeqRow(param_layout.HS_UNIT_PMT),
        param_layout.HomeSeqRow(param_layout.HS_UNIT_MAGNET),
    ]
    harness = _harness(
        {"park_2": MotorBoardMOTOR_CONTROLResponse(2, -1, 0)}, home_seq=rows
    )

    harness.on_home_all_request("")

    assert [context for context, _ in harness.errors] == ["home all: park_2"]


def test_a_refused_pad_reset_keeps_the_smart_engage():
    harness = _harness({"pushpad_reset": False})

    harness.on_home_all_request("")

    assert harness.pads_smart_engaged is True


def test_an_estop_ends_home_all_without_an_error():
    harness = _harness({"mag_reset": None})
    harness.proxy.motor.on_call["mag_reset"] = lambda: harness.on_motor_estop_request(
        ""
    )

    harness.on_home_all_request("")

    assert harness.log == [
        "realtime off",
        "get_params",
        "pmt_reset",
        "mag_reset",
        "motor_estop",
    ]
    assert harness.errors == []


def test_a_second_home_all_is_refused_while_one_runs():
    harness = _harness()
    harness._home_all_lock.acquire()

    harness.on_home_all_request("")

    assert harness.log == []
    assert harness.errors == [("home all", "Home All is already running")]


def test_the_estop_skips_the_proxy_lock_and_marks_every_motor():
    harness = _harness()

    harness.on_motor_estop_request("")

    assert harness.log == ["motor_estop"]
    assert harness.estop_hooks == 1
    assert harness.serialized == {"motor E-STOP": False}
    assert harness._stopped_motor_ids == {0, 1, 2, 3, 4, 5}
    assert harness._home_all_estopped is True
    assert harness.errors == []


def test_the_estop_runs_as_an_urgent_lane_and_clears_it():
    harness = _harness()
    urgent = []
    harness.proxy.motor.motor_estop = lambda: urgent.append(_is_urgent_thread())

    harness.on_motor_estop_request("")

    assert urgent == [True]
    assert _is_urgent_thread() is False


def test_an_unanswered_estop_is_published():
    harness = _harness()
    harness.proxy.motor.motor_estop = lambda: None

    harness.on_motor_estop_request("")

    assert harness.errors == [("motor E-STOP", REFUSAL)]
