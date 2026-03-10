from template_status_and_controls.base_dock_pane import BaseStatusDockPane

from .consts import PKG, PKG_name, listener_name
from .model import MockDropbotStatusModel
from .controller import MockDropbotController as MockDockPaneController
from .message_handler import MockDropbotMessageHandler
from .view import MockDropbotView

from logger.logger_service import get_logger

logger = get_logger(__name__)


class MockDropbotStatusDockPane(BaseStatusDockPane):
    """Dock pane for MockDropBot interactive controls."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    model = MockDropbotStatusModel()
    view = MockDropbotView
    controller = MockDockPaneController(model)
    view.handler = controller

    def _create_message_handler(self) -> MockDropbotMessageHandler:
        return MockDropbotMessageHandler(
            model=self.model,
            name=listener_name,
        )

    def _setup_extras(self):
        pass

    def set_mock_controller(self, mock_controller):
        """Wire the dock pane controller to the mock backend controller."""
        self.controller.mock_controller = mock_controller
        self.model.base_capacitance_pf = mock_controller.base_capacitance_pf
        self.model.capacitance_delta_pf = mock_controller.capacitance_delta_pf
        self.model.capacitance_noise_pf = mock_controller.capacitance_noise_pf
        self.model.stream_interval_ms = mock_controller.stream_interval_ms

        mock_controller.observe(self._on_actuated_channels_changed, "actuated_channels")
        mock_controller.observe(self._on_stream_active_changed, "stream_active")

    def _on_actuated_channels_changed(self, event):
        channels = event.new
        if channels:
            self.model.actuated_channels_text = str(sorted(channels))
        else:
            self.model.actuated_channels_text = "None"

    def _on_stream_active_changed(self, event):
        self.model.stream_active = event.new
