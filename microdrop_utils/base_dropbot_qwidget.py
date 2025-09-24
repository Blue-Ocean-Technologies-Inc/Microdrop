from PySide6.QtCore import Signal
from microdrop_utils._logger import get_logger

from PySide6.QtWidgets import QWidget

logger = get_logger(__name__)


# =============================================================================
# BaseUI Class
# =============================================================================
class BaseDramatiqControllableDropBotQWidget(QWidget):
    """
    A base class for a QWidget components that encapsulates common initialization
    and signal declaration logic with the presence of a controller that uses a dramatiq listener actor.

    This class declares:
      - A common controller_signal (emitting a string) for communication.
      - A controller property (with getter and setter) that uses a
        factory function to create and assign a controller. The controller must implement
        a controller_signal_handler method. The mixin then connects the view's controller_signal
        to the controller's handler method.
      - The controller_dramatiq_listener_name attribute which describes the actor name of the listener actor
        that needs to be created in the controller for updating this widget.

    """
    controller_signal = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._controller = None

        self.controller_dramatiq_listener_name = kwargs.pop('controller_dramatiq_listener_name', None)

    @property
    def controller(self) -> any:
        """
        Retrieve the current controller instance.

        Returns:
            The controller instance if set, or None otherwise.
        """
        return self._controller

    @controller.setter
    def controller(self, controller_factory: callable) -> None:
        """
        Set the controller for the view using a factory function.

        Args:
            controller_factory (callable): A function that accepts the view as an argument
                and returns a controller instance. The controller must implement a
                controller_signal_handler method.

        Raises:
            ValueError: If the provided factory is not callable or if the returned controller
                        does not have a controller_signal_handler method.
        """
        if not callable(controller_factory):
            raise ValueError("Controller factory must be callable")

        # Set the listener actor name based on the root module of the widget's class if one was not initialized
        if self.controller_dramatiq_listener_name is None:
            self.controller_dramatiq_listener_name = self.__class__.__module__.split(".")[0] + "_listener"

        controller = controller_factory(view=self, listener_name=self.controller_dramatiq_listener_name)
        if not hasattr(controller, 'controller_signal_handler'):
            raise ValueError("Controller must implement controller_signal_handler method")

        self._controller = controller
        self.controller_signal.connect(controller.controller_signal_handler)