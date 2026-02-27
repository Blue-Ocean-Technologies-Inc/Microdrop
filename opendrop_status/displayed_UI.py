from functools import wraps

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QSpacerItem, QWidget
from traits.api import HasTraits, Instance, observe

from logger.logger_service import get_logger
from microdrop_style.colors import GREY, SUCCESS_COLOR
from microdrop_utils.ureg_helpers import trim_to_n_digits

from .consts import OPENDROP_CONNECTED_IMAGE, OPENDROP_DISCONNECTED_IMAGE
from .model import OpenDropStatusModel
from .status_label_widgets import OpenDropIconWidget, OpenDropStatusGridWidget

logger = get_logger(__name__)

disconnected_color = GREY["lighter"]
connected_color = SUCCESS_COLOR
N_DISPLAY_DIGITS = 3


class OpenDropStatusViewModelSignals(QObject):
    icon_path_changed = Signal(str)
    icon_color_changed = Signal(str)
    connection_status_text_changed = Signal(str)
    board_id_changed = Signal(str)
    temperature_1_changed = Signal(str)
    temperature_2_changed = Signal(str)
    temperature_3_changed = Signal(str)
    feedback_channels_changed = Signal(str)


class OpenDropStatusViewModel(HasTraits):
    model = Instance(OpenDropStatusModel)
    view_signals = Instance(OpenDropStatusViewModelSignals)

    def _get_connection_status_text(self):
        return "Active" if self.model.connected else "Inactive"

    def _get_icon_path(self):
        if self.model.connected:
            return OPENDROP_CONNECTED_IMAGE
        return OPENDROP_DISCONNECTED_IMAGE

    def _get_icon_color(self):
        return connected_color if self.model.connected else disconnected_color

    @staticmethod
    def _format_measurement(value):
        if value == "-":
            return value
        try:
            return trim_to_n_digits(value, N_DISPLAY_DIGITS)
        except AssertionError:
            return str(value)

    @staticmethod
    def format_and_emit(signal_name: str):
        def decorator(func):
            @wraps(func)
            def wrapper(self, event):
                signal_to_emit = getattr(self.view_signals, signal_name)
                signal_to_emit.emit(self._format_measurement(event.new))

            return wrapper

        return decorator

    @observe("model:connected")
    def update_connection_status(self, event):
        self.view_signals.connection_status_text_changed.emit(self._get_connection_status_text())
        self.view_signals.icon_color_changed.emit(self._get_icon_color())
        self.view_signals.icon_path_changed.emit(self._get_icon_path())

    @observe("model:board_id")
    def update_board_id(self, event):
        self.view_signals.board_id_changed.emit(str(event.new))

    @observe("model:temperature_1")
    @format_and_emit("temperature_1_changed")
    def update_temperature_1(self, event):
        pass

    @observe("model:temperature_2")
    @format_and_emit("temperature_2_changed")
    def update_temperature_2(self, event):
        pass

    @observe("model:temperature_3")
    @format_and_emit("temperature_3_changed")
    def update_temperature_3(self, event):
        pass

    @observe("model:feedback_active_channels")
    def update_feedback_channels(self, event):
        self.view_signals.feedback_channels_changed.emit(str(event.new))


class OpenDropStatusView(QWidget):
    def __init__(self, view_model: "OpenDropStatusViewModel", parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenDrop Status")

        self._view_model = view_model
        self._view_model_signals = self._view_model.view_signals

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setSpacing(15)

        self.icon_widget = OpenDropIconWidget()
        self.icon_widget.set_status_color(disconnected_color)
        self.icon_widget.set_pixmap_from_path(OPENDROP_DISCONNECTED_IMAGE)

        self.grid_widget = OpenDropStatusGridWidget()

        self.main_layout.addWidget(self.icon_widget)
        self.main_layout.addWidget(self.grid_widget)
        spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.main_layout.addSpacerItem(spacer)

        self._view_model_signals.icon_path_changed.connect(self.icon_widget.set_pixmap_from_path)
        self._view_model_signals.icon_color_changed.connect(self.icon_widget.set_status_color)
        self._view_model_signals.connection_status_text_changed.connect(self.grid_widget.connection_status.setText)
        self._view_model_signals.board_id_changed.connect(self.grid_widget.board_id.setText)
        self._view_model_signals.temperature_1_changed.connect(self.grid_widget.temperature_1.setText)
        self._view_model_signals.temperature_2_changed.connect(self.grid_widget.temperature_2.setText)
        self._view_model_signals.temperature_3_changed.connect(self.grid_widget.temperature_3.setText)
        self._view_model_signals.feedback_channels_changed.connect(self.grid_widget.feedback_channels.setText)
