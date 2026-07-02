from microdrop_style.icons.icons import ICON_DROP_EC
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import RealtimeModeIconMixin

from .consts import PKG, PKG_name, listener_name
from .model import MockDropbotStatusModel
from .controller import MockDropbotDockPaneController
from .message_handler import MockDropbotMessageHandler
from .view import MockDropbotView

from logger.logger_service import get_logger

logger = get_logger(__name__)


class MockDropbotStatusDockPane(RealtimeModeIconMixin, BaseStatusDockPane):
    """Dock pane for MockDropBot interactive controls.

    Communicates with the mock backend exclusively via pub/sub topics.
    No direct object references to the backend controller.
    """

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    view = MockDropbotView
    status_bar_icon_glyph = ICON_DROP_EC

    def _create_model(self):
        return MockDropbotStatusModel()

    def _create_controller(self):
        return MockDropbotDockPaneController(self.model)

    def _create_message_handler(self) -> MockDropbotMessageHandler:
        return MockDropbotMessageHandler(
            model=self.model,
            name=listener_name,
        )
