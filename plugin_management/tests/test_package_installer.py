"""Tests for the channel search/parse/cache data layer."""
import json

import pytest

from plugin_management import package_installer, paths


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

    result = package_installer.search_channel("https://prefix.dev/microdrop-plugins")
    assert result[0]["name"] == "scipy_analysis"
    assert json.loads(cache.read_text(encoding="utf-8"))[0]["name"] == "scipy_analysis"


def test_read_cached_index_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "plugin_index_file", lambda: tmp_path / "missing.json")
    assert package_installer.read_cached_index() == []
