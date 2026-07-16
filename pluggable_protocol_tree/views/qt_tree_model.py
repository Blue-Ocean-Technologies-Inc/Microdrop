"""QAbstractItemModel adapter binding RowManager to a QTreeView.

Reads column definitions from the RowManager's column list; delegates
display/edit to each column's view and handler. Signal emissions are
coarse (layoutChanged on structural mutations) in PPT-1; finer-grained
rowsInserted/dataChanged can be added when performance matters.
"""

from functools import partial

from pyface.qt.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal
from pyface.qt.QtGui import QBrush, QColor

from microdrop_style.helpers import is_dark_mode
from pluggable_protocol_tree.models.row import GroupRow


class MvcTreeModel(QAbstractItemModel):
    """Qt tree model over a RowManager.

    An 'active' row (set via set_active_node) gets a blue background
    with white foreground — used by the executor to highlight the
    currently-running step (matching the legacy protocol_grid look).
    In a non-running protocol this stays None.
    """

    structure_changed = Signal()  # high-level "redraw" nudge
    column_changed = Signal()

    _ACTIVE_BG = QBrush(QColor(0, 90, 200))  # solid blue
    _ACTIVE_FG = QBrush(QColor(255, 255, 255))

    # Light-grey fill for read-only cells so they read as non-editable — the
    # same cue the legacy protocol_grid used (issue #359). A cell is read-only
    # here when it is neither editable nor user-checkable: checkbox cells are
    # non-editable by design but stay interactive, so they keep the normal bg.
    _READ_ONLY_BG_LIGHT = QBrush(QColor("#E8E8E8"))
    _READ_ONLY_BG_DARK = QBrush(QColor("#3A3A3A"))

    def __init__(self, row_manager, parent=None):
        super().__init__(parent)
        self._manager = row_manager
        self._active_node = None
        # Set during reset_columns so the rows_changed handler (which fires
        # mid-swap when the column set / tree is rebuilt) doesn't emit a
        # layoutChanged with a stale column count — the surrounding
        # begin/endResetModel already drives the full re-query.
        self._suppress_rows_changed = False
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

        # Rebroadcast manager changes as layoutChanged
        row_manager.observe(self._on_rows_changed, "rows_changed")
        # Cell value edits get a focused dataChanged for the affected
        # (path, col_id) — read-only summary columns (electrodes,
        # routes) don't declare depends_on_row_traits, so this is the
        # only redraw signal they receive on DV-driven write-backs.
        row_manager.observe(self._on_cell_changed, "cell_changed")

        self.column_changed.connect(self._on_column_changed)
        self._wire_column_handlers_with_column_changed_signal()
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
        row_in_grandparent = (
            grandparent.children.index(parent_node) if grandparent is not None else 0
        )
        return self.createIndex(row_in_grandparent, 0, parent_node)

    # ------------ data / flags / header ------------

    @classmethod
    def _read_only_brush(cls):
        """Background brush for read-only cells, theme-aware (mirror of #359)."""
        return cls._READ_ONLY_BG_DARK if is_dark_mode() else cls._READ_ONLY_BG_LIGHT

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

        # Read-only cells get the light-grey fill (mirror of protocol_grid
        # #359): read-only == neither editable nor user-checkable. The
        # active-row highlight above already returned for that row.
        # Reads self.flags(), not the view's raw get_flags, so per-row
        # column locks (issue #541) pick up the fill for free.
        if role == Qt.BackgroundRole:
            flags = self.flags(index)
            if not (flags & Qt.ItemIsEditable) and not (flags & Qt.ItemIsUserCheckable):
                return self._read_only_brush()

        # A locked cell explains itself: lock reasons are the tooltip.
        if role == Qt.ToolTipRole:
            reasons = node.column_lock_reasons(col.model.col_id)
            if reasons:
                return "\n".join(reasons)
            return None

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
                # on_interact writes directly to the row trait, bypassing
                # RowManager.set_value, so the manager would not see
                # this edit. Fire cell_changed with (path, col_id) so
                # the protocol state tracker can update its incremental
                # dirty bookkeeping in O(1).
                self._manager.cell_changed = {
                    "path": tuple(node.path),
                    "col_id": col.model.col_id,
                }
                return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        col = self._manager.columns[index.column()]
        row = index.internalPointer()
        flags = col.view.get_flags(row)
        # Per-row column locks (issue #541): while any owner holds a
        # lock on this col_id, the cell is inert. Both flags must go —
        # checkbox cells are ItemIsUserCheckable, never ItemIsEditable.
        if row.is_column_locked(col.model.col_id):
            flags &= ~(Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        return flags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._manager.columns[section].model.col_name
        return None

    # ------------ helpers ------------

    def set_active_node(self, node):
        self._active_node = node
        self.layoutChanged.emit()

    def reset_columns(self, mutate):
        """Run ``mutate`` (which swaps the bound RowManager's column set and
        rebuilds its tree) inside a full model reset so the QTreeView and its
        header re-query both column AND row counts.

        A plain ``layoutChanged`` (what rows_changed emits) does not update the
        header's section count, so an added/removed column would otherwise
        leave the header stale and risk an out-of-range column access. The
        rows_changed handler is suppressed during ``mutate`` so only the
        bracketing begin/endResetModel drives the refresh. Per-column handler
        signals and row observers are rewired against the new column set."""
        self.beginResetModel()
        self._suppress_rows_changed = True
        try:
            mutate()
        finally:
            self._suppress_rows_changed = False
            # Drop pins to the old tree's rows; the reset invalidates every
            # QModelIndex Qt held, so the stale refs are no longer needed.
            self._owned_rows.clear()
            self._wire_column_handlers_with_column_changed_signal()
            self._wire_row_observers()
            self.endResetModel()

    def _on_rows_changed(self, event):
        if self._suppress_rows_changed:
            return
        self.layoutChanged.emit()
        self.structure_changed.emit()
        # Row set may have changed structurally (add/remove/move); rewire
        # per-row observers so newcomers participate and detached rows
        # stop emitting against a stale column index.
        self._wire_row_observers()

    def _on_column_changed(self):
        # Fired when any column handler emits column_changed (e.g. the
        # Force column on a calibration update). Coarse but correct:
        # layoutChanged forces Qt to repaint the entire visible area,
        # which covers nested rows for free. These events are
        # low-frequency, so the perf cost is negligible compared to
        # walking every (parent, child) pair to emit per-cell
        # dataChanged for the affected column.
        self.layoutChanged.emit()

    def _on_cell_changed(self, event):
        """Focused dataChanged for a single (path, col_id) edit.

        Fires for delegate / setData edits (where dataChanged was
        already emitted at the call site — this is a redundant but
        cheap no-op) AND for direct trait writes from
        DeviceViewerSyncController (where no other refresh signal
        reaches the model).
        """
        payload = event.new
        if not isinstance(payload, dict):
            return
        path = payload.get("path")
        col_id = payload.get("col_id")
        if path is None or col_id is None:
            return
        try:
            row = self._manager.get_row(tuple(path))
        except (IndexError, AttributeError):
            return
        col_idx = next(
            (
                i
                for i, c in enumerate(self._manager.columns)
                if c.model.col_id == col_id
            ),
            None,
        )
        if col_idx is None:
            return
        idx = self._index_for_cell(row, col_idx)
        if idx.isValid():
            self.dataChanged.emit(idx, idx)

    # ------------ reactive wiring for derived columns ------------

    def _iter_all_rows(self):
        def walk(group):
            for child in group.children:
                yield child
                if isinstance(child, GroupRow):
                    yield from walk(child)

        yield from walk(self._manager.root)

    def _wire_column_handlers_with_column_changed_signal(self):
        """Hand every column handler this model's ``column_changed`` signal.

        A handler emits it to request a full repaint of its column when
        an external dependency changes (e.g. the Force column handler on
        a CALIBRATION_DATA message). Assigning the signal also replays
        any repaint the handler buffered before it was wired — see
        BaseColumnHandler.trigger_column_change_when_wired.
        """
        for col in self._manager.columns:
            col.handler.column_changed_signal = self.column_changed

    def _wire_row_observers(self):
        # Identify per-column row-trait dependencies once.
        col_trait_pairs: list = []
        for col_idx, col in enumerate(self._manager.columns):
            traits = list(getattr(col.view, "depends_on_row_traits", []) or [])
            for trait_name in traits:
                col_trait_pairs.append((col_idx, trait_name))

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
            # Column locks repaint centrally for every row (issue #541)
            # — a gated column never has to declare the dependency, so
            # the stale-grey-out class of bug can't recur.
            lock_handler = partial(self._on_row_locks_changed, row)
            row.observe(lock_handler, "column_locks")
            handles.append(("column_locks", lock_handler))
            for col_idx, trait_name in col_trait_pairs:
                if trait_name not in row.trait_names():
                    continue
                handler = partial(self._on_row_trait_changed, row, col_idx)
                row.observe(handler, trait_name)
                handles.append((trait_name, handler))
            self._row_observer_handles[id(row)] = (row, handles)

    def _on_row_trait_changed(self, row, col_idx, event):
        idx = self._index_for_cell(row, col_idx)
        if idx.isValid():
            self.dataChanged.emit(idx, idx)

    def _on_row_locks_changed(self, row, event):
        # A lock can gate any column on the row; one whole-row
        # dataChanged is cheaper than diffing which col_ids moved.
        top_left = self._index_for_cell(row, 0)
        if not top_left.isValid():
            return
        bottom_right = self._index_for_cell(row, len(self._manager.columns) - 1)
        self.dataChanged.emit(top_left, bottom_right)

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
