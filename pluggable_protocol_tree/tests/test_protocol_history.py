# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the protocol edit history (undo/redo, #967)."""

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import HasTraits, Instance, observe

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.protocol_history import ProtocolHistory
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)


@pytest.fixture
def manager():
    return RowManager(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
    )


class TrackerWiring(HasTraits):
    """Feeds the manager's edit events to the state tracker, as the dock
    pane does."""

    manager = Instance(RowManager)

    tracker = Instance(PluggableProtocolStateTracker, ())

    @observe("manager:rows_changed")
    def _on_rows_changed(self, event):
        self.tracker.on_structure_changed(self.manager)

    @observe("manager:cell_changed")
    def _on_cell_changed(self, event):
        self.tracker.on_cell_changed(
            event.new["path"], event.new["col_id"], self.manager
        )


@pytest.fixture
def wiring(manager):
    return TrackerWiring(manager=manager)


@pytest.fixture
def tracker(wiring):
    return wiring.tracker


@pytest.fixture
def history(manager, tracker):
    """A history that records every edit event at once (no event loop)."""
    return ProtocolHistory(manager=manager, protocol_state_tracker=tracker)


class ManualScheduler:
    """Stands in for GUI.invoke_later: queues flushes until ``run``."""

    def __init__(self):
        self.queued = []

    def __call__(self, callback):
        self.queued.append(callback)

    def run(self):
        queued, self.queued = self.queued, []

        for callback in queued:
            callback()


def _durations(manager):
    return [row.duration_s for row in manager.iter_all_rows()]


def _two_steps(manager, history):
    manager.add_step(values={"name": "A"})
    manager.add_step(values={"name": "B"})
    history.reset()


# --- recording, undo and redo ----------------------------------------------


def test_cell_edit_undo_redo(manager, history):
    _two_steps(manager, history)
    manager.set_value((0,), "duration_s", 2.5)

    assert history.undo_name == "Edit Duration (s)"

    history.undo()

    assert _durations(manager) == [1.0, 1.0]
    assert history.undo_name == ""
    assert history.redo_name == "Edit Duration (s)"

    history.redo()

    assert _durations(manager) == [2.5, 1.0]


def test_cell_undo_keeps_the_row_objects(manager, history):
    _two_steps(manager, history)
    rows = list(manager.iter_all_rows())
    manager.set_value((1,), "duration_s", 3.0)

    history.undo()

    assert list(manager.iter_all_rows()) == rows


def test_undo_delete_restores_the_row_with_its_values(manager, history):
    _two_steps(manager, history)
    manager.set_value((1,), "duration_s", 4.0)
    deleted_uuid = manager.get_row((1,)).uuid
    manager.remove([(1,)])

    assert history.undo_name == "Delete Step"

    history.undo()

    restored = manager.get_row((1,))

    assert restored.uuid == deleted_uuid
    assert restored.name == "B"
    assert restored.duration_s == 4.0

    history.redo()

    assert [row.name for row in manager.iter_all_rows()] == ["A"]


def test_undo_add_group_and_move(manager, history):
    _two_steps(manager, history)
    manager.add_group(name="G")

    assert history.undo_name == "Add Group"

    manager.move([(0,)], target_parent_path=(2,), target_index=0)

    assert history.undo_name == "Move Rows"

    history.undo()

    assert [row.name for row in manager.iter_all_rows()] == ["A", "B", "G"]

    history.undo()

    assert [row.name for row in manager.iter_all_rows()] == ["A", "B"]


def test_undo_fold_reuses_rows_and_names_the_action(manager, history):
    _two_steps(manager, history)
    rows = list(manager.iter_all_rows())

    with manager.named_edit("Fold into Group"):
        manager.fold_into_group([(0,), (1,)])

    assert history.undo_name == "Fold into Group"

    history.undo()

    assert list(manager.iter_all_rows()) == rows
    assert [row.path for row in rows] == [(0,), (1,)]


def test_rename_is_named(manager, history):
    _two_steps(manager, history)
    manager.set_value((0,), "name", "Wash")

    assert history.undo_name == "Rename Step"


def test_new_edit_clears_redo(manager, history):
    _two_steps(manager, history)
    manager.set_value((0,), "duration_s", 2.0)
    history.undo()
    manager.set_value((1,), "duration_s", 5.0)

    assert history.redo_name == ""


# --- compound actions --------------------------------------------------------


def test_bulk_set_is_one_entry(manager, history):
    _two_steps(manager, history)
    manager.add_step(values={"name": "C"})
    history.reset()

    with manager.named_edit("Bulk Set"):
        manager.set_values([(0,), (1,), (2,)], "duration_s", 7.0)

    assert history.undo_name == "Bulk Set"

    history.undo()

    assert _durations(manager) == [1.0, 1.0, 1.0]
    assert history.undo_name == ""


