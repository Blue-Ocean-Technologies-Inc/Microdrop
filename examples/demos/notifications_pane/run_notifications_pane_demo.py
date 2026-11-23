# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Eyeball the Notifications pane and its bell, without the app or Redis.

A bare task window with the real pane docked right and the bell in its
status bar, filled with one notification of every kind and a simulated
plugin loading list (one plugin fails, which posts its own notification).
The toolbar posts more, floods the log handler from a thread, and switches
the theme. Actions publish nothing: they say what they would do. Run from
``src/``:

    pixi run python -m examples.demos.notifications_pane.run_notifications_pane_demo

``--theme dark`` (or ``light``) forces a theme; ``--hidden`` starts with
the pane hidden, as in the app: the bell shows the unread count.
"""

# Standard library imports.
import argparse
import threading

# Enthought library imports.
from pyface.api import GUI
from pyface.qt import QtWidgets
from pyface.tasks.api import PaneItem, Task, TaskLayout, TaskPane, TaskWindow
from pyface.timer.api import Timer
from traits.api import HasTraits, Instance

# Microdrop package imports.
from notifications.consts import DOCK_PANE_ID, SEVERITY_INFO
from notifications.controllers.load_failure_notifier import PluginLoadFailureNotifier
from notifications.controllers.notifications_controller import NotificationsController
from notifications.dock_pane import NotificationsDockPane
from notifications.services.log_forwarder import NotificationLogHandler
from notifications.views.bell_indicator import NotificationBellIndicator

# Microdrop style imports.
from microdrop_style.helpers import apply_color_scheme, is_dark_mode, style_app

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import PluginLoadStatus
from microdrop_utils.pyface_helpers import StatusBarManager

# Local imports.
from .sample_notifications import load_next_plugin, plugin_loading_section, post_samples

# Logger import.
from logger.logger_service import get_logger

#: Records the log flood button emits, from a worker thread.
FLOOD_RECORDS = 5000

#: Milliseconds between steps of the simulated plugin loading.
LOAD_STEP_MS = 700

#: The demo's own logger: the flood never reaches the console.
demo_logger = get_logger("notifications_demo.flood")
demo_logger.propagate = False


class _Central(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel(
            "Device viewer would be here.\nClick the bell in the status bar.", parent
        )
        self.control.setStyleSheet("font-size: 14pt; padding: 24px;")


class DemoTask(Task):
    id = "notifications_demo.task"
    name = "Notifications pane demo"

    controller = Instance(NotificationsController)

    def create_central_pane(self):
        return _Central()

    def create_dock_panes(self):
        pane = NotificationsDockPane(model=self.controller.pane_model)
        self.controller.pane = pane

        return [pane]


class _DemoApplication(HasTraits):
    """What the lazy pane reads from its window's application."""

    plugin_load_status = Instance(PluginLoadStatus, ())


def _say(window, controller, text):
    """Stand in for a publish or an open: post what would have happened."""
    window.status_bar_manager.messages = [text]
    controller.pane_model.center.post(f"Demo: {text}", severity=SEVERITY_INFO)


def _flood_log():
    def emit():
        for number in range(FLOOD_RECORDS):
            demo_logger.warning(f"Stage {number % 3} drifted past its limit")

    threading.Thread(target=emit, daemon=True).start()


def _toolbar(window, controller):
    center = controller.pane_model.center
    toolbar = window.control.addToolBar("Demo")

    toolbar.addAction(
        "Post info", lambda: center.post("Device changed", category="device")
    )
    toolbar.addAction(
        "Post warning",
        lambda: center.post(
            "Low liquid level", severity="warning", category="hardware"
        ),
    )
    toolbar.addAction(f"Flood log ({FLOOD_RECORDS} from a thread)", _flood_log)
    toolbar.addAction(
        "Switch theme",
        lambda: apply_color_scheme("light" if is_dark_mode() else "dark"),
    )


def main():
    """Show the demo window until it is closed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--theme", choices=["light", "dark", "system"], default="system"
    )
    parser.add_argument(
        "--hidden", action="store_true", help="start with the pane hidden, as the app"
    )
    args = parser.parse_args()

    gui = GUI()
    style_app(QtWidgets.QApplication.instance())
    apply_color_scheme(args.theme)

    controller = NotificationsController()
    center = controller.pane_model.center
    status = _DemoApplication().plugin_load_status
    section = plugin_loading_section(status)
    controller.pane_model.sections = [section]

    log_handler = NotificationLogHandler(center)
    demo_logger.addHandler(log_handler)
    # Held: its observers do not keep it alive.
    _notifier = PluginLoadFailureNotifier(center=center, status=status)

    post_samples(center)

    window = TaskWindow(size=(1100, 760), title="Notifications pane demo")
    window.application = _DemoApplication(plugin_load_status=status)
    window.add_task(
        DemoTask(
            controller=controller,
            default_layout=(
                TaskLayout()
                if args.hidden
                else TaskLayout(right=PaneItem(DOCK_PANE_ID, width=420))
            ),
        )
    )
    window.open()

    controller.trait_set(
        publish=lambda topic, message: _say(window, controller, f"publish {topic}"),
        open_path=lambda path: _say(window, controller, f"open {path}"),
    )

    window.status_bar_manager = StatusBarManager(messages=["Notifications demo"])
    bell = NotificationBellIndicator(center=center)
    bell.widget.clicked.connect(controller.toggle_pane)
    window.status_bar_manager.status_bar.addPermanentWidget(bell.widget)

    _toolbar(window, controller)

    # Held so the running timer is not garbage collected.
    timer = Timer(
        LOAD_STEP_MS, lambda: load_next_plugin(status, section) or timer.Stop()
    )

    gui.start_event_loop()


if __name__ == "__main__":
    main()
