# enthought imports
from traits.api import observe
from pyface.tasks.dock_pane import DockPane

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel

from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icons.icons import ICON_DROP_EC
from microdrop_utils.pyside_helpers import horizontal_spacer_widget
from .consts import PKG, PKG_name
from .displayed_UI import disconnected_color, connected_no_device_color, connected_color


class DropbotStatusDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    """
    #### 'ITaskPane' interface ################################################

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        # Import all the components from your module
        from .displayed_UI import (
            DropbotStatusViewModelSignals,
            DropBotStatusViewModel,
            DropBotStatusView
        )
        from .model import DropBotStatusModel
        from .dramatiq_UI import DramatiqDropBotStatusViewModel, DramatiqDropBotStatusView, DramatiqDropBotStatusViewModelSignals
        from .dramatiq_dropbot_status_controller import DramatiqDropbotStatusController

        model = DropBotStatusModel()

        # initialize dramatiq controllable dropbot status UI
        dramatiq_view_signals = DramatiqDropBotStatusViewModelSignals()
        dramatiq_view_model = DramatiqDropBotStatusViewModel(
            model=model,
            view_signals=dramatiq_view_signals
        )

        # store controller and view in dock pane
        self.dramatiq_controller = DramatiqDropbotStatusController(ui=dramatiq_view_model,
                                                                   listener_name=dramatiq_view_model.__class__.__module__.split(".")[0] + "_listener")
        self.dramatiq_status_view = DramatiqDropBotStatusView(view_model=dramatiq_view_model)

        # initialize displayed UI
        view_signals = DropbotStatusViewModelSignals()
        view_model = DropBotStatusViewModel(
            model=model,
            view_signals=view_signals
        )

        status_view = DropBotStatusView(view_model=view_model)

        return status_view

    @observe("task:window:status_bar_manager")
    def _setup_app_statusbar_with_dropbot_status_icon(self, event):
        from .displayed_UI import disconnected_color

        _model = self.dramatiq_controller.ui.model

        dropbot_status = QLabel(ICON_DROP_EC)

        _font = QFont(ICON_FONT_FAMILY)
        _font.setPointSize(18)
        dropbot_status.setFont(_font)
        dropbot_status.setStyleSheet(f"color: {disconnected_color}")

        dropbot_status.setToolTip(dropbot_status_icon_tooltip_html)

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(horizontal_spacer_widget(10))
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(dropbot_status, stretch=0.2)

        def set_status_color(color):
            dropbot_status.setStyleSheet(f"color: {color}")

        self.control.widget()._view_model_signals.icon_color_changed.connect(set_status_color)


dropbot_status_icon_tooltip_html = f"""
<div style="font-family: sans-serif; font-size: 10pt; line-height: 1.4;">
  <strong style="font-size: 1.1em;">Dropbot Status:</strong>
  <ul style="margin-top: 5px; margin-bottom: 0; padding-left: 20px;">
    <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
    <li><strong style="color: {connected_no_device_color};">Connected (No Chip)</strong></li>
    <li><strong style="color: {connected_color};">Connected (Chip Detected)</strong></li>
  </ul>
</div>
"""

