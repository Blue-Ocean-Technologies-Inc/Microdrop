# sys imports
import json
import os

# pyside imports
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QPushButton, QMessageBox, QHBoxLayout, QDialog, QTextBrowser, QGridLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

# local imports
from microdrop_utils._logger import get_logger
from microdrop_utils.base_dropbot_qwidget import BaseDramatiqControllableDropBotQWidget
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import DETECT_SHORTS, RETRY_CONNECTION, START_DEVICE_MONITORING, CHIP_CHECK

from .consts import DROPBOT_IMAGE, DROPBOT_CHIP_INSERTED_IMAGE

from traits.api import HasTraits, Range, Bool

logger = get_logger(__name__, level="DEBUG")

red = '#f15854'
yellow = '#decf3f'
green = '#60bd68'


class DropBotStatusLabel(QLabel):
    """
    Class providing some status visuals for when chip has been inserted or not. Or when dropbot has any errors.
    """

    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 120)
        self.setContentsMargins(10, 10, 10, 10)

        # Main horizontal layout to hold icon and grid
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(10)

        # Add dropbot icon to the left
        self.dropbot_icon = QLabel()
        self.dropbot_icon.setFixedSize(100, 100)
        self.dropbot_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.dropbot_icon)

        # Create grid layout for status information
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(10)  # Space between columns
        self.grid_layout.setVerticalSpacing(1)     # Minimal space between rows

        # Create fonts
        bold_font = self.font()
        bold_font.setBold(True)

        # Create label pairs (static label + value label)
        self.connection_label = QLabel("Status:")
        self.connection_label.setFont(bold_font)
        self.dropbot_connection_status = QLabel()
        
        self.chip_label = QLabel("Chip Status:")
        self.chip_label.setFont(bold_font)
        self.dropbot_chip_status = QLabel()
        
        self.capacitance_label = QLabel("Capacitance:")
        self.capacitance_label.setFont(bold_font)
        self.dropbot_capacitance_reading = QLabel("-")
        
        self.voltage_label = QLabel("Voltage:")
        self.voltage_label.setFont(bold_font)
        self.dropbot_voltage_reading = QLabel("-")

        self.pressure_label = QLabel("c<sub>device</sub>:")
        self.pressure_label.setFont(bold_font)
        self.dropbot_pressure_reading = QLabel("-")

        self.force_label = QLabel("Force")
        self.force_label.setFont(bold_font)
        self.dropbot_force_reading = QLabel("-")

        # Set initial status
        self.update_status_icon(dropbot_connected=False, chip_inserted=False)

        # Add pairs to grid - labels in column 0, values in column 1
        self.grid_layout.addWidget(self.connection_label, 0, 0)
        self.grid_layout.addWidget(self.dropbot_connection_status, 0, 1)
        
        self.grid_layout.addWidget(self.chip_label, 1, 0)
        self.grid_layout.addWidget(self.dropbot_chip_status, 1, 1)
        
        self.grid_layout.addWidget(self.capacitance_label, 2, 0)
        self.grid_layout.addWidget(self.dropbot_capacitance_reading, 2, 1)
        
        self.grid_layout.addWidget(self.voltage_label, 3, 0)
        self.grid_layout.addWidget(self.dropbot_voltage_reading, 3, 1)

        self.grid_layout.addWidget(self.pressure_label, 4, 0)
        self.grid_layout.addWidget(self.dropbot_pressure_reading, 4, 1)

        self.grid_layout.addWidget(self.force_label, 5, 0)
        self.grid_layout.addWidget(self.dropbot_force_reading, 5, 1)

        # Add the grid to the main layout
        self.main_layout.addLayout(self.grid_layout)
        
        # Add stretch to the right
        self.main_layout.addStretch(1)

        self.setLayout(self.main_layout)
        self.dropbot_connected = False

    def update_status_icon(self, dropbot_connected=None, chip_inserted=False):
        """
        Update status based on if device connected and chip inserted or not.
        """
        
        if dropbot_connected is not None:
            self.dropbot_connected = dropbot_connected
        else:
            dropbot_connected = self.dropbot_connected
        
        if dropbot_connected:
            logger.info("Dropbot Connected")
            self.dropbot_connection_status.setText("Connected")

            if chip_inserted:
                logger.info("Chip Inserted")
                # dropbot ready to use: give greenlight and display chip.
                self.dropbot_chip_status.setText("Inserted")
                img_path = DROPBOT_CHIP_INSERTED_IMAGE
                status_color = green

            # dropbot connected but no chip inside. Yellow signal.
            else:
                logger.info("Chip Not Inserted")
                self.dropbot_chip_status.setText("Not Inserted")
                img_path = DROPBOT_IMAGE
                status_color = yellow

        else:
            # dropbot not there. Red light.
            logger.info("Dropbot Disconnected")
            img_path = DROPBOT_IMAGE
            status_color = red
            self.dropbot_connection_status.setText("Disconnected")
            self.dropbot_chip_status.setText("Not inserted")

        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            logger.error(f"Failed to load image: {img_path}")
        # Always scale to fit the label size
        self.dropbot_icon.setPixmap(pixmap.scaled(self.dropbot_icon.size(), 
                                                  Qt.AspectRatioMode.KeepAspectRatio, 
                                                  Qt.TransformationMode.SmoothTransformation))
        self.dropbot_icon.setStyleSheet(f'QLabel {{ background-color : {status_color} ; }}')

    def update_capacitance_reading(self, capacitance):
        self.dropbot_capacitance_reading.setText(capacitance)

    def update_voltage_reading(self, voltage):
        self.dropbot_voltage_reading.setText(voltage)

    def update_pressure_reading(self, pressure):
        self.dropbot_pressure_reading.setText(pressure)

    def update_force_reading(self, force):
        self.dropbot_force_reading.setText(force)


