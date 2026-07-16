"""Tests for the channel search/parse/cache data layer."""
import json
from types import SimpleNamespace

import pytest

from plugin_management import package_installer, paths
from plugin_management.consts import PLUGIN_CHANNEL_URL


SAMPLE_STDOUT = """ WARN some deprecation warning on stderr-ish text
Using channels: https://prefix.dev/microdrop-plugins/
{
  "noarch": [
    {
      "name": "scipy_analysis",
      "version": "0.1.0",
      "build": "pyh4616a5c_0",
      "depends": ["scipy >=1.10", "python >=3.11"],
      "size": 5485,
      "timestamp": 1782507668846,
      "fn": "scipy_analysis-0.1.0-pyh4616a5c_0.conda",
      "url": "https://prefix.dev/microdrop-plugins/noarch/scipy_analysis-0.1.0-pyh4616a5c_0.conda"
    }
  ]
}
"""


def test_parse_search_json_flattens_subdirs():
    pkgs = package_installer._parse_search_json(SAMPLE_STDOUT)
    assert [p["name"] for p in pkgs] == ["scipy_analysis"]
    assert pkgs[0]["version"] == "0.1.0"


def test_parse_search_json_no_json_raises():
    with pytest.raises(package_installer.InstallError):
        package_installer._parse_search_json("no json here")


def test_search_channel_writes_cache(tmp_path, monkeypatch):
    cache = tmp_path / "plugin_index.json"
    monkeypatch.setattr(paths, "plugin_index_file", lambda: cache)

    class _Proc:
        stdout = SAMPLE_STDOUT
    monkeypatch.setattr(package_installer, "_run", lambda *a, **k: _Proc())

    result = package_installer.search_channel(PLUGIN_CHANNEL_URL)
    assert result[0]["name"] == "scipy_analysis"
    assert json.loads(cache.read_text(encoding="utf-8"))[0]["name"] == "scipy_analysis"


def test_read_cached_index_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "plugin_index_file", lambda: tmp_path / "missing.json")
    assert package_installer.read_cached_index() == []


def test_read_cached_index_valid_json(tmp_path, monkeypatch):
    cache = tmp_path / "plugin_index.json"
    data = [{"name": "my_plugin", "version": "1.0.0"}]
    cache.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(paths, "plugin_index_file", lambda: cache)
    assert package_installer.read_cached_index() == data


def test_read_cached_index_malformed_json(tmp_path, monkeypatch):
    cache = tmp_path / "plugin_index.json"
    cache.write_text("not valid json {{{{", encoding="utf-8")
    monkeypatch.setattr(paths, "plugin_index_file", lambda: cache)
    assert package_installer.read_cached_index() == []


def test_ensure_channel_registered_passes_url(monkeypatch):
    calls = []
    monkeypatch.setattr(package_installer, "_run",
                        lambda args, cwd=None: calls.append((list(args), cwd)))
    monkeypatch.setattr(package_installer, "_registered_channels", set())
    package_installer._ensure_channel_registered("https://prefix.dev/microdrop-plugins", cwd=None)
    assert calls[0][0] == ["workspace", "channel", "add",
                           "https://prefix.dev/microdrop-plugins"]


def test_ensure_channel_registered_memoizes_per_process(monkeypatch):
    """The channel URL is a fixed constant; re-registering it on every install
    wastes a pixi subprocess. Once per (url, workspace) per run is enough."""
    calls = []
    monkeypatch.setattr(package_installer, "_run",
                        lambda args, cwd=None: calls.append(list(args)))
    monkeypatch.setattr(package_installer, "_registered_channels", set())
    package_installer._ensure_channel_registered("https://c", cwd=None)
    package_installer._ensure_channel_registered("https://c", cwd=None)
    assert len(calls) == 1


