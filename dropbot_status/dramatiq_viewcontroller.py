# sys imports
import json
import os

# pyside imports
from PySide6.QtWidgets import QVBoxLayout, QPushButton, QMessageBox, QDialog, QTextBrowser
from pint import UnitRegistry

# local imports
from microdrop_application.dialogs import show_success
from microdrop_utils._logger import get_logger
from microdrop_utils.base_dropbot_qwidget import BaseDramatiqControllableDropBotQWidget
from microdrop_utils.decorators import timestamped_value, debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.timestamped_message import TimestampedMessage
from protocol_grid.services.force_calculation_service import ForceCalculationService

from dropbot_controller.consts import DETECT_SHORTS, RETRY_CONNECTION
from microdrop_style.colors import SUCCESS_COLOR, WARNING_COLOR, GREY
from microdrop_utils.ureg_helpers import ureg_quant_percent_change, ureg_diff, get_ureg_magnitude, ureg

from .consts import NUM_CAPACITANCE_READINGS_AVERAGED
from .status_label_widget import DropBotStatusViewController

logger = get_logger(__name__, level="DEBUG")

ureg = UnitRegistry()

disconnected_color = GREY["lighter"]  #ERROR_COLOR
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
BORDER_RADIUS = 4


def _maybe_update(old_value, new_value, update_fn, threshold=60, threshold_type='percentage'):
    if old_value == '-' and new_value != '-':
        update_fn(new_value)
        return "updated"

    elif old_value != '-' and new_value != '-':
        change = 0

        if threshold_type == 'percentage':
            change = ureg_quant_percent_change(old=old_value, new=new_value)

        elif threshold_type == 'absolute_diff':
            change = abs(ureg_diff(old=old_value, new=new_value))

        if change > threshold:
            update_fn(new_value)
            return "updated"

