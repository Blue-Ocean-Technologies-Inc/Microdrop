"""QAbstractItemModel adapter binding RowManager to a QTreeView.

Reads column definitions from the RowManager's column list; delegates
display/edit to each column's view and handler. Signal emissions are
coarse (layoutChanged on structural mutations) in PPT-1; finer-grained
rowsInserted/dataChanged can be added when performance matters.
"""

from pyface.qt.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal
from pyface.qt.QtGui import QBrush, QColor

from pluggable_protocol_tree.models.row import GroupRow


class MvcTreeModel(QAbstractItemModel):
    """Qt tree model over a RowManager.

    An 'active' row (set via set_active_node) gets a blue background
    with white foreground — used by the executor to highlight the
    currently-running step (matching the legacy protocol_grid look).
    In a non-running protocol this stays None.
    """

    structure_changed = Signal()   # high-level "redraw" nudge

    _ACTIVE_BG = QBrush(QColor(0, 90, 200))   # solid blue
    _ACTIVE_FG = QBrush(QColor(255, 255, 255))

    def __init__(self, row_manager, parent=None):
        super().__init__(parent)
        self._manager = row_manager
        self._active_node = None

        # Rebroadcast manager changes as layoutChanged
        row_manager.observe(self._on_rows_changed, "rows_changed")

    # ------------ Qt structural API ------------

    def rowCount(self, parent=QModelIndex()):
        node = parent.internalPointer() if parent.isValid() else self._manager.root
        return len(node.children) if isinstance(node, GroupRow) else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self._manager.columns)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = parent.internalPointer() if parent.isValid() else self._manager.root
        if row >= len(node.children):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        parent_node = node.parent
        if parent_node is None or parent_node is self._manager.root:
            return QModelIndex()
        grandparent = parent_node.parent
        row_in_grandparent = (grandparent.children.index(parent_node)
                              if grandparent is not None else 0)
        return self.createIndex(row_in_grandparent, 0, parent_node)

    # ------------ data / flags / header ------------

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        col = self._manager.columns[index.column()]

        if node is self._active_node:
            if role == Qt.BackgroundRole:
                return self._ACTIVE_BG
            if role == Qt.ForegroundRole:
                return self._ACTIVE_FG

        value = col.model.get_value(node)

        if role == Qt.DisplayRole:
            return col.view.format_display(value, node)
        if role == Qt.CheckStateRole:
            return col.view.get_check_state(value, node)
        if role == Qt.UserRole:
            return node
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        col = self._manager.columns[index.column()]
        node = index.internalPointer()
        if role in (Qt.EditRole, Qt.CheckStateRole):
            if role == Qt.CheckStateRole:
                value = value == Qt.Checked or value == 2 or value is True
            if col.handler.on_interact(node, col.model, value):
                self.dataChanged.emit(index, index, [role])
                return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        col = self._manager.columns[index.column()]
        return col.view.get_flags(index.internalPointer())

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._manager.columns[section].model.col_name
        return None

    # ------------ helpers ------------

    def set_active_node(self, node):
        self._active_node = node
        self.layoutChanged.emit()

    def _on_rows_changed(self, event):
        self.layoutChanged.emit()
        self.structure_changed.emit()
