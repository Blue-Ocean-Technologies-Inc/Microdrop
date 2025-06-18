from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMenu, QDialog, QVBoxLayout,
                               QFrame, QToolButton, QWidget,
                               QCheckBox, QDialogButtonBox)
from PySide6.QtGui import (QAction)

from protocol_grid.consts import (protocol_grid_fields, field_groupings,
                                  fixed_fields) 

def edit_context_menu(self, pos):
    index = self.tree.indexAt(pos)
    if not index.isValid():
        return
    menu = QMenu(self)

    action_select_fields = QAction("Select Fields", self)
    action_select_fields.triggered.connect(self.show_column_toggle_dialog)
    menu.addAction(action_select_fields)

    menu.addSeparator()

    actions = [
        ("Delete", self.delete_selected),
        ("Insert Step Above", self.insert_step),
        ("Insert Group Above", self.insert_group),
        ("Copy", self.copy_selected),
        ("Cut", self.cut_selected),
        ("Paste Above", lambda: self.paste_selected(above=True)),
        ("Paste Below", lambda: self.paste_selected(above=False)),
        ("Undo", self.undo_last),
        ("Redo", self.redo_last)
    ]
    for name, slot in actions:
        action = QAction(name, self)
        action.triggered.connect(slot)
        menu.addAction(action)

    menu.addSeparator()

    next_actions = [
        ("Select all rows", self.select_all),
        ("Deselect rows", self.deselect_rows),
        ("Invert row selection", self.invert_row_selection)
    ]
    for name, slot in next_actions:
        action = QAction(name, self)
        action.triggered.connect(slot)
        menu.addAction(action)

    menu.exec(self.tree.viewport().mapToGlobal(pos))

def column_toggle_dialog(self, pos):
    dialog = QDialog(self)
    dialog.setWindowTitle("Options")
    layout = QVBoxLayout(dialog)
    checkboxes = []
    column_indices = []
    field_to_idx = {field: i for i, field in enumerate(protocol_grid_fields)}
    first = True
    group_containers = []

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
            tool_btn = QToolButton() # clickable label
            tool_btn.setText(f"  {group_label}")
            tool_btn.setCheckable(True)
            tool_btn.setChecked(True)
            tool_btn.setStyleSheet("QToolButton { font-weight: bold; border: none; }")
            tool_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            tool_btn.setArrowType(Qt.DownArrow)  # to start as expanded

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)
            group_cbs = []

            for field in fields:
                idx = field_to_idx[field]
                cb = QCheckBox(field)
                cb.setChecked(not self.tree.isColumnHidden(idx))
                container_layout.addWidget(cb)
                checkboxes.append(cb)
                column_indices.append(idx)
                group_cbs.append(cb)
            layout.addWidget(tool_btn)
            layout.addWidget(container)

            def make_toggle_func(btn=tool_btn, cont=container):
                def toggle():
                    expanded = btn.isChecked()
                    cont.setVisible(expanded)
                    btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
                    dialog.adjustSize()
                return toggle

            tool_btn.toggled.connect(make_toggle_func())
            container.setVisible(True)
            tool_btn.setArrowType(Qt.DownArrow)
            group_containers.append((tool_btn, container))
        else:
            for field in fields:
                idx = field_to_idx[field]
                cb = QCheckBox(field)
                cb.setChecked(not self.tree.isColumnHidden(idx))
                layout.addWidget(cb)
                checkboxes.append(cb)
                column_indices.append(idx)

    button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    layout.addWidget(button_box)

    def apply_changes():
        for cb, i in zip(checkboxes, column_indices):
            self.tree.setColumnHidden(i, not cb.isChecked())
        for field in fixed_fields:
            idx = field_to_idx[field]
            self.tree.setColumnHidden(idx, False)
        dialog.accept() 

    button_box.accepted.connect(apply_changes)
    button_box.rejected.connect(dialog.reject)
    dialog.exec()