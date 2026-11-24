# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The prototype's fake plugins: stand-in panes, the Sci-Bots Feed section,
the Demo menu and the session's notifications; and plugin management with
its launch-time network and plugin-group steps left out.
"""

# Standard library imports.
from functools import partial

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.api import Action
from pyface.action.schema.schema_addition import SchemaAddition
from pyface.api import GUI
from pyface.tasks.action.api import SGroup, SMenu
from traits.api import Any, Bool, Instance, List, observe

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_demo import (
    add_feed_actions,
    create_feed_section,
)
from microdrop_application.consts import PKG as microdrop_application_PKG
from notifications.consts import NOTIFICATION_SECTIONS, NOTIFICATIONS_PLUGIN_ID
from plugin_management.plugin import PluginManagementPlugin

# Local imports.
from . import fake_panes, scenarios
from .ux_models import ToastSettings

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The task the fake panes and the Demo menu join.
TASK_ID = f"{microdrop_application_PKG}.task"

#: Milliseconds after the window is up before "plugin updates available"
#: arrives, as the real update check's answer would.
UPDATE_CHECK_MS = 2500

#: The feed plugin's id, by which the Demo menu finds its section.
FEED_PLUGIN_ID = "notifications_ux_demo.sci_bots_feed"

#: The feed action listed first in the Demo menu.
FEED_CREATOR_ACTION = "Feed creator…"

#: The stand-in panes: (id of the real pane, title, factory).
STAND_IN_PANES = [
    ("device_viewer.dock_pane", "Device Viewer", fake_panes.device_viewer),
    ("pluggable_protocol_tree.dock_pane", "Protocol", fake_panes.protocol),
    (
        "dropbot_status_and_controls.dock_pane",
        "DropBot Status",
        fake_panes.dropbot_status,
    ),
]


class StandInPanesPlugin(Plugin):
    """Contributes the stand-in device viewer, protocol and status panes."""

    id = "notifications_ux_demo.stand_in_panes"
    name = "Stand-in Panes Plugin (demo)"

    task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _task_extensions_default(self):
        factories = [
            partial(fake_panes.StandInPane, id=pane_id, name=name, factory=factory)
            for pane_id, name, factory in STAND_IN_PANES
        ]

        return [TaskExtension(task_id=TASK_ID, dock_pane_factories=factories)]

    @observe("application:application_initialized")
    def _fill_window_with_panes(self, event):
        """Hide the task's empty central canvas: the real device viewer is a
        dock pane too, and the canvas would show as a blank band between it
        and the right-hand panes. Hidden, it leaves the docks all the room."""

        for window in self.application.windows:
            central = window.control.centralWidget()

            if central is not None:
                central.hide()


class SciBotsFeedPlugin(Plugin):
    """Contributes the Sci-Bots Feed section of the notifications_pane demo."""

    id = FEED_PLUGIN_ID
    name = "Sci-Bots Feed Plugin (demo)"

    sections = List(contributes_to=NOTIFICATION_SECTIONS)

    def _sections_default(self):
        section = create_feed_section()

        # Collapsed: its chip says what is new; the notifications get the room.
        section.expanded = False

        return [section]


class AutoDismissAction(Action):
    """A checkable menu item kept in step with the toast settings."""

    name = "Toasts time out automatically"
    style = "toggle"

    #: The settings it shows and sets.
    settings = Instance(ToastSettings)

    def perform(self, event=None):
        # A toggle action is already flipped when it is performed.
        self.settings.auto_dismiss = self.checked

    @observe("settings.auto_dismiss")
    def _follow_settings(self, event):
        self.checked = self.settings.auto_dismiss


class _MenuActions:
    """Takes ``addAction(text, callable)`` calls as a QToolBar does, so the
    notifications_pane demo's toolbar actions can fill a menu group."""

    def __init__(self):
        self.actions = []

    def addAction(self, text, callable_):
        self.actions.append(Action(name=text, on_perform=callable_))


