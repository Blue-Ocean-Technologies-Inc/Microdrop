# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Wiring tests for ProtocolAutosaveController (#966).

The timer is never left to fire: tests drive ``_on_timer_timeout`` and
``flush`` directly against a fake clock.
"""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences

# Microdrop package imports.
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services import protocol_autosave_controller
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.services.protocol_autosave_controller import (
    ProtocolAutosaveController,
)
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(qapp, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        protocol_autosave_controller,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    manager = RowManager(columns=[make_type_column(), make_name_column()])
    tracker = PluggableProtocolStateTracker()
    tracker.reseed_baseline(manager)
    tracker.set_saved("C:/protocols/p.json")

    preferences = ProtocolPreferences(preferences=Preferences())
    preferences.protocol_autosave_enabled = True

    writes = []
    clock = _Clock()

    def write_protocol():
        writes.append(tracker.loaded_protocol_path)
        tracker.reseed_baseline(manager)

    controller = ProtocolAutosaveController(
        model=ProtocolAutosaveModel(tracker=tracker),
        manager=manager,
        preferences=preferences,
        write_protocol=write_protocol,
        clock=clock,
    )

    return controller, manager, tracker, writes, warnings, clock


def _edit(manager, tracker):
    manager.add_step()
    tracker.on_structure_changed(manager)


def test_preference_seeds_and_follows_the_toggle(setup):
    controller, _manager, _tracker, _writes, _warnings, _clock = setup

    assert controller.model.enabled

    controller.model.enabled = False

    assert controller.preferences.protocol_autosave_enabled is False


def test_change_is_written_once_the_debounce_elapses(setup):
    controller, manager, tracker, writes, _warnings, clock = setup

    _edit(manager, tracker)
    controller._on_timer_timeout()

    assert writes == []

    clock.now += controller.model.debounce_s
    controller._on_timer_timeout()

    assert writes == [tracker.loaded_protocol_path]
    assert not tracker.is_modified


def test_flush_writes_without_waiting(setup):
    controller, manager, tracker, writes, _warnings, _clock = setup

    _edit(manager, tracker)
    controller.flush()

    assert writes == [tracker.loaded_protocol_path]


def test_run_end_writes_changes_made_during_the_run(setup):
    controller, manager, tracker, writes, _warnings, clock = setup

    tracker.is_active = True
    _edit(manager, tracker)
    clock.now += controller.model.debounce_s
    controller._on_timer_timeout()

    assert writes == []

    tracker.is_active = False
    controller._on_timer_timeout()

    assert writes == [tracker.loaded_protocol_path]


def test_failed_write_is_reported_once_and_stays_dirty(setup):
    controller, manager, tracker, _writes, warnings, _clock = setup

    def failing_write():
        raise OSError("disk full")

    controller.write_protocol = failing_write

    _edit(manager, tracker)
    controller.flush()
    _edit(manager, tracker)
    controller.flush()

    assert len(warnings) == 1
    assert tracker.is_modified
    assert controller.model.last_error == "disk full"


def test_pane_puts_the_toggle_on_the_quick_actions_toolbar(qapp):
    from pluggable_protocol_tree.models.quick_action import BaseQuickAction
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane(
        [make_name_column()],
        preferences=ProtocolPreferences(preferences=Preferences()),
        quick_actions=[BaseQuickAction(action_id="add_step", icon_text="add")],
    )
    toggle = pane.autosave_toggle.control

    assert pane.quick_action_bar.widget().isAncestorOf(toggle)
    assert toggle.text() == "AutoSave: Off"

    toggle.click()

    assert pane.autosave_controller.model.enabled
    assert pane.preferences.protocol_autosave_enabled
    assert toggle.isChecked()
    assert toggle.text() == "AutoSave: On (no file)"
