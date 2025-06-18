from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (QStyledItemDelegate, QSpinBox, QDoubleSpinBox,
                               QLineEdit, QCheckBox)

from protocol_grid.consts import (protocol_grid_fields, 
                                  ROW_TYPE_ROLE 
                                  )


class ProtocolGridDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        col = index.column()
        field = protocol_grid_fields[col]
        if field in ("Label", "Message"):            
            return QLineEdit(parent)
        elif field in ("Repetitions", "Repeat Duration", "Trail Length"):
            editor = QSpinBox(parent)
            editor.setMinimum(1)
            editor.setMaximum(10000)
            return editor
        elif field == "Video":
            cb = QCheckBox(parent)
            cb.setText("")
            cb.setTristate(False)
            return cb
        elif field in ("Duration", "Voltage", "Frequency", "Volume Threshold"):
            editor = QDoubleSpinBox(parent)
            editor.setMinimum(0.0)
            editor.setMaximum(10000.0)
            editor.setDecimals(2)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        col = index.column()
        field = protocol_grid_fields[col]
        if isinstance(editor, QLineEdit):
            editor.setText(str(value) if value is not None else "")
        elif isinstance(editor, QSpinBox):
            editor.setValue(int(value) if value else 0)
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value) if value else 0.0)
        elif isinstance(editor, QCheckBox):
            editor.setChecked(bool(int(value)) if value not in (None, "") else False)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        col = index.column()
        field = protocol_grid_fields[col]
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QSpinBox):
            model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QDoubleSpinBox):
            model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
        elif isinstance(editor, QCheckBox):
            checked = int(editor.isChecked())
            model.setData(index, checked, Qt.ItemDataRole.EditRole)
            model.setData(index, Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            model.setData(index, "", Qt.DisplayRole)
        else:
            super().setModelData(editor, model, index)


class PGCItem(QStandardItem):
    def __init__(self, item_type=None, item_data=None):
        if item_type == "Video":
            item_data = ""
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
        for role in range(Qt.UserRole + 100):
            value = self.data(role)
            if value is not None:
                new_item.setData(value, role)

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
        display_value = "" if field == "Video" else value
        item = PGCItem(item_type=field, item_data=display_value)
        if field == "Description" and row_type:
            item.setData(row_type, ROW_TYPE_ROLE)
        if field == "ID":
            item.setEditable(False)
        else:
            item.setEditable(True)
        if field == "Video":
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable) # prevent editing anywhere else
                                                             # on the cell around the actual checkbox
            item.setData(Qt.Checked if str(value) in ("1", "True", "true")
                          else Qt.Unchecked, Qt.CheckStateRole)
        items.append(item)
    return items

def int_to_letters(n):
    result=''
    while n > 0:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result