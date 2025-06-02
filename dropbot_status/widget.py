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
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.timestamped_message import TimestampedMessage

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

    def update_status_icon(self, dropbot_connected=None, chip_inserted=False, timestamp=None):
        """
        Update status based on if device connected and chip inserted or not. Follows this flowchart:

        Is Dropbot Connected?
            |          \
            n            y
            |             \
        Disconnected       Is Chip Inserted?
            |                   |          \
           Red                  n            y
                                |             \
                            Not Inserted   Inserted
                                |             |
                              Yellow        Green

        If the timestamp is provided, we only update the status if the timestamp is after the most recent status message.
        This is to avoid updating the status if the message is older than the most recent status message.
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
        self.realtime_mode = False
        self.connected_message = TimestampedMessage("", 0) # We initialize it timestamp 0 so any message will be newer. The string is not important.
        self.chip_inserted_message = TimestampedMessage("", 0)
        self.realtime_mode_message = TimestampedMessage("", 0)
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

        if len(shorts) == 0:
            logger.info("No shorts were detected.")
            return
            
        self.shorts_popup = QMessageBox()
        self.shorts_popup.setFixedSize(300, 200)
        self.shorts_popup.setWindowTitle("ERROR: Shorts Detected")
        self.shorts_popup.setButtonText(QMessageBox.StandardButton.Ok, "Close")

        shorts_str = str(shorts).strip('[]')
        self.shorts_popup.setText(f"Shorts were detected on the following channels: \n \n"
                                    f"[{shorts_str}] \n \n"
                                    f"You may continue using the DropBot, but the affected channels have "
                                    f"been disabled until the DropBot is restarted (e.g. unplug all cabled and plug "
                                    f"back in).")


        self.shorts_popup.exec()

    ################# Capcitance Voltage readings ##################
    def _on_capacitance_updated_triggered(self, body):
        if self.realtime_mode: # Only update the capacitance and voltage readings if we are in realtime mode
            capacitance = json.loads(body).get('capacitance', '-')
            voltage = json.loads(body).get('voltage', '-')
            self.status_label.update_capacitance_reading(capacitance)
            self.status_label.update_voltage_reading(voltage)

    ####### Dropbot Icon Image Control Methods ###########

    @timestamped_value('connected_message')
    def _on_disconnected_triggered(self, body):
        self.status_label.update_status_icon(dropbot_connected=False)
        self.connected_message = body

    @timestamped_value('connected_message')
    def _on_connected_triggered(self, body):
        self.status_label.update_status_icon(dropbot_connected=True)
        self.connected_message = body

    @timestamped_value('connected_message')
    def _on_setup_success_triggered(self, body):
        self.status_label.update_status_icon(dropbot_connected=True)
        self.connected_message = body
        
    @timestamped_value('chip_inserted_message')
    def _on_chip_inserted_triggered(self, body : TimestampedMessage):
        if body == 'True':
            chip_inserted = True
            self.dropbot_connected = True # If the chip is inserted, the dropbot must connected already
        elif body == 'False':
            chip_inserted = False
        else:
            logger.error(f"Invalid chip inserted value: {body}")
            chip_inserted = False
        logger.debug(f"Chip inserted: {chip_inserted}")
        self.status_label.update_status_icon(chip_inserted=chip_inserted)
        self.chip_inserted_message = body

    @timestamped_value('realtime_mode_message')
    def _on_realtime_mode_updated_triggered(self, body):
        self.realtime_mode = body == 'True'
        if not self.realtime_mode:
            self.status_label.update_capacitance_reading(capacitance='-')
            self.status_label.update_voltage_reading(voltage='-')
            self.status_label.update_pressure_reading(pressure='-')
            self.status_label.update_force_reading(force='-')

    ##################################################################################################

    ########## Warning methods ################
    def _on_show_warning_triggered(self, body): # This is not controlled by the dramatiq controller! Called manually in dramatiq_dropbot_status_controller.py
        body = json.loads(body)

        title = body.get('title', ''),
        message = body.get('message', '')

        self.warning_popup = QMessageBox()
        self.warning_popup.setWindowTitle(f"WARNING: {title}")
        self.warning_popup.setText(str(message))
        self.warning_popup.exec()

    def _on_no_power_triggered(self, body):
        if self.no_power:
            return

        self.no_power = True
        # Initialize the dialog
        self.no_power_dialog = QDialog()
        self.no_power_dialog.setWindowTitle("ERROR: No Power")
        self.no_power_dialog.setFixedSize(370, 250)

        # Create the layout
        layout = QVBoxLayout()
        self.no_power_dialog.setLayout(layout)

        # Create the web engine view for displaying HTML
        self.browser = QTextBrowser()

        html_content = f"""

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ERROR: No Power</title>
</head>
<body>
    <h3>DropBot currently has no power supply connected.</h3>
    <strong>Plug in power supply cable<br></strong> <img src='{os.path.dirname(__file__)}{os.sep}images{os.sep}dropbot-power.png' width="104" height="90">
    <strong><br>Click the "Retry" button after plugging in the power cable to attempt reconnection</strong>
</body>
</html>

        """

        self.browser.setHtml(html_content)

        # Create the retry button and connect its signal
        self.no_power_retry_button = QPushButton("Retry")
        self.no_power_retry_button.clicked.connect(self.request_retry_connection)

        # Add widgets to the layout
        layout.addWidget(self.browser)
        layout.addWidget(self.no_power_retry_button)

        # Show the dialog
        self.no_power_dialog.exec()

    def _on_halted_triggered(self, message):
        self.halted_popup = QMessageBox()
        self.halted_popup.setWindowTitle("ERROR: DropBot Halted")
        self.halted_popup.setButtonText(QMessageBox.StandardButton.Ok, "Close")
        self.halted_popup.setText(f"DropBot has been halted, reason was {message}."
                                  "\n\n"
                                  "All channels have been disabled and high voltage has been turned off until "
                                  "the DropBot is restarted (e.g. unplug all cables and plug back in).")

        self.halted_popup.exec()