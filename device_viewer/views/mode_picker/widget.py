from functools import partial

from traits.api import HasTraits, Instance, Any, observe, Property
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QLabel,
                               QGridLayout)

from pyface.tasks.dock_pane import DockPane

from device_viewer.models.main_model import DeviceViewMainModel
# Imports from your context
from microdrop_style.icons.icons import (ICON_AUTOMATION, ICON_DRAW,
                                         ICON_EDIT, ICON_RESET_WRENCH)
from microdrop_style.button_styles import get_complete_stylesheet

try:
    from microdrop_style.helpers import is_dark_mode
except ImportError:
    # Fallback if helper is missing in this context
    is_dark_mode = lambda: False


def if_editable(func):
    """Decorator to check if the model is editable before executing the function."""
    def wrapper(self, *args, **kwargs):
        if not self.model.editable:
            # Ensure buttons and label are in sync with the model state
            self.sync_buttons_and_label()
            return
        return func(self, *args, **kwargs)
    return wrapper


# ==========================================
# 1. THE SIGNAL BRIDGE
# ==========================================
class ModePickerSignals(QObject):
    """
    Qt Signals for the ModePicker ViewModel.
    """
    # Emitted when the mode or editability changes, requiring a UI refresh
    state_changed = Signal()

# ==========================================
# 2. THE VIEW MODEL
# ==========================================
class ModePickerViewModel(HasTraits):
    """
    Handles logic for mode switching, undo/redo, and validation.
    """
    # Dependencies (The "Model" layers this VM wraps)
    model = Instance(DeviceViewMainModel)
    pane = Instance(DockPane)
    signals = Instance(ModePickerSignals)

    current_mode = Property(observe="model.mode")
    mode_name = Property(observe="model.mode_name")
    is_editable = Property(observe="model.editable")

    def traits_init(self):
        self.signals = ModePickerSignals()

    # -- Properties for the View --
    def _get_current_mode(self):
        return self.model.mode

    def _get_mode_name(self):
        return self.model.mode_name

    def _get_is_editable(self):
        return self.model.editable

    # -- Actions --
    @if_editable
    def set_mode(self, mode):
        self.model.flip_mode_activation(mode)

    @if_editable
    def undo(self):
        self.pane.undo()

    @if_editable
    def redo(self):
        self.pane.redo()

    @if_editable
    def reset_electrodes(self):
        self.model.electrodes.clear_electrode_states()

    @if_editable
    def reset_routes(self):
        self.model.routes.clear_routes()

    @observe('model:mode')
    def _on_underlying_mode_changed(self, event):
        """Forward underlying model changes to the Qt View."""
        self.signals.state_changed.emit()


# ==========================================
# 3. THE VIEW
# ==========================================
class ModePicker(QWidget):
    def __init__(self, view_model: 'ModePickerViewModel'):
        super().__init__()
        self.vm = view_model

        # Setup UI components
        self._init_ui_elements()
        self._layout_ui()
        self._apply_theme_styling()

        # Initial State Sync
        self.sync_ui()

        # Connect Signals
        self._bind_signals()

    def _init_ui_elements(self):
        # Mode Buttons
        self.button_draw = QPushButton(ICON_DRAW)
        self.button_draw.setToolTip("Draw")
        self.button_draw.setCheckable(True)

        self.button_edit = QPushButton(ICON_EDIT)
        self.button_edit.setToolTip("Edit")
        self.button_edit.setCheckable(True)

        self.button_autoroute = QPushButton(ICON_AUTOMATION)
        self.button_autoroute.setToolTip("Autoroute")
        self.button_autoroute.setCheckable(True)

        self.button_channel_edit = QPushButton("Numbers")
        self.button_channel_edit.setToolTip("Edit Electrode Channels")
        self.button_channel_edit.setCheckable(True)

        # Action Buttons
        self.button_reset_routes = QPushButton("remove_road")
        self.button_reset_routes.setToolTip("Clear Routes")

        self.button_reset_electrodes = QPushButton("layers_clear")
        self.button_reset_electrodes.setToolTip("Clear Electrode States")

        self.button_undo = QPushButton("Undo")
        self.button_undo.setToolTip("Undo")

        self.button_redo = QPushButton("Redo")
        self.button_redo.setToolTip("Redo")

        self.mode_label = QLabel()

    def _layout_ui(self):
        btn_layout = QGridLayout()

        # Row 1: Mode selection
        btn_layout.addWidget(self.button_draw, 0, 0)
        btn_layout.addWidget(self.button_edit, 0, 1)
        btn_layout.addWidget(self.button_autoroute, 0, 2)
        btn_layout.addWidget(self.button_channel_edit, 0, 3)

        # Row 2: Actions
        btn_layout.addWidget(self.button_reset_electrodes, 1, 0)
        btn_layout.addWidget(self.button_reset_routes, 1, 1)
        btn_layout.addWidget(self.button_undo, 1, 2)
        btn_layout.addWidget(self.button_redo, 1, 3)

        # Stretch
        btn_layout.setColumnStretch(4, 1)

        # Main layout
        layout = QVBoxLayout()
        layout.addWidget(self.mode_label)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _bind_signals(self):
        # View -> ViewModel (User Actions)
        self.button_draw.clicked.connect(partial(self.vm.set_mode, "draw"))
        self.button_edit.clicked.connect(partial(self.vm.set_mode, "edit"))
        self.button_autoroute.clicked.connect(partial(self.vm.set_mode, "auto"))
        self.button_channel_edit.clicked.connect(partial(self.vm.set_mode, "channel-edit"))

        self.button_reset_routes.clicked.connect(self.vm.reset_routes)
        self.button_reset_electrodes.clicked.connect(self.vm.reset_electrodes)
        self.button_undo.clicked.connect(self.vm.undo)
        self.button_redo.clicked.connect(self.vm.redo)

        # ViewModel -> View (State Updates)
        self.vm.signals.state_changed.connect(self.sync_ui)

    def sync_ui(self):
        """Update button checked states and label based on VM state."""
        current_mode = self.vm.current_mode

        self.button_draw.setChecked(current_mode in ("draw", "edit-draw"))
        self.button_edit.setChecked(current_mode == "edit")
        self.button_autoroute.setChecked(current_mode == "auto")
        self.button_channel_edit.setChecked(current_mode == "channel-edit")

        self.mode_label.setText(f"Mode: {self.vm.mode_name}")

    def _apply_theme_styling(self):
        theme = "dark" if is_dark_mode() else "light"
        try:
            self.setStyleSheet(get_complete_stylesheet(theme, "default"))
        except Exception:
            self.setStyleSheet(get_complete_stylesheet("light", "default"))

    def update_theme_styling(self, theme="light"):
        self.setStyleSheet(get_complete_stylesheet(theme, "default"))