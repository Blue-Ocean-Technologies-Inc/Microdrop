from traits.api import observe

from template_status_and_controls.base_dock_pane import BaseStatusDockPane

from .consts import PKG, PKG_name, listener_name
from .model import DropbotStatusAndControlsModel
from .controller import ControlsController
from .view import UnifiedView
from .message_handler import DialogSignals, DropbotStatusAndControlsMessageHandler
from .dialog_views import DialogView


class DropbotStatusAndControlsDockPane(BaseStatusDockPane):
    """Dock pane for DropBot status display and controls."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    # TraitsDockPane wires these together; view.handler must be set at class level.
    model = DropbotStatusAndControlsModel()
    view = UnifiedView
    controller = ControlsController(model)
    view.handler = controller

    # ------------------------------------------------------------------ #
    # BaseStatusDockPane factories                                          #
    # ------------------------------------------------------------------ #

    def _create_message_handler(self) -> DropbotStatusAndControlsMessageHandler:
        self._dialog_signals = DialogSignals()
        return DropbotStatusAndControlsMessageHandler(
            model=self.model,
            dialog_signals=self._dialog_signals,
            name=listener_name,
        )

    def _setup_extras(self):
        """Wire up dialog popups and the status-bar icon."""
        self.dialog_view = DialogView(
            dialog_signals=self._dialog_signals,
            message_handler=self.message_handler,
        )

if __name__ == "__main__":
    model = DropbotStatusAndControlsModel()
    dialog_signals = DialogSignals()
    message_handler = DropbotStatusAndControlsMessageHandler(
        model=model, dialog_signals=dialog_signals, name=listener_name
    )
    dialog_view = DialogView(dialog_signals=dialog_signals, message_handler=message_handler)
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
