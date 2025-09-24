from PySide6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QVBoxLayout, 
                                QLabel, QGridLayout)
from PySide6.QtCore import Qt
from pathlib import Path

from microdrop_style.icons.icons import (ICON_AUTOMATION, ICON_DRAW, ICON_EDIT, 
                                         ICON_RESET_WRENCH)
from microdrop_style.button_styles import get_complete_stylesheet
from microdrop_style.font_paths import load_material_symbols_font

# Load the Material Symbols font using the clean API
ICON_FONT_FAMILY = load_material_symbols_font() or "Material Symbols Outlined"


def if_editable(func):
    """Decorator to check if the model is editable before executing the function."""
    def wrapper(self, *args, **kwargs):
        if not self.model.editable:
            # Ensure buttons and label are in sync with the model state
            self.sync_buttons_and_label()
            return
        return func(self, *args, **kwargs)
    return wrapper


class ModePicker(QWidget):
    def __init__(self, model, pane):
        super().__init__()
        self.pane = pane
        self.model = model

        # Apply theme-aware styling
        self._apply_theme_styling()

        # Make checkable buttons
        self.button_draw = QPushButton(ICON_DRAW)
        self.button_draw.setToolTip("Draw")

        self.button_edit = QPushButton(ICON_EDIT)
        self.button_edit.setToolTip("Edit")

        self.button_autoroute = QPushButton(ICON_AUTOMATION)
        self.button_autoroute.setToolTip("Autoroute")

        self.button_reset_routes = QPushButton(ICON_RESET_WRENCH)
        self.button_reset_routes.setToolTip("Reset Routes")

        # TODO: Choose better icons for these buttons
        self.button_reset_electrodes = QPushButton("reset_settings")
        self.button_reset_electrodes.setToolTip("Reset Electrode States")

        self.button_channel_edit = QPushButton("Numbers")
        self.button_channel_edit.setToolTip("Edit Electrode Channels")

        self.button_undo = QPushButton("Undo")
        self.button_undo.setToolTip("Undo")

        self.button_redo = QPushButton("Redo")
        self.button_redo.setToolTip("Redo")

        # Use grid layout for better organization - 2 rows
        btn_layout = QGridLayout()
        
        # Row 1: Mode selection buttons (checkable)
        btn_layout.addWidget(self.button_draw, 0, 0)
        btn_layout.addWidget(self.button_edit, 0, 1)
        btn_layout.addWidget(self.button_autoroute, 0, 2)
        btn_layout.addWidget(self.button_channel_edit, 0, 3)
        
        # Row 2: Action buttons (non-checkable)
        btn_layout.addWidget(self.button_reset_routes, 1, 0)
        btn_layout.addWidget(self.button_reset_electrodes, 1, 1)
        btn_layout.addWidget(self.button_undo, 1, 2)
        btn_layout.addWidget(self.button_redo, 1, 3)
        
        # Add stretch to the right of the grid to expand it
        btn_layout.setColumnStretch(4, 1)
        
        # Make mode selection buttons checkable
        for btn in (self.button_draw, self.button_edit, 
                   self.button_autoroute, self.button_channel_edit):
            btn.setCheckable(True)
        
        # Main layout
        layout = QVBoxLayout()
        
        # Mode label
        self.mode_label = QLabel()
        layout.addWidget(self.mode_label)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.sync_buttons_and_label()

        # Connect button signals
        self.button_draw.clicked.connect(lambda: self.set_mode("draw"))
        self.button_edit.clicked.connect(lambda: self.set_mode("edit"))
        self.button_autoroute.clicked.connect(lambda: self.set_mode("auto"))
        self.button_channel_edit.clicked.connect(
            lambda: self.set_mode("channel-edit"))
        self.button_reset_routes.clicked.connect(lambda: self.reset_routes())
        self.button_reset_electrodes.clicked.connect(
            lambda: self.reset_electrodes())
        self.button_undo.clicked.connect(lambda: self.undo())
        self.button_redo.clicked.connect(lambda: self.redo())
        self.model.observe(self.on_mode_changed, "mode")

    def _apply_theme_styling(self):
        """Apply theme-aware styling to the widget."""
        try:
            # Import here to avoid circular imports
            from microdrop_application.application import is_dark_mode
            
            theme = "dark" if is_dark_mode() else "light"
            # Use complete stylesheet with tooltips for icon buttons
            icon_button_style = get_complete_stylesheet(theme, "default")
            self.setStyleSheet(icon_button_style)
        except Exception as e:
            # Fallback to light theme if there's an error
            icon_button_style = get_complete_stylesheet("light", "default")
            self.setStyleSheet(icon_button_style)

    def update_theme_styling(self, theme="light"):
        """Update styling when theme changes."""
        icon_button_style = get_complete_stylesheet(theme, "default")
        self.setStyleSheet(icon_button_style)

    def on_mode_changed(self, event):
        self.sync_buttons_and_label()

    def sync_buttons_and_label(self):
        """Set checked states and label based on model.mode."""
        self.button_draw.setChecked(self.model.mode in ("draw", "edit-draw"))
        self.button_edit.setChecked(self.model.mode == "edit")
        self.button_autoroute.setChecked(self.model.mode == "auto")
        self.button_channel_edit.setChecked(self.model.mode == "channel-edit")
        self.mode_label.setText(f"Mode: {self.model.mode_name}")

    @if_editable
    def set_mode(self, mode):
        self.model.mode = mode
        self.sync_buttons_and_label()

    @if_editable
    def undo(self):
        self.pane.undo()

    @if_editable
    def redo(self):
        self.pane.redo()

    @if_editable
    def reset_electrodes(self):
        self.model.reset_electrode_states()

    @if_editable
    def reset_routes(self):
        self.model.reset_route_manager()