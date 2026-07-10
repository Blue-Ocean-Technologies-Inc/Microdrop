"""Regression tests for startup adoption (the duplicate-base-class crash).

A Plugin's ``id`` cannot be read off the CLASS (Traits swallows the class-level
default), so adoption/enable must match already-registered plugins by
isinstance against the live plugin manager. Getting this wrong made enable()
add a SECOND instance of each startup-composed plugin, doubling its service
offers and crashing the backend mixin composition ("duplicate base class").

The device stacks are installable packages now, so these tests register a
synthetic manifest whose group specs point at dummy plugin classes defined
here (resolved through the same importlib path production uses).
"""
import pytest
from envisage.plugin import Plugin

from plugin_management import group_manager
from plugin_management.group_manager import PluginGroupManager
from plugin_management.manifest import manifest_from_dict


class DummyUiPlugin(Plugin):
    id = "plugin_management.tests.dummy_ui"


class DummyBackendPlugin(Plugin):
    id = "plugin_management.tests.dummy_backend"


_SPEC_PREFIX = "plugin_management.tests.test_group_manager_adoption"

TEST_MANIFEST = manifest_from_dict({
    "schema_version": 1,
    "name": "dummy_device",
    "packages": ["plugin_management"],
    "groups": [
        {"name": "dummy_ui_group",
         "plugins": [f"{_SPEC_PREFIX}:DummyUiPlugin"],
         "enabled_key": "plugin_group_enabled.dummy_ui_group"},
        {"name": "dummy_backend_group",
         "plugins": [f"{_SPEC_PREFIX}:DummyBackendPlugin"],
         "enabled_key": "plugin_group_enabled.dummy_backend_group"},
    ],
})


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch):
    """Keep enable/disable from persisting flags into the REAL application
    preferences file — a polluted flag makes the real app restore groups
    wrongly."""
    from apptools.preferences.api import Preferences
    store = Preferences()
    monkeypatch.setattr(group_manager, "get_default_preferences",
                        lambda: store)
    return store


def make_manager():
    m = PluginGroupManager()
    m.register_manifest(TEST_MANIFEST, dist_name="dummy-device-plugin")
    return m


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


def test_manifest_groups_register_and_classify_as_installed():
    m = make_manager()
    assert {"dummy_ui_group", "dummy_backend_group"} <= set(m.groups)
    assert m.installed_plugins() == [
        ("dummy_device", "dummy_device", "dummy-device-plugin",
         ["dummy_ui_group", "dummy_backend_group"])]


def test_adopt_running_matches_registered_instances_by_class():
    ui, backend = DummyUiPlugin(), DummyBackendPlugin()
    app = FakeApp(plugins=[ui, backend])
    m = make_manager()
    m.adopt_running(app)
    assert m.groups["dummy_ui_group"].loaded is True
    assert m.groups["dummy_ui_group"].instances == [ui]     # the LIVE instance
    assert m.groups["dummy_backend_group"].instances == [backend]


def test_enable_adopts_already_registered_plugins_instead_of_duplicating():
    backend = DummyBackendPlugin()
    app = FakeApp(plugins=[backend])
    m = make_manager()
    # No adoption ran (simulates the early-restore race): enable must still
    # NOT add a second instance of the already-registered plugin.
    m.enable(app, "dummy_backend_group")
    assert m.is_loaded("dummy_backend_group")
    assert m.groups["dummy_backend_group"].instances == [backend]
    assert not [c for c in app.calls if c[0] == "add"], app.calls


def test_disable_after_adoption_removes_the_adopted_instance():
    backend = DummyBackendPlugin()
    app = FakeApp(plugins=[backend])
    m = make_manager()
    m.adopt_running(app)
    m.disable(app, "dummy_backend_group")
    assert not m.is_loaded("dummy_backend_group")
    assert [name for op, name in app.calls if op == "remove"] == [
        "DummyBackendPlugin"]


def test_enable_constructs_when_nothing_registered():
    app = FakeApp()
    m = make_manager()
    m.enable(app, "dummy_ui_group")
    assert m.is_loaded("dummy_ui_group")
    assert [c for c in app.calls if c[0] == "add"] == [("add", "DummyUiPlugin")]
    m.disable(app, "dummy_ui_group")
    assert not m.is_loaded("dummy_ui_group")


def test_disabled_group_stays_disabled_across_restart(isolated_preferences):
    """The user's toggle-off must survive an app restart: disable persists
    the flag to preferences, and a FRESH manager (new process) restoring
    against the same preferences unloads the startup-composed group."""
    app = FakeApp(plugins=[DummyBackendPlugin()])
    m = make_manager()
    m.adopt_running(app)
    m.disable(app, "dummy_backend_group")

    # "Restart": new manager + new app, same preferences store.
    app2 = FakeApp(plugins=[DummyUiPlugin(), DummyBackendPlugin()])
    m2 = make_manager()
    m2.adopt_running(app2)
    m2.restore_persisted(app2)
    assert not m2.is_loaded("dummy_backend_group")   # stayed disabled
    assert m2.is_loaded("dummy_ui_group")            # untouched: default on


def test_reenabled_group_restores_enabled(isolated_preferences):
    app = FakeApp(plugins=[DummyBackendPlugin()])
    m = make_manager()
    m.adopt_running(app)
    m.disable(app, "dummy_backend_group")
    m.enable(app, "dummy_backend_group")             # user toggles back on

    app2 = FakeApp(plugins=[DummyBackendPlugin()])
    m2 = make_manager()
    m2.adopt_running(app2)
    m2.restore_persisted(app2)
    assert m2.is_loaded("dummy_backend_group")
