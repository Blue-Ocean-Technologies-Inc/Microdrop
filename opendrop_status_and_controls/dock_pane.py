from template_status_and_controls.base_dock_pane import BaseStatusDockPane

from .consts import PKG, PKG_name
from .model import OpendropStatusAndControlsModel
from .controller import ControlsController
from .view import UnifiedView
from .message_handler import OpendropStatusAndControlsMessageHandler


class OpendropStatusAndControls(BaseStatusDockPane):
    """Dock pane for OpenDrop status display and controls."""

    id = PKG + ".dock_pane"
    name = PKG_name

    # TraitsDockPane wires these together; view.handler must be set at class level.
    model = OpendropStatusAndControlsModel()
    view = UnifiedView
    controller = ControlsController(model)
    view.handler = controller

    def _create_message_handler(self) -> OpendropStatusAndControlsMessageHandler:
        return OpendropStatusAndControlsMessageHandler(
            model=self.model,
            name=f"{PKG}_listener",
        )


if __name__ == "__main__":
    model = OpendropStatusAndControlsModel()
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
