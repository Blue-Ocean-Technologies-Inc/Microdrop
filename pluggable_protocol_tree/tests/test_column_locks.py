"""MvcTreeModel enforcement of per-row column locks (issue #541).

Locks live on the row (see test_row.py for storage semantics); this
module covers the central enforcement: flags() clearing, tooltip,
grey read-only fill, and the auto-wired repaint."""

from pyface.qt.QtCore import Qt
from traits.api import Bool

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


class _BoolColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(False)


def _make_checkbox_column():
    return Column(
        model=_BoolColumnModel(col_id="capture", col_name="Capture",
                               default_value=False),
        view=CheckboxColumnView(),
    )


def _build():
    manager = RowManager(columns=[
        make_type_column(), make_name_column(), _make_checkbox_column(),
    ])
    manager.add_step()
    qm = MvcTreeModel(manager)
    ids = [c.model.col_id for c in manager.columns]
    return manager, qm, ids


def _cell(qm, row_idx, col_idx):
    from pyface.qt.QtCore import QModelIndex
    return qm.index(row_idx, col_idx, QModelIndex())


def test_locked_editable_cell_loses_editable_flag():
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("name"))
    assert qm.flags(idx) & Qt.ItemIsEditable
    row.lock_column("name", owner="test", reason="because")
    assert not (qm.flags(idx) & Qt.ItemIsEditable)


def test_locked_checkbox_cell_loses_user_checkable_flag():
    """Checkboxes are never ItemIsEditable — clearing only that flag
    would do nothing at all. Both flags must go."""
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("capture"))
    assert qm.flags(idx) & Qt.ItemIsUserCheckable
    row.lock_column("capture", owner="fluorescence", reason="chain owns step")
    flags = qm.flags(idx)
    assert not (flags & Qt.ItemIsUserCheckable)
    assert not (flags & Qt.ItemIsEditable)
    assert flags & Qt.ItemIsEnabled    # still selectable/enabled, just inert


def test_unlocking_last_owner_restores_flags():
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("capture"))
    row.lock_column("capture", owner="a")
    row.lock_column("capture", owner="b")
    row.unlock_column("capture", owner="a")
    assert not (qm.flags(idx) & Qt.ItemIsUserCheckable)   # b still holds
    row.unlock_column("capture", owner="b")
    assert qm.flags(idx) & Qt.ItemIsUserCheckable


def test_lock_reason_is_cell_tooltip():
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("capture"))
    assert qm.data(idx, Qt.ToolTipRole) is None
    row.lock_column("capture", owner="fluorescence",
                    reason="Captured by fluorescence chain")
    assert qm.data(idx, Qt.ToolTipRole) == "Captured by fluorescence chain"


def test_locked_cell_gets_read_only_background():
    """The grey fill tests for the absence of BOTH flags — it must read
    lock-aware flags, not the view's raw get_flags."""
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("name"))
    assert qm.data(idx, Qt.BackgroundRole) is None
    row.lock_column("name", owner="test")
    assert qm.data(idx, Qt.BackgroundRole) is not None


def test_lock_change_emits_datachanged_for_the_row():
    """Repaint is auto-wired: no gated column declares anything."""
    manager, qm, ids = _build()
    row = manager.root.children[0]
    received = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append(
            (top.row(), top.column(), bottom.column())),
    )
    row.lock_column("capture", owner="fluorescence")
    assert (0, 0, len(ids) - 1) in received
    received.clear()
    row.unlock_column("capture", owner="fluorescence")
    assert (0, 0, len(ids) - 1) in received


def test_lock_repaint_wired_for_rows_added_after_model_creation():
    manager, qm, ids = _build()
    manager.add_step()
    received = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top.row(), top.column())),
    )
    manager.root.children[1].lock_column("capture", owner="fluorescence")
    assert (1, 0) in received
