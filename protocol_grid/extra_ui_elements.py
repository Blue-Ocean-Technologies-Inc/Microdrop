from pathlib import Path

from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtWidgets import (QMenu, QDialog, QVBoxLayout, QHBoxLayout,
                               QPushButton, QSizePolicy, QLabel, QLineEdit,
                               QFrame, QToolButton, QWidget, QScrollArea,
                               QCheckBox, QDialogButtonBox, QApplication, QTextBrowser)
from pyface.qt.QtGui import QAction, QCursor, QContextMenuEvent

from pyface.action.api import Action

from traits.api import Str

from protocol_grid.consts import (protocol_grid_fields, field_groupings, 
                                  fixed_fields, ROW_TYPE_ROLE, STEP_TYPE,
                                  LIGHT_MODE_STYLESHEET, DARK_MODE_STYLESHEET)
from microdrop_style.helpers import is_dark_mode
from microdrop_style.icons.icons import (ICON_FIRST, ICON_PREVIOUS, ICON_PLAY,
                                         ICON_STOP, ICON_NEXT,
                                         ICON_LAST, ICON_PREVIOUS_PHASE,
                                         ICON_NEXT_PHASE, ICON_RESUME)
from microdrop_style.colors import (WHITE, BLACK)
from microdrop_style.button_styles import (
    get_button_dimensions, BUTTON_SPACING, get_button_style
)

LABEL_FONT_FAMILY = "Inter"

# Button styling constants (now imported from button_styles)
BUTTON_MIN_WIDTH, BUTTON_MIN_HEIGHT = get_button_dimensions("navigation")
BUTTON_MAX_WIDTH = 60
BUTTON_BORDER_RADIUS = 8
BUTTON_PADDING = 8


