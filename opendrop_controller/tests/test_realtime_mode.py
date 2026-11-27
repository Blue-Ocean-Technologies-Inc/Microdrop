# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""OpenDrop realtime mode turns on only once the board takes the state: a push
with no reply publishes realtime off and never writes the key True. No Redis,
no hardware."""

# Enthought library imports.
from traits.api import Any, List, observe

# Microdrop package imports.
from dropbot_controller.consts import REALTIME_MODE_KEY
from opendrop_controller.services.opendrop_states_setting_mixin_service import (
    OpenDropStatesSettingMixinService,
)

# Microdrop utils imports.
from microdrop_utils import realtime_mode_mixin
from microdrop_utils.realtime_mode_mixin import RealtimeModeMixin


class _OpenDropStates(OpenDropStatesSettingMixinService, RealtimeModeMixin):
    proxy = Any()

    #: The telemetry the fake board answers a state push with (None: no reply).
    push_reply = Any()

    #: Every realtime mode assigned (each one writes the key), in order.
    assigned_realtime = List()

    #: Every realtime mode published, in order.
    published_realtime = List()

    def _push_state_to_device(self, force=False):
        return self.push_reply

    def _publish_realtime_mode(self):
        self.published_realtime.append(self.realtime_mode)

    @observe("realtime_mode")
    def _record_realtime_mode(self, event):
        self.assigned_realtime.append(event.new)


def test_an_unanswered_enable_publishes_off_and_never_on(monkeypatch):
    key_store = {}
    monkeypatch.setattr(realtime_mode_mixin, "app_globals", key_store)
    backend = _OpenDropStates(push_reply=None)

    backend.on_set_realtime_mode_request("True")

    assert backend.assigned_realtime == [False]
    assert backend.published_realtime == [False]
    assert key_store == {REALTIME_MODE_KEY: False}


def test_an_answered_enable_turns_realtime_on(monkeypatch):
    key_store = {}
    monkeypatch.setattr(realtime_mode_mixin, "app_globals", key_store)
    backend = _OpenDropStates(push_reply={})

    backend.on_set_realtime_mode_request("True")

    assert backend.assigned_realtime == [True]
    assert backend.published_realtime == [True]
    assert key_store == {REALTIME_MODE_KEY: True}
