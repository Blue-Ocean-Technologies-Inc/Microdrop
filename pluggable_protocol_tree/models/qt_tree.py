from pyface.qt.QtCore import QAbstractItemModel, Signal, QModelIndex, Qt
from pyface.qt.QtWidgets import QStyledItemDelegate

from pluggable_protocol_tree.models.steps import GroupStep, ActionStep


class MvcTreeModel(QAbstractItemModel):
    new_node_added = Signal(QModelIndex)

    def __init__(self, root, columns):
        super().__init__()
        self._root = root
        self._cols = columns

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        return self._cols[index.column()].view.get_flags(index.internalPointer())

    def data(self, i, role=Qt.DisplayRole):
        if not i.isValid():
            return None

        column_bundle = self._cols[i.column()]

        step = i.internalPointer()
        val = column_bundle.model.get_value(step)

        if role == Qt.DisplayRole:
            return column_bundle.view.format_display(val, step)

        if role == Qt.CheckStateRole:
            return column_bundle.view.get_check_state(val, step)

        if role == Qt.UserRole:
            return step

        return None

    def setData(self, index, value, role=Qt.EditRole):
        column_bundle = self._cols[index.column()]
        row = index.internalPointer()

        # Handle Checkbox Clicks and Text Edits
        if role in [Qt.CheckStateRole, Qt.EditRole]:

            if column_bundle.handler.on_interact(row, column_bundle.model, value):
                self.dataChanged.emit(index, index, [role])
                return True

        return False

    def add_node(self, idx, node):
        """
        Adds a node relative to the current index 'idx'.
        If idx is a Group, add inside.
        else add sibling (after).
        """
        parent_node = self._root
        parent_index = QModelIndex()
        insert_pos = len(parent_node.children)

        if idx.isValid():
            target = idx.internalPointer()

            if isinstance(target, GroupStep):
                # Add INSIDE the group
                parent_node = target
                parent_index = idx
                insert_pos = len(parent_node.children)

            elif target.parent:
                # Add AFTER the selected step (sibling)
                parent_node = target.parent
                if parent_node != self._root:
                    parent_index = idx.parent()
                insert_pos = parent_node.children.index(target) + 1

        self.beginInsertRows(parent_index, insert_pos, insert_pos)

        if insert_pos >= len(parent_node.children):
            parent_node.add_step(node)

        else:
            parent_node.insert_step(insert_pos, node)

        self.endInsertRows()

        # Signal to View to expand the new item if necessary
        new_index = self.index(insert_pos, 0, parent_index)
        self.new_node_added.emit(new_index)

    def rowCount(self, p=QModelIndex()):
        n = p.internalPointer() if p.isValid() else self._root
        return len(n.children) if isinstance(n, GroupStep) else 0

    def columnCount(self, p=QModelIndex()):
        return len(self._cols)

    def index(self, r, c, p=QModelIndex()):
        if not self.hasIndex(r, c, p):
            return QModelIndex()
        n = p.internalPointer() if p.isValid() else self._root
        if r < len(n.children):
            return self.createIndex(r, c, n.children[r])
        return QModelIndex()

    def parent(self, i):
        if not i.isValid():
            return QModelIndex()

        n = i.internalPointer()
        p = n.parent

        if not p or p == self._root:
            return QModelIndex()

        # Find row of parent within grandparent
        row = p.parent.children.index(p)

        return self.createIndex(row, 0, p)

    def headerData(self, s, o, r=Qt.DisplayRole):
        return (
            self._cols[s].model.col_name
            if r == Qt.DisplayRole and o == Qt.Horizontal
            else None
        )


class ProtocolGridDelegate(QStyledItemDelegate):
    def __init__(self, columns, parent):
        super().__init__(parent)
        self.columns = columns

    def createEditor(self, parent, option, index):
        return self.columns[index.column()].view.create_editor(parent, None)

    def setEditorData(self, editor, index):
        col = self.columns[index.column()]
        step = index.data(Qt.UserRole)
        col.view.set_editor_data(editor, col.model.get_value(step))

    def setModelData(self, editor, model, index):
        column_bundle = self.columns[index.column()]
        step = index.data(Qt.UserRole)
        val = column_bundle.view.get_editor_data(editor)

        if column_bundle.handler.on_interact(step, column_bundle.model, val):
            model.dataChanged.emit(index, index)
