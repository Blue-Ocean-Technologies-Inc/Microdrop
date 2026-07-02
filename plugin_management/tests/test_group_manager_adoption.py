"""Regression tests for startup adoption (the duplicate-base-class crash).

A Plugin's ``id`` cannot be read off the CLASS (Traits swallows the class-level
default), so adoption/enable must match already-registered plugins by
isinstance against the live plugin manager. Getting this wrong made enable()
add a SECOND instance of each startup-composed heater plugin, doubling its
service offers and crashing the backend mixin composition with
"duplicate base class HeaterMonitorMixinService".
"""
import pytest

from heater_controls_ui.plugin import HeaterControlsUiPlugin
from heater_controller.plugin import HeaterControllerPlugin
from plugin_management import group_manager
from plugin_management.group_manager import PluginGroupManager


@pytest.fixture(autouse=True)
def isolated_app_globals(monkeypatch):
    """Keep enable/disable from persisting flags into the REAL redis-backed
    app_globals — a polluted flag makes the real app restore groups wrongly."""
    monkeypatch.setattr(group_manager, "app_globals", {})


class FakeApp:
    """Just enough application surface for adopt/enable/disable."""

    class _Registry:
        _services = {}

    service_registry = _Registry()

    def __init__(self, plugins=()):
        self.plugin_manager = list(plugins)
        self.calls = []

    def add_plugin(self, p):
        self.plugin_manager.append(p)
        self.calls.append(("add", type(p).__name__))

    def start_plugin(self, p):
        self.calls.append(("start", type(p).__name__))

    def stop_plugin(self, p):
        self.calls.append(("stop", type(p).__name__))

    def remove_plugin(self, p):
        self.plugin_manager.remove(p)
        self.calls.append(("remove", type(p).__name__))

    def unregister_service(self, sid):
        self.calls.append(("unreg", sid))


def test_group_registry_splits_ui_and_backend_per_device():
    m = PluginGroupManager()
    assert {"zstage_ui", "zstage_backend", "heater_ui", "heater_backend"} <= set(m.groups)


def test_adopt_running_matches_startup_instances_by_class():
    ui, backend = HeaterControlsUiPlugin(), HeaterControllerPlugin()
    app = FakeApp(plugins=[ui, backend])
    m = PluginGroupManager()
    m.adopt_running(app)
    heater_ui = m.groups["heater_ui"]
    assert heater_ui.loaded is True
    assert heater_ui.instances == [ui]              # the LIVE instance
    # Only the half present in this process becomes active.
    assert heater_ui.active_specs == [
        "heater_controls_ui.plugin:HeaterControlsUiPlugin"]
    heater_backend = m.groups["heater_backend"]
    assert heater_backend.loaded is True
    assert heater_backend.instances == [backend]
    assert m.groups["zstage_ui"].loaded is False    # not in this process


def test_enable_adopts_already_registered_plugins_instead_of_duplicating():
    backend = HeaterControllerPlugin()
    app = FakeApp(plugins=[backend])
    m = PluginGroupManager()
    # No adoption ran (simulates the early-restore race): enable must still
    # NOT add a second instance of the startup-composed plugin.
    m.enable(app, "heater_backend")
    assert m.is_loaded("heater_backend")
    assert m.groups["heater_backend"].instances == [backend]
    assert not [c for c in app.calls if c[0] == "add"], app.calls


def test_disable_after_adoption_removes_the_adopted_instance():
    backend = HeaterControllerPlugin()
    app = FakeApp(plugins=[backend])
    m = PluginGroupManager()
    m.adopt_running(app)
    m.disable(app, "heater_backend")
    assert not m.is_loaded("heater_backend")
    assert [name for op, name in app.calls if op == "remove"] == [
        "HeaterControllerPlugin"]
