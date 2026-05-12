"""Smoke tests for the Qt tree model adapter.

Qt model tests don't need a QApplication for structural queries
(rowCount, columnCount, data for DisplayRole). Editor interactions
are exercised in the widget-level smoke test (Task 22)."""

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column


@pytest.fixture
def manager():
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]
    m = RowManager(columns=cols)
    return m


def test_column_count(manager):
    qm = MvcTreeModel(manager)
    assert qm.columnCount() == 4


def test_row_count_empty(manager):
    qm = MvcTreeModel(manager)
    assert qm.rowCount() == 0


def test_row_count_after_add(manager):
    manager.add_step()
    manager.add_step()
    qm = MvcTreeModel(manager)
    assert qm.rowCount() == 2


def test_display_role_renders_name_column(manager):
    from pyface.qt.QtCore import Qt
    manager.add_step(values={"name": "Hello"})
    qm = MvcTreeModel(manager)
    # Find the 'name' column index
    name_idx = [c.model.col_id for c in manager.columns].index("name")
    idx = qm.index(0, name_idx)
    assert qm.data(idx, Qt.DisplayRole) == "Hello"


def test_header_data(manager):
    from pyface.qt.QtCore import Qt
    qm = MvcTreeModel(manager)
    for col_idx, col in enumerate(manager.columns):
        assert qm.headerData(col_idx, Qt.Horizontal, Qt.DisplayRole) == col.model.col_name


def test_widget_exposes_public_index_to_path(qapp):
    """Public alias for the previously-private _index_to_path. PPT-10.2
    needs this for the device-viewer sync controller to resolve tree
    selection events without reaching into a private API."""
    from pluggable_protocol_tree.builtins.electrodes_column import (
        make_electrodes_column,
    )
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

    manager = RowManager(columns=[make_name_column(), make_electrodes_column()])
    manager.add_step(values={"name": "Step A"})
    widget = ProtocolTreeWidget(manager)
    idx = widget.tree.model().index(0, 0)
    assert widget.index_to_path(idx) == widget._index_to_path(idx) == (0,)
