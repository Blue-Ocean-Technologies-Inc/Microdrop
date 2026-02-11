# enthought imports
from traits.api import observe
from pyface.tasks.dock_pane import DockPane

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QApplication

from microdrop_style.helpers import is_dark_mode
from microdrop_style.colors import WHITE, GREY
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_DROP_EC
from microdrop_utils.pyside_helpers import horizontal_spacer_widget
from .consts import PKG, PKG_name
from .displayed_UI import disconnected_color, connected_no_device_color, connected_color


class DropbotStatusDockPane(DockPane):
    """
    A dock pane to view the status of the dropbot.
    Uses dropbot_status.dock_pane id for layout compatibility (MicrodropTask
    layout references this pane; portable_dropbot_status is a drop-in replacement).
    """
    id = "dropbot_status.dock_pane"
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
                                                                   listener_name=f"{PKG}_listener")
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
        _font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        dropbot_status.setFont(_font)
        dropbot_status.setStyleSheet(f"color: {disconnected_color}")

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(horizontal_spacer_widget(10))
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(dropbot_status)

        def set_status_color(color):
            dropbot_status.setStyleSheet(f"color: {color}")

        control_widget = self.control.widget() if hasattr(self.control, "widget") else self.control
        view_signals = getattr(control_widget, "_view_model_signals", None)
        if view_signals is not None:
            view_signals.icon_color_changed.connect(set_status_color)

        self.status_bar_icon = dropbot_status

        ### update tooltip based on dark / light mode
        def _apply_theme_style():
            self.status_bar_icon.setToolTip(get_status_icon_tooltip_themed())

        _apply_theme_style() # initial setting
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style) # track theme changes



def get_status_icon_tooltip_themed():
    if is_dark_mode():
        title_color = WHITE
    else:
        title_color = GREY['dark']

    dropbot_status_icon_tooltip_html = f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">Dropbot Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_no_device_color};">Connected (No Chip)</strong></li>
        <li><strong style="color: {connected_color};">Connected (Chip Detected)</strong></li>
      </ul>
    </div>
    """

    return dropbot_status_icon_tooltip_html