class DramatiqDropBotStatusWidget(BaseDramatiqControllableDropBotQWidget):
    def __init__(self):
        super().__init__()

        self.capacitances = []
        # flag for if no pwoer is true or not
        self.no_power_dialog = None
        self.no_power = None
        self.realtime_mode = False
        self.connected_message = TimestampedMessage("", 0) # We initialize it timestamp 0 so any message will be newer. The string is not important.
        self.chip_inserted_message = TimestampedMessage("", 0)
        self.realtime_mode_message = TimestampedMessage("", 0)

        self.filler_capacitance_over_area = 0 # Initialize calibration data values
        self.liquid_capacitance_over_area = 0 # Both of these are in pF/mm^2
        self.pressure = 0
        self.active_electrodes = []
        self.electrode_areas = {}

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)  # Minimal margins for compactness

        # Instantiate the new DropBotStatusWidget, which is now the View
        self.status_widget = DropBotStatusViewController()
        self.layout.addWidget(self.status_widget)

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
        show_window = json.loads(shorts_dict).get('Show_window', False)

        if len(shorts) == 0 and not show_window:
            logger.info("No shorts were detected.")
            return        
        else: 
            self.shorts_popup = QMessageBox()
            self.shorts_popup.setFixedSize(300, 200)            
            if len(shorts) == 0:
                self.shorts_popup.setWindowTitle("No shorts were detected.")  
                self.shorts_popup.setText("No shorts were detected on any channels.")              
            else:
                self.shorts_popup.setWindowTitle("Shorts Detected")
                shorts_str = str(shorts).strip('[]')
                self.shorts_popup.setText(f"Shorts were detected on the following channels: \n \n"
                                        f"[{shorts_str}] \n \n"
                                        f"You may continue using the DropBot, but the affected channels have "
                                        f"been disabled until the DropBot is restarted (e.g. unplug all cabled and plug "
                                        f"back in).")     
                    
            self.shorts_popup.setButtonText(QMessageBox.StandardButton.Ok, "Close")
            self.shorts_popup.exec()

    ################# Capcitance Voltage readings ##################
    def _on_capacitance_updated_triggered(self, body):
        if self.realtime_mode: # Only update the capacitance and voltage readings if we are in realtime mode
            new_capacitance = json.loads(body).get('capacitance', '-')
            new_voltage = json.loads(body).get('voltage', '-')

            old_capacitance = self.status_widget.grid_widget.get_capacitance_reading()
            old_voltage = self.status_widget.get_voltage_reading()

            self.capacitances.append(get_ureg_magnitude(new_capacitance))

            if len(self.capacitances) == NUM_CAPACITANCE_READINGS_AVERAGED:
                new_capacitance = sum(self.capacitances) / len(self.capacitances)
                new_capacitance = new_capacitance * ureg.picofarad
                new_capacitance = f"{new_capacitance:.4g~P}"
                self.capacitances = []

            else:
                new_capacitance = old_capacitance


            _maybe_update(old_capacitance, new_capacitance, self.status_widget.update_capacitance_reading, threshold=3, threshold_type='absolute_diff')
            voltage_update_result = _maybe_update(old_voltage, new_voltage, self.status_widget.update_voltage_reading, threshold=1, threshold_type='absolute_diff')

            if voltage_update_result == "updated":
                force = None

                if self.pressure:
                    force = ForceCalculationService.calculate_force_for_step(
                        get_ureg_magnitude(new_voltage),
                        self.pressure
                    )

                self.status_widget.update_force_reading(f"{force:.4f} mN/m" if force is not None else "-")

    ################## Calibration data #########################

    def _on_calibration_data_triggered(self, body):

        message = json.loads(body)

        self.filler_capacitance_over_area = message.get('filler_capacitance_over_area', 0.0)
        self.liquid_capacitance_over_area = message.get('liquid_capacitance_over_area', 0.0)

        if self.filler_capacitance_over_area and self.liquid_capacitance_over_area:

            self.pressure = self.liquid_capacitance_over_area - self.filler_capacitance_over_area

            voltage = self.status_widget.get_voltage_reading()

            force = ForceCalculationService.calculate_force_for_step(
                get_ureg_magnitude(voltage),
                self.pressure
            )

            self.status_widget.update_pressure_reading(f"{self.pressure:.4f} pF/mm^2" if self.pressure is not None else "-")
            self.status_widget.update_force_reading(f"{force:.4f} mN/m" if force is not None else "-")

    ####### Dropbot Icon Image Control Methods ###########

    @timestamped_value('connected_message')
    def _on_disconnected_triggered(self, body):
        self.status_widget.update_status(dropbot_connected=False)
        self._on_realtime_mode_updated_triggered(TimestampedMessage("False", None), force_update=True) # Set realtime mode to False when disconnected

    @timestamped_value('connected_message')
    def _on_connected_triggered(self, body):
        self.status_widget.update_status(dropbot_connected=True)
        
    @timestamped_value('chip_inserted_message')
    def _on_chip_inserted_triggered(self, body : TimestampedMessage):
        if body == 'True':
            chip_inserted = True
        elif body == 'False':
            chip_inserted = False
        else:
            logger.error(f"Invalid chip inserted value: {body}")
            chip_inserted = False
        logger.debug(f"Chip inserted: {chip_inserted}")
        self.status_widget.update_status(dropbot_connected=True, chip_inserted=chip_inserted)

    @timestamped_value('realtime_mode_message')
    def _on_realtime_mode_updated_triggered(self, body):
        self.realtime_mode = body == 'True'
        if not self.realtime_mode:
            self.status_widget.update_capacitance_reading(capacitance='-')
            self.status_widget.update_voltage_reading(voltage='-')
            self.status_widget.update_pressure_reading(pressure='-')
            self.status_widget.update_force_reading(force='-')

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
        self.no_power_dialog.setFixedSize(400, 300)

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

    def _on_drops_detected_triggered(self, message):
        message_obj = json.loads(message)

        dialog_text = f"Droplets detected in following channels:\n{message_obj['detected_channels']} "

        result = show_success(
            parent=self,
            title="Droplets Detected",
            message=dialog_text
        )
