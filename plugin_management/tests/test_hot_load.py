"""Tests for the hot-load gate: when may a just-installed plugin be applied
to the LIVE app instead of relaunching?"""
import importlib
import sys

import pytest

from plugin_management import group_manager, hot_load
from plugin_management.group_manager import PluginGroupManager
from plugin_management.manifest import manifest_from_dict
from plugin_management.package_installer import EnvDiff
from plugin_management.tests.test_group_manager_adoption import FakeApp

PURE_ADDITION = EnvDiff(added={"my-plugin": "1.0"}, changed={}, removed={})
BUMPED_DEP = EnvDiff(added={"my-plugin": "1.0"},
                     changed={"numpy": ("2.1", "2.2")}, removed={})

DIST = "my-microdrop-plugin"


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch):
    """Keep enable/disable from writing the REAL application preferences."""
    from apptools.preferences.api import Preferences
    store = Preferences()
    monkeypatch.setattr(group_manager, "get_default_preferences",
                        lambda: store)
    return store


@pytest.fixture
def dummy_module(tmp_path, monkeypatch):
    """A real, importable, TOP-LEVEL module that is not yet in sys.modules.

    The guard keys on the top-level package name, so a dummy living inside
    `plugin_management` would always trip it — this has to be its own root."""
    (tmp_path / "hotload_dummy_pkg.py").write_text(
        "from envisage.plugin import Plugin\n"
        "\n"
        "class HotDummyPlugin(Plugin):\n"
        "    id = 'hotload_dummy_pkg.plugin'\n",
        encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "hotload_dummy_pkg"
    sys.modules.pop("hotload_dummy_pkg", None)


def _manifest_for(plugin_spec):
    return manifest_from_dict({
        "schema_version": 1,
        "name": "my_plugin",
        "packages": [plugin_spec.partition(":")[0]],
        "groups": [{
            "name": "my_group",
            "plugins": [plugin_spec],
            "enabled_key": "plugin_group_enabled.my_group",
        }],
    })


def _manifest(module):
    return _manifest_for(f"{module}:HotDummyPlugin")


def _patch_discovery(monkeypatch, manifest, dist=DIST):
    monkeypatch.setattr(hot_load, "discover_entry_point_manifests",
                        lambda: [(manifest, dist)])


def test_hot_loads_and_enables_a_pure_addition(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    app, manager = FakeApp(), PluginGroupManager()

    assert hot_load.hot_load_installed(app, manager, DIST, PURE_ADDITION) is None
    assert manager.is_loaded("my_group")
    assert [c for c in app.calls if c[0] == "add"] == [("add", "HotDummyPlugin")]


def test_refuses_when_diff_is_none(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    manager = PluginGroupManager()
    reason = hot_load.hot_load_installed(FakeApp(), manager, DIST, None)
    assert "could not be determined" in reason
    assert "my_group" not in manager.groups


def test_refuses_when_a_dep_was_bumped(monkeypatch, dummy_module):
    """The refusal reason names the moved packages, for the relaunch dialog."""
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    manager = PluginGroupManager()
    reason = hot_load.hot_load_installed(FakeApp(), manager, DIST, BUMPED_DEP)
    assert "numpy" in reason
    assert "my_group" not in manager.groups


def test_refuses_when_nothing_was_discovered(monkeypatch):
    monkeypatch.setattr(hot_load, "discover_entry_point_manifests", lambda: [])
    reason = hot_load.hot_load_installed(
        FakeApp(), PluginGroupManager(), DIST, PURE_ADDITION)
    assert "no plugin manifest" in reason


def test_refuses_when_dist_name_does_not_match(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module), dist="someone-else")
    reason = hot_load.hot_load_installed(
        FakeApp(), PluginGroupManager(), DIST, PURE_ADDITION)
    assert "no plugin manifest" in reason


def test_dist_name_match_ignores_case_and_underscores(monkeypatch, dummy_module):
    _patch_discovery(monkeypatch, _manifest(dummy_module),
                     dist="My_Microdrop_Plugin")
    assert hot_load.hot_load_installed(
        FakeApp(), PluginGroupManager(), DIST, PURE_ADDITION) is None


def test_refuses_when_the_module_is_already_imported(monkeypatch, dummy_module):
    """Reinstall-after-uninstall: the lock diff says 'pure addition', but
    import_module would hand back the STALE module."""
    importlib.import_module(dummy_module)          # simulate it being live
    _patch_discovery(monkeypatch, _manifest(dummy_module))
    manager = PluginGroupManager()

    reason = hot_load.hot_load_installed(
        FakeApp(), manager, DIST, PURE_ADDITION)
    assert "hotload_dummy_pkg" in reason and "already loaded" in reason
    assert "my_group" not in manager.groups


def test_refuses_when_a_colliding_group_is_loaded(monkeypatch, dummy_module):
    """A group-NAME collision across two distributions shipping DIFFERENT
    top-level packages: enable() imports test_group_manager_adoption's
    module (already in sys.modules anyway, since this test suite imports it),
    so the sys.modules guard passes and register_manifest is what refuses."""
    app, manager = FakeApp(), PluginGroupManager()
    loaded_spec = ("plugin_management.tests.test_group_manager_adoption"
                   ":DummyUiPlugin")
    manager.register_manifest(_manifest_for(loaded_spec), dist_name=DIST)
    manager.enable(app, "my_group")               # already live

    # The incoming manifest reuses the NAME but points at a fresh, unimported
    # module, so the guard passes and register_manifest is what refuses.
    _patch_discovery(monkeypatch, _manifest(dummy_module))

    reason = hot_load.hot_load_installed(app, manager, DIST, PURE_ADDITION)
    assert "currently enabled" in reason      # register_manifest's message
    # Prove it refused at register_manifest, not earlier: the live group's
    # spec is still the ORIGINAL one, not overwritten by the incoming one.
    assert manager.groups["my_group"].plugin_specs == [loaded_spec]


def test_refuses_when_the_plugin_cannot_be_imported(monkeypatch):
    """A manifest pointing at a module that does not exist: enable() cannot
    resolve it, the group never loads, and relaunch is a real remedy."""
    _patch_discovery(monkeypatch, _manifest("hotload_missing_pkg"))
    manager = PluginGroupManager()
    reason = hot_load.hot_load_installed(
        FakeApp(), manager, DIST, PURE_ADDITION)
    assert "failed to load" in reason


def test_live_modules_keys_on_the_top_level_package():
    """`plugin_management` is always imported here, so a spec nested under it
    must report the ROOT package, not the leaf module."""
    manifest = _manifest("plugin_management.tests.whatever")
    assert list(hot_load._live_modules(manifest, set(sys.modules))) == [
        "plugin_management"]


def test_live_modules_reads_the_snapshot_not_sys_modules(dummy_module):
    """The guard must key on what was imported BEFORE the install.

    `discover_entry_point_manifests()` reads package data via
    `importlib.resources.files(ep.module)`, which imports the entry point's
    module. If the guard read `sys.modules` live it would see that import and
    refuse every install — so it must consult a pre-discovery snapshot."""
    manifest = _manifest(dummy_module)
    before = set(sys.modules)                     # dummy_module not yet imported
    importlib.import_module(dummy_module)         # what discovery does to us
    assert dummy_module in sys.modules            # live read would refuse...
    assert list(hot_load._live_modules(manifest, before)) == []   # ...snapshot does not


def test_hot_loads_even_though_discovery_imported_the_module(monkeypatch,
                                                             dummy_module):
    """End-to-end regression: real discovery imports the plugin's module, so a
    fresh install must still hot-load. Guarding on a live `sys.modules` read
    made this refuse every time."""
    manifest = _manifest(dummy_module)

    def _discovery_that_imports():
        importlib.import_module(dummy_module)     # exactly what the real one does
        return [(manifest, DIST)]
    monkeypatch.setattr(hot_load, "discover_entry_point_manifests",
                        _discovery_that_imports)

    app, manager = FakeApp(), PluginGroupManager()
    assert hot_load.hot_load_installed(app, manager, DIST, PURE_ADDITION) is None
    assert manager.is_loaded("my_group")
