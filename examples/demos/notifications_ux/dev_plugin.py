# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A dev-only Demo menu firing fake notifications through the real
notifications plugin, for tuning the drawer, toasts and sounds.

The run scripts add it only when MICRODROP_NOTIFICATIONS_DEMO=1 is set
(``examples.plugin_consts.with_notifications_demo``); the isolated demo
always loads it. Cards' demo buttons are answered by a stand-in, other
topics are published for real; help links name the help they would open.
"""

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.api import Action
from pyface.action.schema.api import SchemaAddition
from pyface.api import GUI
from pyface.tasks.action.api import SGroup, SMenu
from traits.api import Any, Bool, Dict, Instance, List, Str, observe

# Microdrop package imports.
from microdrop_application.consts import PKG as microdrop_application_PKG
from news.consts import NEWS_PLUGIN_ID
from notifications.consts import NOTIFICATION_CATEGORIES, NOTIFICATIONS_PLUGIN_ID
from notifications.models.settings import NotificationSettings

# Local imports.
from . import scenarios
from .demo_categories import (
    DROPBOT_CATEGORIES,
    DROPBOT_GROUP,
    PROTOCOL_CATEGORIES,
    PROTOCOL_GROUP,
)

#: The task the Demo menu joins.
TASK_ID = f"{microdrop_application_PKG}.task"

#: Milliseconds after the window is up before "plugin updates available"
#: arrives, as the real update check's answer would.
UPDATE_CHECK_MS = 2500


class SettingToggleAction(Action):
    """A checkable menu item kept in step with one notification setting."""

    style = "toggle"

    #: The settings it shows and sets, and which switch.
    settings = Instance(NotificationSettings)
    setting = Str()

    def perform(self, event=None):
        # A toggle action is already flipped when it is performed.
        setattr(self.settings, self.setting, self.checked)

    @observe("setting, settings.[auto_dismiss, sound_enabled]")
    def _follow_settings(self, event):

        if self.settings is not None and self.setting:
            self.checked = getattr(self.settings, self.setting)


class NotificationsDevPlugin(Plugin):
    """The Demo menu, and what the cards' demo buttons pretend to do."""

    id = "notifications_ux_demo.scenarios"
    name = "Notifications Demo Plugin (dev)"

    task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: It stands in for the protocol tree and the DropBot plugins: their
    #: kinds of notification.
    notification_categories = List(
        PROTOCOL_CATEGORIES + DROPBOT_CATEGORIES,
        contributes_to=NOTIFICATION_CATEGORIES,
    )

    #: Post a session's worth of history before the window is up, and the
    #: plugin update check's answer after (the isolated demo).
    seed_history = Bool(False)

    #: Open no file browser for a card's "Show folder" (the isolated demo).
    pretend_open_path = Bool(False)

    #: Open the drawer once the window is up.
    open_drawer = Bool(False)

    #: Answers the cards' demo buttons.
    _responder = Any()

    #: The News actions.
    _news = Any()

    #: The open group settings windows, by title.
    _settings_uis = Dict()

    def start(self):
        controller = self._notifications.controller
        center = controller.pane_model.center
        self._responder = scenarios.DemoResponder(
            center=center, forward=controller.publish
        )

        controller.trait_set(
            publish=self._responder.publish, open_help=self._responder.open_help
        )

        if self.pretend_open_path:
            controller.open_path = self._responder.open_path

        if self.seed_history:
            scenarios.post_history(center, self._experiment_folder())

    @observe("application:application_initialized")
    def _after_launch(self, event):

        if self.seed_history:
            GUI.invoke_after(UPDATE_CHECK_MS, scenarios.post_plugin_updates)

        if self.open_drawer:
            GUI.invoke_after(400, self._notifications.controller.show_pane)

    @property
    def _notifications(self):
        return self.application.get_plugin(NOTIFICATIONS_PLUGIN_ID)

    @property
    def _pane_model(self):
        return self._notifications.controller.pane_model

    @property
    def _settings(self):
        return self._pane_model.center.settings

    def _experiment_folder(self):
        return str(self.application.current_experiment_directory)

    # ------------------------------------------------------------------ #
    # The Demo menu                                                       #
    # ------------------------------------------------------------------ #

    def _task_extensions_default(self):
        addition = SchemaAddition(
            id="notifications_ux_demo.menu",
            factory=self._demo_menu,
            path="MenuBar",
            after="Help",
        )

        return [TaskExtension(task_id=TASK_ID, actions=[addition])]

    def _demo_menu(self):
        return SMenu(
            SGroup(*self._post_actions(), id="notifications_ux_demo.notifications"),
            SMenu(
                SGroup(
                    _action("DropBot connected", scenarios.post_dropbot_connected),
                    _action(
                        "DropBot disconnected", scenarios.post_dropbot_disconnected
                    ),
                    _action("Flap connection (3×)", scenarios.flap_connection),
                    id="notifications_ux_demo.device.connection",
                ),
                SGroup(
                    _action("Chip inserted", scenarios.post_chip_inserted),
                    _action("Chip removed", self._chip_removed),
                    id="notifications_ux_demo.device.chip",
                ),
                id="notifications_ux_demo.device",
                name="Device",
            ),
            SGroup(*self._news_actions().actions(), id="notifications_ux_demo.news"),
            SGroup(*self._settings_actions(), id="notifications_ux_demo.settings"),
            SGroup(
                _action("Toggle theme", self._toggle_theme),
                _action("Reset", self._reset, "Clear everything and start over"),
                id="notifications_ux_demo.session",
            ),
            id="Demo",
            name="&Demo",
        )

    def _post_actions(self):
        folder = self._experiment_folder

        return [
            _action("Post info", scenarios.post_info),
            _action("Post success", scenarios.post_success),
            _action("Post warning", scenarios.post_warning),
            _action("Post error (with traceback)", scenarios.post_error),
            _action("Post plugin updates available", scenarios.post_plugin_updates),
            _action(
                "Post protocol finished",
                lambda: scenarios.post_protocol_finished(folder()),
            ),
            _action("Post calibration is old", scenarios.post_calibration_old),
            _action("Post self test is stale", scenarios.post_self_test_stale),
            _action(f"Burst of {scenarios.BURST_SIZE}", scenarios.post_burst),
            _action(
                f"Flood from a thread ({scenarios.FLOOD_RECORDS} log records)",
                scenarios.flood_from_thread,
            ),
            _action(
                f"Simulate protocol run ({scenarios.PROTOCOL_RUN_S} s)",
                self._simulate_run,
                "Quiet while it runs: only errors and actions pop up",
            ),
            _action(
                f"Run a {scenarios.STEPPED_RUN_STEPS}-step protocol",
                self._run_steps,
                "Start, one step entry updating in place, finish",
            ),
        ]

    def _news_actions(self):
        """Reload and pushes, on the news plugin's section."""
        from .news_actions import NewsFeedActions

        self._news = NewsFeedActions(
            get_section=self._news_section, window=self._window_control
        )

        return self._news

    def _news_section(self):
        plugin = self.application.get_plugin(NEWS_PLUGIN_ID)

        return plugin.sections[0] if plugin is not None else None

    def _window_control(self):
        window = self.application.active_window

        return getattr(window, "control", None)

    def _settings_actions(self):
        return [
            SettingToggleAction(
                name="Toasts time out automatically",
                settings=self._settings,
                setting="auto_dismiss",
            ),
            SettingToggleAction(
                name="Play a sound for new notifications",
                settings=self._settings,
                setting="sound_enabled",
            ),
            _action("Notification settings…", self._open_settings),
            _action(
                "Protocol notification settings…",
                lambda: self._open_group_settings(PROTOCOL_GROUP),
            ),
            _action(
                "DropBot notification settings…",
                lambda: self._open_group_settings(DROPBOT_GROUP),
            ),
        ]

    def _simulate_run(self):
        model = self._pane_model
        scenarios.simulate_protocol_run(model.center, model.toasts)

    def _run_steps(self):
        scenarios.run_stepped_protocol(
            self._pane_model.toasts, self._experiment_folder()
        )

    def _chip_removed(self):
        """A protocol run waits on the chip while quiet for it."""
        toasts = self._pane_model.toasts

        scenarios.post_chip_removed(
            toasts.quiet and toasts.quiet_reason == PROTOCOL_GROUP
        )

    def _open_settings(self):
        self._pane_model.settings_button = True

    def _open_group_settings(self, group):
        """Only ``group``'s categories, as its owner's own preferences page
        would show them; the same objects as the full settings."""
        from notifications.views.settings_view import group_settings_view

        view, context = group_settings_view(self._settings, group)
        ui = self._settings_uis.get(view.title)
        self._settings.opened = True

        if ui is not None and ui.control is not None:
            ui.control.raise_()

            return

        window = self.application.active_window
        self._settings_uis[view.title] = self._settings.edit_traits(
            view=view, context=context, parent=getattr(window, "control", None)
        )

    def _toggle_theme(self):
        from microdrop_style.helpers import is_dark_mode

        preferences = self.application.preferences_helper
        preferences.color_scheme = "light" if is_dark_mode() else "dark"

    def _reset(self):
        notifications = self._notifications
        model = self._pane_model

        model.is_open = False
        notifications.toast_controller.clear()
        model.center.clear_everything()

        # History, as at start-up: no toasts.
        notifications.toast_controller.enabled = False
        scenarios.post_history(model.center, self._experiment_folder())
        notifications.toast_controller.enabled = True

        GUI.invoke_after(UPDATE_CHECK_MS, scenarios.post_plugin_updates)


def _action(name, callable_, tooltip=""):
    return Action(name=name, on_perform=callable_, tooltip=tooltip)
