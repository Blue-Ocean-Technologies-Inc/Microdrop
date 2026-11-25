# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Microdrop package imports.
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import RealtimeModeIconMixin

# Microdrop style imports.
from microdrop_style.icons.icons import ICON_DROP_EC

# Local imports.
from .consts import PKG, PKG_name
from .controller import MockDropbotDockPaneController
from .message_handler import MockDropbotMessageHandler
from .view import MockDropbotView

# Logger import.
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
        # The plugin made the model and its listener at start, before any
        # routed message could arrive; the pane shows that model.
        return self._status_plugin().status_model

    def _create_controller(self):
        return MockDropbotDockPaneController(self.model)

    def _create_message_handler(self) -> MockDropbotMessageHandler:
        return self._status_plugin().message_handler

    def _status_plugin(self):
        return self.task.window.application.get_plugin(self.status_bar_plugin_id)

    def destroy(self):
        # The listener is the plugin's, released when it stops: a pane
        # closed and remade must not leave its routed messages unhandled.
        self.message_handler = None

        super().destroy()