class DropBotStatusWidget(BaseDramatiqControllableDropBotQWidget):
    def __init__(self):
        super().__init__()

        # flag for if no pwoer is true or not
        self.no_power_dialog = None
        self.no_power = None
        self.layout = QVBoxLayout(self)

        self.status_label = DropBotStatusLabel()
        self.layout.addWidget(self.status_label)

    ###################################################################################################################
    # Publisher methods
    ###################################################################################################################
    def request_detect_shorts(self):
        logger.info("Detecting shorts...")
        publish_message("Detect shorts button triggered", DETECT_SHORTS)

    def request_retry_connection(self):
        logger.info("Retrying connection...")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)

        if self.no_power_dialog:
            self.no_power_dialog.close()

        self.no_power = False
        self.no_power_dialog = None

    ###################################################################################################################
    # Subscriber methods
    ###################################################################################################################

    ######################################### Handler methods #############################################

    ######## shorts found method ###########
    def _on_shorts_detected_triggered(self, shorts_dict):
        shorts = json.loads(shorts_dict).get('Shorts_detected', [])

        self.shorts_popup = QMessageBox()
        self.shorts_popup.setFixedSize(300, 200)
        self.shorts_popup.setWindowTitle("ERROR: Shorts Detected")
        self.shorts_popup.setButtonText(QMessageBox.StandardButton.Ok, "Close")
        if len(shorts) > 0:
            shorts_str = str(shorts).strip('[]')
            self.shorts_popup.setText(f"Shorts were detected on the following channels: \n \n"
                                      f"[{shorts_str}] \n \n"
                                      f"You may continue using the DropBot, but the affected channels have "
                                      f"been disabled until the DropBot is restarted (e.g. unplug all cabled and plug "
                                      f"back in).")
        else:
            self.shorts_popup.setWindowTitle("Short Detection Complete")
            self.shorts_popup.setText("No shorts were detected.")

        self.shorts_popup.exec()

    ################# Capcitance Voltage readings ##################
    def _on_capacitance_updated_triggered(self, body):
        capacitance = json.loads(body).get('capacitance', '-')
        voltage = json.loads(body).get('voltage', '-')
        self.status_label.update_capacitance_reading(capacitance)
        self.status_label.update_voltage_reading(voltage)
