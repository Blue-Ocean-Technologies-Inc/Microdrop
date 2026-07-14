"""Qt widget: QTreeView over a RowManager, with context menu for add /
remove / copy / cut / paste / group."""

from pyface.qt.QtCore import (
    Qt, QItemSelectionModel, QModelIndex, Signal,
)
from pyface.qt.QtGui import QKeySequence, QShortcut
from pyface.qt.QtWidgets import (
    QWidget, QVBoxLayout, QTreeView, QMenu, QAbstractItemView, QDialog,
)

from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.views.bulk_set_dialog import BulkSetDialog
from pluggable_protocol_tree.views.delegate import ProtocolItemDelegate
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel

from logger.logger_service import get_logger
logger = get_logger(__name__)


class _ProtocolTreeView(QTreeView):
    """QTreeView subclass that emits a Qt signal on Delete keypress.

    Using a keyPressEvent override (rather than QShortcut) is the most
    reliable path: the event is captured directly on the focused widget,
    no overload-resolution surprises, no shortcut-context confusion, and
    we explicitly accept() the event so Qt's default key handling
    doesn't get a second chance to interpret it.

    Left-click on empty tree space clears the selection AND the current
    index. Mirrors the legacy protocol_grid behaviour and lets a
    listener on currentRowChanged drive 'no row selected' UI (e.g. the
    SimpleDeviceViewer clears its electrodes/routes display when the
    active row is None).
    """

    delete_pressed = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self.indexAt(event.position().toPoint())
            if not idx.isValid():
                self.clearSelection()
                self.setCurrentIndex(QModelIndex())
                event.accept()
                return
        super().mousePressEvent(event)


