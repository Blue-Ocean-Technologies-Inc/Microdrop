import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QSlider, QLabel, QGraphicsScene, QGraphicsView, QGraphicsPathItem
)
from PySide6.QtGui import QPainter, QColor, QPainterPath, QPen, QTransform
from PySide6.QtCore import Qt, QSize, QRectF

PRIMARY_SHADE = {
    50:  "#E6F4E9",
    100: "#C3E4C9",
    200: "#9DD3A8",
    300: "#75C285",
    400: "#57B66C",
    500: "#37A953",
    600: "#2F9A4A",
    700: "#25883F",
    800: "#1B7734",
    900: "#085822"
}

PRIMARY_COLOR = PRIMARY_SHADE[600]

SECONDARY_SHADE = {
    50:  "#E7E9EF",
    100: "#CED3E0",
    200: "#B6BDD0",
    300: "#9DA7C1",
    400: "#8592B1",
    500: "#6C7CA1",
    600: "#546692",
    700: "#3B5082",
    800: "#233A73",
    900: "#0A2463"
}

from microdrop_style.colors import SECONDARY_SHADE
ELECTRODE_ON =  SECONDARY_SHADE[600]
ELECTRODE_OFF = SECONDARY_SHADE[900]

# --- Define Base Colors ---
# These are the base colors *before* alpha is applied.
# We use your snippet's naming convention.
ELECTRODE_OFF = QColor(ELECTRODE_OFF)
ELECTRODE_ON = QColor(ELECTRODE_ON)
ELECTRODE_LINE = QColor(Qt.GlobalColor.darkGray)


