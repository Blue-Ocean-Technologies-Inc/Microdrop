# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Connect path of the monitor mixin: a session that fails to construct is
reported with its real reason, not the generic handshake text, and the
driver's ``DropBotSession`` still carries the board proxies the backend
mixins call. Hardware-free, no Redis."""

# Third-party imports.
from dropbot_portable import DropBotSession, MotorBoardProxy, SignalBoardProxy

# Enthought library imports.
from traits.api import Any, HasTraits, List

# Microdrop package imports.
from portable_dropbot_controller.services import (
    portable_dropbot_monitor_mixin_service as mod,
)


class _Base(HasTraits):
    proxy = Any()
    errors = List()

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")


class _Harness(mod.PortableDropbotMonitorMixinService, _Base):
    pass


class _BrokenSession:
    def __init__(self, *args, **kwargs):
        raise AttributeError("no setter")


def test_connect_failure_publishes_the_real_reason(monkeypatch):
    monkeypatch.setattr(mod, "DropBotSession", _BrokenSession)
    harness = _Harness()

    harness.on_connect_to_port_request("/dev/ttyX")

    assert len(harness.errors) == 1
    assert "AttributeError" in harness.errors[0]
    assert "no setter" in harness.errors[0]
    assert harness.portable_dropbot_connection_active is False
    assert harness.proxy is None


def test_driver_session_exposes_board_proxies():
    session = DropBotSession()

    assert isinstance(session.sig, SignalBoardProxy)
    assert isinstance(session.motor, MotorBoardProxy)
