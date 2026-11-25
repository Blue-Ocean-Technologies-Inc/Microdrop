# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""NotificationsPlugin — recent events in a floating drawer at the bottom
right of the main window, opened by a bell in the status bar; new ones pop
up as toasts by the bell, with a chime.

Everything that collects notifications starts with the plugin, so nothing
is missed while the drawer is closed or not built yet: the model, the
topic listener, the log handler forwarding warnings and errors, and the
watcher of the plugin load records. At launch the plugin shows only the
bell: the drawer is built the first time it opens, the toasts the first
time one pops up, the sounds the first time one plays and the settings
window the first time it is asked for.

Other plugins post through ``notifications.consts``, add sections through
NOTIFICATION_SECTIONS and declare their kinds of notification through
NOTIFICATION_CATEGORIES.
"""

# Standard library imports.
import logging

# Enthought library imports.
from envisage.api import ExtensionPoint, Plugin
from traits.api import Any, Dict, Instance, List, observe, on_trait_change
from traits.observation.api import trait

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_status_bar.consts import STATUS_BAR_ICONS

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_SECTIONS,
    NOTIFICATIONS_CATEGORIES,
    NOTIFICATIONS_PLUGIN_ID,
    NotificationCategorySpec,
    NotificationSection,
    PKG_name,
)
from .controllers.notifications_controller import NotificationsController
from .controllers.toast_controller import ToastStackController

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsPlugin(Plugin):
    """The notifications model, its collectors, the bell, and the drawer,
    toasts and chime built on first use."""

    id = NOTIFICATIONS_PLUGIN_ID
    name = f"{PKG_name} Plugin"

    #: Sections of the drawer's column, e.g. the plugin loading list.
    sections = ExtensionPoint(
        List(Instance(NotificationSection)),
        id=NOTIFICATION_SECTIONS,
        desc="NotificationSection descriptors shown in the notifications drawer",
    )

    #: The kinds of notification the plugins post, for the user to tune.
    categories = ExtensionPoint(
        List(Instance(NotificationCategorySpec)),
        id=NOTIFICATION_CATEGORIES,
        desc="NotificationCategorySpec declarations, one per kind of notification",
    )

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: This plugin's own kinds of notification.
    own_categories = List(
        NOTIFICATIONS_CATEGORIES, contributes_to=NOTIFICATION_CATEGORIES
    )

    #: The bell while the plugin runs.
    status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)

    #: The model, the drawer's requests and open/close; live from start().
    controller = Instance(NotificationsController)

    #: Pops arrivals up and times the toasts.
    toast_controller = Instance(ToastStackController)

    #: Receives the plugin's topics; forwards log records; posts plugin
    #: load failures; turns sections' alerts into toasts; plays the chime.
    _message_handler = Any()
    _log_handler = Any()
    _load_failure_notifier = Any()
    _alert_watcher = Any()
    _chime = Any()

    #: The drawer's own sections: Needs attention and Activity.
    _own_sections = List()

    #: Keeps the bell in step with the model.
    _bell = Any()

    #: The pyface window the drawer and toasts go on.
    _window = Any()

    #: Built on first use: the drawer's host and the toasts' view.
    _drawer_host = Any()
    _toast_view = Any()

    #: The open settings windows, by title.
    _settings_uis = Dict()

    def start(self):
        """Start collecting notifications and put the bell in the status
        bar; the drawer and toasts go on the main window once it opens."""
        from .controllers.load_failure_notifier import PluginLoadFailureNotifier
        from .controllers.message_handler import NotificationsMessageHandler
        from .controllers.section_alerts import SectionAlertWatcher
        from .models.own_sections import AttentionSection, HistorySection
        from .services.chime import NotificationChime
        from .services.log_forwarder import NotificationLogHandler
        from .views.bell import NotificationBellIndicator

        # Wires the ``*_items`` handlers below to contribution changes.
        self.connect_extension_point_traits()

        self.controller = NotificationsController()
        pane_model = self.controller.pane_model
        center = pane_model.center

        center.settings.declare(self.categories)
        self._own_sections = [
            AttentionSection(center=center),
            HistorySection(center=center),
        ]
        self._show_sections()

        self.toast_controller = ToastStackController(pane_model=pane_model)
        self._alert_watcher = SectionAlertWatcher(
            pane_model=pane_model, offer=self.toast_controller.offer
        )
        self._chime = NotificationChime(pane_model=pane_model)

        # The root logger itself, which get_logger() does not hand out.
        self._log_handler = NotificationLogHandler(center)
        logging.getLogger().addHandler(self._log_handler)

        self._message_handler = NotificationsMessageHandler(controller=self.controller)
        self._load_failure_notifier = PluginLoadFailureNotifier(
            center=center,
            status=getattr(self.application, "plugin_load_status", None),
        )

        self._bell = NotificationBellIndicator(pane_model=pane_model)
        self._bell.widget.clicked.connect(self.controller.toggle_pane)
        self.status_bar_icons.append(self._bell.widget)

        # Started after the window opened: a plugin loaded at runtime.
        window = getattr(self.application, "active_window", None)

        if window is not None and window.control is not None:
            self._put_on_window(window)

    def stop(self):
        """Stop collecting, take the drawer and toasts off and withdraw the
        bell (hot unload)."""
        self._take_off_window()

        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

        if self._message_handler is not None:
            self._message_handler.teardown()
            self._message_handler = None

        if self._bell is not None:
            self.status_bar_icons.remove(self._bell.widget)
            self._bell = None

        for ui in self._settings_uis.values():
            if ui.control is not None:
                ui.dispose()

        self._settings_uis = {}
        self._load_failure_notifier = None
        self._alert_watcher = None
        self._chime = None

    # ------------------------------------------------------------------ #
    # The main window                                                     #
    # ------------------------------------------------------------------ #

    @observe(trait("application", notify=False).trait("window_opened", optional=True))
    def _put_on_opened_window(self, event):

        if self.controller is not None and event.new is not None:
            self._put_on_window(event.new.window)

    @observe(trait("application", notify=False).trait("window_closed", optional=True))
    def _take_off_closed_window(self, event):
        """Detach while the window's widgets still exist: pyface deletes
        them later, and has already let go of ``window.control``."""

        if event.new is not None and event.new.window is self._window:
            self._take_off_window()

    def _put_on_window(self, window):
        """From now on arrivals pop up, and the drawer opens, on ``window``."""
        self._take_off_window()
        self._window = window
        self.toast_controller.enabled = True

        if self.controller.pane_model.is_open:
            self._drawer_on_window()

    def _take_off_window(self):

        for view in (self._drawer_host, self._toast_view):
            if view is not None:
                view.detach()

        self._window = None

    # ------------------------------------------------------------------ #
    # Built on first use                                                  #
    # ------------------------------------------------------------------ #

    @observe("controller:pane_model:is_open")
    def _build_drawer_on_first_open(self, event):

        if event.new and self._window is not None:
            self._drawer_on_window()

    def _drawer_on_window(self):

        if self._drawer_host is None:
            from .views.drawer_host import NotificationsDrawerHost

            self._drawer_host = NotificationsDrawerHost(
                model=self.controller.pane_model,
                click_outside_exempt=[self._bell.widget],
            )

        if self._drawer_host.window is not self._window.control:
            self._drawer_host.attach(self._window.control)

    @observe("toast_controller:pane_model:toasts:items.items")
    def _build_toasts_on_first_toast(self, event):
        toasts = self.toast_controller.pane_model.toasts

        if not toasts.items or self._window is None:
            return

        if self._toast_view is None:
            from .views.toasts import ToastStackView

            self._toast_view = ToastStackView(
                pane_model=self.controller.pane_model,
                controller=self.toast_controller,
                bell=self._bell.widget,
            )

        if self._toast_view.window is not self._window.control:
            self._toast_view.attach(self._window.control)

    @observe("controller:pane_model:settings_button")
    def _open_settings(self, event):
        """The settings window, raised if already open."""
        from .views.settings_view import settings_view

        settings = self.controller.pane_model.center.settings
        view, context = settings_view(settings)
        ui = self._settings_uis.get(view.title)

        settings.opened = True

        if ui is not None and ui.control is not None:
            ui.control.raise_()

            return

        parent = getattr(self._window, "control", None)
        self._settings_uis[view.title] = settings.edit_traits(
            view=view, context=context, parent=parent
        )

    # ------------------------------------------------------------------ #
    # Contributions                                                       #
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

    @on_trait_change("categories_items")
    def _on_categories_items_changed(self, event):
        """A plugin declaring categories was loaded at runtime."""

        if self.controller is not None:
            self.controller.pane_model.center.settings.declare(event.added)

    def _show_sections(self):

        if self.controller is not None:
            sections = [*self.sections, *self._own_sections]
            self.controller.pane_model.sections = sections
