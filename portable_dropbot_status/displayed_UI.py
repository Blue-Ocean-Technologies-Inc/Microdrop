from functools import wraps

from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpacerItem, QSizePolicy
from PySide6.QtCore import Signal, QObject
from traits.api import HasTraits, observe, Instance

from .consts import DROPBOT_CHIP_INSERTED_IMAGE, DROPBOT_IMAGE
from .model import DropBotStatusModel
from .status_label_widgets import DropBotIconWidget, DropBotStatusGridWidget

from microdrop_style.colors import SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR, GREY
from logger.logger_service import get_logger
from microdrop_utils.ureg_helpers import trim_to_n_digits

logger = get_logger(__name__)

disconnected_color = GREY["lighter"] #ERROR_COLOR
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
BORDER_RADIUS = 4

N_DISPLAY_DIGITS = 3


class DropbotStatusViewModelSignals(QObject):
    # Signals that the View will bind to
    icon_path_changed = Signal(str)
    icon_color_changed = Signal(str)

    connection_status_text_changed = Signal(str)
    chip_status_text_changed = Signal(str)

    capacitance_changed = Signal(str)
    voltage_changed = Signal(str)
    pressure_changed = Signal(str)
    force_changed = Signal(str)

class DropBotStatusViewModel(HasTraits):
    """
    Manages the state and logic for the DropBot status view.
    It translates model data into view-friendly properties via signals.
    """

    model = Instance(DropBotStatusModel)
    view_signals = Instance(DropbotStatusViewModelSignals)

    # ---------- Model traits presentation value getters  -----------------
    def _get_connection_status_text(self):
        return "Active" if self.model.connected else "Inactive"

    def _get_chip_status_text(self):
        return "Inserted" if self.model.chip_inserted else "Not Inserted"

    def _get_icon_path(self):
        return DROPBOT_CHIP_INSERTED_IMAGE if self.model.chip_inserted else DROPBOT_IMAGE

    def _get_icon_color(self):
        if self.model.connected:
            if self.model.chip_inserted:
                return connected_color
            else:
                return connected_no_device_color
        else:
            return disconnected_color

    # ----- decorator for emitting formatted measurements ---------

    @staticmethod
    def format_and_emit_measurements(signal_name: str):
        """
        A decorator factory that formats the event.new value from an observer
        and emits it on a specified signal.
        """


        def decorator(func):
            @wraps(func)
            def wrapper(self, event):
                # 1. Format the incoming value
                try:
                    formatted_value = trim_to_n_digits(event.new, N_DISPLAY_DIGITS)
                except AssertionError:
                    if event.new == "-":
                        logger.info(f"{event.name.title()} is not measured by device. Value is {event.new}")
                        formatted_value = event.new
                    else:
                        logger.warning(f"{event.name.title()} changed to value that cannot be parsed. Format needed: '[quantity] [units]'")

                        return

                # 2. Get the correct signal from the instance using its name
                signal_to_emit = getattr(self.view_signals, signal_name)

                # 3. Emit the formatted value
                signal_to_emit.emit(formatted_value)

            return wrapper

        return decorator

    # --- Trait handlers for sensor readings ---

    @observe("model:connected")
    def update_connection_status(self, event):
        self.view_signals.connection_status_text_changed.emit(self._get_connection_status_text())

        self.view_signals.icon_color_changed.emit(self._get_icon_color())

    @observe("model:chip_inserted")
    def update_chip_status(self, event):
        self.view_signals.chip_status_text_changed.emit(self._get_chip_status_text())

        self.view_signals.icon_color_changed.emit(self._get_icon_color())
        self.view_signals.icon_path_changed.emit(self._get_icon_path())

    @observe("model:capacitance")
    @format_and_emit_measurements("capacitance_changed")
    def update_capacitance_reading(self, event):
        pass

    @observe("model:voltage")
    @format_and_emit_measurements("voltage_changed")
    def update_voltage_reading(self, event):
        pass

    @observe("model:pressure")
    @format_and_emit_measurements("pressure_changed")
    def update_pressure_reading(self, event):
        pass

    @observe("model:force")
    @format_and_emit_measurements("force_changed")
    def update_force_reading(self, event):
        pass

class DropBotStatusView(QWidget):
    """
    The main view container. It is "dumb" and only knows how to display
    what the ViewModel tells it.
    """

    def __init__(self, view_model: 'DropBotStatusViewModel', parent=None):
        super().__init__(parent)
        self.setWindowTitle("DropBot Status")

        self._view_model = view_model
        self._view_model_signals = self._view_model.view_signals

        # --- Create and lay out child widgets ---
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setSpacing(15)

        # initialize icon widget
        self.icon_widget = DropBotIconWidget()
        self.icon_widget.set_status_color(disconnected_color)
        self.icon_widget.set_pixmap_from_path(DROPBOT_IMAGE)

        # initialize the status label grid
        self.grid_widget = DropBotStatusGridWidget()

        # compose main layout (icon on left, grid on right)
        self.main_layout.addWidget(self.icon_widget)
        self.main_layout.addWidget(self.grid_widget)
        spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.main_layout.addSpacerItem(spacer)

        # --- Data Binding ---
        # Connect ViewModel signals to the appropriate widget slots/methods.
        self._view_model_signals.icon_path_changed.connect(self.icon_widget.set_pixmap_from_path)
        self._view_model_signals.icon_color_changed.connect(self.icon_widget.set_status_color)
        self._view_model_signals.connection_status_text_changed.connect(self.grid_widget.connection_status.setText)
        self._view_model_signals.chip_status_text_changed.connect(self.grid_widget.chip_status.setText)
        self._view_model_signals.capacitance_changed.connect(self.grid_widget.capacitance_reading.setText)
        self._view_model_signals.voltage_changed.connect(self.grid_widget.voltage_reading.setText)
        self._view_model_signals.pressure_changed.connect(self.grid_widget.pressure_reading.setText)
        self._view_model_signals.force_changed.connect(self.grid_widget.force_reading.setText)
