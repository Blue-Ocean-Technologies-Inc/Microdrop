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
from .controller import ControlsController
from .message_handler import OpendropStatusAndControlsMessageHandler
from .model import OpendropStatusAndControlsModel
from .view import UnifiedView


class OpendropStatusAndControls(RealtimeModeIconMixin, BaseStatusDockPane):
    """Dock pane for OpenDrop status display and controls."""

    id = PKG + ".dock_pane"
    name = PKG_name

    view = UnifiedView
    status_bar_icon_glyph = ICON_DROP_EC

    def _create_model(self):
        # The plugin made the model and its listener at start, before any
        # routed message could arrive; the pane shows that model.
        return self._status_plugin().status_model

    def _create_controller(self):
        return ControlsController(self.model)

    def _create_message_handler(self) -> OpendropStatusAndControlsMessageHandler:
        return self._status_plugin().message_handler

    def _status_plugin(self):
        return self.task.window.application.get_plugin(self.status_bar_plugin_id)

    def destroy(self):
        # The listener is the plugin's, released when it stops: a pane
        # closed and remade must not leave its routed messages unhandled.
        self.message_handler = None

        super().destroy()


if __name__ == "__main__":
    model = OpendropStatusAndControlsModel()
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
