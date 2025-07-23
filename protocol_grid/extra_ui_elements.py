from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtWidgets import (QMenu, QDialog, QVBoxLayout, QHBoxLayout,
                               QPushButton, QSizePolicy, QLabel, QLineEdit,
                               QFrame, QToolButton, QWidget, 
                               QCheckBox, QDialogButtonBox)
from PySide6.QtGui import QAction, QCursor

from pyface.action.api import Action

from protocol_grid.consts import (protocol_grid_fields, field_groupings, fixed_fields,
                                  ROW_TYPE_ROLE, STEP_TYPE)
from microdrop_style.icons.icons import (ICON_FIRST, ICON_PREVIOUS, ICON_PLAY,
                                         ICON_PAUSE, ICON_STOP, ICON_NEXT,
                                         ICON_LAST, ICON_PREVIOUS_PHASE,
                                         ICON_NEXT_PHASE, ICON_RESUME)
from microdrop_style.colors import SECONDARY_SHADE, WHITE

ICON_FONT_FAMILY = "Material Symbols Outlined"


class NavigationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # VLayout: Navigation buttons above checkbox
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)
        
        # HLayout: Navigation buttons
        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.setSpacing(0)

        self.setStyleSheet(f"QPushButton {{ font-family: { ICON_FONT_FAMILY }; font-size: 22px; padding: 2px 2px 2px 2px; }} QPushButton:hover {{ color: { SECONDARY_SHADE[700] }; }} QPushButton:checked {{ background-color: { SECONDARY_SHADE[900] }; color: { WHITE }; }}")

        # main navigation buttons
        self.btn_first = QPushButton(ICON_FIRST)
        self.btn_first.setToolTip("First Step")

        self.btn_prev = QPushButton(ICON_PREVIOUS)
        self.btn_prev.setToolTip("Previous Step")

        self.btn_stop = QPushButton(ICON_STOP)
        self.btn_stop.setToolTip("Stop Protocol")

        self.btn_next = QPushButton(ICON_NEXT)
        self.btn_next.setToolTip("Next Step")

        self.btn_last = QPushButton(ICON_LAST)
        self.btn_last.setToolTip("Last Step")

        self.btn_play = QPushButton(ICON_PLAY)
        self.btn_play.setToolTip("Play Protocol")
        
        # phase navigation buttons (initially hidden)
        self.btn_prev_phase = QPushButton(ICON_PREVIOUS_PHASE)
        self.btn_prev_phase.setToolTip("Previous Phase")

        self.btn_resume = QPushButton(ICON_RESUME)
        self.btn_resume.setToolTip("Resume Protocol")

        self.btn_next_phase = QPushButton(ICON_NEXT_PHASE)
        self.btn_next_phase.setToolTip("Next Phase")

        # container widget for the play/phase buttons area
        self.play_phase_container = QWidget()
        self.play_phase_layout = QHBoxLayout(self.play_phase_container)
        self.play_phase_layout.setContentsMargins(0, 0, 0, 0)
        self.play_phase_layout.setSpacing(0)
        
        self.play_phase_layout.addWidget(self.btn_play)
        
        for btn in [self.btn_prev_phase, self.btn_resume, self.btn_next_phase]:
            btn.setVisible(False)
            self.play_phase_layout.addWidget(btn)
        
        for btn in [self.btn_first, self.btn_prev, self.btn_play, self.btn_stop, self.btn_next, self.btn_last]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        for btn in [self.btn_prev_phase, self.btn_resume, self.btn_next_phase]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.play_phase_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        # add in correct order
        self.button_layout.addWidget(self.btn_first)
        self.button_layout.addWidget(self.btn_prev)
        self.button_layout.addWidget(self.play_phase_container)
        self.button_layout.addWidget(self.btn_stop)
        self.button_layout.addWidget(self.btn_next)
        self.button_layout.addWidget(self.btn_last)
        
        # track navigation state
        self._phase_navigation_active = False
        
        checkbox_layout = QHBoxLayout()
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setSpacing(10)
        
        # right-align checkboxes
        checkbox_layout.addStretch()
        
        self.advanced_user_mode_checkbox = QCheckBox("Advanced User Mode")
        self.advanced_user_mode_checkbox.setToolTip("When checked, navigation buttons remain enabled during protocol execution for advanced users")
        checkbox_layout.addWidget(self.advanced_user_mode_checkbox)
        
        self.preview_mode_checkbox = QCheckBox("Preview Mode")
        self.preview_mode_checkbox.setToolTip("When checked, no hardware messages will be sent during protocol execution")
        checkbox_layout.addWidget(self.preview_mode_checkbox)
        
        main_layout.addLayout(self.button_layout)
        main_layout.addLayout(checkbox_layout)
        
        self.setLayout(main_layout)
    
    def is_preview_mode(self):
        return self.preview_mode_checkbox.isChecked()

    def is_advanced_user_mode(self):
        return self.advanced_user_mode_checkbox.isChecked()

    def set_preview_mode_enabled(self, enabled):
        self.preview_mode_checkbox.setEnabled(enabled)

    def set_advanced_user_mode_enabled(self, enabled):
        self.advanced_user_mode_checkbox.setEnabled(enabled)
    
    def split_play_button_to_phase_controls(self):
        if self._phase_navigation_active:
            return
            
        self._phase_navigation_active = True
        
        self.btn_play.setVisible(False)
        
        self.btn_prev_phase.setVisible(True)
        self.btn_resume.setVisible(True)
        self.btn_next_phase.setVisible(True)
        
        # force layout update
        self.play_phase_container.update()
        self.update()
    
    def merge_phase_controls_to_play_button(self):
        if not self._phase_navigation_active:
            return
            
        self._phase_navigation_active = False
        
        # Hide the phase  buttons
        self.btn_prev_phase.setVisible(False)
        self.btn_resume.setVisible(False) 
        self.btn_next_phase.setVisible(False)
        
        self.btn_play.setVisible(True)
        
        # force layout update
        self.play_phase_container.update()
        self.update()
    
    def set_phase_navigation_enabled(self, prev_enabled, next_enabled):
        self.btn_prev_phase.setEnabled(prev_enabled)
        self.btn_next_phase.setEnabled(next_enabled)
    
    def is_phase_navigation_active(self):
        return self._phase_navigation_active


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(10)

        self.lbl_total_time = QLabel("Total Time: 0.00 s")
        self.lbl_total_time.setFixedWidth(120)
        self.lbl_total_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.lbl_step_time = QLabel("Step Time: 0.00 s")
        self.lbl_step_time.setFixedWidth(115)
        self.lbl_step_time.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        repeat_layout = QHBoxLayout()
        repeat_layout.setContentsMargins(0, 0, 0, 0)
        repeat_layout.setSpacing(2)
        
        self.lbl_repeat_protocol = QLabel("Repeat Protocol:")
        self.lbl_repeat_protocol.setFixedWidth(100)
        self.lbl_repeat_protocol.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.lbl_repeat_protocol_status = QLabel("1/")
        self.lbl_repeat_protocol_status.setFixedWidth(20)
        self.lbl_repeat_protocol_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.edit_repeat_protocol = QLineEdit("1")
        self.edit_repeat_protocol.setFixedWidth(30)
        self.edit_repeat_protocol.setAlignment(Qt.AlignCenter)
        self.edit_repeat_protocol.setFixedHeight(20)
        
        repeat_layout.addWidget(self.lbl_repeat_protocol)
        repeat_layout.addWidget(self.lbl_repeat_protocol_status)
        repeat_layout.addWidget(self.edit_repeat_protocol)
        
        repeat_widget = QWidget()
        repeat_widget.setLayout(repeat_layout)
        repeat_widget.setFixedWidth(150)
        repeat_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        repeat_widget.setFixedHeight(20)

        self.lbl_step_progress = QLabel("Step 0/0")
        self.lbl_step_progress.setFixedWidth(80)
        self.lbl_step_progress.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.lbl_step_repetition = QLabel("Repetition 0/0")
        self.lbl_step_repetition.setFixedWidth(100)
        self.lbl_step_repetition.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.lbl_recent_step = QLabel("Most Recent Step: -")
        self.lbl_recent_step.setFixedWidth(200)
        self.lbl_recent_step.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.lbl_next_step = QLabel("Next Step: -")
        self.lbl_next_step.setFixedWidth(180)
        self.lbl_next_step.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for widget in [self.lbl_total_time, self.lbl_step_time, self.lbl_step_progress, 
                      self.lbl_step_repetition, self.lbl_recent_step, self.lbl_next_step]:
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            widget.setFixedHeight(20)

        layout.addWidget(self.lbl_total_time)
        layout.addWidget(self.lbl_step_time)
        layout.addWidget(repeat_widget)
        layout.addWidget(self.lbl_step_progress)
        layout.addWidget(self.lbl_step_repetition)
        layout.addWidget(self.lbl_recent_step)
        layout.addWidget(self.lbl_next_step)
        
        # push everything to the left
        layout.addStretch()

        self.setLayout(layout)
        
        self.setFixedHeight(25)


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
        
        run_step_action = QAction("Run Step", self)
        run_step_action.triggered.connect(self.widget.run_selected_step)
        
        selected_paths = self.widget.get_selected_paths()
        has_step_selected = any(
            self.widget.get_item_by_path(path) and 
            self.widget.get_item_by_path(path).data(ROW_TYPE_ROLE) == STEP_TYPE 
            for path in selected_paths
        )
        
        run_step_action.setEnabled(not self.widget._protocol_running and has_step_selected)
        
        self.addAction(run_step_action)


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


class StepMessageDialog(QDialog):
    
    def __init__(self, message: str, step_info: str, parent=None):
        super().__init__(parent)
        self.message = message
        self.step_info = step_info
        self.setup_ui()
        
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setModal(True)
    
    def setup_ui(self):
        self.setWindowTitle("Step Message")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        if self.step_info:
            step_label = QLabel(f"<b>{self.step_info}</b>")
            step_label.setAlignment(Qt.AlignCenter)
            step_label.setStyleSheet("QLabel { color: #0066cc; margin-bottom: 5px; }")
            layout.addWidget(step_label)
        
        message_label = QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setMinimumWidth(300)
        message_label.setMaximumWidth(500)
        message_label.setStyleSheet("QLabel { font-size: 12pt; padding: 10px; }")
        layout.addWidget(message_label)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.setMinimumWidth(80)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.adjustSize()
        
        # center on parent if available
        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    def show_message(self):
        self.show()
        self.raise_()
        self.activateWindow()
        
    def closeEvent(self, event):
        self.accept()
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.accept()
        else:
            super().keyPressEvent(event)

    
def make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)
    return line