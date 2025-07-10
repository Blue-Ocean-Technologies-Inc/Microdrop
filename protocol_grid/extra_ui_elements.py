from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (QMenu, QDialog, QVBoxLayout, QHBoxLayout,
                               QPushButton, QSizePolicy, QLabel, QLineEdit,
                               QFrame, QToolButton, QWidget, 
                               QCheckBox, QDialogButtonBox)
from PySide6.QtGui import QAction, QCursor

from pyface.action.api import Action

from protocol_grid.consts import protocol_grid_fields, field_groupings, fixed_fields


class NavigationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        btns = [
            QPushButton("⏮ First"),
            QPushButton("◀ Previous"),
            QPushButton("▶ Play"),
            QPushButton("■ Stop"),
            QPushButton("Next ▶"),
            QPushButton("Last ⏭")
        ]
        for btn in btns:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(btn)

        self.btn_first, self.btn_prev, self.btn_play, self.btn_stop, self.btn_next, self.btn_last = btns
        self.setLayout(layout)


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.lbl_total_time = QLabel("Total Time: 0.00 s")
        self.lbl_step_time = QLabel("Step Time: 0.00 s")

        repeat_layout = QHBoxLayout()
        repeat_layout.setContentsMargins(0, 0, 0, 0)
        repeat_layout.setSpacing(0)
        self.lbl_repeat_protocol = QLabel("Repeat Protocol:")
        self.lbl_repeat_protocol_status = QLabel("1/")
        self.edit_repeat_protocol = QLineEdit("1")
        self.edit_repeat_protocol.setFixedWidth(40)
        for widget in [self.lbl_repeat_protocol, self.lbl_repeat_protocol_status, self.edit_repeat_protocol]:
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            repeat_layout.addWidget(widget)
        repeat_widget = QWidget()
        repeat_widget.setLayout(repeat_layout)
        repeat_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.lbl_step_progress = QLabel("Step 0/0")
        self.lbl_step_repetition = QLabel("Repetition 0/0")
        self.lbl_recent_step = QLabel("Most Recent Step: -")
        self.lbl_next_step = QLabel("Next Step: -")

        for widget in [
            self.lbl_total_time, self.lbl_step_time,
            self.lbl_step_progress, self.lbl_step_repetition,
            self.lbl_recent_step, self.lbl_next_step
        ]:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout.addWidget(self.lbl_total_time)
        layout.addWidget(self.lbl_step_time)
        layout.addWidget(repeat_widget)
        layout.addSpacing(30)
        layout.addWidget(self.lbl_step_progress)
        layout.addWidget(self.lbl_step_repetition)
        layout.addWidget(self.lbl_recent_step)
        layout.addWidget(self.lbl_next_step)

        self.setLayout(layout)


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
        
        structural_actions = [
            ("Insert Step Above", self.widget.insert_step),
            ("Insert Group Above", self.widget.insert_group),
            ("Delete", self.widget.delete_selected),
        ]
        for name, slot in structural_actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action)
            
        self.addSeparator()
        
        clipboard_actions = [
            ("Copy", self.widget.copy_selected),
            ("Cut", self.widget.cut_selected),
            ("Paste Above", lambda: self.widget.paste_selected(above=True)),
            ("Paste Below", lambda: self.widget.paste_selected(above=False)),
            ("Paste Into", self.widget.paste_into),
        ]
        for name, slot in clipboard_actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action)
            
        self.addSeparator()
        
        undo_actions = [
            ("Undo", self.widget.undo_last),
            ("Redo", self.widget.redo_last)
        ]
        for name, slot in undo_actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action)
        self.addSeparator()
        
        selection_actions = [
            ("Select All", self.widget.select_all),
            ("Deselect All", self.widget.deselect_rows),
            ("Invert Selection", self.widget.invert_row_selection)
        ]
        for name, slot in selection_actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action) 
        self.addSeparator()
        
        import_export_actions = [
            ("Import Into", self.widget.import_into_json),
            ("Export to JSON", self.widget.export_to_json),
            ("Import from JSON", self.widget.import_from_json),
        ]
        for name, slot in import_export_actions:
            action = QAction(name, self)
            action.triggered.connect(slot)
            self.addAction(action)
            
        self.addSeparator()


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
        self.setWindowTitle("Select Fields")
        self.setModal(True)
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

    
def make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)
    return line