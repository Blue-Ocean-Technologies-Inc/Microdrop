# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer on a real TaskWindow with dock panes: closed and unbuilt at
first, built when the bell opens it, laid over the panes without moving
them, anchored through resizes, closed by the bell, Esc or a click outside,
never part of the task layout, and let go of cleanly with its window. Its
list keeps in step row by row, an expanded entry's detail is the row's only
widget, sections build on expand, and the bell follows the unread count."""

# Standard library imports.
import time

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from pyface.qt.QtTest import QTest
from pyface.tasks.api import (
    DockPane,
    PaneItem,
    Task,
    TaskLayout,
    TaskPane,
    TaskWindow,
)
from traits.api import Instance

# Microdrop package imports.
from notifications.consts import (
    DRAWER_OBJECT_NAME,
    DRAWER_WIDTH,
    SEVERITY_COLORS,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    NotificationSection,
    PublishAction,
)
from notifications.controllers.notifications_controller import NotificationsController
from notifications.views.bell_indicator import NotificationBellIndicator
from notifications.views.drawer_host import NotificationsDrawerHost
from notifications.views.notification_list_editor import NotificationListView

# Microdrop utils imports.
from microdrop_utils.pyface_helpers import StatusBarManager

#: Long enough for the window to show and paint.
SETTLE_MS = 300

LEFT_PANE_ID = "test.left_pane"
RIGHT_PANE_ID = "test.right_pane"


def settle(ms=SETTLE_MS):
    deadline = time.perf_counter() + ms / 1000

    while time.perf_counter() < deadline:
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        time.sleep(0.005)


class CentralPane(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel("central", parent)


class ButtonDockPane(DockPane):
    """A pane whose button counts its clicks."""

    clicks = Instance(list, ())

    def create_contents(self, parent):
        button = QtWidgets.QPushButton(self.name, parent)
        button.setMinimumSize(80, 40)
        button.clicked.connect(lambda: self.clicks.append(True))

        return button


class PaintCounter(QtCore.QObject):
    """Notes each paint of the widget it filters."""

    def __init__(self, paints):
        super().__init__()

        self._paints = paints

    def eventFilter(self, watched, event):

        if event.type() == QtCore.QEvent.Type.Paint:
            self._paints.append(True)

        return False


class DrawerTask(Task):
    id = "test.drawer_task"

    def create_central_pane(self):
        return CentralPane()

    def create_dock_panes(self):
        return [
            ButtonDockPane(id=LEFT_PANE_ID, name="Left", dock_area="left"),
            ButtonDockPane(id=RIGHT_PANE_ID, name="Right", dock_area="right"),
        ]


@pytest.fixture
def controller():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    return NotificationsController(publish=lambda **message: None)


@pytest.fixture
def bell(controller):
    bell = NotificationBellIndicator(center=controller.pane_model.center)
    bell.widget.clicked.connect(controller.toggle_pane)

    return bell


@pytest.fixture
def host(controller, bell):
    host = NotificationsDrawerHost(
        model=controller.pane_model, click_outside_exempt=[bell.widget], slide_ms=0
    )

    yield host

    host.detach()


@pytest.fixture
def window(host, bell):
    window = TaskWindow(size=(900, 600))
    window.add_task(
        DrawerTask(
            default_layout=TaskLayout(
                left=PaneItem(LEFT_PANE_ID), right=PaneItem(RIGHT_PANE_ID)
            )
        )
    )
    window.open()
    window.status_bar_manager = StatusBarManager(messages=["test"])
    window.status_bar_manager.status_bar.addPermanentWidget(bell.widget)
    host.attach(window.control)
    settle()

    yield window

    window.close()
    settle(50)


def list_view(host):
    return host.drawer.findChild(NotificationListView)


def press(widget, position=None):
    QTest.mouseClick(
        widget,
        QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        position or QtCore.QPoint(),
    )
    settle(50)


def pane_button(window, pane_id):
    return window.get_dock_pane(pane_id).control.widget()


# --------------------------------------------------------------------------- #
# Opening, closing and building                                               #
# --------------------------------------------------------------------------- #


def test_the_drawer_starts_closed_and_unbuilt_but_collects(window, host, bell):
    center = host.model.center
    center.post("Before the drawer opened")

    assert not host.drawer.isVisible()
    assert not host.contents_built
    assert center.unread_count == 1

    press(bell.widget)

    assert host.drawer.isVisible()
    assert host.contents_built
    assert list_view(host).model().rowCount() == 1
    assert center.unread_count == 0

    # One timer refreshes the relative times, only while the drawer is open.
    refresh = list_view(host)._time_refresh

    assert refresh.isActive()

    press(bell.widget)

    assert not host.model.is_open
    assert not host.drawer.isVisible()
    assert not refresh.isActive()


def test_esc_closes_the_drawer(window, host, controller):
    controller.show_pane()
    settle(50)

    QTest.keyClick(host.drawer, QtCore.Qt.Key.Key_Escape)
    settle(50)

    assert not host.model.is_open
    assert not host.drawer.isVisible()


def test_a_click_outside_closes_it_and_is_used_up(window, host, controller):
    left = window.get_dock_pane(LEFT_PANE_ID)
    controller.show_pane()
    settle(50)

    press(pane_button(window, LEFT_PANE_ID))

    assert not host.model.is_open
    assert left.clicks == []

    press(pane_button(window, LEFT_PANE_ID))

    assert left.clicks == [True]


def test_a_click_inside_keeps_it_open(window, host, controller):
    controller.show_pane()
    settle(50)

    press(list_view(host).viewport())

    assert host.model.is_open


def test_click_outside_can_be_turned_off(window, host, controller):
    host.closes_on_click_outside = False
    controller.show_pane()
    settle(50)

    press(pane_button(window, LEFT_PANE_ID))

    assert host.model.is_open
    assert window.get_dock_pane(LEFT_PANE_ID).clicks == [True]


# --------------------------------------------------------------------------- #
# Placement                                                                   #
# --------------------------------------------------------------------------- #


def test_it_lies_over_the_panes_without_moving_them(window, host, controller):
    docks = window.control.findChildren(QtWidgets.QDockWidget)
    before = [dock.geometry() for dock in docks]

    controller.show_pane()
    settle(50)
    drawer = host.drawer
    status_bar = window.control.statusBar()

    assert [dock.geometry() for dock in docks] == before
    assert drawer.geometry().right() == window.control.width() - 1
    assert drawer.width() == DRAWER_WIDTH
    assert drawer.geometry().bottom() == status_bar.geometry().top() - 1

    # On top: the right pane's button lies beneath the drawer.
    under = drawer.mapTo(window.control, drawer.rect().center())
    hit = window.control.childAt(under)

    assert hit is drawer or drawer.isAncestorOf(hit)


def test_it_stays_anchored_as_the_window_resizes(window, host, controller):
    controller.show_pane()
    settle(50)

    window.control.resize(1200, 700)
    settle(100)

    assert host.drawer.geometry().right() == window.control.width() - 1
    assert host.drawer.geometry().bottom() == (
        window.control.statusBar().geometry().top() - 1
    )

    # A window narrower than the drawer gets a drawer as wide as itself.
    window.control.setMinimumWidth(0)
    window.control.resize(DRAWER_WIDTH - 100, 500)
    settle(100)

    assert host.drawer.width() == window.control.width()
    assert host.drawer.x() == 0


def test_a_resize_mid_slide_still_ends_anchored(window, host, controller):
    host.slide_ms = 120
    controller.show_pane()
    settle(20)

    window.control.resize(1000, 650)
    settle(300)

    assert host.drawer.geometry().right() == window.control.width() - 1
    assert host.drawer.width() == DRAWER_WIDTH


def test_the_drawer_is_no_part_of_the_task_layout(window, host, controller):
    controller.show_pane()
    settle(50)

    dock_ids = [pane.id for pane in window.dock_panes]
    layout = window.get_window_layout()
    saved_state = bytes(window.control.saveState())

    assert not isinstance(host.drawer, QtWidgets.QDockWidget)
    assert host.drawer.objectName() == DRAWER_OBJECT_NAME
    assert sorted(dock_ids) == [LEFT_PANE_ID, RIGHT_PANE_ID]
    assert DRAWER_OBJECT_NAME.encode() not in saved_state
    assert "notifications" not in repr(layout)


# --------------------------------------------------------------------------- #
# Translucency                                                                #
# --------------------------------------------------------------------------- #


def away_from_drawer(window):
    QtGui.QCursor.setPos(window.control.mapToGlobal(QtCore.QPoint(5, 5)))


def test_over_still_panes_it_is_translucent_and_idle(window, host, controller):
    away_from_drawer(window)
    controller.show_pane()
    settle(100)
    paints = []
    counter = PaintCounter(paints)
    host.drawer.installEventFilter(counter)
    settle(500)
    host.drawer.removeEventFilter(counter)

    assert host.drawer.is_translucent()
    assert paints == []


def test_over_a_repainting_pane_it_turns_opaque(window, host, controller):
    beneath = pane_button(window, RIGHT_PANE_ID)
    ticks = QtCore.QTimer()
    ticks.timeout.connect(beneath.update)
    ticks.start(30)
    away_from_drawer(window)
    controller.show_pane()
    settle(500)

    assert not host.drawer.is_translucent()

    # Opaque, the drawer is no longer repainted with what lies beneath.
    paints = []
    counter = PaintCounter(paints)
    host.drawer.installEventFilter(counter)
    settle(300)
    host.drawer.removeEventFilter(counter)
    ticks.stop()

    assert len(paints) <= 1

    # Each opening starts translucent again.
    controller.toggle_pane()
    controller.toggle_pane()

    assert host.drawer.is_translucent()


def test_nothing_watches_the_application_while_closed(window, host, controller):
    controller.show_pane()
    settle(50)

    assert host._app_relay is not None

    controller.toggle_pane()
    settle(50)

    assert host._app_relay is None


# --------------------------------------------------------------------------- #
# Window teardown                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("open_drawer", [True, False])
def test_closing_the_window_after_detach_is_clean(controller, host, open_drawer):
    window = TaskWindow(size=(600, 400))
    window.add_task(DrawerTask(default_layout=TaskLayout()))
    window.open()
    host.attach(window.control)
    controller.pane_model.is_open = open_drawer
    settle(50)

    window.close()
    host.detach()
    settle(50)

    assert host.window is None and host.drawer is None
    assert host._app_relay is None
    assert not controller.pane_model.is_open

    # The model lives on; its former editors no longer listen.
    controller.pane_model.center.post("after the window")
    settle(50)


@pytest.mark.parametrize("open_drawer", [True, False])
def test_a_window_deleted_without_detach_is_let_go(controller, host, open_drawer):
    window = QtWidgets.QMainWindow()
    window.resize(600, 400)
    window.show()
    host.attach(window)
    controller.pane_model.is_open = open_drawer
    settle(50)

    window.deleteLater()
    settle(50)

    assert host.window is None and host.drawer is None
    assert host._app_relay is None
    assert not controller.pane_model.is_open

    controller.pane_model.center.post("after the window")
    settle(50)


def test_a_new_window_gets_the_drawer(controller, host):
    first = QtWidgets.QMainWindow()
    first.show()
    host.attach(first)
    controller.show_pane()
    settle(50)

    second = QtWidgets.QMainWindow()
    second.show()
    host.attach(second)
    first.deleteLater()
    controller.show_pane()
    settle(50)

    assert host.window is second
    assert host.drawer.parent() is second
    assert host.drawer.isVisible()

    second.close()
    second.deleteLater()
    settle(50)


# --------------------------------------------------------------------------- #
# The list, sections and bell                                                 #
# --------------------------------------------------------------------------- #


def test_new_entries_insert_rows_without_resetting_the_list(window, host, controller):
    center = controller.pane_model.center
    controller.show_pane()
    settle(50)
    model = list_view(host).model()
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    for number in range(50):
        center.post(f"entry {number}", severity=SEVERITY_WARNING)

    center.post("entry 3", severity=SEVERITY_WARNING)
    settle(50)

    assert resets == []
    assert model.rowCount() == 50
    assert model.index(0).data() == "entry 3"


def test_only_an_expanded_entry_has_a_widget(window, host, controller):
    center = controller.pane_model.center
    controller.show_pane()
    settle(50)
    view = list_view(host)
    plain = center.post("plain", detail="short")
    traceback = center.post(
        "boom",
        detail="Traceback (most recent call last):\n  File x\nValueError: v",
        severity=SEVERITY_ERROR,
        action=PublishAction(label="Retry", topic="a/b"),
    )
    settle(50)

    assert view.findChildren(QtWidgets.QPlainTextEdit) == []

    traceback.expanded = True
    settle(50)
    editors = view.findChildren(QtWidgets.QPlainTextEdit)

    assert len(editors) == 1
    assert "ValueError: v" in editors[0].toPlainText()
    assert editors[0].lineWrapMode() == QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap

    traceback.expanded = False
    plain.expanded = True
    settle(50)

    assert [
        editor.toPlainText()
        for editor in view.findChildren(QtWidgets.QPlainTextEdit)
        if editor.isVisible()
    ] == ["short"]


def test_a_section_builds_on_expand_and_a_request_expands_it(window, host, controller):
    builds = []

    def build(parent):
        builds.append(parent)

        return QtWidgets.QLabel("section contents", parent)

    section = NotificationSection(id="plugins", title="Plugins", factory=build)
    controller.pane_model.sections = [section]
    controller.show_pane()
    settle(50)

    assert builds == []

    controller.show_pane("plugins")
    settle(50)

    labels = [label.text() for label in host.drawer.findChildren(QtWidgets.QLabel)]

    assert len(builds) == 1
    assert "section contents" in labels


def test_the_bell_counts_unread_and_takes_the_most_urgent_colour(controller):
    center = controller.pane_model.center
    bell = NotificationBellIndicator(center=center)

    assert bell.widget.badge.isHidden()

    center.post("warn", severity=SEVERITY_WARNING)
    center.post("err", severity=SEVERITY_ERROR)

    assert bell.widget.badge.text() == "2"
    assert SEVERITY_COLORS[SEVERITY_ERROR] in bell.widget.badge.styleSheet()

    center.mark_all_read()

    assert bell.widget.badge.isHidden()
