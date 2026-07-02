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


def test_adopt_running_matches_startup_instances_by_class():
    ui, backend = HeaterControlsUiPlugin(), HeaterControllerPlugin()
    app = FakeApp(plugins=[ui, backend])
    m = PluginGroupManager()
    m.adopt_running(app)
    heater = m.groups["heater"]
    assert heater.loaded is True
    assert heater.instances == [ui, backend]        # the LIVE instances
    assert m.groups["zstage"].loaded is False       # not in this process


def test_enable_adopts_already_registered_plugins_instead_of_duplicating():
    ui, backend = HeaterControlsUiPlugin(), HeaterControllerPlugin()
    app = FakeApp(plugins=[ui, backend])
    m = PluginGroupManager()
    # No adoption ran (simulates the early-restore race): enable must still
    # NOT add second instances of the startup-composed plugins.
    m.enable(app, "heater")
    assert m.is_loaded("heater")
    assert m.groups["heater"].instances == [ui, backend]
    assert not [c for c in app.calls if c[0] == "add"], app.calls


def test_disable_after_adoption_removes_the_adopted_instances():
    ui, backend = HeaterControlsUiPlugin(), HeaterControllerPlugin()
    app = FakeApp(plugins=[ui, backend])
    m = PluginGroupManager()
    m.adopt_running(app)
    m.disable(app, "heater")
    assert not m.is_loaded("heater")
    removed = [name for op, name in app.calls if op == "remove"]
    # Reverse unload order: backend stopped/removed before the UI.
    assert removed == ["HeaterControllerPlugin", "HeaterControlsUiPlugin"]
