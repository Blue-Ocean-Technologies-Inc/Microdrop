"""Qt widget: QTreeView over a RowManager, with context menu for add /
remove / copy / cut / paste / group."""

import logging
from enum import Enum

from pyface.qt.QtCore import Qt, QPersistentModelIndex, Signal
from pyface.qt.QtGui import QKeySequence, QShortcut
from pyface.qt.QtWidgets import QWidget, QVBoxLayout, QTreeView, QMenu, QAbstractItemView

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.delegate import ProtocolItemDelegate
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


logger = logging.getLogger(__name__)


class _ProtocolTreeView(QTreeView):
    """QTreeView subclass that emits a Qt signal on Delete keypress.

    Using a keyPressEvent override (rather than QShortcut) is the most
    reliable path: the event is captured directly on the focused widget,
    no overload-resolution surprises, no shortcut-context confusion, and
    we explicitly accept() the event so Qt's default key handling
    doesn't get a second chance to interpret it.
    """

    delete_pressed = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ProtocolTreeWidget(QWidget):
    def __init__(self, row_manager: RowManager, parent=None):
        super().__init__(parent)
        self._manager = row_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = _ProtocolTreeView()
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked
                                  | QAbstractItemView.EditKeyPressed)
        self.tree.delete_pressed.connect(self._delete_selection)
        layout.addWidget(self.tree)

        self.model = MvcTreeModel(row_manager, parent=self.tree)
        self.tree.setModel(self.model)

        self.delegate = ProtocolItemDelegate(row_manager, parent=self.tree)
        self.tree.setItemDelegate(self.delegate)

        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        # Copy / Cut / Paste keyboard shortcuts. Bind via
        # .activated.connect() rather than the (seq, parent, callable)
        # constructor — the latter can fail to wire silently in PySide6.
        # WidgetWithChildrenShortcut so they only fire when the tree
        # has focus. Delete is handled by _ProtocolTreeView.keyPressEvent
        # rather than a QShortcut for maximum reliability.
        self._shortcuts = []     # keep refs alive (Qt doesn't, in PySide6)
        for seq, slot in (
            (QKeySequence.Copy,  self._copy),
            (QKeySequence.Cut,   self._cut),
            (QKeySequence.Paste, self._paste),
        ):
            sc = QShortcut(seq, self.tree)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

        # Mirror Qt selection → RowManager selection
        self.tree.selectionModel().selectionChanged.connect(self._sync_selection)

    # --- active-row highlight + scroll (called by the executor wiring) ---

    def highlight_active_row(self, node):
        """Mark `node` as the currently-active step and scroll to it.

        Pass `None` to clear the highlight (typical at protocol end).
        """
        self.model.set_active_node(node)
        if node is None:
            return
        idx = self._node_to_index(node)
        if idx.isValid():
            self.tree.scrollTo(idx, QTreeView.PositionAtCenter)
            # Expand any collapsed ancestor groups so the row is visible.
            parent = idx.parent()
            while parent.isValid():
                self.tree.expand(parent)
                parent = parent.parent()

    def _node_to_index(self, node):
        """Walk the row's path to a QModelIndex on the first column."""
        path = node.path
        idx = self.model.index(path[0], 0) if path else self.model.index(-1, -1)
        for r in path[1:]:
            if not idx.isValid():
                return idx
            idx = self.model.index(r, 0, idx)
        return idx

    # --- selection sync ---

    def _sync_selection(self, *_):
        paths = []
        for idx in self.tree.selectionModel().selectedRows(0):
            paths.append(self._index_to_path(idx))
        self._manager.select(paths, mode="set")

    def _index_to_path(self, index):
        if not index.isValid():
            return ()
        parts = []
        cur = index
        while cur.isValid():
            parts.insert(0, cur.row())
            cur = cur.parent()
        return tuple(parts)

    # --- context menu actions ---

    def _on_context_menu(self, pos):
        idx = self.tree.indexAt(pos)
        menu = QMenu()
        menu.addAction("Add Step", lambda: self._add_step_at(idx))
        menu.addAction("Add Group", lambda: self._add_group_at(idx))
        menu.addSeparator()
        menu.addAction("Copy", self._copy)
        menu.addAction("Cut", self._cut)
        menu.addAction("Paste", self._paste)
        menu.addSeparator()
        menu.addAction("Delete", self._delete_selection)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _add_step_at(self, idx):
        parent_path = self._parent_path_for_anchor(idx)
        self._manager.add_step(parent_path=parent_path)

    def _add_group_at(self, idx):
        parent_path = self._parent_path_for_anchor(idx)
        self._manager.add_group(parent_path=parent_path)

    def _parent_path_for_anchor(self, idx):
        """If anchored on a group → insert inside. On a step → insert as
        sibling. No anchor → root."""
        if not idx.isValid():
            return ()
        from pluggable_protocol_tree.models.row import GroupRow
        node = idx.internalPointer()
        if isinstance(node, GroupRow):
            return self._index_to_path(idx)
        # sibling: parent path
        path = self._index_to_path(idx)
        return path[:-1]

    def _copy(self):
        try:
            self._manager.copy()
        except Exception:
            logger.exception("Copy failed")

    def _cut(self):
        try:
            self._manager.cut()
        except Exception:
            logger.exception("Cut failed")

    def _paste(self):
        try:
            idxs = self.tree.selectionModel().selectedRows(0)
            target = self._index_to_path(idxs[-1]) if idxs else None
            self._manager.paste(target_path=target)
        except Exception:
            logger.exception("Paste failed")

    def _delete_selection(self):
        """Remove the currently-selected rows. Defensive: stale paths
        (rows already removed by a previous action) are silently
        skipped rather than propagating IndexError, which under
        PySide6 6.x terminates the QApplication."""
        try:
            paths = [tuple(p) for p in self._manager.selection]
            valid = []
            for p in paths:
                try:
                    self._manager.get_row(p)
                except (IndexError, KeyError):
                    continue
                valid.append(p)
            if valid:
                self._manager.remove(valid)
        except Exception:
            logger.exception("Delete failed")
