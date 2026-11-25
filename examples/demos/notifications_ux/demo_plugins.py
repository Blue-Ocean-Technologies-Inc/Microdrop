# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The isolated demo's fake plugins: stand-in panes, the News section
(contributed through the notifications plugin's public section API), and
plugin management with its launch-time network and plugin-group steps left
out. The Demo menu itself is ``dev_plugin``.
"""

# Standard library imports.
from functools import partial

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.api import SchemaAddition
from pyface.tasks.action.api import SGroup
from traits.api import Any, List, observe

# Microdrop package imports.
from microdrop_application.consts import PKG as microdrop_application_PKG
from notifications.consts import NOTIFICATION_CATEGORIES, NOTIFICATION_SECTIONS
from plugin_management.plugin import PluginManagementPlugin

# Local imports.
from . import fake_panes
from .demo_categories import NEWS_CATEGORIES, PLUGINS_CATEGORIES
from .news_actions import NewsFeedActions
from .news_models import make_news_section

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The task the fake panes and the News actions join.
TASK_ID = f"{microdrop_application_PKG}.task"

#: The news plugin's id, by which the demo finds the news sections.
NEWS_PLUGIN_ID = "notifications_ux_demo.news"

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


class NewsPlugin(Plugin):
    """Contributes the News section through the notifications plugin's
    public section API, and its feed actions to the Demo menu."""

    id = NEWS_PLUGIN_ID
    name = "News Plugin (demo)"

    sections = List(contributes_to=NOTIFICATION_SECTIONS)

    notification_categories = List(
        NEWS_CATEGORIES, contributes_to=NOTIFICATION_CATEGORIES
    )

    task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #: The Demo menu's News actions.
    _news_actions = Any()

    def _sections_default(self):
        return [make_news_section()]

    def _task_extensions_default(self):
        addition = SchemaAddition(
            id="notifications_ux_demo.news",
            factory=self._news_group,
            path="MenuBar/Demo",
        )

        return [TaskExtension(task_id=TASK_ID, actions=[addition])]

    def _news_group(self):
        self._news_actions = NewsFeedActions(
            section=self.sections[0], window=self._window_control
        )

        return SGroup(*self._news_actions.actions(), id="notifications_ux_demo.news")

    def _window_control(self):
        window = self.application.active_window

        return getattr(window, "control", None)


class DemoPluginManagementPlugin(PluginManagementPlugin):
    """Plugin management without its launch-time plugin-group restore (it
    would load the installed heater and magnet plugins) or its update check
    (a network fetch and a dialog): the demo posts that answer instead."""

    notification_categories = List(
        PLUGINS_CATEGORIES, contributes_to=NOTIFICATION_CATEGORIES
    )

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
