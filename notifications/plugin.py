# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""NotificationsPlugin — recent events in a drawer on the right of the main
window, like a desktop notification centre, opened by a bell in the status
bar.

Everything that collects notifications starts with the plugin, so nothing
is missed while the drawer is closed or not built yet: the model, the
NOTIFICATION_POST listener, the log handler forwarding warnings and errors,
and the watcher of the plugin load records. The drawer goes on each main
window as it opens, and its contents are built the first time it opens.
Other plugins post through ``notifications.consts`` and add sections above
the list through the NOTIFICATION_SECTIONS extension point.
"""

# Standard library imports.
import logging

# Enthought library imports.
from envisage.api import ExtensionPoint, Plugin
from traits.api import Any, Instance, List, observe, on_trait_change
from traits.observation.api import trait

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_status_bar.consts import STATUS_BAR_ICONS

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    NOTIFICATION_SECTIONS,
    NOTIFICATIONS_PLUGIN_ID,
    NotificationSection,
    PKG_name,
)
from .controllers.notifications_controller import NotificationsController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsPlugin(Plugin):
    """The notifications model, its collectors, drawer and status-bar bell."""

    id = NOTIFICATIONS_PLUGIN_ID
    name = f"{PKG_name} Plugin"

    #: Sections shown above the notifications, e.g. the plugin loading list.
    sections = ExtensionPoint(
        List(Instance(NotificationSection)),
        id=NOTIFICATION_SECTIONS,
        desc="NotificationSection descriptors shown above the notifications",
    )

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: The bell while the plugin runs.
    status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)

    #: The model, the drawer's requests and open/close; live from start().
    controller = Instance(NotificationsController)

    #: Receives NOTIFICATION_POST and NOTIFICATIONS_SHOW_PANEL.
    _message_handler = Any()

    #: Forwards warnings and errors from the root logger.
    _log_handler = Any()

    #: Posts a notification for each plugin that fails to load.
    _load_failure_notifier = Any()

    #: Keeps the bell in step with the unread count.
    _bell = Any()

    #: Puts the drawer on the main window.
    _drawer_host = Any()

    #: The pyface window the drawer is on.
    _drawer_window = Any()

    def start(self):
        """Start collecting notifications, put the bell in the status bar and
        the drawer on the main window, if it is open already."""
        from .controllers.load_failure_notifier import PluginLoadFailureNotifier
        from .controllers.message_handler import NotificationsMessageHandler
        from .services.log_forwarder import NotificationLogHandler
        from .views.bell_indicator import NotificationBellIndicator
        from .views.drawer_host import NotificationsDrawerHost

        # Wires the ``sections_items`` handler below to contribution changes.
        self.connect_extension_point_traits()

        self.controller = NotificationsController()
        self.controller.pane_model.sections = list(self.sections)
        center = self.controller.pane_model.center

        # The root logger itself, which get_logger() does not hand out.
        self._log_handler = NotificationLogHandler(center)
        logging.getLogger().addHandler(self._log_handler)

        self._message_handler = NotificationsMessageHandler(controller=self.controller)
        self._load_failure_notifier = PluginLoadFailureNotifier(
            center=center,
            status=getattr(self.application, "plugin_load_status", None),
        )

        self._bell = NotificationBellIndicator(center=center)
        self._bell.widget.clicked.connect(self.controller.toggle_pane)
        self.status_bar_icons.append(self._bell.widget)

        self._drawer_host = NotificationsDrawerHost(
            model=self.controller.pane_model,
            click_outside_exempt=[self._bell.widget],
        )

        # Started after the window opened: a plugin loaded at runtime.
        window = getattr(self.application, "active_window", None)

        if window is not None and window.control is not None:
            self._attach_drawer(window)

    def stop(self):
        """Stop collecting, take the drawer off and withdraw the bell (hot
        unload)."""

        if self._drawer_host is not None:
            self._drawer_host.detach()
            self._drawer_host = None
            self._drawer_window = None

        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

        if self._message_handler is not None:
            self._message_handler.teardown()
            self._message_handler = None

        if self._bell is not None:
            self.status_bar_icons.remove(self._bell.widget)
            self._bell = None

        self._load_failure_notifier = None

    # ------------------------------------------------------------------ #
    # The main window                                                     #
    # ------------------------------------------------------------------ #

    @observe(trait("application", notify=False).trait("window_opened", optional=True))
    def _put_drawer_on_opened_window(self, event):

        if self._drawer_host is not None and event.new is not None:
            self._attach_drawer(event.new.window)

    @observe(trait("application", notify=False).trait("window_closed", optional=True))
    def _take_drawer_off_closed_window(self, event):
        """Detach while the window's widgets still exist: pyface deletes
        them later, and has already let go of ``window.control``."""

        if event.new is None or event.new.window is not self._drawer_window:
            return

        self._drawer_window = None

        if self._drawer_host is not None:
            self._drawer_host.detach()

    def _attach_drawer(self, window):
        self._drawer_window = window
        self._drawer_host.attach(window.control)

    # ------------------------------------------------------------------ #
    # Section contributions                                               #
    # ------------------------------------------------------------------ #

    @on_trait_change("sections_items")
    def _on_sections_items_changed(self, event):
        """A contributing plugin was loaded or unloaded at runtime.

        ``sections_items`` is the synthetic event ExtensionPoint.connect
        fires for contribution changes; no such trait exists, so only the
        string-matched on_trait_change can bind it (observe rejects it).
        """
        self._show_sections()

    @observe("sections")
    def _on_sections_replaced(self, event):
        self._show_sections()

    def _show_sections(self):
        if self.controller is not None:
            self.controller.pane_model.sections = list(self.sections)
