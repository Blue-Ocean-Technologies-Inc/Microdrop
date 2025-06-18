from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (QMenu, QDialog, QVBoxLayout, 
                               QFrame, QToolButton, QWidget, 
                               QCheckBox, QDialogButtonBox)
from PySide6.QtGui import QAction, QCursor

from pyface.action.api import Action

from protocol_grid.consts import protocol_grid_fields, field_groupings, fixed_fields

class EditContextMenu(QMenu):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.widget = parent_widget
        self.build_menu()

    def build_menu(self):
        action_select_fields = QAction("Select Fields", self)
        action_select_fields.triggered.connect(self.widget.show_column_toggle_dialog)
        self.addAction(action_select_fields)
        self.addSeparator()
        actions = [
            ("Delete", self.widget.delete_selected),
            ("Insert Step Above", self.widget.insert_step),
            ("Insert Group Above", self.widget.insert_group),
            ("Copy", self.widget.copy_selected),
            ("Cut", self.widget.cut_selected),
            ("Paste Above", lambda: self.widget.paste_selected(above=True)),
            ("Paste Below", lambda: self.widget.paste_selected(above=False)),
            ("Undo", self.widget.undo_last),
            ("Redo", self.widget.redo_last)
        ]
        for name, slot in actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action)
        self.addSeparator()
        next_actions = [
            ("Select all rows", self.widget.select_all),
            ("Deselect rows", self.widget.deselect_rows),
            ("Invert row selection", self.widget.invert_row_selection)
        ]
        for name, slot in next_actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action)

    def popup_at(self, pos: QPoint):
        self.exec(self.widget.tree.viewport().mapToGlobal(pos))


class ShowEditContextMenuAction(Action):
    name = "Show Edit Context Menu"
    def __init__(self, widget, **kwargs):
        super().__init__(**kwargs)
        self.widget = widget

    def perform(self, event=None, pos=None):
        # Default to showing at mouse cursor if pos not given
        menu = EditContextMenu(self.widget)
        if pos is None:
            pos = QCursor.pos()
            menu.exec(pos)
        else:
            menu.popup_at(pos)


class ColumnToggleDialog(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.widget = parent_widget
        self.setWindowTitle("Options")
        self.checkboxes = []
        self.column_indices = []
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        field_to_idx = {field: i for i, field in enumerate(protocol_grid_fields)}
        first = True

        for group_label, fields in field_groupings:
            fields = [f for f in fields if f not in fixed_fields]
            if not fields:
                continue
            if not first:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                layout.addWidget(sep)
            first = False
            if group_label is not None:
                tool_btn = QToolButton()
                tool_btn.setText(f"  {group_label}")
                tool_btn.setCheckable(True)
                tool_btn.setChecked(True)
                tool_btn.setStyleSheet("QToolButton { font-weight: bold; border: none; }")
                tool_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                tool_btn.setArrowType(Qt.DownArrow)
                container = QWidget()
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)
                for field in fields:
                    idx = field_to_idx[field]
                    cb = QCheckBox(field)
                    cb.setChecked(not self.widget.tree.isColumnHidden(idx))
                    container_layout.addWidget(cb)
                    self.checkboxes.append(cb)
                    self.column_indices.append(idx)
                layout.addWidget(tool_btn)
                layout.addWidget(container)
                def make_toggle_func(btn=tool_btn, cont=container):
                    def toggle():
                        expanded = btn.isChecked()
                        cont.setVisible(expanded)
                        btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
                        self.adjustSize()
                    return toggle
                tool_btn.toggled.connect(make_toggle_func())
                container.setVisible(True)
                tool_btn.setArrowType(Qt.DownArrow)
            else:
                for field in fields:
                    idx = field_to_idx[field]
                    cb = QCheckBox(field)
                    cb.setChecked(not self.widget.tree.isColumnHidden(idx))
                    layout.addWidget(cb)
                    self.checkboxes.append(cb)
                    self.column_indices.append(idx)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(button_box)
        button_box.accepted.connect(self.apply_changes)
        button_box.rejected.connect(self.reject)

    def apply_changes(self):
        field_to_idx = {field: i for i, field in enumerate(protocol_grid_fields)}
        for cb, i in zip(self.checkboxes, self.column_indices):
            self.widget.tree.setColumnHidden(i, not cb.isChecked())
        for field in fixed_fields:
            idx = field_to_idx[field]
            self.widget.tree.setColumnHidden(idx, False)
        self.accept()


class ShowColumnToggleDialogAction(Action):
    name = "Show Column Toggle Dialog"
    def __init__(self, widget, **kwargs):
        super().__init__(**kwargs)
        self.widget = widget

    def perform(self, event=None):
        dialog = ColumnToggleDialog(self.widget)
        dialog.exec()