class ProtocolTreeWidget(QWidget):
    def __init__(self, row_manager: RowManager, preferences=None, parent=None):
        super().__init__(parent)
        self._manager = row_manager
        # Column visibility persists in ProtocolPreferences
        # (protocol_tree_column_visibility), passed down from the pane in
        # the full app; standalone fallback for demos/headless tests.
        self._preferences = preferences or ProtocolPreferences()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = _ProtocolTreeView()
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._default_edit_triggers = (QAbstractItemView.DoubleClicked
                                       | QAbstractItemView.EditKeyPressed)
        self._editable = True
        # Structural edits (Add/Delete/Paste via the context menu) are gated
        # separately from cell-value editing: Advanced Mode reopens value
        # editing during a run but never the structural menu (#434).
        self._structural_editable = True
        self.tree.setEditTriggers(self._default_edit_triggers)
        self.tree.delete_pressed.connect(self._delete_selection)
        layout.addWidget(self.tree)

        self.model = MvcTreeModel(row_manager, parent=self.tree)
        self.tree.setModel(self.model)

        # PPT-3: header right-click menu to toggle column visibility
        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        # Let the user drag header sections to reorder columns. Make sections
        # movable before applying the saved order (moveSection), and connect
        # sectionMoved AFTER so the restore moves don't recursively re-persist.
        header.setSectionsMovable(True)
        self._apply_column_headers()
        header.sectionMoved.connect(self._persist_column_order)

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

        # Mirror Qt selection --> RowManager selection
        self.tree.selectionModel().selectionChanged.connect(self._sync_selection)

    def _apply_column_headers(self):
        """Apply per-column header state (hidden-by-default, persisted
        visibility, persisted order) for the current column set. Called at
        construction and again after a runtime column swap (refresh_columns),
        where the model reset drops the header's hidden/order state back to
        defaults."""
        # PPT-3: hide columns marked hidden_by_default.
        for i, col in enumerate(self._manager.columns):
            if getattr(col.view, "hidden_by_default", False):
                self.tree.setColumnHidden(i, True)

        # Restore the user's persisted column visibility, overriding the
        # hidden_by_default defaults for any column they have toggled before.
        # Columns absent from the saved map keep the default applied above.
        # Keyed by col_id (stable across display renames — col_name keying
        # orphaned saved entries when Routes became "Electrodes"); the
        # col_name fallback reads maps persisted before that change, and
        # the next persist rewrites them under col_id.
        saved_visibility = self._load_column_visibility()
        for i, col in enumerate(self._manager.columns):
            visible = saved_visibility.get(
                col.model.col_id, saved_visibility.get(col.model.col_name))
            if visible is not None:
                self.tree.setColumnHidden(i, not visible)

        # Persisted drag-reordered column order (no-op when nothing saved).
        self._apply_column_order()

    def refresh_columns(self, mutate):
        """Swap the model's column set — via ``mutate``, which mutates the
        bound RowManager (e.g. RowManager.set_columns) — inside a full model
        reset, then re-apply the per-column header state for the new set.

        Used for runtime hot load/unload of a column-contributing plugin: the
        reset is what makes the QTreeView pick up the changed column count (a
        plain layoutChanged would not), and re-applying the headers restores
        hidden/visibility/order which the reset cleared."""
        self.model.reset_columns(mutate)
        self._apply_column_headers()

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
            self._expand_ancestors(idx)

    def set_current_row(self, row):
        """Make ``row`` the tree's current index (expanding any collapsed
        ancestor groups) and scroll to it. Public API for the pane's
        step-cursor navigation — fires currentChanged like a user click."""
        idx = self._node_to_index(row)
        if not idx.isValid():
            return
        self._expand_ancestors(idx)
        self.tree.setCurrentIndex(idx)
        self.tree.scrollTo(idx)

    def set_editable(self, editable: bool, structural: bool = None):
        """Lock/unlock cell editing and (separately) the structural context
        menu. Driven by the status model's ``running`` flag — the protocol is
        read-only while a run is in progress (issue #471), except Advanced
        Mode reopens cell-value editing mid-run (issue #434).

        ``editable`` gates cell-value edit triggers. ``structural`` gates the
        Add/Delete/Paste context menu; it defaults to ``editable`` so existing
        callers keep their all-or-nothing behaviour. Pass them apart to allow
        value edits while keeping structural changes locked (advanced mode
        during a run)."""
        self._editable = bool(editable)
        self._structural_editable = bool(editable if structural is None
                                          else structural)
        self.tree.setEditTriggers(
            self._default_edit_triggers if editable
            else QAbstractItemView.NoEditTriggers)

    def _expand_ancestors(self, idx):
        """Expand every collapsed ancestor group so ``idx`` is visible."""
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

    def index_to_path(self, index):
        return self._index_to_path(index)

    # --- context menu actions ---

    def _on_context_menu(self, pos):
        # No structural edits while a run is in progress (issue #471) — not
        # even in Advanced Mode, which only reopens cell-value editing (#434).
        if not self._structural_editable:
            return
        idx = self.tree.indexAt(pos)
        menu = QMenu()
        menu.addAction("Add Step", lambda: self._add_step_at(idx))
        menu.addAction("Add Group", lambda: self._add_group_at(idx))
        fold = menu.addAction("Fold into Group", self._fold_into_group)
        fold.setEnabled(
            self._manager.can_fold_into_group(self._manager.selection))
        menu.addSeparator()
        menu.addAction("Copy", self._copy)
        menu.addAction("Cut", self._cut)
        menu.addAction("Paste", self._paste)
        menu.addSeparator()
        menu.addAction("Bulk Set Values…", self._bulk_set_values)
        menu.addSeparator()
        menu.addAction("Delete", self._delete_selection)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _on_header_context_menu(self, pos):
        """Header right-click --> menu listing every column with a
        toggleable 'Show' checkmark. Affects only the QTreeView's
        column visibility — does not touch the underlying row data.

        Each toggle persists the full visibility map so the choice
        survives an app restart (see ProtocolPreferences.
        protocol_tree_column_visibility)."""
        menu = QMenu()
        for i, col in enumerate(self._manager.columns):
            action = menu.addAction(col.model.col_name)
            action.setCheckable(True)
            action.setChecked(not self.tree.isColumnHidden(i))

            def _toggle(checked, idx=i):
                self.tree.setColumnHidden(idx, not checked)
                self._persist_column_visibility()

            action.toggled.connect(_toggle)
        menu.exec(self.tree.header().viewport().mapToGlobal(pos))

    def _load_column_visibility(self) -> dict:
        """Return the persisted {col_id: visible} map ({} when nothing
        was saved yet or the preference is unreadable — callers treat an
        absent entry as "use the column default"). Maps persisted before
        the col_id keying are read via the col_name fallback at the call
        site."""
        try:
            saved = self._preferences.protocol_tree_column_visibility
            return {str(name): bool(visible)
                    for name, visible in (saved or {}).items()}
        except Exception as exc:
            logger.warning(f"Could not read column visibility preference: {exc}")
            return {}

    def _persist_column_visibility(self):
        """Save the current {col_id: visible} map for every column."""
        visibility = {
            col.model.col_id: not self.tree.isColumnHidden(i)
            for i, col in enumerate(self._manager.columns)
        }
        try:
            self._preferences.protocol_tree_column_visibility = visibility
        except Exception as exc:
            logger.warning(f"Could not save column visibility preference: {exc}")

    def _load_column_order(self) -> list:
        """Return the persisted [col_id, ...] visual order ([] when nothing
        was saved yet or the preference is unreadable)."""
        try:
            saved = self._preferences.protocol_tree_column_order
            return [str(cid) for cid in (saved or [])]
        except Exception as exc:
            logger.warning(f"Could not read column order preference: {exc}")
            return []

    def _apply_column_order(self):
        """Reorder the header's visual sections to the persisted col_id
        sequence. Columns absent from the saved order (added since the last
        save) keep their natural logical position at the end. No-op when
        nothing is saved. Visibility is independent of order, so hidden
        columns still occupy (and are moved within) the visual sequence."""
        saved_order = self._load_column_order()
        if not saved_order:
            return
        header = self.tree.header()
        id_to_logical = {col.model.col_id: i
                         for i, col in enumerate(self._manager.columns)}
        target = [id_to_logical[cid] for cid in saved_order
                  if cid in id_to_logical]
        seen = set(target)
        target += [i for i in range(len(self._manager.columns))
                   if i not in seen]
        blocked = header.blockSignals(True)
        try:
            for visual, logical in enumerate(target):
                cur = header.visualIndex(logical)
                if cur != visual:
                    header.moveSection(cur, visual)
        finally:
            header.blockSignals(blocked)

    def _persist_column_order(self, *args):
        """Save the current visual column order as a [col_id, ...] list.
        Connected to the header's ``sectionMoved`` signal (which passes the
        moved section's indices — ignored; we re-read the whole order)."""
        header = self.tree.header()
        order = [self._manager.columns[header.logicalIndex(v)].model.col_id
                 for v in range(header.count())]
        try:
            self._preferences.protocol_tree_column_order = order
        except Exception as exc:
            logger.warning(f"Could not save column order preference: {exc}")

    def _add_step_at(self, idx):
        parent_path = self._parent_path_for_anchor(idx)
        self._manager.add_step(parent_path=parent_path)

    def _add_group_at(self, idx):
        parent_path = self._parent_path_for_anchor(idx)
        self._manager.add_group(parent_path=parent_path)

    def _fold_into_group(self):
        """Wrap the selected rows in a new group at the first row's
        position (#518), then select the new group so the user can rename
        it (F2 / double-click) and subsequent actions target it."""
        try:
            group_path = self._manager.fold_into_group(
                [tuple(p) for p in self._manager.selection])
            if group_path is None:
                return
            idx = self._node_to_index(self._manager.get_row(group_path))
            if idx.isValid():
                self._expand_ancestors(idx)
                self.tree.selectionModel().setCurrentIndex(
                    idx,
                    (QItemSelectionModel.SelectionFlag.ClearAndSelect
                     | QItemSelectionModel.SelectionFlag.Rows),
                )
        except Exception:
            logger.exception("Fold into group failed")

    def _parent_path_for_anchor(self, idx):
        """If anchored on a group --> insert inside. On a step --> insert as
        sibling. No anchor --> root."""
        if not idx.isValid():
            return ()
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

    def _bulk_set_values(self):
        """Open the Bulk Set dialog and apply the chosen values to every
        selected step. Groups expand to their child steps — first level only,
        or all descendants when 'Apply to all nested groups' is ticked."""
        paths = [self._index_to_path(i)
                 for i in self.tree.selectionModel().selectedRows(0)]
        if not paths:
            return
        dialog = BulkSetDialog(self._manager, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        updates = dialog.values()
        targets = self._manager.steps_under(paths, recursive=dialog.apply_nested)
        if not updates or not targets:
            return
        # Direct model writes (set_values) rather than per-row handler
        # on_interact: a bulk action must not pop the per-cell confirm dialogs
        # some handlers raise (e.g. route_repetitions). The pane's cell_changed
        # reconciliation still runs for derived columns.
        for col_id, value in updates.items():
            self._manager.set_values(targets, col_id, value)
        logger.info(
            f"Bulk set {list(updates)} on {len(targets)} step(s) "
            f"(nested={dialog.apply_nested})"
        )

    def _delete_selection(self):
        """Remove the currently-selected rows. Defensive: stale paths
        (rows already removed by a previous action) are silently
        skipped rather than propagating IndexError, which under
        PySide6 6.x terminates the QApplication.

        After removal: pick a sensible alternative selection so the
        downstream sync (DV display, status bar, etc.) doesn't get
        stuck on the deleted row. If any rows remain at the root, fall
        back to the first one; if the tree is empty, clear the
        selection entirely (free mode)."""
        try:
            paths = [tuple(p) for p in self._manager.selection]
            valid = []
            for p in paths:
                try:
                    self._manager.get_row(p)
                except (IndexError, KeyError):
                    continue
                valid.append(p)
            if not valid:
                return
            self._manager.remove(valid)

            # Post-removal: ensure a sensible selection state.
            sm = self.tree.selectionModel()
            if not self._manager.root.children:
                # Empty tree --> free mode.
                sm.clearSelection()
                sm.setCurrentIndex(
                    QModelIndex(),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
                return
            cur = sm.currentIndex()
            if cur.isValid():
                # Qt already picked a survivor — leave it alone.
                return
            # Fall back to the first remaining row at the root.
            first = self.model.index(0, 0)
            if first.isValid():
                sm.setCurrentIndex(
                    first,
                    (QItemSelectionModel.SelectionFlag.ClearAndSelect
                     | QItemSelectionModel.SelectionFlag.Rows),
                )
        except Exception:
            logger.exception("Delete failed")
