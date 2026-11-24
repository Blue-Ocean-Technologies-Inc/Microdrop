# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A high-fidelity prototype of MicroDrop's notifications, in the real app.

The real MicroDrop application, task window, menus, status bar, theme and
message layer, with the minimum real plugins for that shell, the real
notifications plugin with the prototype's views (toasts, bell badge, a
resizable drawer of designed sections, cards with buttons), and fake plugins
for panes and notifications. A Demo menu posts scenarios. Run from ``src/``:

    pixi run python -m examples.demos.notifications_ux.run_notifications_ux_demo

``--theme light`` or ``dark`` forces a theme; ``--open`` opens the drawer
once the window is up.

It touches nothing of a MicroDrop already running: it starts its own Redis
on a free port (never 6379) and uses a temporary application home, both gone
when it exits. No hardware or backend plugin is loaded.
"""

# Standard library imports.
import argparse
import signal
import sys

# Local imports.
from .isolated_session import isolated_session

#: The window's size when it opens.
WINDOW_SIZE = (1440, 880)


def run(open_drawer):
    """Run the app until its window closes. Inside ``isolated_session()``:
    imports the plugin modules only now."""
    from envisage.api import CorePlugin
    from envisage.ui.tasks.api import TasksPlugin
    from pyface.qt.QtWidgets import QApplication
    from pyface.tasks.api import TaskWindowLayout

    from logger_ui.plugin import LoggerUIPlugin
    from message_router.plugin import MessageRouterPlugin
    from microdrop_application.application import MicrodropApplication
    from microdrop_application.plugin import MicrodropPlugin
    from microdrop_status_bar.plugin import StatusBarPlugin

    from microdrop_style.helpers import style_app

    from microdrop_utils.broker_server_helpers import (
        dramatiq_workers_context,
        load_dramatiq_worker_settings,
    )
    from microdrop_utils.deferred_plugins import DeferredPlugin

    from .demo_plugins import (
        DemoPluginManagementPlugin,
        NotificationsDemoPlugin,
        SciBotsFeedPlugin,
        StandInPanesPlugin,
    )
    from .ux_plugin import UxNotificationsPlugin

    from logger.plugin import LoggerPlugin

    class NotificationsUxApplication(MicrodropApplication):
        """MicroDrop's application, opening larger and skipping its launch
        dialogs and the DropBot search."""

        def _default_layout_default(self):
            tasks = [factory.id for factory in self.task_factories]

            return [
                TaskWindowLayout(
                    *tasks,
                    active_task=self.preferences_helper.default_task,
                    size=WINDOW_SIZE,
                )
            ]

        def _on_application_initialized(self, event):
            """No beta disclaimer, What's New or DropBot search in the demo."""

    app_instance = QApplication.instance() or QApplication(sys.argv)
    style_app(app_instance)

    plugins = [
        CorePlugin(),
        MessageRouterPlugin(),
        LoggerPlugin(),
        MicrodropPlugin(),
        TasksPlugin(),
        StatusBarPlugin(),
        UxNotificationsPlugin(),
        LoggerUIPlugin(),
        DemoPluginManagementPlugin(),
        StandInPanesPlugin(),
        SciBotsFeedPlugin(),
        NotificationsDemoPlugin(open_drawer=open_drawer),
    ]

    deferred_plugins = [
        DeferredPlugin(
            spec="examples.demos.notifications_ux.fake_deferred_plugins:FakeImageViewerPlugin",
            dock_panes=[],
        ),
        DeferredPlugin(
            spec="examples.demos.notifications_ux.fake_deferred_plugins:FakeHeaterControlsPlugin",
            dock_panes=[],
        ),
    ]

    with dramatiq_workers_context(**load_dramatiq_worker_settings()):
        app = NotificationsUxApplication(plugins=plugins)
        app.deferred_plugins = deferred_plugins

        signal.signal(signal.SIGINT, lambda signum, frame: app.exit())

        app.run()


def main():
    """Parse the command line and run the demo, isolated."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--theme", choices=["light", "dark", "system"], default="system"
    )
    parser.add_argument(
        "--open", action="store_true", help="open the drawer once the window is up"
    )
    args = parser.parse_args()
    theme = "follow_system" if args.theme == "system" else args.theme

    with isolated_session(theme=theme):
        run(open_drawer=args.open)


if __name__ == "__main__":
    main()
