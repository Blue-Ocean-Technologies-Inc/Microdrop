"""Qt delegate that routes editor create/set/get through each column's view.

Pure forwarding — no state. Lives as its own file so the tree widget in
Task 22 can import it without circular dependencies."""

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QStyledItemDelegate


class ProtocolItemDelegate(QStyledItemDelegate):
    def __init__(self, row_manager, parent=None):
        super().__init__(parent)
        self._manager = row_manager

    def createEditor(self, parent, option, index):
        col = self._manager.columns[index.column()]
        return col.view.create_editor(parent, None)

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
