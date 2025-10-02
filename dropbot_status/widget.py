# The Model: Holds the raw data and state. It knows nothing about the UI.
from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Signal, QObject
from traits.api import HasTraits, Bool, observe, Instance, Str, Enum, Property

from dropbot_status.consts import DROPBOT_CHIP_INSERTED_IMAGE, DROPBOT_IMAGE
from dropbot_status.status_label_widget import DropBotIconWidget, DropBotStatusGridWidget

from microdrop_style.colors import SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR
from microdrop_utils._logger import get_logger

logger = get_logger(__name__, level="DEBUG")

disconnected_color = ERROR_COLOR
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR
BORDER_RADIUS = 4


class DropBotStatusModel(HasTraits):
    """Represents the raw state of the DropBot hardware."""
    # Connection state
    connected = Bool(False, desc="True if the DropBot is connected")
    chip_inserted = Bool(False, desc="True if a chip is inserted")

    # Sensor readings
    capacitance = Str("-", desc="Raw capacitance in pF")
    voltage = Str("-", desc="Voltage set to device in V")
    pressure = Str("-", desc="Pressure reading in kPa")
    force = Str("-", desc="Calculated force in N")



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
    def update_capacitance_reading(self, event):
        self.view_signals.capacitance_changed.emit(event.new)

    @observe("model:voltage")
    def update_voltage_reading(self, event):
        self.view_signals.voltage_changed.emit(event.new)

    @observe("model:pressure")
    def update_pressure_reading(self, event):
        self.view_signals.pressure_changed.emit(event.new)

    @observe("model:force")
    def update_force_reading(self, event):
        self.view_signals.force_changed.emit(event.new)


class DropBotStatusView(QWidget):
    """
    The main view container. It is "dumb" and only knows how to display
    what the ViewModel tells it.
    """

    def __init__(self, view_signals: 'DropbotStatusViewModelSignals', parent=None):
        super().__init__(parent)
        self.setWindowTitle("DropBot Status")
        self._view_model_signals = view_signals

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
        self.main_layout.addWidget(self.icon_widget, 1)
        self.main_layout.addWidget(self.grid_widget, 2)

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
