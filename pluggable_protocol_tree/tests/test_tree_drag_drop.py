# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Qt drop path of moving protocol rows (#982): the tree model's
``mimeData``/``canDropMimeData``/``dropMimeData`` and the widget's handling
of the drop. Runs headless (``QT_QPA_PLATFORM=offscreen``); the move logic
itself is covered in test_move_rows.py."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QModelIndex, Qt
from pyface.qt.QtWidgets import QAbstractItemView

# Microdrop package imports.
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.protocol_history import ProtocolHistory
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


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


@pytest.fixture
def widget(qapp, manager):
    return ProtocolTreeWidget(manager)


def _index(widget, path):
    return widget._node_to_index(widget._manager.get_row(path))


def _drag(widget, paths):
    """The mime data a drag of the rows at ``paths`` carries."""
    indexes = [_index(widget, path) for path in paths]

    return widget.model.mimeData(indexes)


def test_steps_drag_and_only_groups_take_drops_onto_them(widget):
    step_flags = widget.model.flags(_index(widget, (0,)))
    group_flags = widget.model.flags(_index(widget, (2,)))

    assert step_flags & Qt.ItemIsDragEnabled
    assert not step_flags & Qt.ItemIsDropEnabled
    assert group_flags & Qt.ItemIsDropEnabled
    assert widget.model.flags(QModelIndex()) & Qt.ItemIsDropEnabled


def test_drop_between_rows_in_a_group_keeps_selection_and_expansion(widget, manager):
    history = ProtocolHistory(manager=manager)
    a = manager.get_row((0,))
    g1_index = _index(widget, (2,))
    g2_index = _index(widget, (3,))

    widget.tree.expand(g1_index)
    widget.tree.expand(g2_index)
    widget._select_paths([(0,), (1,)])

    data = _drag(widget, [(0,), (1,)])

    assert widget.model.canDropMimeData(data, Qt.MoveAction, 1, 0, g1_index)
    assert widget.model.dropMimeData(data, Qt.MoveAction, 1, 0, g1_index)

    widget.tree.rows_dropped.emit()

    assert [row.name for row in manager.get_row((0,)).children] == [
        "C",
        "A",
        "B",
        "D",
    ]
    assert manager.selection == [(0, 1), (0, 2)]
    assert widget.tree.currentIndex().internalPointer() is a
    assert widget.tree.isExpanded(_index(widget, (0,)))
    assert widget.tree.isExpanded(_index(widget, (1,)))
    assert history.undo_name == "Move Steps"
    assert len(history.undo_manager.active_stack._stack) == 1


def test_drop_onto_a_group_is_named_for_the_row(widget, manager):
    history = ProtocolHistory(manager=manager)
    data = _drag(widget, [(2,)])

    assert widget.model.dropMimeData(data, Qt.MoveAction, -1, 0, _index(widget, (3,)))

    assert manager.get_row((2, 1)).name == "G1"
    assert history.undo_name == "Move Group"


def test_group_cannot_be_dropped_into_itself(widget, manager):
    data = _drag(widget, [(2,)])
    g1_index = _index(widget, (2,))

    assert not widget.model.canDropMimeData(data, Qt.MoveAction, -1, 0, g1_index)
    assert not widget.model.dropMimeData(data, Qt.MoveAction, 0, 0, g1_index)
    assert manager.get_row((2,)).name == "G1"


def test_drag_and_drop_is_off_while_structure_is_locked(widget):
    widget.set_editable(True, structural=False)

    assert widget.tree.dragDropMode() == QAbstractItemView.NoDragDrop

    widget.set_editable(True)

    assert widget.tree.dragDropMode() == QAbstractItemView.InternalMove
