from traits.api import observe, Instance
from pyface.qt.QtCore import Qt

from template_status_and_controls.base_dock_pane import (
    BaseStatusDockPane, build_status_icon_tooltip, status_bar_icon_font)
from microdrop_style.icons.icons import ICON_MODE_HEAT
from microdrop_utils.pyside_helpers import ClickableLabel
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_application.dialogs.pyface_wrapper import information
from logger.logger_service import get_logger

from peripheral_controller.preferences import PeripheralPreferences

from .consts import PKG, PKG_name, listener_name, START_DEVICE_MONITORING, DUMP_CONFIG
from .model import HeaterStatusModel
from .controller import HeaterControlsController
from .view import UnifiedView
from .message_handler import HeaterMessageHandler
from .sensor_config.model import SensorConfigModel
from .sensor_config.controller import SensorConfigController
from .sensor_config.view import SensorConfigView

logger = get_logger(__name__)


class HeaterStatusDockPane(BaseStatusDockPane):
    """Dock pane for heater status display and controls.

    No RealtimeModeIconMixin: the heater's status bar shows only the heat
    icon (clickable, triggers a connection scan)."""

    id = PKG + ".dock_pane"
    name = f"{PKG_name} Dock Pane"

    view = UnifiedView
    status_bar_icon_glyph = ICON_MODE_HEAT

    # Shared "Peripheral Settings" preferences (holds heater_show_stream_off_warning).
    heater_preferences = Instance(PeripheralPreferences)

    # Configure Sensors & Heaters editor state (the message handler fills it from
    # the board's config/scan signals; the dialog below renders it).
    sensor_config_model = Instance(SensorConfigModel, ())

    def traits_init(self):
        super().traits_init()
        self.heater_preferences = PeripheralPreferences(
            preferences=self.task.window.application.preferences_helper.preferences
        )

    # ------------------------------------------------------------------ #
    # BaseStatusDockPane factory hooks                                     #
    # ------------------------------------------------------------------ #
    def _create_model(self):
        return HeaterStatusModel()

    def _create_controller(self):
        return HeaterControlsController(self.model)

    def _create_message_handler(self) -> HeaterMessageHandler:
        return HeaterMessageHandler(
            model=self.model, config_model=self.sensor_config_model, name=listener_name)

    # ------------------------------------------------------------------ #
    # Tools ▸ Heater ▸ Configure Sensors & Heaters (opened via DockPaneAction) #
    # ------------------------------------------------------------------ #
    def open_sensor_config(self):
        """Open the modal configure dialog and refresh its data from the board."""
        publish_message(topic=DUMP_CONFIG, message="")
        self.sensor_config_model.edit_traits(
            view=SensorConfigView, handler=SensorConfigController())

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

    # ------------------------------------------------------------------ #
    # Status-bar icon — heat symbol, clickable to trigger a connection scan #
    # ------------------------------------------------------------------ #
    # Overrides of @observe-decorated methods MUST re-apply the decorator:
    # an undecorated override silently drops the base registration.
    @observe("task:window:status_bar_manager")
    def _populate_status_bar(self, event):
        super()._populate_status_bar(event)
        self._sync_search_affordance()  # initial cursor for the search state

    def _create_status_bar_icon(self):
        # Clickable: triggers a heater connection scan (same as Tools ▸ Heater ▸
        # Search Connection), so the user can reconnect straight from the icon.
        # The click is ignored while a scan is already active (see model.searching).
        icon = ClickableLabel(self.status_bar_icon_glyph)
        icon.setFont(status_bar_icon_font())
        icon.setStyleSheet(f"color: {self.model.DISCONNECTED_COLOR}")
        icon.clicked.connect(self._search_heater_connection)
        return icon

    def _build_status_bar_tooltip(self) -> str:
        return build_status_icon_tooltip(
            "Heater Status:",
            [
                (self.model.DISCONNECTED_COLOR, "Disconnected"),
                (self.model.CONNECTED_COLOR, "Connected"),
                (self.model.HALTED_COLOR, "Halted (Fault)"),
            ],
            hint="Searching for device…" if self.model.searching
                 else "Click to search for a connection.",
        )

    # ------------------------------------------------------------------ #
    # Status-icon "search connection" click (gated on an active scan)      #
    # ------------------------------------------------------------------ #
    def _search_heater_connection(self):
        """Ask the backend to start a connection scan, unless one is already
        running. The backend acknowledges by publishing its searching state,
        which disables the icon (see _sync_search_affordance)."""
        if self.model.searching:
            logger.debug("Heater search already active; ignoring status-icon click")
            return
        publish_message(topic=START_DEVICE_MONITORING, message="")

    @observe("model:searching", dispatch="ui")
    def _sync_search_affordance(self, event=None):
        """Pointing-hand cursor only when a click would do something — i.e. when
        no scan is currently active — and flip the tooltip to match."""
        if self.status_bar_icon is not None:
            self.status_bar_icon.setCursor(
                Qt.CursorShape.ArrowCursor if self.model.searching
                else Qt.CursorShape.PointingHandCursor)
        self._refresh_status_bar_tooltip()
