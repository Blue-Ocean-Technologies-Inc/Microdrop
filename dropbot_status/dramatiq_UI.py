# sys imports
import json
import os

from PySide6.QtCore import QObject, Signal, Slot
# pyside imports
from PySide6.QtWidgets import QVBoxLayout, QPushButton, QMessageBox, QDialog, QTextBrowser, QWidget
from traits.has_traits import HasTraits
from traits.trait_types import Instance

# local imports
from logger.logger_service import get_logger
from microdrop_utils.decorators import timestamped_value
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.datetime_helpers import TimestampedMessage
from protocol_grid.services.force_calculation_service import ForceCalculationService

from dropbot_controller.consts import RETRY_CONNECTION
from microdrop_style.colors import SUCCESS_COLOR, WARNING_COLOR, GREY
from microdrop_utils.ureg_helpers import ureg_quant_percent_change, ureg_diff, get_ureg_magnitude, ureg

from .consts import NUM_CAPACITANCE_READINGS_AVERAGED
from .model import DropBotStatusModel

logger = get_logger(__name__)

from microdrop_utils.ureg_helpers import ureg

disconnected_color = GREY["lighter"]  #ERROR_COLOR
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
BORDER_RADIUS = 4


def check_change_significance(old_value, new_value, threshold=60, threshold_type='percentage') -> bool:
    if old_value == '-' and new_value != '-':
        return True

    elif old_value != '-' and new_value != '-':
        change = 0

        if threshold_type == 'percentage':
            change = ureg_quant_percent_change(old=old_value, new=new_value)

        elif threshold_type == 'absolute_diff':
            change = abs(ureg_diff(old=old_value, new=new_value))

        if change > threshold:
            return True
    return False


class DramatiqDropBotStatusViewModelSignals(QObject):
    """A dedicated QObject to hold signals for UI events, ensuring thread safety."""
    show_shorts_popup = Signal(dict)
    show_warning_popup = Signal(dict)
    show_no_power_dialog = Signal()
    close_no_power_dialog = Signal()
    show_halted_popup = Signal(str)
    show_drops_detected_popup = Signal(dict)


