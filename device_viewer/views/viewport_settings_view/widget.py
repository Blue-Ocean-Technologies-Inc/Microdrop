from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget,  QHBoxLayout, QPushButton

from device_viewer.models.main_model import DeviceViewMainModel
# Assumes microdrop_style is available in the python environment
from microdrop_style.button_styles import get_complete_stylesheet

from traits.api import HasTraits, Instance, Bool, observe, Event


class ZoomViewModelSignals(QObject):
    # Signals to notify the View of changes
    pan_mode_changed = Signal(bool)  # Emits when drag/pan is toggled


class ZoomViewModel(HasTraits):
    model = Instance(DeviceViewMainModel)
    drag_enabled = Bool(False)
    signals = Instance(ZoomViewModelSignals)

    def traits_init(self):
        self.signals = ZoomViewModelSignals()
        self.drag_enabled = False

    def zoom_in(self):
        self.model.zoom_in_event = True

    def zoom_out(self):
        self.model.zoom_out_event = True

    def reset_view(self):
        self.model.reset_view_event = True

    def toggle_drag_mode(self, *args, **kwargs):
        """
        Enable view to toggle pan mode on/off
        """
        self.model.flip_mode_activation(mode='pan')

    @observe('model:mode')
    def _mode_changed(self, event):
        """
        inform view of current mode. Is it pan mode or not
        """
        self.drag_enabled = event.new == 'pan'
        self.signals.pan_mode_changed.emit(self.drag_enabled)


class ZoomControlWidget(QWidget):
    def __init__(self, view_model: ZoomViewModel, parent=None):
        super().__init__(parent)
        self.vm = view_model

        ##### Create layout with required buttons #####
        layout = QHBoxLayout(self)

        btn_out = QPushButton("zoom_out")
        btn_out.setToolTip("Zoom out")

        btn_in = QPushButton("zoom_in")
        btn_in.setToolTip("Zoom In")

        btn_reset = QPushButton("fit_screen")
        btn_reset.setToolTip("Reset Zoom: Fit to View")

        btn_pan = QPushButton("pan_tool")
        btn_pan.setToolTip("Toggle Pan/Drag (Space key)")
        btn_pan.setCheckable(True)
        btn_pan.setChecked(self.vm.drag_enabled)

        layout.addWidget(btn_out)
        layout.addWidget(btn_in)
        layout.addWidget(btn_reset)
        layout.addWidget(btn_pan)  # Added Pan button
        layout.addStretch()

        # Apply theme-aware styling
        self._apply_theme_styling()

        ##### View Model Bindings ######
        # Ensure button UI stays in sync if VM changes externally
        self.vm.signals.pan_mode_changed.connect(btn_pan.setChecked)
        btn_out.clicked.connect(self.vm.zoom_out)
        btn_in.clicked.connect(self.vm.zoom_in)
        btn_pan.clicked.connect(self.vm.toggle_drag_mode)
        btn_reset.clicked.connect(self.vm.reset_view)

    def _apply_theme_styling(self):
        """Apply theme-aware styling to the widget."""
        try:
            # Import here to avoid circular imports
            from microdrop_style.helpers import is_dark_mode

            theme = "dark" if is_dark_mode() else "light"
        except Exception as e:
            # Fallback to light theme if there's an error
            theme = 'light'

        self.update_theme_styling(theme)

    def update_theme_styling(self, theme="light"):
        """Update styling when theme changes."""
        icon_button_style = get_complete_stylesheet(theme, "default")
        self.setStyleSheet(icon_button_style)