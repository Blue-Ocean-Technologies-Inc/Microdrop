# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Touch Select mode on the protocol tree: taps toggle rows, never edit,
and a context menu on a selected row keeps the whole selection."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import Qt
from pyface.qt.QtTest import QTest
from pyface.qt.QtWidgets import QAbstractItemView

# Microdrop package imports.
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


@pytest.fixture
def widget(qapp):
    manager = RowManager(
        columns=[make_type_column(), make_id_column(), make_name_column()]
    )

    for name in "ABCD":
        manager.add_step(values={"name": name})

    widget = ProtocolTreeWidget(manager)
    widget.resize(400, 300)
    widget.show()
    qapp.processEvents()

    yield widget

    widget.close()


def tap(widget, row, release=True):
    tree = widget.tree
    point = tree.visualRect(tree.model().index(row, 2)).center()
    QTest.mousePress(tree.viewport(), Qt.LeftButton, Qt.NoModifier, point)

    if release:
        QTest.mouseRelease(tree.viewport(), Qt.LeftButton, Qt.NoModifier, point)


def selected_rows(widget):
    return sorted(index.row() for index in widget.tree.selectionModel().selectedRows())


def test_select_mode_taps_toggle_rows_and_never_edit(widget):
    widget.set_multi_select(True)

    for row in (0, 2, 3, 2):
        tap(widget, row)

    assert selected_rows(widget) == [0, 3]
    assert widget.tree.editTriggers() == QAbstractItemView.NoEditTriggers

    widget.set_multi_select(False)

    assert selected_rows(widget) == [0, 3]
    assert widget.tree.selectionMode() == QAbstractItemView.ExtendedSelection
    assert widget.tree.editTriggers() != QAbstractItemView.NoEditTriggers


def test_select_mode_respects_the_run_lock(widget):
    widget.set_editable(False)
    widget.set_multi_select(True)
    widget.set_multi_select(False)

    assert widget.tree.editTriggers() == QAbstractItemView.NoEditTriggers
    assert not widget.can_show_row_menu()


@pytest.mark.parametrize("multi_select", [True, False])
def test_menu_on_a_selected_row_keeps_the_selection(widget, multi_select):
    widget.set_multi_select(True)
    tap(widget, 0)
    tap(widget, 2)
    widget.set_multi_select(multi_select)

    # A long-press: the press lands, the menu opens on it, and the release
    # reaches the tree afterwards.
    tap(widget, 2, release=False)
    widget.tree.forget_pending_press()
    point = widget.tree.visualRect(widget.tree.model().index(2, 2)).center()
    QTest.mouseRelease(widget.tree.viewport(), Qt.LeftButton, Qt.NoModifier, point)

    assert selected_rows(widget) == [0, 2]
