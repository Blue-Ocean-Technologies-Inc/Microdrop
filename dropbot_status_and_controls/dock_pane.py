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
        self._dialog_signals.voltage_frequency_range_changed.connect(
            self._update_spinner_ranges
        )

    def _update_spinner_ranges(self, data):
        """Update the QSpinBox min/max on the voltage and frequency controls."""
        if self.controller.info and self.controller.info.initialized:
            info = self.controller.info
            if hasattr(info, 'voltage') and info.voltage.control is not None:
                info.voltage.control.setMinimum(data['ui_min_voltage'])
                info.voltage.control.setMaximum(data['ui_max_voltage'])
            if hasattr(info, 'frequency') and info.frequency.control is not None:
                info.frequency.control.setMinimum(data['ui_min_frequency'])
                info.frequency.control.setMaximum(data['ui_max_frequency'])


if __name__ == "__main__":
    model = DropbotStatusAndControlsModel()
    dialog_signals = DialogSignals()
    message_handler = DropbotStatusAndControlsMessageHandler(
        model=model, dialog_signals=dialog_signals, name=listener_name
    )
    dialog_view = DialogView(dialog_signals=dialog_signals, message_handler=message_handler)
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