class ExperimentLabel(QLabel):
    """shows experiment info - clickable label"""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("<b>Experiment: </b>")
        self.setToolTip("Active Experiment (Click to open folder)")
        self.setCursor(Qt.PointingHandCursor)

        self._experiment_id = None

        self._tooltip_visible = True

        # apply initial styling and update whenever app color scheme changes
        self.apply_styling()
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_styling)

    def mousePressEvent(self, event):
        """Emit signal on left click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def handle_tooltip_toggle(self, checked):
        """Handler method when user requests tooltip toggle"""
        self._tooltip_visible = checked
        if checked:
            self.setToolTip("Active Experiment (Click to open folder)")
        else:
            self.setToolTip("")

    def contextMenuEvent(self, event: QContextMenuEvent):
        context_menu = QMenu(self)

        # Create Action
        tooltip_toggle_action = QAction("Enable Tooltip", checkable=True, checked=self._tooltip_visible)

        # Connect signal (checkable actions emit the bool state)
        tooltip_toggle_action.triggered.connect(self.handle_tooltip_toggle)

        context_menu.addAction(tooltip_toggle_action)

        # Use globalPos() for correct menu placement
        context_menu.exec(event.globalPos())

    def update_experiment_id(self, experiment_id=None):
        # if for style updates, id is None. Use the stored experiment id
        if experiment_id is None:
            experiment_id = self._experiment_id

        # Dark Mode Link: Soft Sky Blue (Good contrast on dark backgrounds)
        # Light Mode Link: Deep Primary Blue (Standard web-link style)
        link_color = "#82B1FF" if is_dark_mode() else "#0066CC"
        self.setText(
            f"<b>Experiment: </b> "
            f"<span style='text-decoration: underline; color: {link_color};'>{experiment_id}</span>"
        )

        self._experiment_id = experiment_id

    def apply_styling(self):
        # Define base colors (Soft White vs Soft Black/Charcoal)
        text_color = "#F0F0F0" if is_dark_mode() else "#333333"

        # Define hover background colors (Slightly lighter/darker than bg)
        hover_bg = "#3a3a3a" if is_dark_mode() else "#e0e0e0"

        self.setStyleSheet(
            f"""
            QLabel {{ 
                color: {text_color};
                padding: 2px;
                border-radius: 4px; /* Softens corners on hover */
            }}

            /* Visual feedback when hovering over the clickable area */
            QLabel:hover {{
                background-color: {hover_bg};
            }}
            """
        )

        self.update_experiment_id()

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

        # Create a LEFT SLOT container
        self.left_slot_container = QWidget()
        self.left_slot_layout = QHBoxLayout(self.left_slot_container)
        self.left_slot_layout.setContentsMargins(0, 0, 0, 0)
        self.left_slot_layout.setSpacing(5)

        # Add the left slot to the layout FIRST
        checkbox_layout.addWidget(self.left_slot_container)

        # 2. Add Stretch (pushes left slot to left, checkboxes to right)
        checkbox_layout.addStretch()

        # Add Checkboxes
        self.droplet_check_checkbox = QCheckBox("Droplet Check")
        self.droplet_check_checkbox.setToolTip( "Droplet Detection on step end")

        self.preview_mode_checkbox = QCheckBox("Preview Mode")
        msg = "Send no hardware messages on protocol run and do not trigger errors."
        self.preview_mode_checkbox.setToolTip(f"<div style='width: 150px;'>{msg}</div>")

        self.advanced_user_mode_checkbox = QCheckBox("Advanced User Mode")
        self.advanced_user_mode_checkbox.setToolTip(
            "When checked, navigation buttons remain enabled during protocol execution for advanced users"
        )
        self.advanced_user_mode_checkbox.setVisible(False)
        
        checkbox_layout.addWidget(self.preview_mode_checkbox)
        checkbox_layout.addWidget(self.droplet_check_checkbox)
        # checkbox_layout.addWidget(self.advanced_user_mode_checkbox)

        main_layout.addLayout(self.button_layout)
        main_layout.addLayout(checkbox_layout)
        
        self.setLayout(main_layout)
        
        # apply initial styling
        self._apply_styling()
    
    def _apply_styling(self):
        if is_dark_mode():
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

    def add_widget_to_left_slot(self, widget):
        """Helper to add widgets to the bottom-left area."""
        self.left_slot_layout.addWidget(widget)


class StatusBar(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 1. Create a container widget for all the status bar items.
        #    This widget will be the one that actually scrolls.
        scroll_content = QWidget()

        # 2. The layout is now applied to the container widget, not the main class.
        layout = QHBoxLayout(scroll_content)
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
        self.lbl_repeat_protocol.setFixedWidth(140)
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
        repeat_widget.setFixedWidth(170)
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

        # --- Configure the QScrollArea itself ---

        # 3. Set the container as the scroll area's widget.
        self.setWidget(scroll_content)
        self.setWidgetResizable(True)

        # 4. We only want a horizontal scrollbar, never a vertical one.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 5. Adjust the height to account for the scrollbar itself.
        self.setFixedHeight(40)
        
        # Apply initial styling
        self._apply_styling()
    
    def _apply_styling(self):
        """Apply theme-specific styling to all labels and input fields."""
        if is_dark_mode():
            text_color = WHITE
            input_style = f"""
                QLineEdit {{
                    color: {WHITE};
                    background-color: #2d2d2d;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 2px;
                }}
            """
        else:
            text_color = BLACK
            input_style = f"""
                QLineEdit {{
                    color: {BLACK};
                    background-color: white;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    padding: 2px;
                }}
            """
        
        label_style = f"QLabel {{ color: {text_color}; }}"
        
        # Apply styling to all labels
        all_labels = [
            self.lbl_total_time, self.lbl_step_time, self.lbl_repeat_protocol,
            self.lbl_repeat_protocol_status, self.lbl_step_progress,
            self.lbl_step_repetition, self.lbl_recent_step, self.lbl_next_step
        ]
        
        for label in all_labels:
            label.setStyleSheet(label_style)
        
        # Apply styling to input field
        self.edit_repeat_protocol.setStyleSheet(input_style)
    
    def update_theme_styling(self):
        """Update theme styling when theme changes."""
        self._apply_styling()


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
            ("Save As", self.widget.export_to_json),
            ("Load", self.widget.import_from_json),
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
        
        # Use centralized button styles
        no_button = QPushButton("NO")
        no_button.setStyleSheet(get_button_style("light", "default"))
        no_button.setMinimumWidth(100)
        no_button.clicked.connect(self.reject)        
        
        yes_button = QPushButton("YES")
        yes_button.setStyleSheet(get_button_style("light", "default"))
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

        # Use centralized button styles
        no_button = QPushButton("NO")
        no_button.setStyleSheet(get_button_style("light", "default"))
        no_button.setMinimumWidth(100)
        no_button.clicked.connect(self.reject)        
        
        yes_button = QPushButton("YES")
        yes_button.setStyleSheet(get_button_style("light", "default"))
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
        
        # Use centralized button styles
        no_button = QPushButton("NO (Stay Paused)")
        no_button.setStyleSheet(get_button_style("light", "default"))
        no_button.setMinimumWidth(120)
        no_button.clicked.connect(self.reject)
        
        yes_button = QPushButton("YES (Continue)")
        yes_button.setStyleSheet(get_button_style("light", "default"))
        yes_button.setDefault(True)
        yes_button.setMinimumWidth(120)
        yes_button.clicked.connect(self.accept)
        
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