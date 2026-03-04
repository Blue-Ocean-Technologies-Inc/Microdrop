from traits.api import observe

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QApplication

from microdrop_style.helpers import is_dark_mode
from microdrop_style.colors import WHITE, GREY, SUCCESS_COLOR, WARNING_COLOR
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_DROP_EC
from microdrop_utils.pyside_helpers import horizontal_spacer_widget

from template_status_and_controls.base_dock_pane import BaseStatusDockPane

from .consts import PKG, PKG_name, listener_name
from .model import PortableDropbotStatusAndControlsModel
from .controller import ControlsController
from .view import UnifiedView
from .message_handler import DialogSignals, PortableDropbotMessageHandler
from .dialog_views import DialogView

disconnected_color = GREY["lighter"]
connected_no_device_color = WARNING_COLOR
connected_color = SUCCESS_COLOR


class PortableDropbotStatusAndControlsDockPane(BaseStatusDockPane):
    """Dock pane for Portable DropBot status display and controls."""

    # Use dropbot_status.dock_pane id for layout compatibility
    id = "dropbot_status.dock_pane"
    name = f"{PKG_name} Dock Pane"

    model = PortableDropbotStatusAndControlsModel()
    view = UnifiedView
    controller = ControlsController(model)
    view.handler = controller

    def _create_message_handler(self) -> PortableDropbotMessageHandler:
        self._dialog_signals = DialogSignals()
        return PortableDropbotMessageHandler(
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

    # ---- Status-bar icon ----

    @observe("task:window:status_bar_manager")
    def _setup_statusbar_icon(self, event):
        icon = QLabel(ICON_DROP_EC)
        font = QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        icon.setFont(font)
        icon.setStyleSheet(f"color: {disconnected_color}")

        self.task.window.status_bar_manager.status_bar.addPermanentWidget(
            horizontal_spacer_widget(10)
        )
        self.task.window.status_bar_manager.status_bar.addPermanentWidget(icon)

        self.model.observe(
            lambda e: icon.setStyleSheet(f"color: {e.new}"), "icon_color"
        )
        self.status_bar_icon = icon

        def _apply_tooltip():
            icon.setToolTip(_build_status_icon_tooltip())

        _apply_tooltip()
        QApplication.styleHints().colorSchemeChanged.connect(_apply_tooltip)


def _build_status_icon_tooltip() -> str:
    title_color = WHITE if is_dark_mode() else GREY["dark"]
    return f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">Portable Dropbot Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_no_device_color};">Connected (No Chip)</strong></li>
        <li><strong style="color: {connected_color};">Connected (Chip Detected)</strong></li>
      </ul>
    </div>
    """


if __name__ == "__main__":
    model = PortableDropbotStatusAndControlsModel()
    dialog_signals = DialogSignals()
    message_handler = PortableDropbotMessageHandler(
        model=model, dialog_signals=dialog_signals, name=listener_name
    )
    dialog_view = DialogView(
        dialog_signals=dialog_signals, message_handler=message_handler
    )
    controller = ControlsController(model)
    model.configure_traits(view=UnifiedView, handler=controller)
