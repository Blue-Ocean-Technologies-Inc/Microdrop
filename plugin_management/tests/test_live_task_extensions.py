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
kept and applied once it does, instead of being dropped."""

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
    """``GUI.invoke_later`` as a queue the test drains."""

    def __init__(self):
        self.calls = []

    def invoke_later(self, callable, *args, **kwargs):
        self.calls.append((callable, args, kwargs))

    def drain(self):
        while self.calls:
            callable, args, kwargs = self.calls.pop(0)
            callable(*args, **kwargs)


class FakePane:
    def __init__(self, pane_id):
        self.id = pane_id


def _pane_factory(**traits):
    """Stands in for a dock pane class."""


@pytest.fixture
def mounted(monkeypatch):
    """Replace the live Qt helpers; collect the ids of the mounted panes."""
    mounted_ids = []

    def add_dock_pane_live(window, task, factory):
        mounted_ids.append("test.pane")

        return FakePane("test.pane")

    monkeypatch.setattr(live_task_extensions, "add_dock_pane_live", add_dock_pane_live)
    monkeypatch.setattr(
        live_task_extensions, "rebuild_menu_bar_live", lambda *args: None
    )

    return mounted_ids


@pytest.fixture
def event_loop(monkeypatch):
    loop = FakeEventLoop()
    monkeypatch.setattr(live_task_extensions, "GUI", loop)

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

    assert mounted == ["test.pane"]
    assert not controller.has_pending_changes
    assert controller.mounted_pane_ids([extension]) == ["test.pane"]


def test_changes_apply_at_once_when_a_task_shows(mounted, event_loop):
    application = FakeApplication(active_window=FakeWindow(active_task=FakeTask()))
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])

    controller.on_changed([extension], [])
    event_loop.drain()

    assert mounted == ["test.pane"]
    assert not controller.has_pending_changes


def test_an_extension_withdrawn_while_waiting_is_never_mounted(mounted, event_loop):
    application = FakeApplication()
    controller = LiveTaskExtensionsController(application=application)
    extension = TaskExtension(task_id="test.task", dock_pane_factories=[_pane_factory])

    controller.on_changed([extension], [])
    controller.on_changed([], [extension])
    application.active_window = FakeWindow(active_task=FakeTask())
    event_loop.drain()

    assert mounted == []
