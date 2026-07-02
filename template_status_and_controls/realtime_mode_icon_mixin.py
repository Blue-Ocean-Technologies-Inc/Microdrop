"""
RealtimeModeIconMixin — opt-in status-bar toggle for realtime mode.

Mix into a BaseStatusDockPane subclass, listed BEFORE the base so this
class's _create_status_bar_widgets override runs first::

    class MyDevicePane(RealtimeModeIconMixin, BaseStatusDockPane):
        ...

The mixin appends a ClickableToggleIcon after the device status icon. The
toggle publishes SET_REALTIME_MODE (the pub/sub contract with the DropBot
backend), greys out while disconnected, and locks while a protocol runs.
Never instantiated standalone: its ``model.*`` observers bind against the
pane's model trait.
"""
from traits.api import Any, HasTraits, observe

from dropbot_controller.consts import SET_REALTIME_MODE
from microdrop_style.colors import GREY, SUCCESS_COLOR
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.pyside_helpers import ClickableToggleIcon

from .base_dock_pane import status_bar_icon_font

REALTIME_ICON_GLYPH = "live_tv"
REALTIME_ICON_ACTIVE_INACTIVE_DISABLED_STYLES = (
    f"QLabel {{color: {SUCCESS_COLOR};}}",
    f"QLabel {{color: {GREY['lighter']};}}",
    f"QLabel {{color: {GREY['lighter']};}}",
)
REALTIME_ICON_ACTIVE_INACTIVE_DISABLED_TOOLTIPS = (
    "Click to <b>disable</b> realtime mode",
    "Click to <b>enable</b> realtime mode",
    "Cannot enable realtime mode. No device <b>connection</b>",
)
REALTIME_ICON_LOCKED_TOOLTIP = (
    "Realtime mode is locked while a <b>protocol</b> is running"
)


class RealtimeModeIconMixin(HasTraits):
    """Adds a realtime-mode toggle next to the device status-bar icon."""

    #: Status-bar toggle widget (built with the other status-bar widgets).
    realtime_mode_icon = Any(None)

    def _create_status_bar_widgets(self):
        self.realtime_mode_icon = self._create_realtime_mode_icon()
        # initial check: enable / disable based on the current connection state
        self._enable_realtime_icon_based_on_modes()
        return super()._create_status_bar_widgets() + [self.realtime_mode_icon]

    def _create_realtime_mode_icon(self):
        icon = ClickableToggleIcon(
            REALTIME_ICON_GLYPH,
            REALTIME_ICON_ACTIVE_INACTIVE_DISABLED_STYLES,
            REALTIME_ICON_ACTIVE_INACTIVE_DISABLED_TOOLTIPS,
            locked_tooltip=REALTIME_ICON_LOCKED_TOOLTIP,
        )
        icon.setFont(status_bar_icon_font())
        icon.toggled.connect(
            lambda is_active: publish_message(
                topic=SET_REALTIME_MODE, message=str(is_active)
            )
        )
        return icon

    @observe("model.connected", dispatch="ui")
    @observe("model.protocol_running", dispatch="ui")
    def _enable_realtime_icon_based_on_modes(self, event=None):
        # Disabled (greyed + "no connection" tooltip) reflects connection only.
        # While connected and a protocol is running, lock the icon instead:
        # it keeps its normal appearance but is non-interactive.
        if self.realtime_mode_icon is None:
            return
        self.realtime_mode_icon.setEnabled(self.model.connected)
        self.realtime_mode_icon.setLocked(
            self.model.connected and self.model.protocol_running
        )

    @observe("model.realtime_mode", dispatch="ui")
    def _sync_realtime_icon(self, event):
        if self.realtime_mode_icon is None:
            return
        self.realtime_mode_icon.is_active = event.new
        self.realtime_mode_icon.update_style()
