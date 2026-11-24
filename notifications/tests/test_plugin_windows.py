# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The plugin puts the drawer on each application window as it opens and
takes it off when that window closes, before pyface deletes its widgets."""

# Enthought library imports.
from envisage.ui.tasks.api import TasksApplication, TaskWindow, TaskWindowEvent
from pyface.qt import QtWidgets

# Microdrop package imports.
from notifications.controllers.notifications_controller import NotificationsController
from notifications.plugin import NotificationsPlugin
from notifications.views.drawer_host import NotificationsDrawerHost


def test_the_drawer_follows_the_application_windows():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    plugin = NotificationsPlugin()
    application = TasksApplication(plugins=[plugin])
    controller = NotificationsController(publish=lambda **message: None)
    host = NotificationsDrawerHost(model=controller.pane_model, slide_ms=0)
    plugin._drawer_host = host

    first = TaskWindow(size=(400, 300))
    first.open()
    application.window_opened = TaskWindowEvent(window=first)

    assert plugin.application is application
    assert host.window is first.control

    controller.show_pane()
    second = TaskWindow(size=(400, 300))
    second.open()

    # Another window closing leaves the drawer where it is.
    second.close()
    application.window_closed = TaskWindowEvent(window=second)

    assert host.window is not None
    assert host.drawer.isVisible()

    first.close()
    application.window_closed = TaskWindowEvent(window=first)

    assert host.window is None
    assert host._app_relay is None
    assert not controller.pane_model.is_open
