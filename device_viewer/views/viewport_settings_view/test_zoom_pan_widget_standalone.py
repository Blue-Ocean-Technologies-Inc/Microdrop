import sys
import unittest

from PySide6.QtGui import Qt
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QPainter, QFont, QIcon, QBrush, QPen
from PySide6.QtWidgets import QGraphicsView, QApplication, QMainWindow, QWidget, QVBoxLayout, QGraphicsScene, \
    QGraphicsRectItem

from device_viewer.views.viewport_settings_view.widget import ZoomViewModel, ZoomControlWidget
from microdrop_style.font_paths import load_material_symbols_font

if __name__ == "__main__":

    class _ZoomViewModel(QObject):


        def __init__(self, start_scale=1.0, zoom_factor=1.15):
            super().__init__()
            self._current_scale = start_scale
            self._zoom_factor = zoom_factor
            self._min_scale = 0.1  # 10%
            self._max_scale = 10.0  # 1000%
            self._drag_enabled = False  # Default to enabled

            class _VSignals(QObject):
                # Signals to notify the View of changes
                zoom_changed = Signal(float)  # Emits new absolute scale factor
                reset_requested = Signal()  # Emits when fit-to-view is needed
                drag_mode_changed = Signal(bool)  # Emits when drag/pan is toggled

            self.vm_signals = _VSignals()

        @property
        def current_scale(self):
            return self._current_scale

        @property
        def drag_enabled(self):
            return self._drag_enabled

        def zoom_in(self):
            new_scale = self._current_scale * self._zoom_factor
            self._set_scale(new_scale)

        def zoom_out(self):
            new_scale = self._current_scale / self._zoom_factor
            self._set_scale(new_scale)

        def set_absolute_scale(self, value):
            """Called if the View changes zoom via other means (not used here but good for sync)"""
            self._current_scale = value

        def reset_view(self):
            """Reset logic. We reset our internal counter and tell View to fit."""
            self._current_scale = 1.0
            self.vm_signals.reset_requested.emit()

        def set_drag_mode(self, enabled: bool):
            """Explicitly set the drag mode state."""
            if self._drag_enabled == enabled:
                return
            self._drag_enabled = enabled
            self.vm_signals.drag_mode_changed.emit(self._drag_enabled)

        def toggle_drag_mode(self):
            """Toggles the current state."""
            self.set_drag_mode(not self._drag_enabled)

        def _set_scale(self, new_scale):
            # Clamp values
            if new_scale < self._min_scale: new_scale = self._min_scale
            if new_scale > self._max_scale: new_scale = self._max_scale

            self._current_scale = new_scale
            self.vm_signals.zoom_changed.emit(self._current_scale)



    class ZoomableView(QGraphicsView):
        def __init__(self, view_model: ZoomViewModel, parent=None):
            super().__init__(parent)
            self.vm = view_model
            self.vm_signals = view_model.signals

            # Internal state for temporary spacebar panning
            self._is_space_panning = False

            # Cosmetic Setup
            self.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.setBackgroundBrush(Qt.GlobalColor.black)  # Black background

            # Ensure view accepts focus to catch key events
            self.setFocusPolicy(Qt.StrongFocus)

            # Hide scrollbars for a cleaner canvas look
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            # Bind Signals
            self.vm_signals.zoom_changed.connect(self.apply_zoom)
            self.vm_signals.reset_requested.connect(self.apply_fit)
            self.vm_signals.pan_mode_changed.connect(self.apply_drag_mode)

            # Set Initial State
            self.apply_drag_mode(self.vm.drag_enabled)

        def apply_drag_mode(self, enabled: bool):
            if enabled:
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                # Disable interaction with items (clicking/hovering) while panning
                self.setInteractive(False)
            else:
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
                # Re-enable interaction with items
                self.setInteractive(True)

        def apply_zoom(self, new_absolute_scale):
            """
            Calculates the delta required to move from Current -> New.
            This allows us to use PySide's 'scale()' which respects anchors (mouse pos).
            """
            current_m11 = self.transform().m11()
            if current_m11 == 0: current_m11 = 1.0  # Protect against zero div

            # Calculate relative factor needed
            relative_factor = new_absolute_scale / current_m11
            self.scale(relative_factor, relative_factor)

        def apply_fit(self):
            """
            Handles the Geometry of fitting (View concern, not ViewModel).
            """
            if not self.scene(): return

            # 1. Fit exactly
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

            # 2. Add Padding (90% size = borders)
            self.scale(0.9, 0.9)

            # 3. Sync VM with the new reality
            new_scale = self.transform().m11()
            self.vm.set_absolute_scale(new_scale)

        def wheelEvent(self, event):
            """Captures Input -> Commands ViewModel"""
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Anchor under mouse for wheel zooming
                self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

                angle = event.angleDelta().y()
                if angle > 0:
                    self.vm.zoom_in()
                else:
                    self.vm.zoom_out()

                event.accept()

                # Reset anchor to default after operation so programmatic zooms (fit) stay centered
                QTimer.singleShot(0,
                                  lambda: self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter))
            else:
                super().wheelEvent(event)

        def keyPressEvent(self, event):
            """Handle Spacebar for temporary panning"""
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                # Only enable temporary panning if drag isn't ALREADY enabled manually
                if not self.vm.drag_enabled:
                    self._is_space_panning = True
                    self.vm.set_drag_mode(True)
                event.accept()
                return

            super().keyPressEvent(event)

        def keyReleaseEvent(self, event):
            """Handle Spacebar release to revert panning"""
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                # Only disable if it was enabled via the spacebar
                if self._is_space_panning:
                    self.vm.set_drag_mode(False)
                    self._is_space_panning = False
                event.accept()
                return

            super().keyReleaseEvent(event)



    # Font paths & Constants
    LABEL_FONT_FAMILY = "Inter"
    ICON_FONT_FAMILY = "Material Symbols Outlined"

    # Check if user wants to run tests
    if "test" in sys.argv:
        # Remove 'test' arg so unittest doesn't get confused
        sys.argv.pop()
        unittest.main()
    else:
        # Run the GUI
        app = QApplication(sys.argv)

        # Load fonts if available in the environment
        try:
            load_material_symbols_font()
        except NameError:
            print("Warning: load_material_symbols_font not defined or imported.")
        except Exception as e:
            print(f"Warning: Could not load Material Symbols font: {e}")

        # Set Global App Font
        app.setFont(QFont(LABEL_FONT_FAMILY, 11))
        QIcon.setThemeName("Material Symbols Outlined")

        # 1. Setup Logic (ViewModel)
        vm = _ZoomViewModel()

        # 2. Setup Container
        window = QMainWindow()
        window.setWindowTitle("MVVM Zoom Architect")
        container = QWidget()
        layout = QVBoxLayout(container)

        # 3. Create Scene & Content
        scene = QGraphicsScene(0, 0, 400, 300)  # Scene Area

        # Add the Red Square
        rect_item = QGraphicsRectItem(0, 0, 100, 50)
        rect_item.setPos(50, 70)
        rect_item.setBrush(QBrush(Qt.GlobalColor.red))
        rect_item.setPen(QPen(Qt.GlobalColor.white, 2))
        scene.addItem(rect_item)

        # Add Text
        text = scene.addText("MVVM Zoom")
        text.setDefaultTextColor(Qt.GlobalColor.white)
        text.setPos(55, 80)

        # 4. Create View and inject ViewModel
        view = ZoomableView(vm)
        view.setScene(scene)

        # 5. Create Controls and inject ViewModel
        controls = ZoomControlWidget(vm)

        layout.addWidget(controls)
        layout.addWidget(view)

        window.setCentralWidget(container)
        window.resize(600, 400)
        window.show()

        # Initial Fit (Delayed slightly to ensure Viewport is ready)
        QTimer.singleShot(100, vm.reset_view)

        sys.exit(app.exec())
