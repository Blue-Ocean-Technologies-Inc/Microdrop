"""Qt widget: QTreeView over a RowManager, with context menu for add /
remove / copy / cut / paste / group."""

from enum import Enum

from pyface.qt.QtCore import Qt, QPersistentModelIndex
from pyface.qt.QtWidgets import QWidget, QVBoxLayout, QTreeView, QMenu, QAbstractItemView

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.delegate import ProtocolItemDelegate
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


class ProtocolTreeWidget(QWidget):
    def __init__(self, row_manager: RowManager, parent=None):
        super().__init__(parent)
        self._manager = row_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeView()
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked
                                  | QAbstractItemView.EditKeyPressed)
        layout.addWidget(self.tree)

        self.model = MvcTreeModel(row_manager, parent=self.tree)
        self.tree.setModel(self.model)

        self.delegate = ProtocolItemDelegate(row_manager, parent=self.tree)
        self.tree.setItemDelegate(self.delegate)

        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        # Keyboard shortcuts for copy/cut/paste
        from pyface.qt.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence.Copy, self, self._copy)
        QShortcut(QKeySequence.Cut, self, self._cut)
        QShortcut(QKeySequence.Paste, self, self._paste)
        QShortcut(QKeySequence.Delete, self, self._delete_selection)

        # Mirror Qt selection → RowManager selection
        self.tree.selectionModel().selectionChanged.connect(self._sync_selection)

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
        self._manager.copy()

    def _cut(self):
        self._manager.cut()

    def _paste(self):
        # Use current anchor as target
        idxs = self.tree.selectionModel().selectedRows(0)
        target = self._index_to_path(idxs[-1]) if idxs else None
        self._manager.paste(target_path=target)

    def _delete_selection(self):
        self._manager.remove(list(self._manager.selection))
