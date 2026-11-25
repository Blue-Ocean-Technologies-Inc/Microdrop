# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The clear-alarms request: every active code is cleared, a code that
stays latched (or is refused) is reported as still active rather than
raised, and the outcome is published per board. Hardware-free, no Redis."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.board_alarms import clear_board_alarms
from portable_dropbot_controller.consts import AlarmsCleared
from portable_dropbot_controller.services import (
    portable_dropbot_states_setting_mixin_service as states_module,
)


class _FakeSession:
    """GET_ALARMS / CLEAR_ALARM on two boards. Codes in ``persistent`` stay
    latched after an answered clear; codes in ``refused`` get no reply."""

    def __init__(self, active, persistent=(), refused=()):
        self.active = {board: list(codes) for board, codes in active.items()}
        self.persistent = set(persistent)
        self.refused = set(refused)
        self.cleared_calls = []
        self.uart = SimpleNamespace(get_alarms=self._get_alarms)

    def _get_alarms(self, board):
        return [
            {"code": code, "level": 5, "text": f"{code} text", "title": f"{code} title"}
            for code in self.active[board]
        ]

    def clear_alarm(self, board, code):
        self.cleared_calls.append((board, code))

        if code in self.refused:
            return False

        if code not in self.persistent and code in self.active[board]:
            self.active[board].remove(code)

        return True


def test_every_active_code_is_cleared():
    session = _FakeSession({"motor": ["04012", "04001"]})

    result = clear_board_alarms(session, "motor")

    assert session.cleared_calls == [("motor", "04012"), ("motor", "04001")]
    assert result["cleared"] == ["04012", "04001"]
    assert result["failed"] == []
    assert result["still_active"] == {}


def test_a_code_whose_condition_persists_is_reported_still_active():
    session = _FakeSession({"signal": ["07001", "01004"]}, persistent={"07001"})

    result = clear_board_alarms(session, "signal")

    assert result["cleared"] == ["01004"]
    assert result["failed"] == ["07001"]
    assert result["still_active"] == {"07001": "07001 title"}


def test_a_refused_clear_fails_even_if_not_active():
    session = _FakeSession({"motor": []}, refused={"99999"})

    result = clear_board_alarms(session, "motor", ["99999"])

    assert result["failed"] == ["99999"]
    assert result["cleared"] == []


def test_unreadable_alarms_clear_nothing():
    session = _FakeSession({"motor": ["04012"]})
    session.uart.get_alarms = lambda board: None

    result = clear_board_alarms(session, "motor")

    assert session.cleared_calls == []
    assert result["error"]


class _Base(HasTraits):
    proxy = Any()
    errors = List()

    def _proxy_call(self, context, call, serialize=True):
        return True, call()

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")


class _Harness(states_module.PortableDropbotStatesSettingMixinService, _Base):
    pass


@pytest.fixture
def published(monkeypatch):
    payloads = []
    monkeypatch.setattr(
        states_module,
        "alarms_cleared_publisher",
        SimpleNamespace(publish=payloads.append),
    )

    return payloads


def test_the_request_clears_both_boards_by_default(published):
    session = _FakeSession(
        {"motor": ["04012"], "signal": ["07001"]}, persistent={"07001"}
    )
    harness = _Harness(proxy=session)

    harness.on_clear_alarms_request("")

    outcome = AlarmsCleared.model_validate(published[0])
    motor, signal = outcome.results

    assert (motor.board, motor.cleared, motor.still_active) == ("motor", ["04012"], {})
    assert (signal.board, signal.failed) == ("signal", ["07001"])
    assert signal.still_active == {"07001": "07001 title"}
    assert harness.errors == []


def test_a_malformed_code_is_an_error_not_a_clear(published):
    session = _FakeSession({"motor": ["04012"]})
    harness = _Harness(proxy=session)

    harness.on_clear_alarms_request('{"codes": ["4012"]}')

    assert session.cleared_calls == []
    assert published == []
    assert harness.errors and harness.errors[0].startswith("alarm clear:")
