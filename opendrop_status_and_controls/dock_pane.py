from microdrop_style.icons.icons import ICON_DROP_EC
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import RealtimeModeIconMixin

from .consts import PKG, PKG_name
from .model import OpendropStatusAndControlsModel
from .controller import ControlsController
from .view import UnifiedView
from .message_handler import OpendropStatusAndControlsMessageHandler


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
        return OpendropStatusAndControlsMessageHandler(
            model=self.model,
            name=f"{PKG}_listener",
        )


if __name__ == "__main__":
    model = OpendropStatusAndControlsModel()
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
