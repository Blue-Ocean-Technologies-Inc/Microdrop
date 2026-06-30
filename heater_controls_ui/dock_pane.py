from functools import partial

from traits.api import observe, Instance
from pyface.qt.QtGui import QApplication, QFont

from template_status_and_controls.base_dock_pane import BaseStatusDockPane
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE
from microdrop_style.icons.icons import ICON_MODE_HEAT
from microdrop_style.colors import WHITE, GREY
from microdrop_style.helpers import is_dark_mode
from microdrop_utils.pyside_helpers import horizontal_spacer_widget, ClickableLabel
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_application.dialogs.pyface_wrapper import information

from peripheral_controller.preferences import PeripheralPreferences

from .consts import PKG, PKG_name, listener_name, START_DEVICE_MONITORING
from .model import HeaterStatusModel
from .controller import HeaterControlsController
from .view import UnifiedView
from .message_handler import HeaterMessageHandler


class HeaterStatusDockPane(BaseStatusDockPane):
    """Dock pane for heater status display and controls."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    # TraitsDockPane wires these together; view.handler must be set at class level.
    model = HeaterStatusModel()
    view = UnifiedView
    controller = HeaterControlsController(model)
    view.handler = controller

    # Shared "Peripheral Settings" preferences (holds heater_show_stream_off_warning).
    heater_preferences = Instance(PeripheralPreferences)

    def traits_init(self):
        super().traits_init()
        self.heater_preferences = PeripheralPreferences(
            preferences=self.task.window.application.preferences_helper.preferences
        )

    # ------------------------------------------------------------------ #
    # BaseStatusDockPane factory hooks                                     #
    # ------------------------------------------------------------------ #
    def _create_message_handler(self) -> HeaterMessageHandler:
        return HeaterMessageHandler(model=self.model, name=listener_name)

    # ------------------------------------------------------------------ #
    # "Applies when streaming starts" warning (setpoint edited, stream off) #
    # ------------------------------------------------------------------ #
    @observe("model:stream_off_edit_warning", dispatch="ui")
    def _warn_edit_stream_off(self, event):
        if self.heater_preferences is None or not self.heater_preferences.heater_show_stream_off_warning:
            return
        result = information(
            parent=None,
            title="Streaming is off",
            message="The change will apply when you start streaming.",
            cancel=False,
            checkbox_text="Don't show this again",
        )
        # With checkbox_text, information() returns (result, checked).
        if isinstance(result, tuple) and result[1]:
            self.heater_preferences.heater_show_stream_off_warning = False

    def _setup_extras(self):
        """Status-bar icon is set up via the overridden _setup_statusbar_icon."""

    # ------------------------------------------------------------------ #
    # Status-bar icon — heater symbol only (no realtime toggle icon)       #
    # ------------------------------------------------------------------ #
    @observe("task:window:status_bar_manager")
    def _setup_statusbar_icon(self, event):
        font = QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)

        # Clickable: triggers a heater connection scan (same as Tools ▸ Heater ▸
        # Search Connection), so the user can reconnect straight from the icon.
        icon = ClickableLabel(ICON_MODE_HEAT)
        icon.setFont(font)
        icon.setStyleSheet(f"color: {self.model.DISCONNECTED_COLOR}")
        icon.clicked.connect(
            partial(publish_message, topic=START_DEVICE_MONITORING, message=""))
        self.status_bar_icon = icon  # inherited _sync_model_icon_color recolors this

        def _apply_tooltip():
            icon.setToolTip(_build_heater_status_tooltip(
                self.model.DISCONNECTED_COLOR,
                self.model.CONNECTED_COLOR,
                self.model.HALTED_COLOR,
            ))

        _apply_tooltip()
        QApplication.styleHints().colorSchemeChanged.connect(_apply_tooltip)

        self.task.window.status_bar_manager.status_bar.insertPermanentWidget(2, icon)
        self.task.window.status_bar_manager.status_bar.insertPermanentWidget(
            2, horizontal_spacer_widget(10))

    # The base wires a realtime-mode status-bar icon; the heater has none, so
    # override those observers to no-ops (the base bodies reference an icon we
    # never create).
    def _enable_realtime_icon_based_on_modes(self, event=None):
        pass

    def _sync_realtime_icon(self, event=None):
        pass


def _build_heater_status_tooltip(disconnected_color, connected_color, halted_color) -> str:
    title_color = WHITE if is_dark_mode() else GREY["dark"]
    return f"""
    <div style="font-family: sans-serif; font-size: 10pt; line-height: 1;">
      <strong style="font-size: 1.1em; color: {title_color}">Heater Status:</strong>
      <ul style="margin-top: 1px; margin-bottom: 1px; padding-left: 20px;">
        <li><strong style="color: {disconnected_color};">Disconnected</strong></li>
        <li><strong style="color: {connected_color};">Connected</strong></li>
        <li><strong style="color: {halted_color};">Halted (Fault)</strong></li>
      </ul>
      <div style="margin-top: 3px;"><em>Click to search for a connection.</em></div>
    </div>
    """
