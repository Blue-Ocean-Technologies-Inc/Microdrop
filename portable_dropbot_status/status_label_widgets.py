from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget, QGridLayout, QPushButton, QSizePolicy
from PySide6.QtGui import QPixmap, QCursor, QColor, QPainter

from logger.logger_service import get_logger
logger = get_logger(__name__)

BORDER_RADIUS = 4

class DropBotIconWidget(QPushButton):
    """
    A button widget to display the DropBot's icon and connection status color.
    Inherits from QPushButton for native click handling and styling.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Sizing and Policy
        self.setMinimumWidth(60)
        self.setMaximumWidth(106)
        self.setFixedHeight(106)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Cursor
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Internal image storage
        self._pixmap = QPixmap()
        self._current_status_color = QColor("transparent")

        self.setDisabled(True)

    def set_pixmap_from_path(self, path):
        """Loads the pixmap and triggers a repaint."""
        self._pixmap = QPixmap(path)
        if self._pixmap.isNull():
            logger.error(f"Failed to load image: {path}")

        # Trigger a UI update
        self.update()

    def paintEvent(self, event):
        """
        Custom paint event to draw the button background (via stylesheet)
        and then draw the scaled image on top.
        """
        # 1. Let QPushButton draw the background/borders/pressed state first
        super().paintEvent(event)

        # 2. Draw the image on top
        if not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # Calculate the rectangle to center the image while keeping aspect ratio
            rect = self.rect()
            scaled_pixmap = self._pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Center the image in the button
            x = (rect.width() - scaled_pixmap.width()) // 2
            y = (rect.height() - scaled_pixmap.height()) // 2

            painter.drawPixmap(x, y, scaled_pixmap)

    def set_status_color(self, color_str: str):
        """
        Sets the background color and defines the 'pressed' state appearance.
        """
        self._current_status_color = QColor(color_str)
        pressed_color = self._current_status_color.darker(120)

        normal_rgb = self._current_status_color.name()
        pressed_rgb = pressed_color.name()

        # Note: We target 'DropBotIconWidget' so it applies to this class
        stylesheet = f"""
            DropBotIconWidget {{
                background-color: {normal_rgb};
                border-radius: {BORDER_RADIUS}px;
                border: 1px solid transparent;
            }}
            DropBotIconWidget:pressed {{
                background-color: {pressed_rgb};
                border: 1px solid {pressed_color.darker(110).name()};
            }}
        """
        self.setStyleSheet(stylesheet)


class DropBotStatusGridWidget(QWidget):
    """
    A compact grid of labels and values for displaying detailed DropBot status.
    This widget is designed to be as compact as possible.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(2)

        bold_font = self.font()
        bold_font.setBold(True)

        # --- Create and add widgets to the grid ---
        # Connection
        conn_label = QLabel("Connection:")
        conn_label.setFont(bold_font)
        self.connection_status = QLabel("Inactive")
        layout.addWidget(conn_label, 0, 0)
        layout.addWidget(self.connection_status, 0, 1)

        # Chip Status
        chip_label = QLabel("Chip Status:")
        chip_label.setFont(bold_font)
        self.chip_status = QLabel("Not Inserted")
        layout.addWidget(chip_label, 1, 0)
        layout.addWidget(self.chip_status, 1, 1)

        # Capacitance
        cap_label = QLabel("Capacitance:")
        cap_label.setFont(bold_font)
        self.capacitance_reading = QLabel("-")
        layout.addWidget(cap_label, 2, 0)
        layout.addWidget(self.capacitance_reading, 2, 1)

        # Voltage
        volt_label = QLabel("Voltage:")
        volt_label.setFont(bold_font)
        self.voltage_reading = QLabel("-")
        layout.addWidget(volt_label, 3, 0)
        layout.addWidget(self.voltage_reading, 3, 1)

        # c_device (Pressure)
        c_device_label = QLabel("c<sub>device</sub>:")
        c_device_label.setFont(bold_font)
        self.pressure_reading = QLabel("-")
        layout.addWidget(c_device_label, 4, 0)
        layout.addWidget(self.pressure_reading, 4, 1)

        # Force
        force_label = QLabel("Force:")
        force_label.setFont(bold_font)
        self.force_reading = QLabel("-")
        layout.addWidget(force_label, 5, 0)
        layout.addWidget(self.force_reading, 5, 1)


        # The 'Maximum' policy tells the layout that the widget's size hint
        # is also its maximum size.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        # This calculates the ideal size needed to fit all content and
        # sets it as the maximum size, preventing the widget from stretching.
        self.setMaximumSize(self.sizeHint())
