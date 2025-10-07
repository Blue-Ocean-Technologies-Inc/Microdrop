from PySide6.QtGui import Qt, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget, QGridLayout

from microdrop_style.colors import SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR
from microdrop_utils._logger import get_logger

logger = get_logger(__name__, level="DEBUG")

disconnected_color = ERROR_COLOR
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
BORDER_RADIUS = 4

class DropBotIconWidget(QLabel):
    """
    A scalable widget to display the DropBot's icon and connection status color.
    The image scales proportionally to the widget's size.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(60)
        self.setMaximumWidth(106)
        self.setFixedHeight(106)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._pixmap = QPixmap()

    def set_pixmap_from_path(self, path):
        """Loads the pixmap from a file path."""
        self._pixmap = QPixmap(path)
        if self._pixmap.isNull():
            logger.error(f"Failed to load image: {path}")
        self.update_scaled_pixmap()

    def resizeEvent(self, event):
        """
        Overrides the resize event to rescale the pixmap while maintaining aspect ratio.
        """
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self.update_scaled_pixmap()

    def update_scaled_pixmap(self):
        """Scales the pixmap to fit the label's current size."""
        scaled_pixmap = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled_pixmap)

    def set_status_color(self, color: str):
        """Sets the background color and border radius of the icon."""
        self.setStyleSheet(f'background-color: {color}; border-radius: {BORDER_RADIUS}px;')


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