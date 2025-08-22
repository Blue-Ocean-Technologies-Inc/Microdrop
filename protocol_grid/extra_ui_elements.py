from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QMenu, QDialog, QVBoxLayout, QHBoxLayout,
                               QPushButton, QSizePolicy, QLabel, QLineEdit,
                               QFrame, QToolButton, QWidget, 
                               QCheckBox, QDialogButtonBox, QApplication)
from PySide6.QtGui import QAction, QCursor

from pyface.action.api import Action
from pyface.qt.QtWidgets import QTextBrowser
from traits.api import Str

from protocol_grid.consts import (protocol_grid_fields, field_groupings, fixed_fields,
                                  ROW_TYPE_ROLE, STEP_TYPE,
                                  DARK_MODE_STYLESHEET, LIGHT_MODE_STYLESHEET)
from microdrop_application.application import is_dark_mode
from microdrop_style.icons.icons import (ICON_FIRST, ICON_PREVIOUS, ICON_PLAY,
                                         ICON_STOP, ICON_NEXT,
                                         ICON_LAST, ICON_PREVIOUS_PHASE,
                                         ICON_NEXT_PHASE, ICON_RESUME)
from microdrop_style.colors import (WHITE, BLACK)

LABEL_FONT_FAMILY = "Inter"

# Button styling constants
BUTTON_SPACING = 2


class InformationPanel(QWidget):
    """shows device, protocol, experiment info, and button to open experiment directory."""    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.apply_styling()
    
    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)
        
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(5, 5, 5, 5)
        text_layout.setSpacing(3)
        
        # self.device_label = QLabel("Device: ")
        # self.device_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.protocol_label = QLabel("Protocol: untitled [not modified]")
        self.protocol_label.setAlignment(Qt.AlignLeft)
        
        self.experiment_label = QLabel("Experiment: ")
        self.experiment_label.setAlignment(Qt.AlignLeft)
        
        # layout.addWidget(self.device_label)
        text_layout.addWidget(self.protocol_label)
        text_layout.addWidget(self.experiment_label)
        
        self.open_button = QPushButton("folder_open")
        self.open_button.setToolTip("Open current experiment directory")
        
        layout.addLayout(text_layout)
        layout.addWidget(self.open_button, alignment=Qt.AlignLeft)
        layout.addStretch()
                
        self.setLayout(layout)
    
    def apply_styling(self):
        dark = is_dark_mode()
        
        if dark:
            text_color = WHITE
            button_style = DARK_MODE_STYLESHEET
        else:
            text_color = BLACK
            button_style = LIGHT_MODE_STYLESHEET
        
        label_style = f"QLabel {{ color: {text_color}; }}"
        
        # for label in [self.device_label, self.protocol_label, self.experiment_label]:
        for label in [self.protocol_label, self.experiment_label]:
            label.setStyleSheet(label_style)
        
        self.open_button.setStyleSheet(button_style)
    
    # def update_device_name(self, device_name):
    #     self.device_label.setText(f"Device: {device_name}")
    
    def update_protocol_name(self, protocol_display_name):
        self.protocol_label.setText(f"Protocol: {protocol_display_name}")
    
    def update_experiment_id(self, experiment_id):
        self.experiment_label.setText(f"Experiment: {experiment_id}")
    
    def update_theme_styling(self):
        self.apply_styling()


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
        self.button_layout.setSpacing(BUTTON_SPACING)

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
        self.play_phase_layout.setSpacing(BUTTON_SPACING)
        
        self.play_phase_layout.addWidget(self.btn_play)
        
        for btn in [self.btn_prev_phase, self.btn_resume, self.btn_next_phase]:
            btn.setVisible(False)
            self.play_phase_layout.addWidget(btn)
        
        # Set consistent sizing for all buttons
        all_buttons = [
            self.btn_first, self.btn_prev, self.btn_play,
            self.btn_stop, self.btn_next, self.btn_last,
            self.btn_prev_phase, self.btn_resume, self.btn_next_phase
        ]
        
        for btn in all_buttons:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.play_phase_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed)
        
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

        self.droplet_check_checkbox = QCheckBox("Droplet Check")
        self.droplet_check_checkbox.setToolTip(
            "When checked, droplet detection will be performed at the end of each step"
        )
        
        self.advanced_user_mode_checkbox = QCheckBox("Advanced User Mode")
        self.advanced_user_mode_checkbox.setToolTip(
            "When checked, navigation buttons remain enabled during protocol execution for advanced users"
        )
        
        self.preview_mode_checkbox = QCheckBox("Preview Mode")
        self.preview_mode_checkbox.setToolTip(
            "When checked, no hardware messages will be sent during protocol execution"
        )
        
        checkbox_layout.addWidget(self.preview_mode_checkbox)
        checkbox_layout.addWidget(self.droplet_check_checkbox)
        checkbox_layout.addWidget(self.advanced_user_mode_checkbox)
            
        main_layout.addLayout(self.button_layout)
        main_layout.addLayout(checkbox_layout)
        
        self.setLayout(main_layout)
        
        # apply initial styling
        self._apply_styling()
    
    def _apply_styling(self):
        dark = is_dark_mode()
        
        if dark:
            button_style = DARK_MODE_STYLESHEET
            checkbox_style = f"""
                QCheckBox {{
                    color: {WHITE};
                }}
            """
        else:
            button_style = LIGHT_MODE_STYLESHEET
            checkbox_style = f"""
                QCheckBox {{
                    color: {BLACK};
                }}
            """
        self.setStyleSheet(button_style)
        self.droplet_check_checkbox.setStyleSheet(checkbox_style)
        self.advanced_user_mode_checkbox.setStyleSheet(checkbox_style)
        self.preview_mode_checkbox.setStyleSheet(checkbox_style)
    
    def update_theme_styling(self):
        self._apply_styling()

    def is_droplet_check_enabled(self):
        return self.droplet_check_checkbox.isChecked()
    
    def is_preview_mode(self):
        return self.preview_mode_checkbox.isChecked()

    def is_advanced_user_mode(self):
        return self.advanced_user_mode_checkbox.isChecked()
    
    def set_droplet_check_enabled(self, enabled):
        self.droplet_check_checkbox.setEnabled(enabled)

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
        
        # Hide the phase buttons
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
        
        no_button = QPushButton("NO")
        no_button.setMinimumWidth(80)
        no_button.clicked.connect(self.reject)        
        
        yes_button = QPushButton("YES")
        yes_button.setDefault(True)
        yes_button.setMinimumWidth(80)
        yes_button.clicked.connect(self.accept)

        button_layout.addWidget(yes_button)
        button_layout.addWidget(no_button)
        
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
        self.reject()
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()  # Enter = YES
        elif event.key() == Qt.Key_Escape:
            self.reject()  # Escape = NO
        else:
            super().keyPressEvent(event)


