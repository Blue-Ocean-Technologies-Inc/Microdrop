"""
StatusBarPlugin — the one home for the application status bar.

Creates the window's StatusBarManager and owns the ``status_bar_icons``
extension point: other plugins contribute QWidget instances (typically at
runtime, from their dock panes) and this plugin places them in a single
icon container whose QHBoxLayout gives every icon the same gap. Removing
a widget from the extension point removes it from the bar and deletes it.

Dynamic contribution handling mirrors MessageRouterPlugin: apply the
current extensions once the container exists, then react to
``<name>_items`` delta events for runtime (hot load/unload) changes.
"""
from envisage.api import ExtensionPoint, Plugin
from pyface.qt.QtGui import QHBoxLayout, QWidget
from traits.api import Any, List, observe, on_trait_change

from logger.logger_service import get_logger
from microdrop_utils.pyface_helpers import StatusBarManager

from .consts import (
    DEFAULT_STATUS_MESSAGE,
    ICON_SPACING,
    PKG,
    PKG_name,
    STATUS_BAR_CONTENTS_MARGINS,
    STATUS_BAR_ICONS,
)

logger = get_logger(__name__)


class StatusBarPlugin(Plugin):
    """Creates the app status bar and manages contributed status icons."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    status_bar_icons = ExtensionPoint(
        List(),
        id=STATUS_BAR_ICONS,
        desc="QWidget instances to show in the app status bar; this plugin "
             "owns their placement, spacing, and removal",
    )

    #: Single container appended to the status bar; its HBox layout gives
    #: every contributed icon the same gap.
    _icon_container = Any(None)

    def start(self):
        # Wire the registry's extension-point listeners to this plugin's
        # traits so the handlers below fire when contributions change at
        # runtime. Opt-in (envisage never calls it for you), and only
        # possible once the plugin is attached to the application.
        self.connect_extension_point_traits()

    @observe("application:active_window")
    def _setup_status_bar(self, event):
        """Build the status bar on the first window; later re-fires no-op."""
        window = event.new
        if window is None or self._icon_container is not None:
            return
        if window.status_bar_manager is None:
            window.status_bar_manager = StatusBarManager(
                messages=[DEFAULT_STATUS_MESSAGE], size_grip=True
            )
        status_bar = window.status_bar_manager.status_bar
        status_bar.setContentsMargins(*STATUS_BAR_CONTENTS_MARGINS)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ICON_SPACING)
        # Appended, i.e. rightmost — so the joystick indicator's deferred
        # insert at the first permanent slot stays LEFT of every
        # contributed icon (see StatusBarManager.attach_gamepad_indicator).
        status_bar.addPermanentWidget(container)
        self._icon_container = container

        # Contributions made before the window existed already sit in the
        # extension point — apply them now; the _items handler below keeps
        # the bar in sync from here on.
        self._apply_icon_changes(added=self.status_bar_icons, removed=[])

    # ------------------------------------------------------------------ #
    # Extension-point sync                                                 #
    # ------------------------------------------------------------------ #

    def _apply_icon_changes(self, added, removed):
        """Apply contribution deltas to the icon container."""
        if self._icon_container is None:
            return  # no window yet; current extensions applied at setup
        layout = self._icon_container.layout()
        for widget in removed:
            try:
                layout.removeWidget(widget)
                widget.deleteLater()
            except RuntimeError as e:
                logger.debug(f"status-bar icon already deleted: {e}")
        for widget in added:
            layout.addWidget(widget)
        logger.info(
            f"status bar icons changed: +{len(added)} -{len(removed)}; "
            f"{layout.count()} in the bar"
        )

    @on_trait_change("status_bar_icons_items")
    def _on_status_bar_icons_items_changed(self, event):
        """A contribution changed while the app is running.

        Plugin-driven changes (a contributing plugin mutating its
        contribution trait, plugins added/removed from the manager) always
        carry an index, which ExtensionPoint.connect surfaces as this
        synthetic "<name>_items" property event. No real
        ``status_bar_icons_items`` trait exists, so the string-matched
        on_trait_change must bind it — observe() rejects unknown names.
        """
        self._apply_icon_changes(event.added, event.removed)

    @observe("status_bar_icons")
    def _on_status_bar_icons_replaced(self, event):
        """Index-less wholesale replacement of the extension point
        (registry.set_extensions) — never fired for plugin contribution
        changes; covered for completeness."""
        self._apply_icon_changes(added=event.new, removed=event.old)
