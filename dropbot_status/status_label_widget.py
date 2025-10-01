import logging


from PySide6.QtGui import Qt, QPixmap
from PySide6.QtWidgets import QMainWindow, QGroupBox, QVBoxLayout, QPushButton, QLabel, QSizePolicy, QWidget, \
    QGridLayout, QHBoxLayout, QApplication

from dropbot_status.consts import DROPBOT_IMAGE, DROPBOT_CHIP_INSERTED_IMAGE

# --- Set up a basic logger for demonstration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Dummy constants for demonstration purposes ---
BORDER_RADIUS = 10
connected_color = "#4CAF50"  # Green
connected_no_device_color = "#FFC107"  # Yellow
disconnected_color = "#F44336"  # Red

class DropBotIconWidget(QLabel):
    """
    A scalable widget to display the DropBot's icon and connection status color.
    The image scales proportionally to the widget's size.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(60, 60)
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

        # Use a size policy that prevents horizontal stretching
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

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

    # --- Public methods to update label text ---
    def update_connection_status(self, text: str):
        self.connection_status.setText(text)

    def update_chip_status(self, text: str):
        self.chip_status.setText(text)

    def update_capacitance_reading(self, capacitance: str):
        self.capacitance_reading.setText(capacitance)

    def update_voltage_reading(self, voltage: str):
        self.voltage_reading.setText(voltage)

    def update_pressure_reading(self, pressure: str):
        self.pressure_reading.setText(pressure)

    def update_force_reading(self, force: str):
        self.force_reading.setText(force)

    #---------- status getter methods -----------------

    def get_capacitance_reading(self):
        return self.capacitance_reading.text()

    def get_voltage_reading(self):
        return self.voltage_reading.text()


class DropBotStatusViewController(QWidget):
    """
    A compact and scalable main widget that combines the icon and the status grid.
    It manages the state and updates its child widgets accordingly.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(10, 10, 10, 10)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(15)

        # Create child widgets
        self.icon_widget = DropBotIconWidget()
        self.grid_widget = DropBotStatusGridWidget()

        # Add widgets to the layout
        self.main_layout.addWidget(self.icon_widget, 1)  # Add with stretch factor of 1
        self.main_layout.addWidget(self.grid_widget, 2)  # Add with stretch factor of 2

        self.dropbot_connected = False
        self.update_status(dropbot_connected=False, chip_inserted=False)  # Set initial state

    def update_status(self, dropbot_connected: bool, chip_inserted: bool = False):
        """
        Updates the visual status based on connection and chip state.
        This method orchestrates the updates to the child widgets.
        """
        self.dropbot_connected = dropbot_connected

        if chip_inserted:
            # If a chip is inserted, we can assume the bot is connected.
            self.dropbot_connected = True

        if self.dropbot_connected:
            self.grid_widget.update_connection_status("Active")
            if chip_inserted:
                logger.info("Status: Chip Inserted")
                self.icon_widget.set_pixmap_from_path(DROPBOT_CHIP_INSERTED_IMAGE)
                self.icon_widget.set_status_color(connected_color)
                self.grid_widget.update_chip_status("Inserted")
            else:
                logger.info("Status: Connected, No Chip")
                self.icon_widget.set_pixmap_from_path(DROPBOT_IMAGE)
                self.icon_widget.set_status_color(connected_no_device_color)
                self.grid_widget.update_chip_status("Not Inserted")
        else:
            logger.critical("Status: Disconnected")
            self.icon_widget.set_pixmap_from_path(DROPBOT_IMAGE)
            self.icon_widget.set_status_color(disconnected_color)
            self.grid_widget.update_connection_status("Inactive")
            self.grid_widget.update_chip_status("Not Inserted")

    # --- Forwarding methods to the grid widget ---
    def update_capacitance_reading(self, capacitance: str):
        self.grid_widget.update_capacitance_reading(capacitance)

    def update_voltage_reading(self, voltage: str):
        self.grid_widget.update_voltage_reading(voltage)

    def update_pressure_reading(self, pressure: str):
        self.grid_widget.update_pressure_reading(pressure)

    def update_force_reading(self, force: str):
        self.grid_widget.update_force_reading(force)

    def get_capacitance_reading(self):
        return self.grid_widget.get_capacitance_reading()

    def get_voltage_reading(self):
        return self.grid_widget.get_voltage_reading()


# --- Test Harness ---
if __name__ == '__main__':
    import sys
    import random

    class ControlsWindow(QWidget):
        """A separate window for controlling the DropBotStatusWidget."""

        def __init__(self, target_widget: DropBotStatusViewController):
            super().__init__()
            self.target_widget = target_widget
            self.setWindowTitle("Controls")

            controls_group = QGroupBox("Controls")
            controls_layout = QVBoxLayout()

            # State change buttons
            btn_connect = QPushButton("Set Status: Connect (No Chip)")
            btn_connect.clicked.connect(
                lambda: self.target_widget.update_status(True, False)
            )

            btn_insert_chip = QPushButton("Set Status: Connect & Insert Chip")
            btn_insert_chip.clicked.connect(
                lambda: self.target_widget.update_status(True, True)
            )

            btn_disconnect = QPushButton("Set Status: Disconnect")
            btn_disconnect.clicked.connect(
                lambda: self.target_widget.update_status(False, False)
            )

            # Data update button
            btn_update_readings = QPushButton("Update Sensor Readings")
            btn_update_readings.clicked.connect(self.update_random_readings)

            controls_layout.addWidget(btn_connect)
            controls_layout.addWidget(btn_insert_chip)
            controls_layout.addWidget(btn_disconnect)
            controls_layout.addWidget(btn_update_readings)
            controls_group.setLayout(controls_layout)

            main_layout = QVBoxLayout(self)
            main_layout.addWidget(controls_group)

            self.update_random_readings()

        def update_random_readings(self):
            """Updates the status widget with random sensor data."""

            cap = f"{random.uniform(1.5, 2.5):.2f} pF"
            volt = f"{random.uniform(4.8, 5.2):.2f} V"
            press = f"{random.uniform(90.0, 110.0):.1f} kPa"
            force = f"{random.uniform(0.5, 1.5):.2f} N"

            self.target_widget.update_capacitance_reading(cap)
            self.target_widget.update_voltage_reading(volt)
            self.target_widget.update_pressure_reading(press)
            self.target_widget.update_force_reading(force)


    class DemoWindow(QMainWindow):
        """A simple window to demonstrate the DropBotStatusWidget."""

        def __init__(self):
            super().__init__()
            self.setWindowTitle("DropBot Status Widget Test")
            self.setGeometry(100, 100, 400, 150)

            self.dropbot_widget = DropBotStatusViewController()
            self.setCentralWidget(self.dropbot_widget)

    app = QApplication(sys.argv)

    # Create and show the main status window
    main_window = DemoWindow()
    main_window.show()

    # Create and show the controls window, passing it the widget to control
    controls_window = ControlsWindow(target_widget=main_window.dropbot_widget)
    controls_window.show()

    sys.exit(app.exec())