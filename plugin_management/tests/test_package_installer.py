"""Tests for the channel search/parse/cache data layer."""
import json

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
    package_installer._ensure_channel_registered("https://prefix.dev/microdrop-plugins", cwd=None)
    assert calls[0][0] == ["workspace", "channel", "add",
                           "https://prefix.dev/microdrop-plugins"]


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
