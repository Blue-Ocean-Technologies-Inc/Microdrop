# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from traits.api import Instance, observe

from dropbot_status_and_controls.preferences import DropbotStatusAndControlsPreferences
from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from template_status_and_controls.realtime_mode_icon_mixin import RealtimeModeIconMixin

from microdrop_style.icons.icons import ICON_DROP_EC

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name, listener_name
from .controller import ControlsController
from .dialog_views import DialogView
from .message_handler import DialogSignals, DropbotStatusAndControlsMessageHandler
from .model import DropbotStatusAndControlsModel
from .view import UnifiedView


class DropbotStatusAndControlsDockPane(RealtimeModeIconMixin, BaseStatusDockPane):
    """Dock pane for DropBot status display and controls."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    view = UnifiedView
    status_bar_icon_glyph = ICON_DROP_EC

    dropbot_status_preferences = Instance(DropbotStatusAndControlsPreferences)
    dialog_view = Instance(DialogView)
    _dialog_signals = Instance(DialogSignals)

    def traits_init(self):
        super().traits_init()
        self.dropbot_status_preferences = DropbotStatusAndControlsPreferences(
            preferences=self.task.window.application.preferences_helper.preferences
        )
        self.model.preferences = self.dropbot_status_preferences

    # ------------------------------------------------------------------ #
    # BaseStatusDockPane factories                                          #
    # ------------------------------------------------------------------ #

    def _create_model(self):
        return DropbotStatusAndControlsModel()

    def _create_controller(self):
        return ControlsController(self.model)

    def _create_message_handler(self) -> DropbotStatusAndControlsMessageHandler:
        self._dialog_signals = DialogSignals()
        return DropbotStatusAndControlsMessageHandler(
            model=self.model,
            dialog_signals=self._dialog_signals,
            name=listener_name,
            topics=ACTOR_TOPIC_DICT[listener_name],
        )

    def _setup_extras(self):
        """Wire up the dialog popups."""
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
            if hasattr(info, "voltage") and info.voltage.control is not None:
                info.voltage.control.setMinimum(data["ui_min_voltage"])
                info.voltage.control.setMaximum(data["ui_max_voltage"])
            if hasattr(info, "frequency") and info.frequency.control is not None:
                info.frequency.control.setMinimum(data["ui_min_frequency"])
                info.frequency.control.setMaximum(data["ui_max_frequency"])

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
    dialog_view = DialogView(
        dialog_signals=dialog_signals, message_handler=message_handler
    )
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