class NotificationsDemoPlugin(Plugin):
    """The Demo menu, the session's start-up notifications, and what the
    cards' buttons pretend to do."""

    id = "notifications_ux_demo.scenarios"
    name = "Notifications Demo Plugin (demo)"

    task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: Opens the drawer once the window is up (``--open``).
    open_drawer = Bool(False)

    #: Answers the cards' buttons.
    _responder = Any()

    #: The open Notification settings window, if any.
    _settings_ui = Any()

    def start(self):
        """Post the session's history before the window is up: no toasts."""
        controller = self._notifications.controller
        center = controller.pane_model.center
        self._responder = scenarios.DemoResponder(center=center)

        controller.trait_set(
            publish=self._responder.publish,
            open_path=self._responder.open_path,
            open_tutorial=self._responder.open_tutorial,
        )
        scenarios.post_history(center, self._experiment_folder())

    @observe("application:application_initialized")
    def _after_launch(self, event):
        GUI.invoke_after(UPDATE_CHECK_MS, scenarios.post_plugin_updates)

        if self.open_drawer:
            GUI.invoke_after(400, self._notifications.controller.show_pane)

    @property
    def _notifications(self):
        return self.application.get_plugin(NOTIFICATIONS_PLUGIN_ID)

    def _experiment_folder(self):
        return str(self.application.current_experiment_directory)

    # ------------------------------------------------------------------ #
    # The Demo menu                                                       #
    # ------------------------------------------------------------------ #

    def _task_extensions_default(self):
        return [
            TaskExtension(
                task_id=TASK_ID,
                actions=[
                    SchemaAddition(
                        id="notifications_ux_demo.menu",
                        factory=self._demo_menu,
                        path="MenuBar",
                        after="Help",
                    )
                ],
            )
        ]

    def _demo_menu(self):
        def action(name, callable_, tooltip=""):
            return Action(name=name, on_perform=callable_, tooltip=tooltip)

        return SMenu(
            SGroup(
                action("Post info", scenarios.post_info),
                action("Post success", scenarios.post_success),
                action("Post warning", scenarios.post_warning),
                action("Post error (with traceback)", scenarios.post_error),
                action("Post action required", scenarios.post_action_required),
                action("Post plugin updates available", scenarios.post_plugin_updates),
                action(
                    "Post protocol finished",
                    lambda: scenarios.post_protocol_finished(self._experiment_folder()),
                ),
                action("Post calibration is old", scenarios.post_calibration_old),
                action(f"Burst of {scenarios.BURST_SIZE}", scenarios.post_burst),
                action(
                    f"Flood from a thread ({scenarios.FLOOD_RECORDS} log records)",
                    scenarios.flood_from_thread,
                ),
                id="notifications_ux_demo.notifications",
            ),
            SGroup(*self._feed_actions(), id="notifications_ux_demo.feed"),
            SGroup(
                AutoDismissAction(settings=self._toast_settings),
                action("Notification settings…", self._open_settings),
                id="notifications_ux_demo.settings",
            ),
            SGroup(
                action("Toggle theme", self._toggle_theme),
                action("Reset", self._reset, "Clear everything and start over"),
                id="notifications_ux_demo.session",
            ),
            id="Demo",
            name="&Demo",
        )

    def _feed_actions(self):
        """The notifications_pane demo's feed actions, on this prototype's
        feed section: the feed creator first."""
        section = self.application.get_plugin(FEED_PLUGIN_ID).sections[0]
        window = self.application.active_window
        menu = _MenuActions()

        add_feed_actions(menu, section, getattr(window, "control", None))

        return sorted(menu.actions, key=lambda item: item.name != FEED_CREATOR_ACTION)

    @property
    def _toast_settings(self):
        return self._notifications.controller.pane_model.toasts.settings

    def _open_settings(self):
        """The toast settings, as a future preferences tab would show them;
        one window at a time."""
        from .toast_settings_view import ToastSettingsView

        if self._settings_ui is not None and self._settings_ui.control is not None:
            self._settings_ui.control.raise_()

            return

        window = self.application.active_window
        self._settings_ui = self._toast_settings.edit_traits(
            view=ToastSettingsView, parent=getattr(window, "control", None)
        )

    def _toggle_theme(self):
        from microdrop_style.helpers import is_dark_mode

        preferences = self.application.preferences_helper
        preferences.color_scheme = "light" if is_dark_mode() else "dark"

    def _reset(self):
        notifications = self._notifications
        center = notifications.controller.pane_model.center

        notifications.controller.pane_model.is_open = False
        notifications.toast_controller.clear()
        center.clear_everything()

        # History, as at start-up: no toasts.
        notifications.toast_controller.enabled = False
        scenarios.post_history(center, self._experiment_folder())
        notifications.toast_controller.enabled = True

        GUI.invoke_after(UPDATE_CHECK_MS, scenarios.post_plugin_updates)


class DemoPluginManagementPlugin(PluginManagementPlugin):
    """Plugin management without its launch-time plugin-group restore (it
    would load the installed heater and magnet plugins) or its update check
    (a network fetch and a dialog): the demo posts that answer instead."""

    @observe("application:application_initialized")
    def _restore_groups_on_launch(self, event):
        """Start the deferred plugins only."""

        if self._groups_restored:
            return

        self._groups_restored = True
        self._live_task_exts.call_when_settled(self._after_launch_restore_mounts)

    @observe("application:application_initialized")
    def _check_plugin_updates_on_launch(self, event):
        """No update check: the demo posts its answer as a notification."""