class ClickablePathItem(QGraphicsPathItem):
    """
    A QGraphicsPathItem that represents a clickable 'electrode' or box.
    It follows the logic from your snippet and our coloring discussion.
    """

    def __init__(self, path_data, color_off, color_on, pen_color, id_=None, parent=None):
        super().__init__(parent)

        self.id = id_
        self.state = False  # Corresponds to True/False in your state_map

        # Store the colors
        self.color_off = QColor(color_off)
        self.color_on = QColor(color_on)

        # Create the path from the provided data
        self.item_path = QPainterPath()
        if path_data:
            self.item_path.moveTo(path_data[0][0], path_data[0][1])
            for x, y in path_data[1:]:
                self.item_path.lineTo(x, y)
            self.item_path.closeSubpath()
        self.setPath(self.item_path)

        # Cache the smaller path for the 'on' state
        self._inner_path = self._create_inner_path(self.item_path, scale_factor=0.8)  # 80% size

        # Set the pen for the outline
        self.setPen(QPen(pen_color, 1))

    def _create_inner_path(self, original_path, scale_factor):
        """
        Creates a scaled-down and centered version of the original path.
        """
        bbox = original_path.boundingRect()

        # Calculate new size
        scaled_width = bbox.width() * scale_factor
        scaled_height = bbox.height() * scale_factor

        # Calculate translation to center the scaled path
        translate_x = bbox.x() + (bbox.width() - scaled_width) / 2
        translate_y = bbox.y() + (bbox.height() - scaled_height) / 2

        # Create a transform
        transform = QTransform()
        transform.translate(translate_x, translate_y)  # Move to the new top-left
        transform.scale(scale_factor, scale_factor)  # Scale relative to (0,0)

        # Apply the inverse translation to scale around the center (before scaling)
        transform.translate(-bbox.x(), -bbox.y())

        # It's actually easier to scale around center by doing this:
        # 1. Translate so bbox center is at (0,0)
        # 2. Scale
        # 3. Translate back
        center = bbox.center()
        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.scale(scale_factor, scale_factor)
        transform.translate(-center.x(), -center.y())

        return transform.map(original_path)

    def set_state(self, new_state):
        """Public method to update the item's state."""
        self.state = bool(new_state)
        self.update()  # Schedule a repaint

    def set_off_color(self, color, alpha):
        """Slot-like method to update the 'off' color."""
        self.color_off = QColor(color)
        self.color_off.setAlpha(alpha)
        self.update()

    def set_on_color(self, color, alpha):
        """Slot-like method to update the 'on' color."""
        self.color_on = QColor(color)
        self.color_on.setAlpha(alpha)
        self.update()

    def set_pen_alpha(self, alpha_value_int):
        """Updates the alpha of the outline pen."""
        pen = self.pen()
        color = pen.color()
        color.setAlpha(alpha_value_int)
        pen.setColor(color)
        self.setPen(pen)
        self.update()

    # --- Overridden Qt Methods ---

    def paint(self, painter, option, widget):
        """
        Handles the painting of the item.
        Implements the overlay coloring with a smaller inner path for 'on' state.
        """
        # Use SourceOver composition to allow alpha blending
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # 1. Always paint the 'off' color as the base, using the full path
        painter.fillPath(self.path(), self.color_off)

        # 2. If the state is 'on' (True), paint the 'on' color
        #    using the _inner_path over the 'off' color.
        if self.state:
            # This is the only line that should be here:
            painter.fillPath(self._inner_path, self.color_on)

        # 3. Draw the outline (using the full path)
        painter.strokePath(self.path(), self.pen())

    def mousePressEvent(self, event):
        """Handles mouse clicks to toggle the state."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_state(not self.state)  # Toggle state

        # Pass the event on
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """
    Main application window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGraphicsScene Color Grid")

        # Store the base colors (will be modified by sliders)
        self.color_start = QColor(ELECTRODE_OFF)
        self.color_clicked = QColor(ELECTRODE_ON)
        self.color_line = QColor(ELECTRODE_LINE)

        # Keep a list of all items to update them
        self.items = []

        # Set up the main layout
        main_layout = QVBoxLayout()

        # --- Create QGraphicsScene and QGraphicsView ---
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.scene.setBackgroundBrush(QColor("black"))

        main_layout.addWidget(self.view)  # Add view to main layout

        # --- Create Grid of Path Items ---
        rows = 5
        cols = 5
        box_size = 50
        spacing = 5

        # Define the path data for a simple box (relative to 0,0)
        box_path_data = [
            (0, 0),
            (box_size, 0),
            (box_size, box_size),
            (0, box_size)
        ]

        for row in range(rows):
            for col in range(cols):
                # Calculate position in the scene
                x_pos = col * (box_size + spacing)
                y_pos = row * (box_size + spacing)

                # Create the item
                item = ClickablePathItem(
                    box_path_data,
                    self.color_start,
                    self.color_clicked,
                    self.color_line,
                    id_=f"item_{row}_{col}"
                )

                # Set the item's position in the scene
                item.setPos(x_pos, y_pos)

                self.scene.addItem(item)
                self.items.append(item)  # Store the item

        # --- Create Controls (same as before) ---
        controls_widget = QWidget()
        controls_layout = QVBoxLayout()
        controls_widget.setLayout(controls_layout)

        # Off Color Alpha Slider
        off_alpha_layout = QHBoxLayout()
        off_alpha_label = QLabel("Off Color Alpha:")
        self.off_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.off_alpha_slider.setRange(0, 255)
        self.off_alpha_slider.setValue(self.color_start.alpha())
        self.off_alpha_slider.valueChanged.connect(self.update_off_alpha)
        off_alpha_layout.addWidget(off_alpha_label)
        off_alpha_layout.addWidget(self.off_alpha_slider)
        controls_layout.addLayout(off_alpha_layout)

        # On Color Alpha Slider
        on_alpha_layout = QHBoxLayout()
        on_alpha_label = QLabel("On Color Alpha:")
        self.on_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.on_alpha_slider.setRange(0, 255)
        self.on_alpha_slider.setValue(self.color_clicked.alpha())
        self.on_alpha_slider.valueChanged.connect(self.update_on_alpha)
        on_alpha_layout.addWidget(on_alpha_label)
        on_alpha_layout.addWidget(self.on_alpha_slider)
        controls_layout.addLayout(on_alpha_layout)

        main_layout.addWidget(controls_widget)  # Add controls to main layout

        # Set the central widget
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.resize(400, 500)

    def update_off_alpha(self, value):
        """
        Slot to update the alpha of the 'off' color for all items.
        """
        for item in self.items:
            item.set_off_color(self.color_start, value)  # This calls item.update()

    def update_on_alpha(self, value):
        """
        Slot to update the alpha of the 'on' color for all items.
        """
        for item in self.items:
            item.set_on_color(self.color_clicked, value)  # This calls item.update()


def main():
    """
    Main function to run the application.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()