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

# Standard library imports.
import sys

# Third-party imports.
import pytest
from send2trash import TrashPermissionError

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from image_viewer import discovery, menus
from image_viewer.consts import (
    EXPERIMENT_LOGS_DIR_NAME,
    TRASH_FEATURE,
    TRASH_PACKAGE,
)
from microdrop_application.dialogs.pyface_wrapper import CANCEL, YES

# Microdrop utils imports.
from microdrop_utils import environment_update_dialog


def _logs_only_experiment(root, name):
    experiment = root / name
    logs = experiment / EXPERIMENT_LOGS_DIR_NAME
    logs.mkdir(parents=True)
    (logs / "app.log").write_text("log line")

    return experiment


@pytest.fixture
def trashed(monkeypatch):
    """Record send2trash calls instead of trashing anything."""
    calls = []
    monkeypatch.setattr(discovery, "_send2trash", lambda: calls.append)

    return calls


def test_prunes_only_experiments_holding_nothing_but_logs(
    tmp_path, monkeypatch, trashed
):
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

    moved = discovery.prune_experiments(targets)

    assert moved == targets
    assert trashed == [str(empty_captures), str(logs_only)]


def test_prune_stops_on_a_trash_failure(tmp_path, monkeypatch):
    first = _logs_only_experiment(tmp_path, "first")
    second = _logs_only_experiment(tmp_path, "second")
    trashed = []

    def refuse_second(path):
        if path == str(second):
            raise TrashPermissionError(path)

        trashed.append(path)

    monkeypatch.setattr(discovery, "_send2trash", lambda: refuse_second)

    with pytest.raises(TrashPermissionError):
        discovery.prune_experiments([first, second])

    # No permanent-delete fallback: the failing folder is still on disk.
    assert trashed == [str(first)]
    assert (second / EXPERIMENT_LOGS_DIR_NAME / "app.log").is_file()


def test_nothing_prunable_without_an_experiments_root(monkeypatch):
    def unavailable():
        raise RuntimeError("no Redis")

    monkeypatch.setattr(discovery, "get_current_experiment_directory", unavailable)

    assert discovery.prunable_experiments() == []


def test_prune_without_send2trash_moves_nothing(tmp_path, monkeypatch):
    first = _logs_only_experiment(tmp_path, "first")
    monkeypatch.setitem(sys.modules, "send2trash", None)

    with pytest.raises(discovery.TrashUnavailableError):
        discovery.prune_experiments([first])

    assert (first / EXPERIMENT_LOGS_DIR_NAME / "app.log").is_file()


def test_prune_action_without_send2trash_offers_an_update(tmp_path, monkeypatch):
    current = _logs_only_experiment(tmp_path, "current")
    logs_only = _logs_only_experiment(tmp_path, "logs_only")
    offers = []

    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setitem(sys.modules, "send2trash", None)
    monkeypatch.setattr(menus, "confirm", lambda **kwargs: YES)
    monkeypatch.setattr(
        environment_update_dialog,
        "warning",
        lambda parent, message, **kwargs: offers.append(message) or CANCEL,
    )
    monkeypatch.setattr(
        menus,
        "information",
        lambda *args, **kwargs: pytest.fail("nothing was pruned"),
    )

    menus.PruneExperimentsAction().perform(None)

    assert offers == [
        environment_update_dialog.missing_package_message(TRASH_FEATURE, TRASH_PACKAGE)
    ]
    assert (logs_only / EXPERIMENT_LOGS_DIR_NAME / "app.log").is_file()


def _prune_action(monkeypatch, tmp_path, ready):
    """Run Prune Experiments over one logs-only experiment, confirming once,
    with an environment update that answers ``ready``; return that
    experiment and what the flow did."""
    current = _logs_only_experiment(tmp_path, "current")
    logs_only = _logs_only_experiment(tmp_path, "logs_only")
    record = {"confirms": 0, "offers": [], "informed": [], "errors": []}

    def confirm(**kwargs):
        record["confirms"] += 1

        return YES

    def offer(*args, **kwargs):
        record["offers"].append(args)

        return ready

    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setattr(menus, "confirm", confirm)
    monkeypatch.setattr(menus, "offer_environment_update", offer)
    monkeypatch.setattr(
        menus,
        "information",
        lambda parent, message, **kwargs: record["informed"].append(message),
    )
    monkeypatch.setattr(
        environment_update_dialog,
        "error",
        lambda parent, message, **kwargs: record["errors"].append(message),
    )

    menus.PruneExperimentsAction().perform(None)

    return logs_only, record


def test_prune_action_retries_once_the_update_makes_send2trash_available(
    tmp_path, monkeypatch
):
    trashed = []
    lookups = []

    def send2trash_after_the_update():
        lookups.append(None)

        if len(lookups) == 1:
            raise discovery.TrashUnavailableError("not installed yet")

        return trashed.append

    monkeypatch.setattr(discovery, "_send2trash", send2trash_after_the_update)

    logs_only, record = _prune_action(monkeypatch, tmp_path, ready=True)

    assert record["confirms"] == 1
    assert record["offers"] == [(TRASH_FEATURE, TRASH_PACKAGE)]
    assert trashed == [str(logs_only)]
    assert record["informed"] == ["Moved 1 experiment folder(s) to the trash."]
    assert record["errors"] == []


def test_prune_action_does_not_loop_when_send2trash_stays_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "send2trash", None)

    logs_only, record = _prune_action(monkeypatch, tmp_path, ready=True)

    assert len(record["offers"]) == 1
    [message] = record["errors"]
    assert "pixi install" in message
    assert record["informed"] == []
    assert (logs_only / EXPERIMENT_LOGS_DIR_NAME / "app.log").is_file()
