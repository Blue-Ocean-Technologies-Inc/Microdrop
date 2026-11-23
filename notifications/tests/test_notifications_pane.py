# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pane in a real TaskWindow: hidden and unbuilt at first, built when
the bell shows it, its list kept in step row by row (never rebuilt), an
expanded entry's detail as the row's only widget, sections built on
expand, and the bell following the unread count."""

# Standard library imports.
import time

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtWidgets
from pyface.tasks.api import Task, TaskLayout, TaskPane, TaskWindow
from traits.api import HasTraits, Instance

# Microdrop package imports.
from notifications.consts import (
    DOCK_PANE_ID,
    SEVERITY_COLORS,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    NotificationSection,
    PublishAction,
)
from notifications.controllers.notifications_controller import NotificationsController
from notifications.dock_pane import NotificationsDockPane
from notifications.views.bell_indicator import NotificationBellIndicator
from notifications.views.notification_list_editor import NotificationListView

# Microdrop utils imports.
from microdrop_utils.deferred_content import CONTENT_BUILT
from microdrop_utils.plugin_load_status import PluginLoadStatus

#: Long enough for a paint, a paced turn and its pause.
SETTLE_MS = 400


def settle(ms=SETTLE_MS):
    deadline = time.perf_counter() + ms / 1000

    while time.perf_counter() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)


class CentralPane(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel("central", parent)


class NotificationsTask(Task):
    id = "test.notifications_task"

    #: Supplies the pane's model, as the plugin does.
    controller = Instance(NotificationsController)

    def create_central_pane(self):
        return CentralPane()

    def create_dock_panes(self):
        pane = NotificationsDockPane(model=self.controller.pane_model)
        self.controller.pane = pane

        return [pane]


class FakeApplication(HasTraits):
    plugin_load_status = Instance(PluginLoadStatus, ())


@pytest.fixture
def controller():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    return NotificationsController(publish=lambda **message: None)


@pytest.fixture
def window(controller):
    window = TaskWindow(size=(900, 600))
    window.application = FakeApplication()
    window.add_task(
        NotificationsTask(controller=controller, default_layout=TaskLayout())
    )
    window.open()
    settle()

    yield window

    window.close()


def list_view(window):
    return window.get_dock_pane(DOCK_PANE_ID).control.findChild(NotificationListView)


def test_the_pane_starts_hidden_and_unbuilt_but_collects(window, controller):
    pane = window.get_dock_pane(DOCK_PANE_ID)
    controller.pane_model.center.post("Before the pane was built")

    assert not pane.visible
    assert pane.deferred_contents.state != CONTENT_BUILT

    controller.toggle_pane()
    settle()

    assert pane.deferred_contents.state == CONTENT_BUILT
    assert pane.showing_contents
    assert list_view(window).model().rowCount() == 1
    assert controller.pane_model.center.unread_count == 0

    # One timer refreshes the relative times, only while the list shows.
    refresh = list_view(window)._time_refresh

    assert refresh.isActive()

    controller.toggle_pane()
    settle()

    assert not pane.visible
    assert not refresh.isActive()


def test_new_entries_insert_rows_without_resetting_the_list(window, controller):
    center = controller.pane_model.center
    controller.show_pane()
    settle()
    model = list_view(window).model()
    resets = []
    model.modelReset.connect(lambda: resets.append(True))

    for number in range(50):
        center.post(f"entry {number}", severity=SEVERITY_WARNING)

    center.post("entry 3", severity=SEVERITY_WARNING)
    settle(50)

    assert resets == []
    assert model.rowCount() == 50
    assert model.index(0).data() == "entry 3"


def test_only_an_expanded_entry_has_a_widget(window, controller):
    center = controller.pane_model.center
    controller.show_pane()
    settle()
    view = list_view(window)
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


def test_a_section_builds_on_expand_and_a_request_expands_it(window, controller):
    builds = []

    def build(parent):
        builds.append(parent)

        return QtWidgets.QLabel("section contents", parent)

    section = NotificationSection(id="plugins", title="Plugins", factory=build)
    controller.pane_model.sections = [section]
    controller.show_pane()
    settle()

    assert builds == []

    controller.show_pane("plugins")
    settle(50)

    pane = window.get_dock_pane(DOCK_PANE_ID)
    labels = [label.text() for label in pane.control.findChildren(QtWidgets.QLabel)]

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
