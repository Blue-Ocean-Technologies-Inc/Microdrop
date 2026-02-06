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

        # ... existing widgets (up to row 5 for Force) ...

        # Frequency
        freq_label = QLabel("Frequency:")
        freq_label.setFont(bold_font)
        self.frequency_reading = QLabel("-")
        layout.addWidget(freq_label, 6, 0)
        layout.addWidget(self.frequency_reading, 6, 1)

        # Device Temperature
        dev_temp_label = QLabel("Device Temp:")
        dev_temp_label.setFont(bold_font)
        self.device_temp_reading = QLabel("-")
        layout.addWidget(dev_temp_label, 7, 0)
        layout.addWidget(self.device_temp_reading, 7, 1)

        # Device Humidity
        dev_hum_label = QLabel("Device Humidity:")
        dev_hum_label.setFont(bold_font)
        self.device_humidity_reading = QLabel("-")
        layout.addWidget(dev_hum_label, 8, 0)
        layout.addWidget(self.device_humidity_reading, 8, 1)

        # Chip Temperature
        chip_temp_label = QLabel("Chip Temp:")
        chip_temp_label.setFont(bold_font)
        self.chip_temp_reading = QLabel("-")
        layout.addWidget(chip_temp_label, 9, 0)
        layout.addWidget(self.chip_temp_reading, 9, 1)

        # The 'Maximum' policy tells the layout that the widget's size hint
        # is also its maximum size.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        # This calculates the ideal size needed to fit all content and
        # sets it as the maximum size, preventing the widget from stretching.
        self.setMaximumSize(self.sizeHint())
