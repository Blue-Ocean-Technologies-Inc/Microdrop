# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The controller's reactions to the drawer, its open/close, entry actions,
and the plugin load failures posted as notifications. Qt-free; nothing is
published: the controller's publisher is a stub."""

# Microdrop package imports.
from notifications.consts import (
    SEVERITY_ERROR,
    NotificationSection,
    OpenPathAction,
    PublishAction,
)
from notifications.controllers.load_failure_notifier import PluginLoadFailureNotifier
from notifications.controllers.notifications_controller import NotificationsController
from notifications.models.notification_center import NotificationCenter

# Microdrop utils imports.
from microdrop_utils.plugin_load_status import PluginLoadStatus


def _controller(**traits):
    published = []
    opened = []
    stubs = {
        "publish": lambda **message: published.append(message),
        "open_path": opened.append,
    }
    controller = NotificationsController(**{**stubs, **traits})

    return controller, published, opened


def test_the_header_buttons_and_dismiss_act_on_the_center():
    controller, _published, _opened = _controller()
    model = controller.pane_model
    first = model.center.post("one")
    model.center.post("two")

    model.mark_all_read_button = True

    assert model.center.unread_count == 0

    model.dismiss = first

    assert [entry.title for entry in model.center.entries] == ["two"]

    model.clear_all_button = True

    assert model.center.entries == []


def test_an_action_publishes_or_opens_what_it_names():
    controller, published, opened = _controller()
    model = controller.pane_model
    publish = model.center.post(
        "p", action=PublishAction(label="Go", topic="a/b", message="1")
    )
    open_path = model.center.post("o", action=OpenPathAction(label="Open", path="C:/x"))

    model.run_action = publish
    model.run_action = open_path

    assert published == [{"topic": "a/b", "message": "1"}]
    assert opened == ["C:/x"]


def test_a_path_that_will_not_open_is_posted_as_an_error():
    def refuse(path):
        raise FileNotFoundError(path)

    controller, _published, _opened = _controller(open_path=refuse)
    center = controller.pane_model.center
    entry = center.post("o", action=OpenPathAction(label="Open", path="C:/gone"))

    controller.pane_model.run_action = entry

    assert center.entries[0].title == "Could not open C:/gone"
    assert center.entries[0].severity == SEVERITY_ERROR


def test_toggle_opens_then_closes_and_open_marks_read():
    controller, _published, _opened = _controller()
    model = controller.pane_model
    center = model.center
    center.post("unseen")

    controller.toggle_pane()

    assert model.is_open
    assert center.unread_count == 0

    center.post("arrives while open")

    assert center.unread_count == 0

    controller.toggle_pane()
    center.post("arrives while closed")

    assert not model.is_open
    assert center.unread_count == 1


def test_show_pane_opens_and_expands_the_requested_section():
    section = NotificationSection(id="plugins", title="Plugins")
    controller, _published, _opened = _controller()
    controller.pane_model.sections = [section]

    controller.show_pane("plugins")
    controller.show_pane()

    assert section.expanded
    assert controller.pane_model.is_open


def test_the_close_button_closes():
    controller, _published, _opened = _controller()
    controller.show_pane()

    controller.pane_model.close_button = True

    assert not controller.pane_model.is_open


def test_load_failures_before_and_after_start_are_posted_once_each():
    status = PluginLoadStatus()
    status.mark_failed("early.plugin", "ImportError: x", "Traceback ...", name="Early")
    status.mark_pending("late.plugin", "Late")
    center = NotificationCenter()

    # Held: the notifier's observers do not keep it alive.
    _notifier = PluginLoadFailureNotifier(center=center, status=status)

    assert [entry.title for entry in center.entries] == ["Early failed to load"]

    status.mark_failed("late.plugin", "RuntimeError: y", "Traceback (most recent ...")
    status.mark_pending("late.plugin", "Late")
    status.mark_failed("late.plugin", "RuntimeError: y", "Traceback (most recent ...")

    late = center.entries[0]

    assert late.title == "Late failed to load"
    assert late.count == 2
    assert late.category == "plugins"
    assert late.severity == SEVERITY_ERROR
    assert len(center.entries) == 2
