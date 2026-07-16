"""Tests for the pixi environment snapshot + diff that gates hot-loading."""
import json

import pytest
from types import SimpleNamespace

from plugin_management import package_installer
from plugin_management.package_installer import (
    EnvDiff, diff_snapshots, env_snapshot)


def _snap(**pkgs):
    """{name: (version, build, kind)} from name="version" kwargs."""
    return {n: (v, "b0", "conda") for n, v in pkgs.items()}


def test_diff_detects_added():
    d = diff_snapshots(_snap(a="1.0"), _snap(a="1.0", b="2.0"))
    assert d.added == {"b": "2.0"}
    assert d.changed == {} and d.removed == {}


def test_diff_detects_removed():
    d = diff_snapshots(_snap(a="1.0", b="2.0"), _snap(a="1.0"))
    assert d.removed == {"b": "2.0"}
    assert d.added == {} and d.changed == {}


def test_diff_detects_changed_version():
    d = diff_snapshots(_snap(a="1.0"), _snap(a="1.1"))
    assert d.changed == {"a": ("1.0", "1.1")}


def test_diff_build_only_change_counts_as_changed():
    """A same-version rebuild replaces files on disk under live modules."""
    before = {"a": ("1.0", "b0", "conda")}
    after = {"a": ("1.0", "b1", "conda")}
    assert diff_snapshots(before, after).changed == {"a": ("1.0", "1.0")}


def test_diff_kind_change_counts_as_changed():
    before = {"a": ("1.0", "b0", "conda")}
    after = {"a": ("1.0", "b0", "pypi")}
    assert diff_snapshots(before, after).changed == {"a": ("1.0", "1.0")}


def test_is_pure_addition_only_when_nothing_else_moved():
    assert EnvDiff({"b": "1"}, {}, {}).is_pure_addition is True
    assert EnvDiff({"b": "1"}, {"a": ("1", "2")}, {}).is_pure_addition is False
    assert EnvDiff({"b": "1"}, {}, {"c": "1"}).is_pure_addition is False


def test_is_pure_removal_only_when_nothing_else_moved():
    assert EnvDiff({}, {}, {"c": "1"}).is_pure_removal is True
    assert EnvDiff({"b": "1"}, {}, {"c": "1"}).is_pure_removal is False
    assert EnvDiff({}, {"a": ("1", "2")}, {"c": "1"}).is_pure_removal is False


def test_empty_diff_is_both_pure_addition_and_pure_removal():
    """A no-op pixi call changes nothing, so both directions are trivially safe."""
    empty = EnvDiff({}, {}, {})
    assert empty.is_pure_addition is True
    assert empty.is_pure_removal is True


def test_env_snapshot_parses_records(monkeypatch):
    payload = [{"name": "numpy", "version": "2.1.0", "build": "py313h0",
                "kind": "conda"}]
    monkeypatch.setattr(package_installer, "_run",
                        lambda a, cwd=None: SimpleNamespace(
                            stdout=json.dumps(payload)))
    assert env_snapshot() == {"numpy": ("2.1.0", "py313h0", "conda")}


def test_env_snapshot_tolerates_leading_warnings(monkeypatch):
    """pixi prints warnings before the JSON, exactly as `search` does."""
    payload = [{"name": "numpy", "version": "2.1.0", "build": "b0",
                "kind": "conda"}]
    stdout = f" WARN something deprecated\n{json.dumps(payload)}"
    monkeypatch.setattr(package_installer, "_run",
                        lambda a, cwd=None: SimpleNamespace(stdout=stdout))
    assert env_snapshot()["numpy"][0] == "2.1.0"


def test_parse_list_json_without_array_raises():
    with pytest.raises(package_installer.InstallError):
        package_installer._parse_list_json("no json here")
