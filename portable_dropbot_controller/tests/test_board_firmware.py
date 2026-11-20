# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Firmware versions read on connect: check_versions' verdict becomes the
per-board version tuples the backend gates features on (unknown = False)
and the payload the status pane shows. Hardware-free, no Redis."""

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, HasTraits

# Microdrop package imports.
from portable_dropbot_controller import board_firmware
from portable_dropbot_controller.board_firmware import (
    firmware_at_least,
    summarize_firmware_checks,
)
from portable_dropbot_controller.services import (
    portable_dropbot_monitor_mixin_service as mod,
)

CHECKS = {
    "signal": ("DroSIG_1.0.1.32", ">= DroSIG_1.0.1.31", True),
    "motor": ("DroDri_1.0.0.25-3-gabc", ">= DroDri_1.0.0.26", False),
}


class _Base(HasTraits):
    proxy = Any()
    realtime_mode = Bool(False)

    def _publish_realtime_mode(self):
        pass

    def _proxy_call(self, context, call):
        return True, call()


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(board_firmware, "FIRMWARE_READ_RETRY_DELAY_S", 0)


@pytest.fixture
def published_firmware(monkeypatch):
    published = []
    monkeypatch.setattr(
        board_firmware.firmware_versions_publisher, "publish", published.append
    )

    return published


class _Harness(mod.PortableDropbotMonitorMixinService, _Base):
    pass


class _Session:
    def __init__(self, checks):
        self.checks = checks

    def check_versions(self, ignore=False):
        assert ignore is True
        return self.checks


def test_checks_become_version_tuples_and_an_outdated_line():
    versions, payload = summarize_firmware_checks(CHECKS)

    assert versions == {"mcu": (1, 0, 1, 32), "motor": (1, 0, 0, 25)}
    assert payload["mcu"] == "DroSIG_1.0.1.32"
    assert payload["motor"] == "DroDri_1.0.0.25-3-gabc"
    assert payload["outdated"] == [
        "Motor board firmware DroDri_1.0.0.25-3-gabc (needs >= DroDri_1.0.0.26)"
    ]


def test_unknown_or_absent_boards_are_left_out():
    versions, payload = summarize_firmware_checks(
        {"signal": ("unknown", ">= DroSIG_1.0.1.31", None)}
    )

    assert versions == {}
    assert payload == {"mcu": "", "motor": "", "outdated": []}


@pytest.mark.parametrize(
    ("version", "expected"),
    [((1, 0, 1, 31), True), ((1, 0, 1, 32), True), ((1, 0, 1, 33), False)],
)
def test_firmware_at_least_compares_tuples(version, expected):
    assert firmware_at_least({"mcu": (1, 0, 1, 32)}, "mcu", version) is expected


def test_firmware_at_least_is_false_while_unknown():
    assert firmware_at_least({}, "motor", (0,)) is False


def test_monitor_helpers_gate_on_the_versions_read_at_connect():
    harness = _Harness()

    assert harness._mcu_firmware_at_least((1, 0, 1, 30)) is False
    assert harness._motor_firmware_at_least((1, 0, 0, 1)) is False

    payload = harness._read_board_firmware(_Session(CHECKS))

    assert payload["outdated"]
    assert harness._mcu_firmware_at_least((1, 0, 1, 31)) is True
    assert harness._mcu_firmware_at_least((1, 0, 1, 33)) is False
    assert harness._motor_firmware_at_least((1, 0, 0, 25)) is True
    assert harness._motor_firmware_at_least((1, 0, 0, 26)) is False


def test_disconnect_forgets_the_versions():
    harness = _Harness()
    harness._read_board_firmware(_Session(CHECKS))

    harness._forget_connection()

    assert harness.board_firmware_versions == {}
    assert harness._mcu_firmware_at_least((1,)) is False


def test_a_failed_version_read_leaves_everything_unknown():
    class _Broken:
        def check_versions(self, ignore=False):
            raise TimeoutError("no VERSION reply")

    harness = _Harness()

    payload = harness._read_board_firmware(_Broken())

    assert harness.board_firmware_versions == {}
    assert payload == {"mcu": "", "motor": "", "outdated": []}


class _Scripted:
    """A session whose check_versions answers from a script, one entry per
    call (an exception entry is raised)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def check_versions(self, ignore=False):
        self.calls += 1
        answer = self.answers.pop(0)

        if isinstance(answer, Exception):
            raise answer

        return answer


UNKNOWN_MOTOR = {**CHECKS, "motor": ("unknown", ">= DroDri_1.0.0.26", None)}


def test_a_version_read_failing_at_connect_is_retried_once():
    session = _Scripted(TimeoutError("still homing"), CHECKS)
    harness = _Harness()

    harness._read_board_firmware(session)

    assert session.calls == 2
    assert harness._motor_firmware_at_least((1, 0, 0, 25)) is True


def test_a_board_answering_no_version_is_retried_once_then_left_unknown():
    session = _Scripted(UNKNOWN_MOTOR, UNKNOWN_MOTOR)
    harness = _Harness()

    harness._read_board_firmware(session)

    assert session.calls == 2
    assert "motor" not in harness.board_firmware_versions
    assert harness._mcu_firmware_at_least((1, 0, 1, 31)) is True


def test_an_unknown_motor_version_is_read_again_on_demand(published_firmware):
    harness = _Harness()
    harness.proxy = _Scripted(CHECKS)

    assert harness._motor_firmware_known() is True
    assert harness.proxy.calls == 1
    assert published_firmware[0]["motor"] == "DroDri_1.0.0.25-3-gabc"

    # Known now: no further read.
    assert harness._motor_firmware_known() is True
    assert harness.proxy.calls == 1


def test_a_motor_version_still_unknown_after_the_reread_stays_unknown(
    published_firmware,
):
    harness = _Harness()
    harness.proxy = _Scripted(UNKNOWN_MOTOR)

    assert harness._motor_firmware_known() is False
    assert harness.proxy.calls == 1
