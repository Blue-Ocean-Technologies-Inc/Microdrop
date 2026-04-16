from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from traits.api import Instance, observe

from dropbot_status_and_controls.preferences import DropbotStatusAndControlsPreferences
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
    dropbot_status_preferences = Instance(DropbotStatusAndControlsPreferences)
    model = DropbotStatusAndControlsModel()
    view = UnifiedView
    controller = ControlsController(model)
    view.handler = controller

    def traits_init(self):
        super().traits_init()
        self.dropbot_status_preferences = DropbotStatusAndControlsPreferences(
            preferences=self.task.window.application.preferences_helper.preferences
        )
        self.model.preferences=self.dropbot_status_preferences

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

    @observe("control")
    def _install_context_menu(self, event):
        widget = event.new
        if widget is None:
            return
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, point):
        menu = QMenu(self.control)
        action = menu.addAction("Show Dielectric Info")
        action.setCheckable(True)
        action.setChecked(self.model.show_dielectric_info)
        action.toggled.connect(
            lambda checked: setattr(self.model, "show_dielectric_info", checked)
        )
        menu.exec(self.control.mapToGlobal(point))

if __name__ == "__main__":
    model = DropbotStatusAndControlsModel()
    dialog_signals = DialogSignals()
    message_handler = DropbotStatusAndControlsMessageHandler(
        model=model, dialog_signals=dialog_signals, name=listener_name
    )
    dialog_view = DialogView(dialog_signals=dialog_signals, message_handler=message_handler)
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
