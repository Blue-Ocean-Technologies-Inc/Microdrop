"""QAbstractItemModel adapter binding RowManager to a QTreeView.

Reads column definitions from the RowManager's column list; delegates
display/edit to each column's view and handler. Signal emissions are
coarse (layoutChanged on structural mutations) in PPT-1; finer-grained
rowsInserted/dataChanged can be added when performance matters.
"""

from functools import partial

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
        # Strong refs to every row this model has handed to Qt via
        # createIndex(). Qt stores the third arg as a raw void*; if
        # Python GCs the row before Qt drops the QModelIndex, the
        # next access (selection sync, parent walk, etc.) dereferences
        # freed memory and segfaults the QApplication. Keeping refs
        # here costs O(rows-ever-shown) memory but is bulletproof.
        self._owned_rows = set()

        # Per-row trait observers wired by _wire_row_observers; tracked
        # by row id() so we can deregister on rebuild without holding
        # a hard ref to detached rows.
        self._row_observer_handles: dict = {}
        # Cache-event observers wired in __init__; kept so callers (or
        # tests) can deterministically tear down the model.
        self._event_observer_handles: list = []

        # Rebroadcast manager changes as layoutChanged
        row_manager.observe(self._on_rows_changed, "rows_changed")

        self._wire_event_observers()
        self._wire_row_observers()

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
        child = node.children[row]
        # Pin the row so Qt's createIndex pointer stays valid even
        # after the user removes the row from the manager (Qt's stale
        # QModelIndex would otherwise dereference freed memory).
        self._owned_rows.add(child)
        return self.createIndex(row, column, child)

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
        # Row set may have changed structurally (add/remove/move); rewire
        # per-row observers so newcomers participate and detached rows
        # stop emitting against a stale column index.
        self._wire_row_observers()

    # ------------ reactive wiring for derived columns ------------

    def _iter_all_rows(self):
        def walk(group):
            for child in group.children:
                yield child
                if isinstance(child, GroupRow):
                    yield from walk(child)
        yield from walk(self._manager.root)

    def _wire_event_observers(self):
        for col_idx, col in enumerate(self._manager.columns):
            view = col.view
            source = getattr(view, "depends_on_event_source", None)
            trait_name = getattr(view, "depends_on_event_trait_name", None)
            if source is None or not trait_name:
                continue
            handler = partial(self._on_event_dependency_fired, col_idx)
            source.observe(handler, trait_name)
            self._event_observer_handles.append((source, trait_name, handler))

    def _on_event_dependency_fired(self, col_idx, event):
        self._emit_column_changed(col_idx)

    def _emit_column_changed(self, col_idx):
        # Coarse but correct: layoutChanged forces Qt to repaint the
        # entire visible area, which covers nested rows for free.
        # cache_changed is low-frequency (calibration updates), so the
        # perf cost is negligible compared to walking every (parent,
        # child) pair to emit per-cell dataChanged.
        if col_idx < 0 or col_idx >= self.columnCount():
            return
        self.layoutChanged.emit()

    def _wire_row_observers(self):
        # Identify per-column row-trait dependencies once.
        col_trait_pairs: list = []
        for col_idx, col in enumerate(self._manager.columns):
            traits = list(getattr(col.view, "depends_on_row_traits", []) or [])
            for trait_name in traits:
                col_trait_pairs.append((col_idx, trait_name))
        if not col_trait_pairs:
            self._row_observer_handles.clear()
            return

        live_rows = list(self._iter_all_rows())
        live_ids = {id(r) for r in live_rows}

        # Tear down handles for rows that are no longer in the tree.
        for row_id in list(self._row_observer_handles.keys()):
            if row_id in live_ids:
                continue
            row, handles = self._row_observer_handles.pop(row_id)
            for trait_name, handler in handles:
                try:
                    row.observe(handler, trait_name, remove=True)
                except Exception:
                    pass

        # Wire newcomers; skip rows already wired (Traits' observe is
        # idempotent on identical (handler, trait) but only if the
        # callable identity matches — partial() makes a new object each
        # call, so we MUST guard ourselves).
        for row in live_rows:
            if id(row) in self._row_observer_handles:
                continue
            handles: list = []
            for col_idx, trait_name in col_trait_pairs:
                if trait_name not in row.trait_names():
                    continue
                handler = partial(self._on_row_trait_changed, row, col_idx)
                row.observe(handler, trait_name)
                handles.append((trait_name, handler))
            if handles:
                self._row_observer_handles[id(row)] = (row, handles)

    def _on_row_trait_changed(self, row, col_idx, event):
        idx = self._index_for_cell(row, col_idx)
        if idx.isValid():
            self.dataChanged.emit(idx, idx)

    def _index_for_cell(self, row, col_idx) -> QModelIndex:
        parent = row.parent
        if parent is None:
            return QModelIndex()
        try:
            row_in_parent = parent.children.index(row)
        except ValueError:
            return QModelIndex()
        if parent is self._manager.root:
            return self.index(row_in_parent, col_idx, QModelIndex())
        qparent = self._index_for_cell(parent, 0)
        return self.index(row_in_parent, col_idx, qparent)
