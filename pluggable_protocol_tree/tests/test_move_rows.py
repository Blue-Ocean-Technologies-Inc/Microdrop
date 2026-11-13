# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for ``RowManager.move_rows``, the drag-and-drop move (#982)."""

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import HasTraits, Instance, Int, observe

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.protocol_history import ProtocolHistory


@pytest.fixture
def manager():
    """A, B, G1[C, D], G2[E], F at the top level."""
    manager = RowManager(
        columns=[
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
    )

    manager.add_step(values={"name": "A"})
    manager.add_step(values={"name": "B"})
    g1 = manager.add_group(name="G1")
    manager.add_step(parent_path=g1, values={"name": "C"})
    manager.add_step(parent_path=g1, values={"name": "D"})
    g2 = manager.add_group(name="G2")
    manager.add_step(parent_path=g2, values={"name": "E"})
    manager.add_step(values={"name": "F"})

    return manager


def _shape(group):
    """Names in tree order, a group as ``(name, [children])``."""
    return [
        (row.name, _shape(row)) if isinstance(row, GroupRow) else row.name
        for row in group.children
    ]


class RowsChangedCounter(HasTraits):
    """Counts the manager's structural-change events."""

    manager = Instance(RowManager)

    count = Int(0)

    @observe("manager:rows_changed")
    def _on_rows_changed(self, event):
        self.count += 1


@pytest.fixture
def counter(manager):
    return RowsChangedCounter(manager=manager)


# --- moves ---


def test_drop_onto_group_appends_as_last_child(manager):
    new_paths = manager.move_rows([(0,)], (2,), None)

    assert _shape(manager.root) == [
        "B",
        ("G1", ["C", "D", "A"]),
        ("G2", ["E"]),
        "F",
    ]
    assert new_paths == [(1, 2)]
    assert manager.get_row((1, 2)).dotted_path() == "2.3"


def test_drop_between_rows_inside_a_group(manager):
    manager.move_rows([(4,)], (2,), 1)

    assert _shape(manager.root) == [
        "A",
        "B",
        ("G1", ["C", "F", "D"]),
        ("G2", ["E"]),
    ]


def test_move_out_of_group_to_top_level(manager):
    new_paths = manager.move_rows([(2, 0)], (), 0)

    assert _shape(manager.root) == [
        "C",
        "A",
        "B",
        ("G1", ["D"]),
        ("G2", ["E"]),
        "F",
    ]
    assert new_paths == [(0,)]


def test_move_between_groups(manager):
    manager.move_rows([(2, 1)], (3,), 0)

    assert _shape(manager.root) == [
        "A",
        "B",
        ("G1", ["C"]),
        ("G2", ["D", "E"]),
        "F",
    ]


def test_reorder_within_a_level_counts_index_before_the_move(manager):
    # Index 3 is "before G2" in the tree as it is now.
    new_paths = manager.move_rows([(0,)], (), 3)

    assert _shape(manager.root) == [
        "B",
        ("G1", ["C", "D"]),
        "A",
        ("G2", ["E"]),
        "F",
    ]
    assert new_paths == [(2,)]


def test_reorder_upwards(manager):
    manager.move_rows([(4,)], (), 1)

    assert _shape(manager.root) == [
        "A",
        "F",
        "B",
        ("G1", ["C", "D"]),
        ("G2", ["E"]),
    ]


def test_out_of_range_index_appends(manager):
    manager.move_rows([(0,)], (), 99)

    assert [row.name for row in manager.root.children][-1] == "A"


def test_multi_selection_moves_as_one_block_in_tree_order(manager):
    # Paths given out of order and from different levels.
    new_paths = manager.move_rows([(4,), (2, 1), (0,)], (3,), None)

    assert _shape(manager.root) == [
        "B",
        ("G1", ["C"]),
        ("G2", ["E", "A", "D", "F"]),
    ]
    assert new_paths == [(2, 1), (2, 2), (2, 3)]


def test_group_selected_with_its_own_child_moves_once(manager):
    g1 = manager.get_row((2,))

    new_paths = manager.move_rows([(2,), (2, 0)], (), 0)

    assert _shape(manager.root) == [
        ("G1", ["C", "D"]),
        "A",
        "B",
        ("G2", ["E"]),
        "F",
    ]
    assert new_paths == [(0,)]
    assert manager.root.children[0] is g1


# --- refused moves ---


def test_group_into_itself_is_refused(manager, counter):

    assert manager.move_rows([(2,)], (2,), None) is None
    assert not manager.can_move_rows([(2,)], (2,), 0)
    assert counter.count == 0


def test_group_into_its_descendant_is_refused(manager):
    manager.add_group(parent_path=(2,), name="H")
    before = _shape(manager.root)
    counter = RowsChangedCounter(manager=manager)

    assert manager.move_rows([(2,)], (2, 2), None) is None
    assert manager.move_rows([(0,), (2,)], (2, 2), 0) is None
    assert _shape(manager.root) == before
    assert counter.count == 0


def test_drop_into_a_step_is_refused(manager):
    assert manager.move_rows([(0,)], (1,), None) is None


@pytest.mark.parametrize(
    "paths, parent_path, index",
    [
        ([(0,)], (), 0),
        ([(0,)], (), 1),
        ([(0,), (1,)], (), 2),
        ([(2, 1)], (2,), None),
        ([(4,)], (), None),
    ],
)
def test_drop_onto_own_position_is_a_no_op(manager, counter, paths, parent_path, index):
    before = _shape(manager.root)

    assert manager.move_rows(paths, parent_path, index) is None
    assert _shape(manager.root) == before
    assert counter.count == 0


def test_stale_paths_are_ignored(manager):
    assert manager.move_rows([(42,)], (), 0) is None


# --- identity and data ---


def test_moved_rows_keep_their_objects_uuids_and_values(manager):
    c = manager.get_row((2, 0))
    c.duration_s = 7.5
    g1 = manager.get_row((2,))
    uuids = {row.uuid for row in manager.iter_all_rows()}

    manager.move_rows([(2,)], (3,), None)

    assert manager.get_row((2, 1)) is g1
    assert manager.get_row((2, 1, 0)) is c
    assert c.duration_s == 7.5
    assert {row.uuid for row in manager.iter_all_rows()} == uuids


def test_one_move_fires_one_structural_change(manager, counter):

    manager.move_rows([(0,), (1,)], (3,), None)

    assert counter.count == 1


# --- history ---


def test_named_move_is_one_history_entry_and_undo_redo_restore_it(manager):
    history = ProtocolHistory(manager=manager)
    before = _shape(manager.root)
    a = manager.get_row((0,))

    with manager.named_edit("Move Steps"):
        manager.move_rows([(0,), (1,)], (2,), None)

    after = _shape(manager.root)

    assert history.undo_name == "Move Steps"
    assert len(history.undo_manager.active_stack._stack) == 1

    history.undo()

    assert _shape(manager.root) == before
    assert manager.get_row((0,)) is a

    history.redo()

    assert _shape(manager.root) == after
    assert manager.get_row((0, 2)) is a
