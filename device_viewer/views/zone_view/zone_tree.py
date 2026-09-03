# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tree-table over a ZoneLayerManager: zone types are the top-level rows and
their regions the child rows, replacing the two separate sidebar tables.

Qt lives here — a QAbstractItemModel reading the manager, a QTreeView, and an
item delegate that paints the color swatch and the two glyph columns in the
icon font and turns a click in them into a model edit. The sidebar embeds it
through ``zone_tree_factory`` with a TraitsUI ``CustomEditor``.
"""

# Enthought library imports.
from pyface.qt.QtCore import (
    QAbstractItemModel,
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    Qt,
    Signal,
)
from pyface.qt.QtGui import QColor, QFont, QFontMetrics
from pyface.qt.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QHeaderView,
    QStyledItemDelegate,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

# Microdrop style imports.
from microdrop_style.button_styles import TEXT_BUTTON_STYLE
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import (
    ICON_DELETE,
    ICON_VISIBILITY,
    ICON_VISIBILITY_OFF,
)

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import DEFAULT_GLYPH_POINT_SIZE_PX

# Local imports.
from ...consts import (
    ZONE_TREE_COLOR_COLUMN,
    ZONE_TREE_COLOR_COLUMN_WIDTH_PX,
    ZONE_TREE_COUNT_COLUMN,
    ZONE_TREE_DELETE_COLUMN,
    ZONE_TREE_GLYPH_COLUMN_PADDING_PX,
    ZONE_TREE_HEADERS,
    ZONE_TREE_NAME_COLUMN,
    ZONE_TREE_SWATCH_INSET_PX,
    ZONE_TREE_VISIBLE_COLUMN,
)
from ...models.zones import ZoneType

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Manager traits that change WHICH rows exist; each drives a full model reset.
_STRUCTURE_TRAITS = "[zone_types.items, regions.items, regions:items:zone_id]"

#: Manager traits that change what a row DISPLAYS; each repaints that row.
_CELL_TRAITS = "[zone_types:items:[name, color, visible], regions:items:[id, visible]]"


def _glyph_font():
    return QFont(ICON_FONT_FAMILY, DEFAULT_GLYPH_POINT_SIZE_PX)


class ZoneTreeModel(QAbstractItemModel):
    """Qt tree model over a ZoneLayerManager.

    Structural changes are coarse (a full reset — the table holds a handful
    of rows), value changes repaint the one affected row. The manager is the
    only source of truth; the model caches nothing.
    """

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        manager.observe(self._on_structure_changed, _STRUCTURE_TRAITS)
        manager.observe(self._on_cell_changed, _CELL_TRAITS)

    def dispose(self):
        """Detach from the manager, which outlives this model (it is rebuilt
        with the sidebar view, the manager only with the device viewer)."""
        self._manager.observe(
            self._on_structure_changed, _STRUCTURE_TRAITS, remove=True
        )
        self._manager.observe(self._on_cell_changed, _CELL_TRAITS, remove=True)

    # ------------------------------------------------------------ structure
    def _rows_under(self, parent):
        if not parent.isValid():
            return self._manager.zone_types
        node = parent.internalPointer()
        # Children hang off the first column only, as Qt's tree views expect.
        if parent.column() != 0 or not isinstance(node, ZoneType):
            return []
        return self._manager.get(node.id)

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows_under(parent))

    def columnCount(self, parent=QModelIndex()):
        return len(ZONE_TREE_HEADERS)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column, self._rows_under(parent)[row])

    def parent(self, index=QModelIndex()):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        if isinstance(node, ZoneType):
            return QModelIndex()
        zone_type = self._manager.zone_type_for(node.zone_id)
        if zone_type not in self._manager.zone_types:
            return QModelIndex()
        return self.createIndex(self._manager.zone_types.index(zone_type), 0, zone_type)

    def index_for(self, node, column=ZONE_TREE_NAME_COLUMN):
        """QModelIndex of the row showing ``node`` (a ZoneType or a
        ZoneRegion); invalid when the manager no longer holds it."""
        if isinstance(node, ZoneType):
            if node not in self._manager.zone_types:
                return QModelIndex()
            return self.index(self._manager.zone_types.index(node), column)
        if node is None:
            return QModelIndex()
        zone_type = self._manager.zone_type_for(node.zone_id)
        if zone_type is None:
            return QModelIndex()
        siblings = self._manager.get(zone_type.id)
        if node not in siblings:
            return QModelIndex()
        return self.index(siblings.index(node), column, self.index_for(zone_type))

    # ----------------------------------------------------------------- data
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        column = index.column()

        if role == Qt.UserRole:
            return node
        if role == Qt.TextAlignmentRole and column != ZONE_TREE_NAME_COLUMN:
            return Qt.AlignCenter
        if role == Qt.ToolTipRole:
            # The region id ("heating-1") is what the SVG Zones layer, the logs
            # and the delete dialog speak, so it stays reachable from the row
            # that only shows a position.
            if column == ZONE_TREE_NAME_COLUMN and not isinstance(node, ZoneType):
                return node.id
            return None
        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None

        if column == ZONE_TREE_NAME_COLUMN:
            # A region row already sits under its zone's row, so its id would
            # just repeat the parent's name — show its position instead.
            if isinstance(node, ZoneType):
                return node.name
            return str(index.row() + 1)
        if column == ZONE_TREE_COUNT_COLUMN:
            return str(node.region_count) if isinstance(node, ZoneType) else ""
        if column == ZONE_TREE_VISIBLE_COLUMN:
            return ICON_VISIBILITY if node.visible else ICON_VISIBILITY_OFF
        if column == ZONE_TREE_DELETE_COLUMN:
            return ICON_DELETE
        # The color column is painted by the delegate, not written as text.
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        node = index.internalPointer()
        column = index.column()
        # The manager's own observers turn each of these into the matching
        # dataChanged / reset, so nothing is emitted here.
        if column == ZONE_TREE_NAME_COLUMN and isinstance(node, ZoneType):
            node.name = str(value)
            return True
        if column == ZONE_TREE_VISIBLE_COLUMN:
            node.visible = bool(value)
            return True
        if column == ZONE_TREE_DELETE_COLUMN:
            node.delete_requested = True
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        node = index.internalPointer()
        if index.column() == ZONE_TREE_NAME_COLUMN and isinstance(node, ZoneType):
            flags |= Qt.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return ZONE_TREE_HEADERS[section]
        return None

    # ------------------------------------------------------- manager events
    def _on_structure_changed(self, event):
        self.beginResetModel()
        self.endResetModel()

    def _on_cell_changed(self, event):
        index = self.index_for(event.object)
        if index.isValid():
            self.dataChanged.emit(index, index.siblingAtColumn(self.columnCount() - 1))


class ZoneTreeDelegate(QStyledItemDelegate):
    """Paints the zone color swatch and renders the eye/delete cells in the
    icon font; a click in one of those three columns acts on the row instead
    of opening an editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = _glyph_font()

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.column() in (ZONE_TREE_VISIBLE_COLUMN, ZONE_TREE_DELETE_COLUMN):
            option.font = self._font

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.column() != ZONE_TREE_COLOR_COLUMN:
            return
        node = index.data(Qt.UserRole)
        if not isinstance(node, ZoneType):
            return  # regions take their color from their zone; cell stays empty
        inset = ZONE_TREE_SWATCH_INSET_PX
        painter.save()
        painter.fillRect(
            option.rect.adjusted(inset, inset, -inset, -inset), QColor(node.color)
        )
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            node = index.data(Qt.UserRole)
            column = index.column()
            if column == ZONE_TREE_VISIBLE_COLUMN:
                return model.setData(index, not node.visible)
            if column == ZONE_TREE_DELETE_COLUMN:
                return model.setData(index, True)
            if column == ZONE_TREE_COLOR_COLUMN and isinstance(node, ZoneType):
                self._pick_color(node)
                return True
        return super().editorEvent(event, model, option, index)

    def _pick_color(self, zone_type):
        """Modal color picker for the zone. Under the sidebar stylesheet an
        unstyled dialog inherits the glyph-font push-button rule, so the
        app's text-button style has to be applied to the dialog itself."""
        dialog = QColorDialog(QColor(zone_type.color), self.parent())
        dialog.setWindowTitle("Select Color")
        dialog.setStyleSheet(TEXT_BUTTON_STYLE)
        if dialog.exec() and dialog.selectedColor().isValid():
            zone_type.color = dialog.selectedColor().name()