def test_install_from_channel_adds_and_returns(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    (tmp_path / "pixi.lock").write_text("lock", encoding="utf-8")
    calls = []
    monkeypatch.setattr(package_installer, "_run",
                        lambda args, cwd=None: calls.append(list(args)))
    result = package_installer.install_from_channel(
        "scipy_analysis", "https://prefix.dev/microdrop-plugins", cwd=tmp_path)
    assert ["add", "scipy_analysis"] in calls
    assert result.name == "scipy_analysis"
    # The fake _run returns None, so snapshotting fails -> unknown -> relaunch.
    assert result.diff is None
    assert result.requires_relaunch is True


def test_install_from_channel_rolls_back(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    (tmp_path / "pixi.lock").write_text("lock", encoding="utf-8")

    def fake_run(args, cwd=None):
        if args[:1] == ["add"]:
            raise package_installer.InstallError("boom")
    monkeypatch.setattr(package_installer, "_run", fake_run)
    with pytest.raises(package_installer.InstallError):
        package_installer.install_from_channel("x", "https://c", cwd=tmp_path)
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == "orig"


def test_installed_plugin_dists_shape():
    """Every entry maps a non-empty dist name to a non-empty version string;
    only distributions advertising the microdrop.plugins entry point appear."""
    dists = package_installer.installed_plugin_dists()
    assert isinstance(dists, dict)
    for name, version in dists.items():
        assert name and isinstance(name, str)
        assert version and isinstance(version, str)


def _rec(name, version, build="b0", kind="conda"):
    return {"name": name, "version": version, "build": build, "kind": kind}


class _FakeRun:
    """Stands in for package_installer._run.

    Serves a different `pixi list --json` payload on each successive `list`
    call, so an install can be made to look purely additive or not."""

    def __init__(self, *list_payloads):
        self.payloads = list(list_payloads)
        self.calls = []

    def __call__(self, args, cwd=None):
        self.calls.append(list(args))
        if args[:1] == ["list"]:
            return SimpleNamespace(stdout=json.dumps(self.payloads.pop(0)))
        return None


def test_install_pure_addition_does_not_require_relaunch(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    fake = _FakeRun([_rec("numpy", "2.1.0")],
                    [_rec("numpy", "2.1.0"), _rec("my-plugin", "1.0.0")])
    monkeypatch.setattr(package_installer, "_run", fake)

    result = package_installer.install_from_channel(
        "my-plugin", "https://c", cwd=tmp_path)

    assert result.requires_relaunch is False
    assert result.diff.added == {"my-plugin": "1.0.0"}


def test_install_that_bumps_a_dep_requires_relaunch(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    fake = _FakeRun([_rec("numpy", "2.1.0")],
                    [_rec("numpy", "2.2.0"), _rec("my-plugin", "1.0.0")])
    monkeypatch.setattr(package_installer, "_run", fake)

    result = package_installer.install_from_channel(
        "my-plugin", "https://c", cwd=tmp_path)

    assert result.requires_relaunch is True
    assert result.diff.changed == {"numpy": ("2.1.0", "2.2.0")}


def test_install_snapshot_failure_still_installs_and_asks_relaunch(
        tmp_path, monkeypatch):
    """A broken `pixi list` must never break the install — it degrades to the
    relaunch prompt."""
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")

    def fake_run(args, cwd=None):
        if args[:1] == ["list"]:
            raise package_installer.InstallError("list exploded")
        return None
    monkeypatch.setattr(package_installer, "_run", fake_run)

    result = package_installer.install_from_channel(
        "my-plugin", "https://c", cwd=tmp_path)

    assert result.name == "my-plugin"
    assert result.diff is None
    assert result.requires_relaunch is True


def test_uninstall_pure_removal_does_not_require_relaunch(tmp_path, monkeypatch):
    fake = _FakeRun([_rec("numpy", "2.1.0"), _rec("my-plugin", "1.0.0")],
                    [_rec("numpy", "2.1.0")])
    monkeypatch.setattr(package_installer, "_run", fake)

    result = package_installer.uninstall_package("my-plugin", cwd=tmp_path)

    assert result.requires_relaunch is False
    assert result.diff.removed == {"my-plugin": "1.0.0"}


def test_uninstall_failure_raises(tmp_path, monkeypatch):
    """A failed `pixi remove` must RAISE, not be swallowed — swallowing made
    it indistinguishable from success-needing-relaunch, so the UI reported
    'Uninstalled X.' for a package still on disk. The controllers' on_error
    path turns the raise into an error dialog."""
    def fake_run(args, cwd=None):
        if args[:1] == ["remove"]:
            raise package_installer.InstallError("boom")
        return SimpleNamespace(stdout=json.dumps([_rec("numpy", "2.1.0")]))
    monkeypatch.setattr(package_installer, "_run", fake_run)

    with pytest.raises(package_installer.InstallError):
        package_installer.uninstall_package("my-plugin", cwd=tmp_path)


def test_reinstall_diffs_across_the_whole_cycle(tmp_path, monkeypatch):
    """The diff must span pre-remove -> post-add: a plugin-only dep that left
    and came back at a DIFFERENT version is a change (its old build may still
    be imported), never a harmless addition against the post-remove trough."""
    fake = _FakeRun([_rec("my-plugin", "1.0"), _rec("scipy", "1.10")],
                    [_rec("my-plugin", "2.0"), _rec("scipy", "1.11")])
    monkeypatch.setattr(package_installer, "_run", fake)
    monkeypatch.setattr(package_installer, "_registered_channels", set())

    result = package_installer.reinstall_from_channel(
        "my-plugin", "https://c", cwd=tmp_path, version="2.0")

    assert ["remove", "my-plugin"] in fake.calls
    assert ["add", "my-plugin==2.0"] in fake.calls
    assert result.diff.changed == {"my-plugin": ("1.0", "2.0"),
                                   "scipy": ("1.10", "1.11")}


def test_reinstall_failure_rolls_back_and_rematerializes(tmp_path, monkeypatch):
    """A failed add must restore pyproject/lock AND re-run `pixi install`, so
    the env is not left at the post-remove trough."""
    (tmp_path / "pyproject.toml").write_text("orig", encoding="utf-8")
    calls = []

    def fake_run(args, cwd=None):
        calls.append(list(args))
        if args[:1] == ["add"]:
            raise package_installer.InstallError("boom")
        if args[:1] == ["list"]:
            return SimpleNamespace(stdout=json.dumps([_rec("my-plugin", "1.0")]))
        return None
    monkeypatch.setattr(package_installer, "_run", fake_run)
    monkeypatch.setattr(package_installer, "_registered_channels", set())

    with pytest.raises(package_installer.InstallError):
        package_installer.reinstall_from_channel("my-plugin", "https://c",
                                                 cwd=tmp_path)

    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == "orig"
    assert ["install"] in calls
