import functools

from PySide6.QtCore import QObject, Signal

from traits.has_traits import HasTraits, observe
from traits.trait_types import Instance

from microdrop_utils.decorators import debounce
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from peripherals_ui.model import PeripheralModel

from logger.logger_service import get_logger
logger = get_logger(__name__)

from peripheral_controller.consts import GO_HOME, MOVE_UP, MOVE_DOWN, SET_POSITION

def log_function_call_and_exceptions(func):
    """
    A decorator that wraps the decorated function in a try-except block,
    logging the function's name and any exceptions that occur.
    """
    @functools.wraps(func)  # Preserves the original function's metadata
    def wrapper(*args, **kwargs):
        func_name = f"{func.__module__}.{func.__name__}"
        logger.info(f"Calling function: {func_name}")
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            logger.error(f"Error in function: {func_name}: {e}")
            raise

    return wrapper

# ----------------------------------------------------------------------------
# The ViewModel's Signal Bridge
# A dedicated QObject to hold Qt signals for thread-safe communication.
# ----------------------------------------------------------------------------

class ZStageViewModelSignals(QObject):
    """Holds Qt signals for the ViewModel to communicate with the View."""
    status_text_changed = Signal(str)
    position_text_changed = Signal(str)
    position_value_changed = Signal(float)  # Signal for the raw float value
    controls_enabled_changed = Signal(bool)


class ZStageViewModel(HasTraits):
    """Manages the logic for the Positioner View."""
    model = Instance(PeripheralModel)
    view_signals = Instance(ZStageViewModelSignals, ())  # Auto-creates an instance

    # --- Commands (for the View's buttons to call) ---
    @log_function_call_and_exceptions
    def move_up(self):
        """Command to move the position up."""
        publish_message("", MOVE_UP)

    @log_function_call_and_exceptions
    def move_down(self):
        """Command to move the position down."""
        publish_message("", MOVE_DOWN)

    @log_function_call_and_exceptions
    def go_home(self):
        """Command to send the positioner to the home position."""
        publish_message("", GO_HOME)

    @log_function_call_and_exceptions
    @debounce(0.3)
    def set_position(self, value: float):
        """Command to set the positioner to a specific value."""
        publish_message(str(value), SET_POSITION)

    @log_function_call_and_exceptions
    def disconnect_device(self):
        self.model.status = not self.model.status

    # --- Logic Methods ---
    # These contain the formatting logic, so observers are simple.
    @log_function_call_and_exceptions
    def _update_status_text(self):
        """Formats and emits the current status text."""
        status = "Active" if self.model.status else "Inactive"
        display_text = f"Status: {status}"
        self.view_signals.status_text_changed.emit(display_text)

    @log_function_call_and_exceptions
    def _update_position_display(self):
        """Formats and emits the current position as a string."""
        display_text = f"Position: {self.model.position:.2f} mm"
        self.view_signals.position_text_changed.emit(display_text)

    @log_function_call_and_exceptions
    def _update_controls_enabled(self):
        # if self.model.realtime_mode and self.model.status:
        #     enabled = True
        # else:
        #     enabled = False

        self.view_signals.controls_enabled_changed.emit(self.model.status)


    # --- Observers (React to Model changes) ---

    @observe("model:status")
    def _on_status_changed(self, event):
        """Fires when model.status changes."""
        logger.info(f"{self.model.device_name} Status change: {event}")
        self._update_status_text()
        self._update_controls_enabled()

    # @observe("model:realtime_mode")
    # def _on_realtime_mode_changed(self, event):
    #     """Fires when model.realtime_mode changes."""
    #     self._update_controls_enabled()

    @observe("model:position")
    def _on_position_changed(self, event):
        """Fires when model.position changes."""
        self._update_position_display()
        # Emit the raw float value for the spin box
        self.view_signals.position_value_changed.emit(event.new)


    # --- Initializer ---
    def force_initial_update(self):
        """Pushes the current model state to the view's signals."""
        self._update_status_text()
        self._update_position_display()
        self.view_signals.position_value_changed.emit(self.model.position)
        self.view_signals.controls_enabled_changed.emit(self.model.status)