class _ZoneTreeView(QTreeView):
    """QTreeView that reports a click on empty space, so the widget can drop
    the manager's selection the way clicking outside a table row did, and that
    honours the manager's touch-friendly ``multi_select`` toggle."""

    selection_cleared = Signal()

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager

    def selectionCommand(self, index, event=None):
        """While ``multi_select`` is on, a plain click on a region row adds to
        or removes it from the selection instead of replacing it — the touch
        equivalent of holding ctrl, which still works on its own."""
        if (
            self._manager.multi_select
            and index.isValid()
            and not isinstance(index.data(Qt.UserRole), ZoneType)
        ):
            return (
                QItemSelectionModel.SelectionFlag.Toggle
                | QItemSelectionModel.SelectionFlag.Rows
            )
        return super().selectionCommand(index, event)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and not self.indexAt(event.position().toPoint()).isValid()
        ):
            self.selection_cleared.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class ZoneTreeWidget(QWidget):
    """The zones tree-table: zone types with their regions nested underneath,
    with the manager's selection mirrored both ways."""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        # True while one direction of the selection sync is writing, so the
        # echo coming back the other way is ignored instead of ping-ponging.
        self._syncing = False
        # Ids of the zones the user folded; a model reset (add, delete,
        # reorder) rebuilds every row expanded unless the id is in here.
        self._collapsed_zone_ids = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = _ZoneTreeView(manager)
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        layout.addWidget(self.tree)

        self.model = ZoneTreeModel(manager, parent=self.tree)
        self.tree.setModel(self.model)
        self.delegate = ZoneTreeDelegate(parent=self.tree)
        self.tree.setItemDelegate(self.delegate)
        self._size_columns()
        self.tree.expandAll()

        self.model.modelReset.connect(self._on_model_reset)
        self.tree.collapsed.connect(
            lambda index: self._collapsed_zone_ids.add(index.internalPointer().id)
        )
        self.tree.expanded.connect(
            lambda index: self._collapsed_zone_ids.discard(index.internalPointer().id)
        )
        self.tree.selectionModel().selectionChanged.connect(self._on_rows_selected)
        self.tree.selection_cleared.connect(self.clear_selection)

        # Manager -> view. Wired here rather than on the model so both
        # directions of the sync share the one re-entrancy guard.
        manager.observe(self._on_manager_selection_changed, "selected_regions.items")
        manager.observe(self._on_manager_selection_changed, "selected_zone_type")
        # The manager outlives this widget, so every observer above must come
        # off when Qt destroys it or a rebuilt sidebar would stack duplicates.
        self.destroyed.connect(lambda *_: self._dispose())

    def _dispose(self):
        self.model.dispose()
        self._manager.observe(
            self._on_manager_selection_changed, "selected_regions.items", remove=True
        )
        self._manager.observe(
            self._on_manager_selection_changed, "selected_zone_type", remove=True
        )

    def _size_columns(self):
        """Zone stretches so it follows the sidebar width preference; every
        other section is Interactive at a fixed starting width, so the user can
        drag its divider.

        Two Qt defaults have to be undone first, or the widths set below are
        silently ignored: stretch-last-section blows the delete column out to
        fill the row, and the app style's minimum section size (44 px) is wider
        than a glyph column needs.
        """
        glyph_width = (
            QFontMetrics(_glyph_font()).height() + ZONE_TREE_GLYPH_COLUMN_PADDING_PX
        )
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(glyph_width)
        for column in range(self.model.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(
            ZONE_TREE_NAME_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        self.tree.setColumnWidth(
            ZONE_TREE_COLOR_COLUMN, ZONE_TREE_COLOR_COLUMN_WIDTH_PX
        )
        for column in (
            ZONE_TREE_COUNT_COLUMN,
            ZONE_TREE_VISIBLE_COLUMN,
            ZONE_TREE_DELETE_COLUMN,
        ):
            self.tree.setColumnWidth(column, glyph_width)

    # ------------------------------------------------------- selection sync
    def clear_selection(self):
        """View-side clear: a click on empty tree space drops both manager
        selections. (Escape does the same from ZonesSidebarHandler, which
        writes the manager traits directly.)"""
        self._manager.selected_region = None
        self._manager.selected_zone_type = None

    def _on_rows_selected(self, *_):
        """View -> manager. Selected region rows become ``selected_regions`` in
        tree order, with the current row last so the manager's "primary is the
        last one" reading of ``selected_region`` matches what the user clicked.
        A selection of zone rows only sets ``selected_zone_type`` instead.

        An empty selection is deliberately NOT propagated: a model reset clears
        the Qt selection transiently, and clearing the manager from that echo
        would lose the rows we are about to restore. Clearing is explicit, via
        clear_selection."""
        if self._syncing:
            return
        selection_model = self.tree.selectionModel()
        rows = selection_model.selectedRows(ZONE_TREE_NAME_COLUMN)
        if not rows:
            return
        selected_ids = {id(row.data(Qt.UserRole)) for row in rows}
        current = selection_model.currentIndex()
        primary = current.data(Qt.UserRole) if current.isValid() else None
        # Walk the manager rather than the QItemSelection, whose ranges come in
        # click order — tree order is what the manager's list should carry.
        regions = [
            region
            for zone_type in self._manager.zone_types
            for region in self._manager.get(zone_type.id)
            if id(region) in selected_ids
        ]
        self._syncing = True
        try:
            if regions:
                if any(region is primary for region in regions):
                    regions = [r for r in regions if r is not primary] + [primary]
                self._manager.selected_zone_type = self._manager.zone_type_for(
                    regions[-1].zone_id
                )
                self._manager.selected_regions = regions
            else:
                zones = [
                    zone_type
                    for zone_type in self._manager.zone_types
                    if id(zone_type) in selected_ids
                ]
                self._manager.selected_regions = []
                self._manager.selected_zone_type = (
                    primary if isinstance(primary, ZoneType) else zones[-1]
                )
        finally:
            self._syncing = False

    def _on_manager_selection_changed(self, event):
        """Manager -> view: the selected regions win over their zone, so the
        deeper rows are the ones shown selected, and the primary region (the
        last of the list) becomes the current row."""
        if self._syncing:
            return
        regions = list(self._manager.selected_regions)
        if regions:
            self._select_rows_for(regions, regions[-1])
        else:
            zone_type = self._manager.selected_zone_type
            self._select_rows_for([] if zone_type is None else [zone_type], zone_type)

    def _select_rows_for(self, nodes, current):
        """Select exactly the rows for ``nodes`` and make ``current``'s row the
        current index, without echoing back through _on_rows_selected."""
        selection_model = self.tree.selectionModel()
        last_column = self.model.columnCount() - 1
        self._syncing = True
        try:
            selection_model.clearSelection()
            for node in nodes:
                index = self.model.index_for(node)
                if not index.isValid():
                    continue
                self.tree.expand(index.parent())
                selection_model.select(
                    QItemSelection(index, index.siblingAtColumn(last_column)),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
            current_index = self.model.index_for(current)
            if not current_index.isValid():
                selection_model.setCurrentIndex(
                    QModelIndex(), QItemSelectionModel.SelectionFlag.Clear
                )
                return
            selection_model.setCurrentIndex(
                current_index, QItemSelectionModel.SelectionFlag.NoUpdate
            )
            self.tree.scrollTo(current_index)
        finally:
            self._syncing = False

    def _on_model_reset(self):
        for zone_type in self._manager.zone_types:
            self.tree.setExpanded(
                self.model.index_for(zone_type),
                zone_type.id not in self._collapsed_zone_ids,
            )
        self._on_manager_selection_changed(None)


def zone_tree_factory(parent, editor):
    """TraitsUI CustomEditor factory: the editor's object is the manager.

    ``parent`` is the enclosing QLayout, not a QWidget (traitsui.qt's
    CustomEditor passes the layout), so it cannot be the widget's parent —
    TraitsUI reparents the returned widget when it adds it to that layout.
    """
    return ZoneTreeWidget(editor.object)
