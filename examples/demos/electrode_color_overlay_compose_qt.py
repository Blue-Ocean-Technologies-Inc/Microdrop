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

        self.hover_factor_base = 0.5
        self.hover_factor_actuation = 0.5
        self.id = id_
        self.state = False
        self._is_hovered = False

        # Store the base colors
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

        # Tell the item to accept hover events
        self.setAcceptHoverEvents(True)

    def _create_inner_path(self, original_path, scale_factor):
        """
        Creates a scaled-down and centered version of the original path.
        """
        center = original_path.boundingRect().center()
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

    def set_hover_factor_base(self, factor):
        """Sets the lightness factor for hovering."""
        self.hover_factor_base = factor

    def set_hover_factor_actuation(self, factor):
        """Sets the lightness factor for hovering."""
        self.hover_factor_actuation = factor


    # --- Overridden Qt Methods ---

    def _get_lighter_percent(self, color, lightness_scale):
        """
        Calculates the integer percentage for QColor.lighter()
        based on a 0.0-1.0 scale.

        color: QColor
        lightness_scale: float (0.0 to 1.0)
            0.0 means same lightness as color (returns 100).
            1.0 means fully white (returns 100 / lightnessF).
        """

        # 1. Define the start of our scale (100% = no change)
        min_lightness_percent = 100.0

        current_lightness = color.lightness()

        # 2. Define the end of our scale (the factor to get to white)
        if current_lightness == 0:
            # Handle pure black:
            h, s, l, a = color.getHsl()
            color.setHsl(h, s, 1, a)

        # The factor needed to reach 1.0 lightness (white)
        # e.g., if lightnessF is 0.5 (gray), we need a factor of
        # 1.0 / 0.5 = 2.0, which is 200%.
        max_lightness_percent = int(255*100 / current_lightness)
        for n in range(max_lightness_percent, max_lightness_percent + 10000):
            if color.lighter(n).lightness() == 255:
                max_lightness_percent = n
                break

        # 3. Linearly interpolate between min and max
        # This was the missing piece.
        lightness_percentage = min_lightness_percent + (max_lightness_percent - min_lightness_percent) * lightness_scale

        # QColor.lighter() expects an integer
        return int(lightness_percentage)

    def paint(self, painter, option, widget):
        """
        Handles the painting of the item.
        Implements the overlay coloring with a smaller inner path for 'on' state.
        """
        # Use SourceOver composition to allow alpha blending
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # 1. Determine the *actual* colors to use based on hover state
        if self._is_hovered:
            current_off_color = self.color_off.lighter(self._get_lighter_percent(self.color_off, self.hover_factor_base))
            current_on_color = self.color_on.lighter(self._get_lighter_percent(self.color_on, self.hover_factor_actuation))
        else:
            current_off_color = self.color_off
            current_on_color = self.color_on

        # 2. Always paint the 'off' color as the base, using the calculated color
        painter.fillPath(self.path(), current_off_color)

        # 3. If the state is 'on' (True), paint the 'on' color
        #    using the _inner_path over the 'off' color.
        if self.state:
            painter.fillPath(self._inner_path, current_on_color)

        # 4. Draw the outline (using the full path)
        painter.strokePath(self.path(), self.pen())

    def mousePressEvent(self, event):
        """Handles mouse clicks to toggle the state."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_state(not self.state)  # Toggle state

        # Pass the event on
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        """Handles mouse hovering events by setting a flag."""
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Handles mouse hovering events by clearing a flag."""
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)


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

        # lightness on hover slider:
        hover_layout = QHBoxLayout()
        hover_label = QLabel("Base Hover Lightness (%):")
        hover_slider = QSlider(Qt.Orientation.Horizontal)
        hover_slider.setRange(0, 100)  # 100% (no change) to 250%
        hover_slider.setValue(50)
        hover_slider.valueChanged.connect(self.update_base_hover_lightness)
        hover_layout.addWidget(hover_label)
        hover_layout.addWidget(hover_slider)
        controls_layout.addLayout(hover_layout)

        # lightness on hover slider:
        hover_layout = QHBoxLayout()
        hover_label = QLabel("Actuation Hover Lightness (%):")
        hover_slider = QSlider(Qt.Orientation.Horizontal)
        hover_slider.setRange(0, 100)  # 100% (no change) to 250%
        hover_slider.setValue(50)
        hover_slider.valueChanged.connect(self.update_actuation_hover_lightness)
        hover_layout.addWidget(hover_label)
        hover_layout.addWidget(hover_slider)
        controls_layout.addLayout(hover_layout)


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
            item.set_on_color(self.color_clicked, value)  # This calls item.update()\

    def update_base_hover_lightness(self, value):
        """
        Slot to update the hover lightness factor for all items.
        """
        for item in self.items:
            item.set_hover_factor_base(value / 100)

    def update_actuation_hover_lightness(self, value):
        """
        Slot to update the hover lightness factor for all items.
        """
        for item in self.items:
            item.set_hover_factor_actuation(value / 100)


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