class ExperimentCompleteDialog(QDialog):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setModal(True)
    
    def setup_ui(self):
        self.setWindowTitle("Experiment Complete")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        message_label = QLabel("Experiment complete. Would you like to start a new experiment?")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setMinimumWidth(400)
        message_label.setStyleSheet("QLabel { font-size: 14pt; padding: 15px; }")
        layout.addWidget(message_label)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        button_style = f"""
            QPushButton {{ 
                font-family: {LABEL_FONT_FAMILY}; 
            }}
        """
        
        no_button = QPushButton("NO")
        no_button.setStyleSheet(button_style)
        no_button.setMinimumWidth(100)
        no_button.clicked.connect(self.reject)        
        
        yes_button = QPushButton("YES")
        yes_button.setStyleSheet(button_style)
        yes_button.setDefault(True)
        yes_button.setMinimumWidth(100)
        yes_button.clicked.connect(self.accept)

        button_layout.addWidget(yes_button)
        button_layout.addWidget(no_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.adjustSize()
        
        # center on parent if available
        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    def show_completion_dialog(self):
        self.show()
        self.raise_()
        self.activateWindow()
        
    def closeEvent(self, event):
        self.reject()
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class DropbotDisconnectedBeforeRunDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dropbot Disconnected")
        self.setModal(True)
        self.setFixedSize(400, 350)

        self.preview_mode_requested = False  # track whether preview mode was requested

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        img_path = Path(__file__).parent.parent / "dropbot_status" / "images" / "dropbot-power-usb.png"

        html_content = f"""
        <html>
        <head></head>
        <body>
            <h3>DropBot is not connected.</h3>
            <strong>Plug in the DropBot USB cable and power supply.<br></strong>
            <img src='{img_path.as_posix()}' width="104" height="90">
            <strong><br>Click "OK" after connecting the DropBot and try again.</strong>
            <strong><br>OR</strong>
            <strong><br>Turn on Preview Mode and try again.</strong>
        </body>
        </html>
        """

        browser = QTextBrowser()
        browser.setHtml(html_content)
        browser.setOpenExternalLinks(True)
        browser.setAlignment(Qt.AlignCenter)
        layout.addWidget(browser)

        button_layout = QHBoxLayout()

        preview_button = QPushButton("Turn on Preview Mode")
        preview_button.clicked.connect(self._on_preview_mode_clicked)
        button_layout.addWidget(preview_button)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)

    def _on_preview_mode_clicked(self):
        self.preview_mode_requested = True
        self.accept()

    def was_preview_mode_requested(self):
        return self.preview_mode_requested


