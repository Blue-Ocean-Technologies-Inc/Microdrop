import sys
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                                QMainWindow, QGraphicsView,
                               QGraphicsScene, QGraphicsRectItem, QSplitter)
from PySide6.QtGui import QColor, QBrush, QPen

from traits.api import observe, Instance, HasTraits

from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.views.viewport_settings_view.widget import ZoomViewModel, ZoomControlWidget


class ZoomableGraphicsView(QGraphicsView):
    """
    The Main View Controller.
    It listens to the Shared Model events to update the UI.
    """
    zoom = Signal(int)
    pan_mode_toggle = Signal()

    def __init__(self):
        super().__init__()
        # Setup Scene
        self.scene = QGraphicsScene(0, 0, 400, 400)
        self.setScene(self.scene)

        # Draw Red Rectangle
        self.rect_item = QGraphicsRectItem(150, 150, 100, 100)
        self.rect_item.setBrush(QBrush(QColor("red")))
        self.rect_item.setPen(QPen(Qt.NoPen))
        self.scene.addItem(self.rect_item)

        # Background reference grid
        self.scene.addRect(0, 0, 400, 400, QPen(QColor("gray")))

        # Visual tweaking
        self.setBackgroundBrush(QBrush(QColor("#222")))

    def wheelEvent(self, event):
        self.zoom.emit(event.angleDelta().y())

    def keyPressEvent(self, event):
        if (event.modifiers() & Qt.ControlModifier):
            # Check for Plus (Key_Plus is Numpad, Key_Equal is standard keyboard '+')
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom.emit(1)

            if event.key() == Qt.Key.Key_Minus:
                self.zoom.emit(-1)

        if event.key() == Qt.Key.Key_Space:
            self.pan_mode_toggle.emit()


# ---------------------------------------------------------
# VIEW Controller: Zoomable Red Rectangle
# ---------------------------------------------------------

# --- Event Handlers ---

class ZoomableGraphicsViewController(HasTraits):

    model = Instance(DeviceViewMainModel)
    view = Instance(ZoomableGraphicsView)

    def traits_init(self):
        self.view.zoom.connect(self.handle_zoom_request_from_view)
        self.view.pan_mode_toggle.connect(self.handle_pan_mode_toggle_request_from_view)

    def handle_zoom_request_from_view(self, value):
        if value > 0:
            self.model.zoom_in_event = True
        else:
            self.model.zoom_out_event = True

    def handle_pan_mode_toggle_request_from_view(self):
        self.model.flip_mode_activation("pan")

    @observe("model:zoom_in_event")
    def handle_zoom_in(self, event):
        print("View: applying scale 1.2x")
        self.view.scale(1.2, 1.2)


    @observe("model:zoom_out_event")
    def handle_zoom_out(self, event):
        print("View: applying scale 0.8x")
        self.view.scale(0.8, 0.8)


    @observe("model:reset_view_event")
    def handle_reset(self, event):
        print("View: resetting transform")
        self.view.resetTransform()
        self.view.fitInView(self.view.scene.itemsBoundingRect(), Qt.KeepAspectRatio)


    @observe("model:mode")
    def handle_mode(self, event):
        new_mode = event.new
        if new_mode == 'pan':
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            print("View: Drag Mode ON")
        else:
            self.view.setDragMode(QGraphicsView.NoDrag)
            print("View: Drag Mode OFF")


# ---------------------------------------------------------
# Main Window
# ---------------------------------------------------------

class RunnerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zoom Architecture Test Runner")
        self.resize(800, 600)

        # 1. Create the Shared Model
        self.shared_model = DeviceViewMainModel()

        # 2. Create the View Model (passed to the sidebar widget)
        self.zoom_vm = ZoomViewModel(model=self.shared_model)

        # 3. Create Widgets
        self.sidebar_widget = ZoomControlWidget(self.zoom_vm)
        self.main_view = ZoomableGraphicsView()
        self.main_view_controller = ZoomableGraphicsViewController(model=self.shared_model, view=self.main_view)

        # 4. Layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # Sidebar container
        sidebar_container = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.addWidget(self.sidebar_widget)
        sidebar_layout.addStretch()  # Push widget to top

        # Splitter to hold Sidebar (Left) and View (Right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar_container)
        splitter.addWidget(self.main_view)
        splitter.setStretchFactor(1, 1)  # Give view more space

        main_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)

    from microdrop_style.helpers import style_app
    style_app(app)

    window = RunnerWindow()
    window.show()

    sys.exit(app.exec())