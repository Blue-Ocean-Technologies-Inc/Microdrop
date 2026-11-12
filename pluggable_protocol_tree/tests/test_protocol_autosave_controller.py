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

# Standard library imports.
import json

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
from pluggable_protocol_tree.services.protocol_history import ProtocolHistory
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


def test_undo_after_an_autosave_is_saved_again(setup):
    controller, manager, tracker, writes, _warnings, clock = setup
    path = tracker.loaded_protocol_path

    # The dock pane's dirty bookkeeping, which the bare manager lacks.
    manager.observe(lambda event: tracker.on_structure_changed(manager), "rows_changed")
    history = ProtocolHistory(manager=manager, protocol_state_tracker=tracker)

    manager.add_step()
    clock.now += controller.model.debounce_s
    controller._on_timer_timeout()

    assert writes == [path]
    assert not tracker.is_modified
    assert history.undo_name

    history.undo()

    assert tracker.is_modified
    assert history.redo_name

    clock.now += controller.model.debounce_s
    controller._on_timer_timeout()

    assert writes == [path, path]
    assert not tracker.is_modified
    assert history.redo_name


def test_loading_a_protocol_does_not_rewrite_it(qapp, tmp_path, monkeypatch):
    from pluggable_protocol_tree.views import protocol_tree_pane as ptp

    source = RowManager(columns=[make_type_column(), make_name_column()])
    source.add_step(values={"name": "saved step"})
    path = tmp_path / "p.json"
    path.write_text(json.dumps(source.to_json()), encoding="utf-8")

    pane = ptp.ProtocolTreePane(
        [make_type_column(), make_name_column()],
        preferences=ProtocolPreferences(preferences=Preferences()),
    )
    tracker = pane.protocol_state_tracker
    controller = pane.autosave_controller
    clock = _Clock()
    controller.clock = clock

    # The dock pane's dirty bookkeeping, which a standalone pane lacks.
    pane.manager.observe(
        lambda event: tracker.on_structure_changed(pane.manager), "rows_changed"
    )

    writes = []
    monkeypatch.setattr(pane, "_dump_protocol_json", writes.append)
    monkeypatch.setattr(
        ptp.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )

    assert controller.model.enabled

    pane.load_protocol_dialog()
    clock.now += controller.model.debounce_s
    controller._on_timer_timeout()
    controller.flush()

    assert writes == []
    assert not tracker.is_modified

    pane.manager.add_step()
    clock.now += controller.model.debounce_s
    controller._on_timer_timeout()

    assert writes == [tracker.loaded_protocol_path]


def test_status_bar_glyph_binds_to_the_model(qapp):
    from pluggable_protocol_tree.consts import PROTOCOL_AUTOSAVE_STATUS_BAR_PRIORITY
    from pluggable_protocol_tree.views.autosave_status_icon import (
        AutosaveStatusIcon,
    )

    model = ProtocolAutosaveModel(enabled=False)
    view = AutosaveStatusIcon(model=model)
    icon = view.control

    assert icon.status_bar_icon_priority == PROTOCOL_AUTOSAVE_STATUS_BAR_PRIORITY
    assert not icon.is_active
    assert "enable" in icon.toolTip()

    model.enabled = True

    assert icon.is_active
    assert "save the protocol once" in icon.toolTip()
    assert "disable" in icon.toolTip()

    model.tracker.loaded_protocol_path = "C:/protocols/p.json"

    assert "save the protocol once" not in icon.toolTip()


def test_checkbox_and_glyph_follow_each_other_through_the_model(qapp):
    from pluggable_protocol_tree.views.autosave_checkbox import AutosaveCheckbox
    from pluggable_protocol_tree.views.autosave_status_icon import (
        AutosaveStatusIcon,
    )

    model = ProtocolAutosaveModel()
    view = AutosaveCheckbox(model=model)
    glyph_view = AutosaveStatusIcon(model=model)
    glyph = glyph_view.control
    checkbox = view.control

    assert checkbox.isChecked()
    assert checkbox.toolTip() == model.tooltip

    model.enabled = False

    assert not checkbox.isChecked()
    assert "enable" in checkbox.toolTip()

    checkbox.click()

    assert model.enabled
    assert glyph.is_active
    assert "disable" in checkbox.toolTip()

    glyph.toggled.emit(False)

    assert not model.enabled
    assert not checkbox.isChecked()
