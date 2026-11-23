# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""An electrode write the board refuses (setElectrodeStates False, e.g.
0x1242 FAIL while the 24 V rails are off) is published as a failure and
never recorded as the applied state. Hardware-free, no Redis."""

# Standard library imports.
import json

# Third-party imports.
import pytest
from dropbot_portable.portable_dropbot_service import CMD_ELECTRODE_STATE_CH

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, List

# Microdrop package imports.
from device_viewer.consts import user_disabled_channels_mirror
from portable_dropbot_controller.consts import LAST_CHANNEL_STATES_REQUESTED_KEY
from portable_dropbot_controller.services import (
    portable_dropbot_electrodes_mixin_service as electrodes_service,
)

#: What the driver's last_result says about the refused write.
REFUSAL = "cmd 0x1242: FAIL RESP_FAIL (0.05 s)"


class _Result:
    def describe(self):
        return REFUSAL


class _Uart:
    board_channels = 8

    def __init__(self, applied):
        self.applied = applied
        self.writes = []
        self.asked = []

    def setElectrodeStates(self, states):
        self.writes.append(list(states))

        return self.applied

    def last_result(self, cmd):
        self.asked.append(cmd)

        return _Result()


class _Session:
    def __init__(self, applied):
        self.uart = _Uart(applied)


class _Base(HasTraits):
    proxy = Any()
    realtime_mode = Bool(True)
    errors = List()

    def _proxy_call(self, context, call, serialize=True):
        return True, call()

    def _publish_error(self, context, error):
        self.errors.append((context, error))


class _Harness(electrodes_service.PortableDropbotElectrodesMixinService, _Base):
    pass


@pytest.fixture
def app_globals(monkeypatch):
    store = {}
    monkeypatch.setattr(electrodes_service, "app_globals", store)
    monkeypatch.setattr(user_disabled_channels_mirror, "read", lambda: set())

    return store


def test_an_applied_write_is_recorded(app_globals):
    harness = _Harness(proxy=_Session(applied=True))
    message = json.dumps({"channels": [1, 3]})

    harness.on_electrodes_state_change_request(message)

    assert harness.proxy.uart.writes == [
        [False, True, False, True, False, False, False, False]
    ]
    assert app_globals == {LAST_CHANNEL_STATES_REQUESTED_KEY: message}
    assert harness.errors == []


def test_a_refused_write_is_published_and_not_recorded(app_globals):
    harness = _Harness(proxy=_Session(applied=False))

    harness.on_electrodes_state_change_request(json.dumps({"channels": [1]}))

    [(context, error)] = harness.errors

    assert context == "electrode actuation"
    assert REFUSAL in error
    assert harness.proxy.uart.asked == [CMD_ELECTRODE_STATE_CH]
    assert app_globals == {}
