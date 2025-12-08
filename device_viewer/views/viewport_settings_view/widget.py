import sys
import unittest
from PySide6.QtCore import QObject, Signal, Qt, QEvent, QTimer, QRectF
from PySide6.QtWidgets import (QApplication, QGraphicsView, QGraphicsScene,
                               QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
                               QMainWindow, QGraphicsRectItem, QPushButton)
from PySide6.QtGui import QPainter, QColor, QBrush, QTransform, QPen, QFont, QIcon

from device_viewer.models.main_model import DeviceViewMainModel
# Assumes microdrop_style is available in the python environment
from microdrop_style.button_styles import get_complete_stylesheet
from microdrop_style.font_paths import load_material_symbols_font

from traits.api import HasTraits, Instance, Str, Bool, observe


class ZoomViewModelSignals(QObject):
    # Signals to notify the View of changes
    zoom_changed = Signal(int)  # Emits new absolute scale factor
    reset_requested = Signal()  # Emits when fit-to-view is needed
    drag_mode_changed = Signal(bool)  # Emits when drag/pan is toggled

class ZoomViewModel(HasTraits):
    model = Instance(DeviceViewMainModel)
    drag_enabled = Bool(False)
    signals = Instance(ZoomViewModelSignals)

    def traits_init(self):
        self.signals = ZoomViewModelSignals()
        self.drag_enabled = False

    def zoom_in(self):
        print("zoom in")

    def zoom_out(self):
        print("zoom_out")

    def reset_view(self):
        """Reset logic. We reset our internal counter and tell View to fit."""
        print("reset view")

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
        self.signals.drag_mode_changed.emit(self.drag_enabled)


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
        self.vm.signals.drag_mode_changed.connect(btn_pan.setChecked)
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
            # Use complete stylesheet with tooltips for icon buttons
            icon_button_style = get_complete_stylesheet(theme, "default")
            self.setStyleSheet(icon_button_style)
        except Exception as e:
            # Fallback to light theme if there's an error
            icon_button_style = get_complete_stylesheet("light", "default")
            self.setStyleSheet(icon_button_style)