from template_status_and_controls.base_dock_pane import BaseStatusDockPane

from .consts import PKG, PKG_name, listener_name
from .model import MockDropbotStatusModel
from .controller import MockDropbotDockPaneController
from .message_handler import MockDropbotMessageHandler
from .view import MockDropbotView

from logger.logger_service import get_logger

logger = get_logger(__name__)


class MockDropbotStatusDockPane(BaseStatusDockPane):
    """Dock pane for MockDropBot interactive controls.

    Communicates with the mock backend exclusively via pub/sub topics.
    No direct object references to the backend controller.
    """

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    model = MockDropbotStatusModel()
    view = MockDropbotView
    controller = MockDropbotDockPaneController(model)
    view.handler = controller

    def _create_message_handler(self) -> MockDropbotMessageHandler:
        return MockDropbotMessageHandler(
            model=self.model,
            name=listener_name,
        )
