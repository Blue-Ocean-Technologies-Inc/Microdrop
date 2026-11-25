# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""MicroDrop's notifications in an isolated shell of the real app.

The real MicroDrop application, task window, menus, status bar, theme and
message layer, with the minimum real plugins for that shell, the real
notifications plugin, and fake plugins for panes, a News section (through
the plugin's public section API) and notifications. A Demo menu posts
scenarios. Run from ``src/``:

    pixi run python -m examples.demos.notifications_ux.run_notifications_ux_demo

``--theme light`` or ``dark`` forces a theme; ``--open`` opens the drawer
once the window is up (without it the drawer stays closed: the app's own
opening at start-up is off here). ``--app-font-pt 14`` sets the application's font to
that size, as a larger text size would: the rest of the window grows with
it, the notifications panel (its own fixed type scale) does not.

It touches nothing of a MicroDrop already running: it starts its own Redis
on a free port (never 6379) and uses a temporary application home, both gone
when it exits. No hardware or backend plugin is loaded.
"""

# Standard library imports.
import argparse
import os
import signal
import sys

# Local imports.
from .isolated_session import isolated_session

#: The window's size when it opens.
WINDOW_SIZE = (1440, 880)


def run(open_drawer, app_font_pt=None):
    """Run the app until its window closes, its font at ``app_font_pt``
    points if given. Inside ``isolated_session()``: imports the plugin
    modules only now."""
    from envisage.api import CorePlugin
    from envisage.ui.tasks.api import TasksPlugin
    from pyface.qt.QtWidgets import QApplication
    from pyface.tasks.api import TaskWindowLayout

    from logger_ui.plugin import LoggerUIPlugin
    from message_router.plugin import MessageRouterPlugin
    from microdrop_application.application import MicrodropApplication
    from microdrop_application.plugin import MicrodropPlugin
    from microdrop_status_bar.plugin import StatusBarPlugin
    from news.plugin import NewsPlugin
    from notifications.consts import OPEN_AT_START_ENV
    from notifications.plugin import NotificationsPlugin

    from microdrop_style.helpers import style_app

    from microdrop_utils.broker_server_helpers import (
        dramatiq_workers_context,
        load_dramatiq_worker_settings,
    )
    from microdrop_utils.deferred_plugins import DeferredPlugin

    from .demo_plugins import DemoPluginManagementPlugin, StandInPanesPlugin
    from .dev_plugin import NotificationsDevPlugin

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

    # The drawer opens only on --open, never also at start-up; unless the
    # environment already says otherwise.
    os.environ.setdefault(OPEN_AT_START_ENV, "0")

    app_instance = QApplication.instance() or QApplication(sys.argv)
    style_app(app_instance)

    if app_font_pt:
        font = app_instance.font()
        font.setPointSizeF(app_font_pt)
        app_instance.setFont(font)

    plugins = [
        CorePlugin(),
        MessageRouterPlugin(),
        LoggerPlugin(),
        MicrodropPlugin(),
        TasksPlugin(),
        StatusBarPlugin(),
        NotificationsPlugin(),
        LoggerUIPlugin(),
        DemoPluginManagementPlugin(),
        StandInPanesPlugin(),
        NewsPlugin(),
        NotificationsDevPlugin(
            seed_history=True, pretend_open_path=True, open_drawer=open_drawer
        ),
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
    parser.add_argument(
        "--app-font-pt",
        type=float,
        help="the application's font size (points), e.g. 14 to mimic larger text",
    )
    args = parser.parse_args()
    theme = "follow_system" if args.theme == "system" else args.theme

    with isolated_session(theme=theme):
        run(open_drawer=args.open, app_font_pt=args.app_font_pt)


if __name__ == "__main__":
    main()
