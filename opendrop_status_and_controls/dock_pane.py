# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import RealtimeModeIconMixin

from microdrop_style.icons.icons import ICON_DROP_EC

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
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
        return OpendropStatusAndControlsModel()

    def _create_controller(self):
        return ControlsController(self.model)

    def _create_message_handler(self) -> OpendropStatusAndControlsMessageHandler:
        name = f"{PKG}_listener"
        return OpendropStatusAndControlsMessageHandler(
            model=self.model,
            name=name,
            topics=ACTOR_TOPIC_DICT[name],
        )


if __name__ == "__main__":
    model = OpendropStatusAndControlsModel()
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
