# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""REALTIME_MODE_KEY has one writer, the backend: RealtimeModeMixin writes it on
every assignment of realtime_mode, a DropBot disconnect turns it off, and a
frontend status model never writes it; a refused enable publishes off without
ever turning it on. No Redis."""

# Standard library imports.
import threading

# Enthought library imports.
from traits.api import Any, Bool, List, observe

# Microdrop package imports.
from dropbot_controller.consts import REALTIME_MODE_KEY, REALTIME_MODE_UPDATED
from dropbot_controller.services import dropbot_states_setting_mixin_service
from dropbot_controller.services.dropbot_monitor_mixin_service import (
    DropbotMonitorMixinService,
)
from dropbot_controller.services.dropbot_states_setting_mixin_service import (
    DropbotStatesSettingMixinService,
)
from template_status_and_controls.base_model import BaseStatusModel

# Microdrop utils imports.
from microdrop_utils.realtime_mode_mixin import RealtimeModeMixin
from microdrop_utils.redis_manager import RedisHashDictProxy


class _DropbotMonitor(DropbotMonitorMixinService, RealtimeModeMixin):
    proxy = Any()
    dropbot_connection_active = Bool(True)


class _DropbotStates(DropbotStatesSettingMixinService):
    proxy = Any()

    #: Every realtime mode assigned (each one writes the key), in order.
    assigned_realtime = List()

    @observe("realtime_mode")
    def _record_realtime_mode(self, event):
        self.assigned_realtime.append(event.new)


class _TimingOutProxy:
    transaction_lock = threading.Lock()

    def update_state(self, **states):
        raise TimeoutError("no reply from the board")


def test_constructing_a_backend_writes_nothing(realtime_mode_key_store):
    RealtimeModeMixin()

    assert realtime_mode_key_store == {}


def test_applying_a_mode_writes_the_key(realtime_mode_key_store):
    backend = RealtimeModeMixin()
    backend.realtime_mode = True

    assert realtime_mode_key_store == {REALTIME_MODE_KEY: True}


def test_an_unchanged_mode_overwrites_a_stale_key(realtime_mode_key_store):
    realtime_mode_key_store[REALTIME_MODE_KEY] = True

    RealtimeModeMixin().realtime_mode = False

    assert realtime_mode_key_store == {REALTIME_MODE_KEY: False}


def test_a_dropbot_disconnect_turns_the_key_off(realtime_mode_key_store):
    # No power: the handler waits for a retry request instead of rescanning.
    monitor = _DropbotMonitor(_no_power=True)
    monitor.realtime_mode = True

    monitor.on_disconnected_signal("")

    assert realtime_mode_key_store == {REALTIME_MODE_KEY: False}


def test_a_failed_realtime_enable_publishes_off_and_never_on(
    realtime_mode_key_store, monkeypatch
):
    published = []
    monkeypatch.setattr(
        dropbot_states_setting_mixin_service,
        "publish_message",
        lambda topic, message: published.append((topic, message)),
    )
    backend = _DropbotStates(proxy=_TimingOutProxy())

    backend.on_set_realtime_mode_request("True")

    assert backend.assigned_realtime == [False]
    assert realtime_mode_key_store == {REALTIME_MODE_KEY: False}
    assert published == [(REALTIME_MODE_UPDATED, "False")]


def test_a_status_model_never_writes_the_key(monkeypatch):
    writes = []
    monkeypatch.setattr(
        RedisHashDictProxy,
        "__setitem__",
        lambda proxy, key, value: writes.append(key),
    )

    model = BaseStatusModel()
    model.realtime_mode = True

    assert writes == []