class DropbotDisconnectedBeforeRunDialogAction(Action):
    name = Str("Dropbot Disconnected Before Run Dialog")
    
    def perform(self, parent_widget):
        dialog_parent = None
        
        if parent_widget:
            dialog_parent = parent_widget.window()
            if not dialog_parent:
                dialog_parent = parent_widget
        
        if not dialog_parent:
            dialog_parent = QApplication.activeWindow()
        
        dialog = DropbotDisconnectedBeforeRunDialog(parent=dialog_parent)
        result = dialog.exec()
        
        if result == QDialog.Accepted:
            return dialog.was_preview_mode_requested()
        return False

    def close(self):
        if hasattr(self, 'dialog'):
            self.dialog.close()
            self.dialog = None


class DropletDetectionFailureDialog(QDialog):
    
    def __init__(self, expected_electrodes, detected_electrodes, missing_electrodes, parent=None):
        super().__init__(parent)
        self.expected_electrodes = expected_electrodes
        self.detected_electrodes = detected_electrodes
        self.missing_electrodes = missing_electrodes
        self.setup_ui()
        
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setModal(True)
    
    def setup_ui(self):
        self.setWindowTitle("Droplet Detection Failed")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Main message
        main_message = QLabel("Droplet detection failed at the end of this step.")
        main_message.setWordWrap(True)
        main_message.setAlignment(Qt.AlignCenter)
        main_message.setStyleSheet("QLabel { font-size: 14pt; font-weight: bold; color: #cc3300; }")
        layout.addWidget(main_message)
        
        # Details section
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)
        
        expected_label = QLabel(f"Expected droplets at: {', '.join(self.expected_electrodes) if self.expected_electrodes else 'None'}")
        expected_label.setWordWrap(True)
        expected_label.setStyleSheet("QLabel { font-size: 11pt; font-weight: bold; color: #cc3300; }")
        details_layout.addWidget(expected_label)
        
        detected_label = QLabel(f"Detected droplets at: {', '.join(self.detected_electrodes) if self.detected_electrodes else 'None'}")
        detected_label.setWordWrap(True)
        detected_label.setStyleSheet("QLabel { font-size: 11pt; font-weight: bold; color: #cc3300; }")
        details_layout.addWidget(detected_label)
        
        if self.missing_electrodes:
            missing_label = QLabel(f"Missing droplets at: {', '.join(self.missing_electrodes)}")
            missing_label.setWordWrap(True)
            missing_label.setStyleSheet("QLabel { font-size: 11pt; font-weight: bold; color: #cc3300; }")
            details_layout.addWidget(missing_label)
        
        details_widget.setStyleSheet("QWidget { background-color: #f5f5f5; border: 1px solid #cccccc; border-radius: 5px; }")
        layout.addWidget(details_widget)
        
        # Question
        question_label = QLabel("Would you like to continue with the protocol anyway?")
        question_label.setWordWrap(True)
        question_label.setAlignment(Qt.AlignCenter)
        question_label.setStyleSheet("QLabel { font-size: 12pt; margin: 10px 0; }")
        layout.addWidget(question_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        no_button = QPushButton("NO (Stay Paused)")
        no_button.setMinimumWidth(120)
        no_button.clicked.connect(self.reject)
        no_button.setStyleSheet("""
            QPushButton {
                background-color: #cc3300;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #aa2200;
            }
        """)
        
        yes_button = QPushButton("YES (Continue)")
        yes_button.setDefault(True)
        yes_button.setMinimumWidth(120)
        yes_button.clicked.connect(self.accept)
        yes_button.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0055aa;
            }
        """)
        
        button_layout.addWidget(yes_button)
        button_layout.addWidget(no_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        self.setMinimumWidth(450)
        self.adjustSize()
        
        # Center on parent if available
        if self.parent():
            parent_geometry = self.parent().geometry()
            x = parent_geometry.x() + (parent_geometry.width() - self.width()) // 2
            y = parent_geometry.y() + (parent_geometry.height() - self.height()) // 2
            self.move(x, y)
    
    def show_detection_dialog(self):
        self.show()
        self.raise_()
        self.activateWindow()
        
    def closeEvent(self, event):
        self.reject()
        event.accept()
    
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


class DropletDetectionFailureDialogAction(Action):
    name = Str("Droplet Detection Failure Dialog")
    
    def perform(self, expected_electrodes, detected_electrodes, missing_electrodes, parent_widget):
        dialog_parent = None
        
        if parent_widget:
            dialog_parent = parent_widget.window()
            if not dialog_parent:
                dialog_parent = parent_widget
        
        if not dialog_parent:
            dialog_parent = QApplication.activeWindow()
        
        dialog = DropletDetectionFailureDialog(
            expected_electrodes, detected_electrodes, missing_electrodes, 
            parent=dialog_parent
        )
        result = dialog.exec()
        
        return result == QDialog.Accepted

    def close(self):
        if hasattr(self, 'dialog'):
            self.dialog.close()
            self.dialog = None


def make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setLineWidth(1)
    return line