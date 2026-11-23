# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Task-extension changes that arrive before a window shows its task are
kept and applied once it does, instead of being dropped; a reconcile mounts
one pane per turn and rebuilds the menu bar once, after the last pane."""

# Third-party imports.
import pytest

# Enthought library imports.
from envisage.ui.tasks.api import TaskExtension
from traits.api import Any, HasTraits, Str

# Microdrop package imports.
from plugin_management import live_task_extensions
from plugin_management.live_task_extensions import LiveTaskExtensionsController


class FakeTask(HasTraits):
    id = Str("test.task")


class FakeWindow(HasTraits):
    active_task = Any()


class FakeApplication(HasTraits):
    active_window = Any()


class FakeEventLoop:
    """``GUI.invoke_later`` and ``invoke_after`` as a queue the test drains,
    one call per turn."""

    def __init__(self):
        self.calls = []

    def invoke_later(self, callable, *args, **kwargs):
        self.calls.append((callable, args, kwargs))

    def invoke_after(self, millisecs, callable, *args, **kwargs):
        self.calls.append((callable, args, kwargs))

    def turn(self):
        callable, args, kwargs = self.calls.pop(0)
        callable(*args, **kwargs)

    def drain(self):
        while self.calls:
            self.turn()


class FakePane:
    def __init__(self, pane_id):
        self.id = pane_id


def _pane_factory(**traits):
    """Stands in for a dock pane class."""


def _other_pane_factory(**traits):
    """Stands in for a second dock pane class."""


@pytest.fixture
def mounted(monkeypatch):
    """Replace the live Qt helpers; collect the ids of the mounted panes,
    and "menu" for each menu-bar rebuild."""
    mounted_ids = []

    def add_dock_pane_live(window, task, factory):
        pane_id = "test.pane" if factory is _pane_factory else "test.other_pane"
        mounted_ids.append(pane_id)

        return FakePane(pane_id)

    monkeypatch.setattr(live_task_extensions, "add_dock_pane_live", add_dock_pane_live)
    monkeypatch.setattr(
        live_task_extensions,
        "rebuild_menu_bar_live",
        lambda *args: mounted_ids.append("menu"),
    )

    return mounted_ids


@pytest.fixture
def event_loop(monkeypatch):
    loop = FakeEventLoop()
    monkeypatch.setattr(live_task_extensions, "invoke_paced", loop.invoke_later)

    return loop


def test_changes_wait_for_a_window_and_are_applied_when_it_shows(mounted, event_loop):
    application = FakeApplication()
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])

    controller.on_changed([extension], [])
    event_loop.drain()

    assert mounted == []
    assert controller.has_pending_changes

    # A window without its task yet still keeps them.
    window = FakeWindow()
    application.active_window = window
    event_loop.drain()

    assert mounted == []
    assert controller.has_pending_changes

    window.active_task = FakeTask()
    event_loop.drain()

    assert mounted == ["test.pane", "menu"]
    assert not controller.has_pending_changes
    assert controller.mounted_pane_ids([extension]) == ["test.pane"]


def test_changes_apply_at_once_when_a_task_shows(mounted, event_loop):
    application = FakeApplication(active_window=FakeWindow(active_task=FakeTask()))
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])

    controller.on_changed([extension], [])
    event_loop.drain()

    assert mounted == ["test.pane", "menu"]
    assert not controller.has_pending_changes


def test_an_extension_withdrawn_while_waiting_is_never_mounted(mounted, event_loop):
    application = FakeApplication()
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])

    controller.on_changed([extension], [])
    controller.on_changed([], [extension])
    application.active_window = FakeWindow(active_task=FakeTask())
    event_loop.drain()

    assert "test.pane" not in mounted


def test_panes_mount_one_per_turn_then_the_menu_bar_once(mounted, event_loop):
    application = FakeApplication(active_window=FakeWindow(active_task=FakeTask()))
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(
        task_id="test.task", dock_pane_factories=[_pane_factory, _other_pane_factory]
    )

    controller.on_changed([extension], [])

    assert controller.busy

    # The reconcile turn mounts the first pane only.
    event_loop.turn()

    assert mounted == ["test.pane"]
    assert controller.busy

    event_loop.turn()

    assert mounted == ["test.pane", "test.other_pane"]

    event_loop.turn()

    assert mounted == ["test.pane", "test.other_pane", "menu"]
    assert not controller.busy
    assert not controller.has_pending_changes
    assert event_loop.calls == []


def test_changes_during_a_reconcile_join_it_before_its_menu_rebuild(
    mounted, event_loop
):
    application = FakeApplication(active_window=FakeWindow(active_task=FakeTask()))
    controller = LiveTaskExtensionsController(application=application)
    first = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])
    second = TaskExtension(
        task_id="test.task", dock_pane_factories=[_other_pane_factory]
    )

    controller.on_changed([first], [])
    event_loop.turn()
    controller.on_changed([second], [])
    event_loop.drain()

    assert mounted == ["test.pane", "test.other_pane", "menu"]


def test_call_when_settled_waits_for_the_running_reconcile(mounted, event_loop):
    application = FakeApplication(active_window=FakeWindow(active_task=FakeTask()))
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])
    settled = []

    controller.on_changed([extension], [])
    controller.call_when_settled(lambda: settled.append(list(mounted)))
    event_loop.drain()

    # Only after the menu-bar rebuild, on a turn of its own.
    assert settled == [["test.pane", "menu"]]


def test_call_when_settled_runs_on_a_later_turn_when_idle(event_loop):
    controller = LiveTaskExtensionsController(application=FakeApplication())
    settled = []

    controller.call_when_settled(lambda: settled.append(True))

    assert settled == []

    event_loop.drain()

    assert settled == [True]
