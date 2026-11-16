# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""LOCK_CHIP: the chip engage mode picks the classic motor-board press or the
smart PAD_ENGAGE; an unlock retracts through PAD_ENGAGE whenever a smart
engage may hold the pads; every PAD_ENGAGE failure is published with its
reason. Hardware-free, no Redis."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    CHIP_ENGAGE_MODE_CLASSIC,
    CHIP_ENGAGE_MODE_SMART,
    PAD_ENGAGE_CMD,
    PAD_ENGAGE_FAILURES,
    PAD_ENGAGE_MAX_STEPS,
    PAD_ENGAGE_OVERDRIVE_UM,
    PAD_ENGAGE_STEP_UM,
    SMART_ENGAGE_NEEDS,
    ChipLockFailed,
)
from portable_dropbot_controller.services import (
    portable_dropbot_motors_mixin_service as motors_service,
)

REFUSAL = "cmd 0x1250: FAIL RESP_FAIL (0.05 s)"


class _Result:
    """The driver's CommandResult, reduced to describe()."""

    def describe(self):
        return REFUSAL


class _Uart:
    def __init__(self, log):
        self.log = log

    def setPogo(self, state):
        self.log.append(("setPogo", state))
        return b"\x00"

    def last_result(self, cmd):
        assert cmd == PAD_ENGAGE_CMD
        return _Result()


class _Sig:
    def __init__(self, log, status):
        self.log = log
        self.status = status

    def pad_engage(self, action, mode, step, max_steps, overdrive_um):
        self.log.append(("pad_engage", action, mode, step, max_steps, overdrive_um))

        if isinstance(self.status, Exception):
            raise self.status

        if self.status is None:
            return None

        return SimpleNamespace(status=self.status, l_steps=3, r_steps=4)


class _Base(HasTraits):
    proxy = Any()
    preferences = Any()
    pads_smart_engaged = Bool(False)
    log = List()
    snapshots = List()

    def _proxy_call(self, context, call):
        """The real _proxy_call's contract: the raised exception on failure."""
        try:
            return True, call()
        except Exception as error:
            return False, error

    def _publish_status_snapshot(self):
        self.snapshots.append(True)


class _Harness(motors_service.PortableDropbotMotorsMixinService, _Base):
    pass


@pytest.fixture
def failures(monkeypatch):
    """The CHIP_LOCK_FAILED payloads, in order, validated like the real
    publisher does."""
    published = []

    monkeypatch.setattr(
        motors_service,
        "chip_lock_failed_publisher",
        SimpleNamespace(
            publish=lambda payload: published.append(
                ChipLockFailed.model_validate(payload)
            )
        ),
    )

    return published


def _harness(mode, status=0, smart_engaged=False):
    harness = _Harness(
        preferences=SimpleNamespace(chip_engage_mode=mode),
        pads_smart_engaged=smart_engaged,
    )
    harness.proxy = SimpleNamespace(
        uart=_Uart(harness.log), sig=_Sig(harness.log, status)
    )

    return harness


def _pad_engage(action, mode):
    return (
        "pad_engage",
        action,
        mode,
        PAD_ENGAGE_STEP_UM,
        PAD_ENGAGE_MAX_STEPS,
        PAD_ENGAGE_OVERDRIVE_UM,
    )


@pytest.mark.parametrize(("message", "state"), [("True", 1), ("False", 0)])
def test_classic_mode_presses_and_releases_through_the_motor_board(
    message, state, failures
):
    harness = _harness(CHIP_ENGAGE_MODE_CLASSIC)

    harness.on_lock_chip_request(message)

    assert harness.log == [("setPogo", state)]
    assert harness.snapshots == [True]
    assert failures == []


def test_smart_lock_engages_with_the_fixed_descent(failures):
    harness = _harness(CHIP_ENGAGE_MODE_SMART)

    harness.on_lock_chip_request("True")

    assert harness.log == [_pad_engage(1, 1)]
    assert harness.pads_smart_engaged is True
    assert harness.snapshots == [True]
    assert failures == []


@pytest.mark.parametrize(
    ("mode", "smart_engaged"),
    [
        (CHIP_ENGAGE_MODE_SMART, True),
        (CHIP_ENGAGE_MODE_SMART, False),
        # The mode changed back to classic after a smart lock.
        (CHIP_ENGAGE_MODE_CLASSIC, True),
    ],
)
def test_unlock_retracts_whenever_a_smart_engage_may_hold_the_pads(
    mode, smart_engaged, failures
):
    harness = _harness(mode, smart_engaged=smart_engaged)

    harness.on_lock_chip_request("False")

    assert harness.log == [_pad_engage(0, 0)]
    assert harness.pads_smart_engaged is False
    assert failures == []


@pytest.mark.parametrize("status", [1, 2, 3])
def test_a_failed_smart_lock_reports_why_and_stays_unlocked(status, failures):
    harness = _harness(CHIP_ENGAGE_MODE_SMART, status=status)

    harness.on_lock_chip_request("True")

    assert harness.pads_smart_engaged is False
    assert harness.snapshots == [True]
    assert len(failures) == 1
    assert failures[0].action == "lock"
    assert failures[0].error.startswith(PAD_ENGAGE_FAILURES[status])
    assert failures[0].pads_may_be_pressed is False


def test_a_smart_lock_motor_error_names_the_homing_prerequisite(failures):
    harness = _harness(CHIP_ENGAGE_MODE_SMART, status=2)

    harness.on_lock_chip_request("True")

    assert SMART_ENGAGE_NEEDS in failures[0].error


@pytest.mark.parametrize("status", [4, 5])
def test_a_lock_that_may_leave_the_pads_pressed_warns_and_reads_locked(
    status, failures
):
    harness = _harness(CHIP_ENGAGE_MODE_SMART, status=status)

    harness.on_lock_chip_request("True")

    assert harness.pads_smart_engaged is True
    assert failures[0].error == PAD_ENGAGE_FAILURES[status]
    assert failures[0].pads_may_be_pressed is True


def test_an_unanswered_smart_lock_carries_the_drivers_account(failures):
    harness = _harness(CHIP_ENGAGE_MODE_SMART, status=None)

    harness.on_lock_chip_request("True")

    assert harness.pads_smart_engaged is False
    assert failures[0].error == f"{REFUSAL}; {SMART_ENGAGE_NEEDS}"


def test_a_raised_driver_error_is_the_failure_reason(failures):
    harness = _harness(CHIP_ENGAGE_MODE_SMART, status=RuntimeError("link lost"))

    harness.on_lock_chip_request("True")

    assert failures[0].error == "link lost"
    assert failures[0].pads_may_be_pressed is False


@pytest.mark.parametrize("status", [4, None])
def test_a_failed_retract_warns_and_keeps_the_pads_locked(status, failures):
    harness = _harness(CHIP_ENGAGE_MODE_CLASSIC, status=status, smart_engaged=True)

    harness.on_lock_chip_request("False")

    assert harness.pads_smart_engaged is True
    assert failures[0].action == "unlock"
    assert failures[0].pads_may_be_pressed is True
    assert SMART_ENGAGE_NEEDS not in failures[0].error