def test_paste_of_many_rows_is_one_entry(manager, history):
    _two_steps(manager, history)
    manager.select([(0,), (1,)])
    payload = manager._serialize_selection()

    with manager.named_edit("Paste"):
        manager._paste_from_payload(payload, target_path=(1,))

    assert len(list(manager.iter_all_rows())) == 4
    assert history.undo_name == "Paste"

    history.undo()

    assert [row.name for row in manager.iter_all_rows()] == ["A", "B"]


def test_deferred_flush_settles_one_action_into_one_entry(manager, tracker):
    scheduler = ManualScheduler()
    history = ProtocolHistory(
        manager=manager, protocol_state_tracker=tracker, schedule_flush=scheduler
    )
    _two_steps(manager, history)

    manager.set_value((0,), "duration_s", 2.0)
    manager.set_value((1,), "duration_s", 3.0)
    scheduler.run()

    assert history.undo_name == "Edit Duration (s)"

    history.undo()

    assert _durations(manager) == [1.0, 1.0]
    assert history.undo_name == ""


def test_named_edit_survives_a_flush_from_a_nested_event_loop(manager, tracker):
    scheduler = ManualScheduler()
    history = ProtocolHistory(
        manager=manager, protocol_state_tracker=tracker, schedule_flush=scheduler
    )
    _two_steps(manager, history)

    with manager.named_edit("Bulk Set"):
        manager.set_value((0,), "duration_s", 2.0)
        # A modal prompt mid-action runs the event loop.
        scheduler.run()
        manager.set_value((1,), "duration_s", 3.0)

    scheduler.run()
    history.undo()

    assert _durations(manager) == [1.0, 1.0]
    assert history.undo_name == ""


def test_named_edit_that_changes_nothing_records_nothing(manager, history):
    _two_steps(manager, history)

    with manager.named_edit("Paste"):
        pass

    manager.set_value((0,), "duration_s", 2.0)

    assert history.undo_name == "Edit Duration (s)"


# --- bounds, runs, resets ----------------------------------------------------


def test_history_is_bounded(manager, tracker):
    history = ProtocolHistory(
        manager=manager, protocol_state_tracker=tracker, max_entries=3
    )
    _two_steps(manager, history)

    for duration in (2.0, 3.0, 4.0, 5.0, 6.0):
        manager.set_value((0,), "duration_s", duration)

    undone = 0

    while history.undo_name:
        history.undo()
        undone += 1

    assert undone == 3
    assert _durations(manager) == [3.0, 1.0]


def test_nothing_is_recorded_or_undone_during_a_run(manager, tracker, history):
    _two_steps(manager, history)
    manager.set_value((0,), "duration_s", 2.0)

    tracker.is_active = True
    manager.set_value((1,), "duration_s", 9.0)
    history.undo()

    assert _durations(manager) == [2.0, 9.0]
    assert history.undo_name == "Edit Duration (s)"

    tracker.is_active = False
    history.undo()

    # The run's own write survives the undo of the edit before it.
    assert _durations(manager) == [1.0, 9.0]


def test_reset_forgets_the_history(manager, history):
    _two_steps(manager, history)
    manager.set_value((0,), "duration_s", 2.0)

    history.reset()

    assert history.undo_name == ""
    assert history.redo_name == ""


# --- interplay ---------------------------------------------------------------


def test_dirty_flag_follows_undo_and_redo(manager, tracker, history):
    _two_steps(manager, history)
    tracker.reseed_baseline(manager)

    manager.remove([(1,)])

    assert tracker.is_modified

    history.undo()

    assert not tracker.is_modified

    manager.set_value((0,), "duration_s", 2.0)

    assert tracker.is_modified

    history.undo()

    assert not tracker.is_modified

    history.redo()

    assert tracker.is_modified


def test_undo_resolves_containers_live(manager, history):
    """#755: reassigning a container after the edit must not detach undo."""
    _two_steps(manager, history)
    manager.remove([(0,)])
    manager.root.children = list(manager.root.children)

    history.undo()

    assert [row.name for row in manager.iter_all_rows()] == ["A", "B"]


def test_pane_binds_each_history_shortcut_once(qapp):
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column(), make_name_column()])
    keys = [
        shortcut.key().toString()
        for shortcut in pane.findChildren(type(pane._history_shortcuts[0]))
    ]

    for key in ("Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z"):
        assert keys.count(key) == 1


def test_pane_undo_is_ignored_while_a_cell_is_being_edited(qapp):
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column(), make_name_column()])
    pane.protocol_history.schedule_flush = None
    pane.manager.add_step()
    pane.show()
    qapp.processEvents()

    tree = pane.widget.tree
    tree.edit(pane.widget.model.index(0, 1))

    assert pane._is_editing_cell()

    pane.undo()

    assert len(list(pane.manager.iter_all_rows())) == 1

    tree.closePersistentEditor(tree.currentIndex())
    tree.setFocus()
    qapp.processEvents()
    pane.close()