class DramatiqDropBotStatusViewModel(HasTraits):

    model = Instance(DropBotStatusModel)
    view_signals = Instance(DramatiqDropBotStatusViewModelSignals)

    def traits_init(self):

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

    ###################################################################################################################
    # Publisher methods
    ###################################################################################################################
    def request_retry_connection(self):
        logger.info("Retrying connection...")
        publish_message("Retry connection button triggered", RETRY_CONNECTION)

        if self.no_power:
            self.no_power = False
            self.view_signals.close_no_power_dialog.emit()

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
                title = "No shorts were detected."
                text = "No shorts were detected on any channels."
            else:
                title = "Shorts Detected"
                shorts_str = str(shorts).strip('[]')
                text = (f"Shorts were detected on the following channels: \n \n"
                                        f"[{shorts_str}] \n \n"
                                        f"You may continue using the DropBot, but the affected channels have "
                                        f"been disabled until the DropBot is restarted (e.g. unplug all cabled and plug "
                                        f"back in).")     
                    
            self.view_signals.show_shorts_popup.emit({'title': title, 'text': text})

    ################# Capcitance Voltage readings ##################
    def _on_capacitance_updated_triggered(self, body):
        if self.realtime_mode: # Only update the capacitance and voltage readings if we are in realtime mode
            new_capacitance = json.loads(body).get('capacitance', '-')
            new_voltage = json.loads(body).get('voltage', '-')

            old_capacitance = self.model.capacitance
            old_voltage = self.model.voltage

            self.capacitances.append(get_ureg_magnitude(new_capacitance))

            if len(self.capacitances) == NUM_CAPACITANCE_READINGS_AVERAGED:
                new_capacitance = sum(self.capacitances) / len(self.capacitances)
                new_capacitance = new_capacitance * ureg.picofarad
                new_capacitance = f"{new_capacitance:.4g~P}"
                self.capacitances = []

            else:
                new_capacitance = old_capacitance


            cap_change_significant = check_change_significance(old_capacitance, new_capacitance, threshold=3, threshold_type='absolute_diff')
            voltage_change_significant = check_change_significance(old_voltage, new_voltage, threshold=1, threshold_type='absolute_diff')

            if cap_change_significant:
                self.model.capacitance = new_capacitance

            if voltage_change_significant:
                self.model.voltage = new_voltage
                force = None

                if self.model.pressure != "-":
                    force = ForceCalculationService.calculate_force_for_step(
                        get_ureg_magnitude(new_voltage),
                        get_ureg_magnitude(self.model.pressure)
                    )

                self.model.force = f"{force:.4f} mN/m" if force is not None else "-"

    ################## Calibration data #########################

    def _on_calibration_data_triggered(self, body_str):
        data = json.loads(body_str)
        filler_cap = data.get('filler_capacitance_over_area', 0.0)
        liquid_cap = data.get('liquid_capacitance_over_area', 0.0)

        if filler_cap and liquid_cap:
            self.pressure_value = liquid_cap - filler_cap
            force = ForceCalculationService.calculate_force_for_step(
                get_ureg_magnitude(self.model.voltage),
                self.pressure_value
            )
            self.model.pressure = f"{self.pressure_value:.4f} pF/mm^2"
            self.model.force = f"{force:.4f} mN/m"

    ####### Dropbot Icon Image Control Methods ###########

    @timestamped_value('connected_message')
    def _on_disconnected_triggered(self, body):
        self.model.connected = False
        self._on_realtime_mode_updated_triggered(TimestampedMessage("False", None), force_update=True) # Set realtime mode to False when disconnected

    @timestamped_value('connected_message')
    def _on_connected_triggered(self, body):
        self.model.connected = True
        
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
        self.model.chip_inserted = chip_inserted

    @timestamped_value('realtime_mode_message')
    def _on_realtime_mode_updated_triggered(self, body):
        self.realtime_mode = body == 'True'
        if not self.realtime_mode:
            self.model.reset_readings()

    ##################################################################################################

    ########## Warning methods ################
    def _on_no_power_triggered(self, body):
        if self.no_power:
            return
        self.no_power = True
        self.view_signals.show_no_power_dialog.emit()

    def _on_halted_triggered(self, message):
        text = (f"DropBot has been halted, reason was {message}.\n\n"
                "All channels have been disabled until the DropBot is restarted.")
        self.view_signals.show_halted_popup.emit(text)


class DramatiqDropBotStatusView(QWidget):
    """
    The View: Manages UI elements only (popups, dialogs).
    It listens to signals from the ViewModel and delegates user actions back to it.
    """

    def __init__(self, view_model: DramatiqDropBotStatusViewModel, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        self.no_power_dialog = None  # To hold a reference to the dialog

        # --- Connect signals from the ViewModel to slots in this View ---
        vm_signals = self.view_model.view_signals
        vm_signals.show_halted_popup.connect(self.on_show_halted_popup)
        vm_signals.show_no_power_dialog.connect(self.on_show_no_power)
        vm_signals.close_no_power_dialog.connect(self.on_close_no_power)

    @Slot(str)
    def on_show_halted_popup(self, text):
        QMessageBox.critical(self, "ERROR: DropBot Halted", text)

    @Slot()
    def on_show_no_power(self):
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
        self.no_power_retry_button.clicked.connect(self.view_model.request_retry_connection)

        # Add widgets to the layout
        layout.addWidget(self.browser)
        layout.addWidget(self.no_power_retry_button)

        # Show the dialog
        self.no_power_dialog.exec()

    @Slot()
    def on_close_no_power(self):
        if self.no_power_dialog:
            self.no_power_dialog.close()
            self.no_power_dialog = None