"""Qt delegate that routes editor create/set/get through each column's view.

Lives as its own file so the tree widget in Task 22 can import it
without circular dependencies. The only state is the index currently
being edited — while an editor is open, the cell's display text is
suppressed so the editor never paints on top of the old value (the app
stylesheet leaves editor widgets translucent, which otherwise shows
both overlaid)."""

from pyface.qt.QtCore import Qt, QPersistentModelIndex
from pyface.qt.QtWidgets import QStyledItemDelegate


class ProtocolItemDelegate(QStyledItemDelegate):
    def __init__(self, row_manager, parent=None):
        super().__init__(parent)
        self._manager = row_manager
        self._editing_index = None

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if self._editing_index is not None and self._editing_index == index:
            # The open editor replaces the value display entirely; the
            # underlying cell must not show the stale text beneath it.
            option.text = ""

    def createEditor(self, parent, option, index):
        col = self._manager.columns[index.column()]
        # Context is the row being edited — views with row-dependent
        # bounds (e.g. trail overlay <= trail length - 1) read it.
        editor = col.view.create_editor(parent, index.data(Qt.UserRole))
        if editor is not None:
            # Opaque background regardless of stylesheet, so the cell
            # underneath can never bleed through the editor.
            editor.setAutoFillBackground(True)
            self._editing_index = QPersistentModelIndex(index)
        return editor

    def destroyEditor(self, editor, index):
        self._editing_index = None
        super().destroyEditor(editor, index)

    def setEditorData(self, editor, index):
        if editor is None:
            return
        col = self._manager.columns[index.column()]
        node = index.data(Qt.UserRole)
        col.view.set_editor_data(editor, col.model.get_value(node))

    def setModelData(self, editor, model, index):
        if editor is None:
            return
        col = self._manager.columns[index.column()]
        node = index.data(Qt.UserRole)
        value = col.view.get_editor_data(editor)
        if col.handler.on_interact(node, col.model, value):
            model.dataChanged.emit(index, index)
            # on_interact writes the trait directly, bypassing the
            # manager's set_value path. Fire cell_changed with the
            # (path, col_id) so the protocol state tracker can update
            # its incremental dirty bookkeeping in O(1).
            self._manager.cell_changed = {
                "path": tuple(node.path),
                "col_id": col.model.col_id,
            }
