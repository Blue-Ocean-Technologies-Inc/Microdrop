# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The deferred-plugin loader starts its plugins in order, one per turn,
records each, skips failures without stopping, fires ``finished`` once, and
warns when a plugin's panes differ from its declaration. Runs a real Envisage
application with fake plugins named by spec; the event loop is a queue."""

# Third-party imports.
import pytest

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Application, CorePlugin, Plugin
from envisage.ui.tasks.api import TaskExtension
from traits.api import List

# Microdrop package imports.
from plugin_management import deferred_loader
from plugin_management.deferred_loader import (
    DeferredPluginLoader,
    compare_declared_panes,
)
from plugin_management.live_task_extensions import LiveTaskExtensionsController

# Microdrop utils imports.
from microdrop_utils.deferred_plugins import DeferredDockPane, DeferredPlugin
from microdrop_utils.isolating_plugin_manager import IsolatingPluginManager
from microdrop_utils.plugin_load_status import LOAD_FAILED, LOAD_LOADED, LOAD_PENDING

_SPEC_PREFIX = "plugin_management.tests.test_deferred_loader"

#: Ids of the fake plugins, in the order their start() ran.
STARTED = []


def _pane_factory(**traits):
    """Stands in for a dock pane class; never called by these tests."""


def _other_pane_factory(**traits):
    """A second pane factory, for the declaration mismatch."""


class FirstPlugin(Plugin):
    id = "test.first"
    name = "First Plugin"

    task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _task_extensions_default(self):
        return [TaskExtension(dock_pane_factories=[_pane_factory])]

    def start(self):
        STARTED.append(self.id)


class FailingPlugin(Plugin):
    id = "test.failing"

    def start(self):
        raise RuntimeError("camera not found")


class LastPlugin(Plugin):
    id = "test.last"

    task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _task_extensions_default(self):
        return [TaskExtension(dock_pane_factories=[_other_pane_factory])]

    def start(self):
        STARTED.append(self.id)


class FakeEventLoop:
    """``GUI.invoke_later`` as a queue the test drains."""

    def __init__(self):
        self.calls = []

    def invoke_later(self, callable, *args, **kwargs):
        self.calls.append((callable, args, kwargs))

    def drain(self):
        turns = 0

        while self.calls:
            callable, args, kwargs = self.calls.pop(0)
            callable(*args, **kwargs)
            turns += 1

        return turns


#: Pane id the fake controller "mounts" for each pane factory.
MOUNTED_PANE_IDS = {
    _pane_factory: "test.first.pane",
    _other_pane_factory: "test.last.surprise_pane",
}


class FakeLiveTaskExtensions(LiveTaskExtensionsController):
    """Reports the panes 'mounted' for each extension and records unmounts."""

    unmounted = List()

    def mounted_pane_ids(self, extensions):
        return [
            MOUNTED_PANE_IDS[factory]
            for extension in extensions
            for factory in extension.dock_pane_factories
        ]

    def unmount_pane(self, pane_id):
        self.unmounted.append(pane_id)


@pytest.fixture
def event_loop(monkeypatch):
    loop = FakeEventLoop()
    monkeypatch.setattr(deferred_loader, "GUI", loop)
    STARTED.clear()

    return loop


def _deferred(class_name, *pane_ids):
    return DeferredPlugin(
        spec=f"{_SPEC_PREFIX}:{class_name}",
        dock_panes=[DeferredDockPane(id=pane_id, name=pane_id) for pane_id in pane_ids],
    )


def _make_loader(tmp_path, deferred_plugins):
    application = Application(
        plugins=[CorePlugin()],
        plugin_manager=IsolatingPluginManager(),
        home=str(tmp_path / "home"),
        user_data=str(tmp_path / "data"),
    )
    application.start()

    loader = DeferredPluginLoader(
        application=application,
        deferred_plugins=deferred_plugins,
        load_status=application.plugin_manager.load_status,
    )
    loader.mark_pending()

    return loader


def test_plugins_load_in_order_and_a_failure_does_not_stop_the_rest(
    tmp_path, event_loop
):
    deferred_plugins = [
        _deferred("FirstPlugin", "test.first.pane"),
        _deferred("NoSuchPlugin", "test.missing.pane"),
        _deferred("FailingPlugin"),
        _deferred("LastPlugin"),
    ]
    loader = _make_loader(tmp_path, deferred_plugins)
    status = loader.load_status
    finished = []
    loader.observe(finished.append, "finished")

    pending = [record.plugin_id for record in status.records[1:]]

    assert pending == [deferred.spec for deferred in deferred_plugins]
    assert {record.state for record in status.records[1:]} == {LOAD_PENDING}

    loader.start(FakeLiveTaskExtensions())

    # One plugin per turn: nothing loads until the event loop runs.
    assert STARTED == []

    turns = event_loop.drain()

    assert STARTED == ["test.first", "test.last"]
    assert turns >= len(deferred_plugins) + 1
    assert len(finished) == 1
    assert not loader.running

    states = {record.plugin_id: record.state for record in status.records[1:]}

    assert states == {
        "test.first": LOAD_LOADED,
        f"{_SPEC_PREFIX}:NoSuchPlugin": LOAD_FAILED,
        "test.failing": LOAD_FAILED,
        "test.last": LOAD_LOADED,
    }
    assert status.get_record("test.failing").error == "RuntimeError: camera not found"
    assert status.get_record(f"{_SPEC_PREFIX}:NoSuchPlugin").error.startswith(
        "AttributeError"
    )

    application = loader.application

    assert application.get_plugin("test.failing") is None
    assert application.get_plugin("test.last") is not None


def test_a_record_keeps_its_place_and_object_when_it_takes_the_plugin_id(
    tmp_path, event_loop
):
    deferred = _deferred("FirstPlugin")
    loader = _make_loader(tmp_path, [deferred])
    record = loader.record_for(deferred)

    loader.start(FakeLiveTaskExtensions())
    event_loop.drain()

    assert loader.load_status.get_record("test.first") is record
    assert record.name == "First Plugin"
    assert record.state == LOAD_LOADED


def test_finished_fires_once_with_nothing_to_load(tmp_path, event_loop):
    loader = _make_loader(tmp_path, [])
    finished = []
    loader.observe(finished.append, "finished")

    loader.start(FakeLiveTaskExtensions())
    loader.start(FakeLiveTaskExtensions())
    event_loop.drain()

    assert len(finished) == 1


def test_panes_that_differ_from_the_declaration_are_warned_about(
    tmp_path, event_loop, caplog
):
    deferred_plugins = [
        _deferred("FirstPlugin", "test.first.pane"),
        _deferred("LastPlugin", "test.last.pane"),
    ]
    loader = _make_loader(tmp_path, deferred_plugins)
    controller = FakeLiveTaskExtensions()

    loader.start(controller)
    event_loop.drain()

    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING" and "declares dock panes" in record.message
    ]

    assert len(warnings) == 1
    assert "LastPlugin" in warnings[0]
    assert "test.last.surprise_pane" in warnings[0]

    # The declared pane never arrived, so its placeholder is taken down.
    assert controller.unmounted == ["test.last.pane"]


def test_compare_declared_panes():
    assert compare_declared_panes(["a", "b"], ["b", "c"]) == (["a"], ["c"])
    assert compare_declared_panes(["a"], ["a"]) == ([], [])
