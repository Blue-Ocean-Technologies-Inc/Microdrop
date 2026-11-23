# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Eyeball the notifications drawer and its bell, without the app or Redis.

A bare task window with stand-in dock panes — a protocol list, a camera
feed drawn by a real QGraphicsVideoItem, a dense report, a log — and the
real drawer and bell. The drawer opens from the bell over the panes without moving them;
Esc, the close button or a click elsewhere closes it. It is filled with one
notification of every kind and a simulated plugin loading list (one plugin
fails, which posts its own notification). The toolbar posts more, floods
the log handler from a thread, and switches the theme. Actions publish
nothing: they say what they would do. Run from ``src/``:

    pixi run python -m examples.demos.notifications_pane.run_notifications_pane_demo

``--theme dark`` (or ``light``) forces a theme; ``--open`` starts with the
drawer open; ``--backdrop camera`` docks the camera feed under the drawer
instead of a dense report, over which the drawer turns opaque.
"""

# Standard library imports.
import argparse
import threading

# Enthought library imports.
from pyface.api import GUI
from pyface.qt import QtCore, QtGui, QtWidgets
from pyface.qt.QtMultimedia import QVideoFrame
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from pyface.tasks.api import (
    DockPane,
    PaneItem,
    Task,
    TaskLayout,
    TaskPane,
    TaskWindow,
    VSplitter,
)
from pyface.timer.api import Timer
from traits.api import Callable

# Microdrop package imports.
from notifications.consts import SEVERITY_INFO
from notifications.controllers.load_failure_notifier import PluginLoadFailureNotifier
from notifications.controllers.notifications_controller import NotificationsController
from notifications.services.log_forwarder import NotificationLogHandler
from notifications.views.bell_indicator import NotificationBellIndicator
from notifications.views.drawer_host import NotificationsDrawerHost

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

#: Milliseconds between frames of the stand-in camera feed.
CAMERA_FRAME_MS = 100

#: Size of the stand-in camera frames.
CAMERA_FRAME_SIZE = QtCore.QSize(640, 480)

#: The demo's own logger: the flood never reaches the console.
demo_logger = get_logger("notifications_demo.flood")
demo_logger.propagate = False


class _Central(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel(
            "Device viewer would be here.\nClick the bell in the status bar.", parent
        )
        self.control.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.control.setStyleSheet("font-size: 14pt; padding: 24px;")


class _StandInPane(DockPane):
    """A dock pane showing whatever ``factory(parent)`` makes."""

    factory = Callable()

    def create_contents(self, parent):
        return self.factory(parent)


def _protocol_list(parent):
    steps = QtWidgets.QListWidget(parent)
    steps.addItems([f"Step {number}: move droplet" for number in range(1, 40)])

    return steps


def _log_view(parent):
    log = QtWidgets.QPlainTextEdit(parent)
    log.setReadOnly(True)
    log.setPlainText("\n".join(f"12:00:{n:02d} INFO tick {n}" for n in range(60)))

    return log


def _dense_report(parent):
    """Small, dense text, to judge the cards' legibility over it."""
    report = QtWidgets.QPlainTextEdit(parent)
    report.setReadOnly(True)
    report.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    report.setPlainText(
        "\n".join(
            f"step {n:03d}  electrodes {n % 7},{n % 11},{n % 13}  "
            f"C={1.5 + n / 100:.3f} pF  V=100  f=10000 Hz  t={n * 0.25:.2f} s  ok"
            for n in range(200)
        )
    )

    return report


class _FittedView(QtWidgets.QGraphicsView):
    """Keeps its scene fitted to its size."""

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self.fitInView(self.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)


def _camera_feed(parent):
    """A QGraphicsView showing a QGraphicsVideoItem fed changing frames, as
    the device viewer shows the camera: the drawer must cover it."""
    scene = QtWidgets.QGraphicsScene(parent)
    view = _FittedView(scene, parent)
    video = QGraphicsVideoItem()
    video.setSize(QtCore.QSizeF(CAMERA_FRAME_SIZE))
    scene.addItem(video)
    scene.setSceneRect(video.boundingRect())

    frame = {"number": 0}

    def next_frame():
        image = QtGui.QImage(CAMERA_FRAME_SIZE, QtGui.QImage.Format.Format_RGB32)
        hue = (frame["number"] * 7) % 360
        image.fill(QtGui.QColor.fromHsv(hue, 200, 230))

        painter = QtGui.QPainter(image)
        painter.setPen(QtGui.QColor("black"))
        painter.setFont(QtGui.QFont("Arial", 28))
        painter.drawText(image.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "CAMERA")
        painter.end()

        video.videoSink().setVideoFrame(QVideoFrame(image))
        frame["number"] += 1

    # Parented to the view, so it stops with it.
    timer = QtCore.QTimer(view)
    timer.timeout.connect(next_frame)
    timer.start(CAMERA_FRAME_MS)
    next_frame()

    return view


class DemoTask(Task):
    id = "notifications_demo.task"
    name = "Notifications drawer demo"

    def create_central_pane(self):
        return _Central()

    def create_dock_panes(self):
        return [
            _StandInPane(id="demo.protocol", name="Protocol", factory=_protocol_list),
            _StandInPane(id="demo.camera", name="Camera", factory=_camera_feed),
            _StandInPane(id="demo.report", name="Report", factory=_dense_report),
            _StandInPane(id="demo.log", name="Log", factory=_log_view),
        ]


def _layout(backdrop):
    """Dock ``backdrop`` (``camera`` or ``report``) right, under the drawer,
    and the other pane left."""
    beneath, aside = ("demo.camera", "demo.report")[
        :: 1 if backdrop == "camera" else -1
    ]

    return TaskLayout(
        left=VSplitter(PaneItem("demo.protocol", width=300), PaneItem(aside)),
        right=PaneItem(beneath, width=560),
        bottom=PaneItem("demo.log", height=140),
    )


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
    toolbar.setObjectName("notifications_demo.toolbar")

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
    parser.add_argument("--open", action="store_true", help="start with it open")
    parser.add_argument(
        "--backdrop",
        choices=["report", "camera"],
        default="report",
        help="the pane docked right, under the drawer",
    )
    args = parser.parse_args()

    gui = GUI()
    style_app(QtWidgets.QApplication.instance())
    apply_color_scheme(args.theme)

    controller = NotificationsController()
    center = controller.pane_model.center
    status = PluginLoadStatus()
    section = plugin_loading_section(status)
    controller.pane_model.sections = [section]

    log_handler = NotificationLogHandler(center)
    demo_logger.addHandler(log_handler)
    # Held: its observers do not keep it alive.
    _notifier = PluginLoadFailureNotifier(center=center, status=status)

    post_samples(center)

    window = TaskWindow(size=(1100, 760), title="Notifications drawer demo")
    window.add_task(DemoTask(default_layout=_layout(args.backdrop)))
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

    drawer_host = NotificationsDrawerHost(
        model=controller.pane_model, click_outside_exempt=[bell.widget]
    )
    # Closing the window lets go of the drawer: it goes with the window.
    drawer_host.attach(window.control)

    if args.open:
        controller.show_pane()

    # Held so the running timer is not garbage collected.
    timer = Timer(
        LOAD_STEP_MS, lambda: load_next_plugin(status, section) or timer.Stop()
    )

    gui.start_event_loop()


if __name__ == "__main__":
    main()
