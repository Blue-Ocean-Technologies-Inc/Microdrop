"""Tests for the 3-tier manifest lookup in entry_point_discovery.

A plugin's microdrop_plugin.toml may ship as package data of the entry-point
module (step 1), in the distribution's dist-info (step 2), or as any other
file the distribution installs — e.g. a top-level manifest shipped as a
namespaced data file (step 3). _read_manifest_text tries them in that order.
"""
import types

from plugin_management import entry_point_discovery as d

MANIFEST = """schema_version = 1
name = "toplevel_demo"
version = "0.1.0"
packages = ["pkgx"]
[[groups]]
name = "g"
plugins = ["pkgx.plugin:P"]
enabled_key = "microdrop.x_enabled"
"""


def _ep(dist):
    # ep.module points at a real, importable package that has NO manifest, so
    # step 1 (package data) misses and the dist-based steps are exercised.
    return types.SimpleNamespace(name="demo", module="plugin_management", dist=dist)


def test_step2_reads_from_dist_info():
    class DistInfo:
        name = "demo_dist"
        files = ()
        def read_text(self, n):
            return MANIFEST if n == "microdrop_plugin.toml" else None

    assert d._read_manifest_text(_ep(DistInfo())) == MANIFEST


def test_step3_reads_any_named_dist_file():
    class Path:
        name = "microdrop_plugin.toml"
        def read_text(self, encoding=None):
            return MANIFEST

    class DistFiles:
        name = "demo_dist"
        files = [Path()]
        def read_text(self, n):
            return None

    assert d._read_manifest_text(_ep(DistFiles())) == MANIFEST


def test_missing_anchor_falls_through_to_dist():
    # ep.module names a package that does not exist -> step 1 raises
    # ModuleNotFoundError, is swallowed, and the dist-based step 3 still finds it.
    class Path:
        name = "microdrop_plugin.toml"
        def read_text(self, encoding=None):
            return MANIFEST

    class DistFiles:
        name = "demo_dist"
        files = [Path()]
        def read_text(self, n):
            return None

    ep = types.SimpleNamespace(name="demo", module="no_such_pkg_xyz",
                               dist=DistFiles())
    assert d._read_manifest_text(ep) == MANIFEST


def test_broken_anchor_import_falls_through_to_dist():
    # anchor exists but raises ImportError on access -> must not break discovery.
    class DistInfo:
        name = "demo_dist"
        files = ()
        def read_text(self, n):
            return MANIFEST if n == "microdrop_plugin.toml" else None

    def boom(_pkg):
        raise ImportError("broken anchor dependency")

    ep = types.SimpleNamespace(name="demo", module="plugin_management",
                               dist=DistInfo())
    original = d.importlib_resources.files
    d.importlib_resources.files = boom
    try:
        assert d._read_manifest_text(ep) == MANIFEST
    finally:
        d.importlib_resources.files = original


def test_missing_manifest_returns_none():
    class NoManifest:
        name = "demo_dist"
        files = ()
        def read_text(self, n):
            return None

    assert d._read_manifest_text(_ep(NoManifest())) is None


def test_step1_reads_package_data_manifest():
    # peripheral_controller ships microdrop_plugin.toml as package data; step 1
    # reads it straight from the package (no entry-point registration needed).
    # This is the path package-data plugins use.
    ep = types.SimpleNamespace(name="magnet", module="peripheral_controller",
                               dist=None)
    text = d._read_manifest_text(ep)
    assert text is not None and "magnet_peripherals" in text
