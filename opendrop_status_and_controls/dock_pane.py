from pyface.tasks.api import TraitsDockPane


# Handle imports gracefully depending on execution context
try:
    # Attempt relative imports (Works when imported normally as part of the package)
    from .consts import PKG, PKG_name
    from .model import OpendropStatusAndControlsModel
    from .controller import ControlsController
    from .view import UnifiedView
    from .message_handler import OpendropStatusAndControlsMessageHandler
except ImportError:
    from opendrop_status_and_controls.consts import PKG, PKG_name
    from opendrop_status_and_controls.model import OpendropStatusAndControlsModel
    from opendrop_status_and_controls.controller import ControlsController
    from opendrop_status_and_controls.view import UnifiedView
    from opendrop_status_and_controls.message_handler import OpendropStatusAndControlsMessageHandler

class OpendropStatusAndControls(TraitsDockPane):
    """
    A unified dock pane combining status display and manual controls.
    """

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    # 1. Shared model
    model = OpendropStatusAndControlsModel()
    view = UnifiedView
    controller = ControlsController(model)
    view.handler = controller

    def traits_init(self):
        # Message handler (Dramatiq listener)
        self.message_handler = OpendropStatusAndControlsMessageHandler(
            model=self.model,
            name=f"{PKG}_listener"
        )


if __name__ == '__main__':

    # 1. Shared model
    model = OpendropStatusAndControlsModel()

    # 3. Single unified TraitsUI view
    controls_controller = ControlsController(model)
    ui = model.configure_traits(
        view=UnifiedView, handler=controls_controller
    )
