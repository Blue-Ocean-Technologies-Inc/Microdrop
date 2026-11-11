# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Locating and reading the daemon's status file."""

# Standard library imports.
import json
from pathlib import Path

# Microdrop package imports.
from rpi_battery_status.consts import STATUS_FILE_ENV_VAR
from rpi_battery_status.services import status_file_reader
from rpi_battery_status.services.status_file_reader import (
    read_snapshot,
    status_file_path,
)


def test_reads_a_status_object(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"schema": 1, "timestamp": 1.0, "soc": 73}))

    assert read_snapshot(path) == {"schema": 1, "timestamp": 1.0, "soc": 73}


def test_missing_file_reads_as_none(tmp_path):
    assert read_snapshot(tmp_path / "absent" / "status.json") is None


def test_malformed_json_reads_as_none(tmp_path):
    path = tmp_path / "status.json"
    path.write_text('{"soc": 7')

    assert read_snapshot(path) is None


def test_undecodable_bytes_read_as_none(tmp_path):
    path = tmp_path / "status.json"
    path.write_bytes(b"\xff\xfe\xfa")

    assert read_snapshot(path) is None


def test_non_object_json_reads_as_none(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("[1, 2, 3]")

    assert read_snapshot(path) is None


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(STATUS_FILE_ENV_VAR, str(tmp_path / "mine.json"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")

    assert status_file_path() == tmp_path / "mine.json"


def test_xdg_runtime_dir_is_used(monkeypatch):
    monkeypatch.delenv(STATUS_FILE_ENV_VAR, raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")

    expected = Path("/run/user/1000/rpi-battery-monitor/status.json")

    assert status_file_path() == expected


def test_tmp_fallback_uses_the_uid(monkeypatch):
    monkeypatch.delenv(STATUS_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(status_file_reader.os, "getuid", lambda: 1000, raising=False)

    expected = Path("/tmp/rpi-battery-monitor-1000/rpi-battery-monitor/status.json")

    assert status_file_path() == expected


def test_tmp_fallback_without_getuid(monkeypatch):
    monkeypatch.delenv(STATUS_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.delattr(status_file_reader.os, "getuid", raising=False)

    expected = Path("/tmp/rpi-battery-monitor-unknown/rpi-battery-monitor/status.json")

    assert status_file_path() == expected
