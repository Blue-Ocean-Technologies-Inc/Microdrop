# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""prunable_experiments / prune_experiments: only experiments holding
nothing but logs go, never the current one."""

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from image_viewer import discovery
from image_viewer.consts import EXPERIMENT_LOGS_DIR_NAME


def _logs_only_experiment(root, name):
    experiment = root / name
    logs = experiment / EXPERIMENT_LOGS_DIR_NAME
    logs.mkdir(parents=True)
    (logs / "app.log").write_text("log line")

    return experiment


def test_prunes_only_experiments_holding_nothing_but_logs(tmp_path, monkeypatch):
    current = _logs_only_experiment(tmp_path, "current")
    logs_only = _logs_only_experiment(tmp_path, "logs_only")

    empty_captures = _logs_only_experiment(tmp_path, "empty_captures")
    (empty_captures / CAPTURES_DIR_NAME / "burst").mkdir(parents=True)

    with_capture = _logs_only_experiment(tmp_path, "with_capture")
    (with_capture / CAPTURES_DIR_NAME).mkdir()
    (with_capture / CAPTURES_DIR_NAME / "frame.png").write_bytes(b"")

    stray_file = _logs_only_experiment(tmp_path, "stray_file")
    (stray_file / "protocol.json").write_text("{}")

    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)

    targets = discovery.prunable_experiments()

    assert targets == [empty_captures, logs_only]

    removed = discovery.prune_experiments(targets)

    assert removed == targets
    assert not logs_only.exists()
    assert not empty_captures.exists()

    for kept in (current, with_capture, stray_file):
        assert kept.is_dir()


def test_nothing_prunable_without_an_experiments_root(monkeypatch):
    def unavailable():
        raise RuntimeError("no Redis")

    monkeypatch.setattr(discovery, "get_current_experiment_directory", unavailable)

    assert discovery.prunable_experiments() == []
