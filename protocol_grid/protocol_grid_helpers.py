from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (QStyledItemDelegate, 
                               QSpinBox, QDoubleSpinBox)

from protocol_grid.consts import (protocol_grid_fields, 
                                  ROW_TYPE_ROLE 
                                  )


class SpinBoxDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, integer=True):
        super().__init__(parent)
        self.integer = integer

    def createEditor(self, parent, option, index):
        if self.integer:
            editor = QSpinBox(parent)
        else:
            editor = QDoubleSpinBox(parent)
            editor.setDecimals(2)
            editor.setSingleStep(0.01)
        editor.setMinimum(0)
        editor.setMaximum(10000)  # Set as per your requirement
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setValue(int(value) if self.integer else float(value))

    def setModelData(self, editor, model, index):
        value = editor.value()
        model.setData(index, value, Qt.ItemDataRole.EditRole)


class PGCItem(QStandardItem):
    def __init__(self, item_type=None, item_data=None):
        super().__init__(item_data)
        self.item_type = item_type
        self.item_data = item_data

    def get_item_type(self):
        return self.item_type

    def get_item_data(self):
        return self.item_data

    def set_item_type(self, item_type):
        self.item_type = item_type

    def set_item_data(self, item_data):
        self.item_data = item_data

    def clone(self):
        new_item = PGCItem(self.item_type, self.item_data)
        new_item.setEditable(self.isEditable())
        for role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            new_item.setData(self.data(role), role)

        for row in range(self.rowCount()):
            # recursion
            child_row = [self.child(row, col).clone() for col in range(self.columnCount())]
            new_item.appendRow(child_row)
        return new_item
    

def make_row(defaults, overrides=None, row_type=None):
    """
    Create row (Step/Group) using default values defined in consts.py
    """
    overrides = overrides or {}
    items = []
    for i, field in enumerate(protocol_grid_fields):
        value = overrides.get(field, defaults.get(field, ""))
        item = PGCItem(item_type=field, item_data=value)
        if field == "Description" and row_type:
            item.setData(row_type, ROW_TYPE_ROLE)
        if field == "ID":
            item.setEditable(False)
        else:
            item.setEditable(True)
        items.append(item)
    return items

def int_to_letters(n):
    result=''
    while n > 0:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result