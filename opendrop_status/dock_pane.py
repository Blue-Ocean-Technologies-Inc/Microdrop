from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel
from pyface.tasks.dock_pane import DockPane
from traits.api import observe

from microdrop_style.colors import GREY, WHITE
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.helpers import is_dark_mode
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_DROP_EC
from microdrop_utils.pyside_helpers import horizontal_spacer_widget

from .consts import PKG, PKG_name
from .displayed_UI import connected_color, disconnected_color


class OpenDropStatusDockPane(DockPane):
    """Dock pane to view OpenDrop status."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    def create_contents(self, parent):
        from .displayed_UI import OpenDropStatusView, OpenDropStatusViewModel, OpenDropStatusViewModelSignals
        from .dramatiq_UI import DramatiqOpenDropStatusView, DramatiqOpenDropStatusViewModel
        from .dramatiq_opendrop_status_controller import DramatiqOpenDropStatusController
        from .model import OpenDropStatusModel

        model = OpenDropStatusModel()

        dramatiq_view_model = DramatiqOpenDropStatusViewModel(model=model)
        self.dramatiq_controller = DramatiqOpenDropStatusController(
            ui=dramatiq_view_model,
            listener_name=dramatiq_view_model.__class__.__module__.split(".")[0] + "_listener",
        )
        self.dramatiq_status_view = DramatiqOpenDropStatusView(view_model=dramatiq_view_model)

        view_signals = OpenDropStatusViewModelSignals()
        view_model = OpenDropStatusViewModel(model=model, view_signals=view_signals)
        status_view = OpenDropStatusView(view_model=view_model)
        return status_view

    @observe("task:window:status_bar_manager")
    def _setup_app_statusbar_with_opendrop_status_icon(self, event):
        opendrop_status = QLabel(ICON_DROP_EC)

        _font = QFont(ICON_FONT_FAMILY)
        _font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        opendrop_status.setFont(_font)
        opendrop_status.setStyleSheet(f"color: {disconnected_color}")

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(horizontal_spacer_widget(10))
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(opendrop_status)

        def set_status_color(color):
            opendrop_status.setStyleSheet(f"color: {color}")

        self.control.widget()._view_model_signals.icon_color_changed.connect(set_status_color)
        self.status_bar_icon = opendrop_status

        def _apply_theme_style():
            self.status_bar_icon.setToolTip(get_status_icon_tooltip_themed())

        _apply_theme_style()
        QApplication.styleHints().colorSchemeChanged.connect(_apply_theme_style)


def get_status_icon_tooltip_themed():
    title_color = WHITE if is_dark_mode() else GREY["dark"]
    return f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">OpenDrop Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_color};">Connected</strong></li>
      </ul>
    </div>
    """
