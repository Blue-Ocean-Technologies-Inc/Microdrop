# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""delete_experiment: trashes a browsed experiment, never the current one."""

# Standard library imports.
import sys

# Third-party imports.
import pytest
from send2trash import TrashPermissionError

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from image_viewer import controller as viewer_controller
from image_viewer import discovery
from image_viewer.consts import TRASH_FEATURE, TRASH_PACKAGE
from image_viewer.controller import ImageViewerController
from image_viewer.model import ImageViewerModel
from microdrop_application.dialogs.pyface_wrapper import CANCEL, YES

# Microdrop utils imports.
from microdrop_utils import environment_update_dialog


def _experiment(root, name):
    captures = root / name / CAPTURES_DIR_NAME
    captures.mkdir(parents=True)
    (captures / "frame.png").write_bytes(b"")

    return captures


@pytest.fixture
def trashed(monkeypatch):
    """Record send2trash calls instead of trashing anything."""
    calls = []
    monkeypatch.setattr(discovery, "_send2trash", lambda: calls.append)

    return calls


def test_delete_experiment_sends_its_folder_to_the_trash(
    tmp_path, monkeypatch, trashed
):
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)

    moved = discovery.delete_experiment(old)

    assert moved == old.parent
    assert trashed == [str(old.parent)]


def test_delete_experiment_refuses_the_current_experiment(
    tmp_path, monkeypatch, trashed
):
    captures = _experiment(tmp_path, "current")
    monkeypatch.setattr(
        discovery, "get_current_experiment_directory", lambda: captures.parent
    )

    with pytest.raises(ValueError, match="current experiment"):
        discovery.delete_experiment(captures)

    assert trashed == []
    assert (captures / "frame.png").is_file()


def test_delete_experiment_propagates_a_trash_failure(tmp_path, monkeypatch):
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    failure = TrashPermissionError(str(old.parent))

    def refuse(path):
        raise failure

    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setattr(discovery, "_send2trash", lambda: refuse)

    with pytest.raises(TrashPermissionError) as raised:
        discovery.delete_experiment(old)

    # No permanent-delete fallback: the folder is still on disk.
    assert raised.value is failure
    assert (old / "frame.png").is_file()


def test_delete_experiment_without_send2trash_deletes_nothing(tmp_path, monkeypatch):
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setitem(sys.modules, "send2trash", None)

    with pytest.raises(discovery.TrashUnavailableError):
        discovery.delete_experiment(old)

    assert (old / "frame.png").is_file()


def test_delete_button_without_send2trash_offers_an_update(tmp_path, monkeypatch):
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    warnings = []

    def decline(parent, message, **kwargs):
        warnings.append((message, kwargs))

        return CANCEL

    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setitem(sys.modules, "send2trash", None)
    monkeypatch.setattr(viewer_controller, "confirm", lambda **kwargs: (YES, False))
    monkeypatch.setattr(environment_update_dialog, "warning", decline)
    monkeypatch.setattr(
        environment_update_dialog,
        "run_with_wait",
        lambda *args, **kwargs: pytest.fail("Not now must not start the update"),
    )

    model = ImageViewerModel(experiments=[("old", old)], selected_experiment="old")
    ImageViewerController(model=model)._delete_experiment(None)

    [(message, kwargs)] = warnings
    assert message == environment_update_dialog.missing_package_message(
        TRASH_FEATURE, TRASH_PACKAGE
    )
    assert kwargs["ok_label"] == environment_update_dialog.UPDATE_LABEL
    assert kwargs["cancel_label"] == environment_update_dialog.NOT_NOW_LABEL
    assert (old / "frame.png").is_file()


def _delete_button(monkeypatch, tmp_path, ready):
    """Press Delete on an old experiment, confirming once, with an
    environment update that answers ``ready``; return the old experiment's
    captures and what the flow did."""
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    record = {"confirms": 0, "offers": [], "selected": [], "errors": []}

    def confirm(**kwargs):
        record["confirms"] += 1

        return YES, False

    def offer(*args, **kwargs):
        record["offers"].append(args)

        return ready

    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setattr(viewer_controller, "confirm", confirm)
    monkeypatch.setattr(viewer_controller, "offer_environment_update", offer)
    monkeypatch.setattr(
        environment_update_dialog,
        "error",
        lambda parent, message, **kwargs: record["errors"].append(message),
    )
    monkeypatch.setattr(
        ImageViewerController,
        "_select_neighbour_of_deleted",
        lambda self, removed: record["selected"].append(removed),
    )

    model = ImageViewerModel(experiments=[("old", old)], selected_experiment="old")
    ImageViewerController(model=model)._delete_experiment(None)

    return old, record


def test_delete_button_retries_once_the_update_makes_send2trash_available(
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

    old, record = _delete_button(monkeypatch, tmp_path, ready=True)

    assert record["confirms"] == 1
    assert record["offers"] == [(TRASH_FEATURE, TRASH_PACKAGE)]
    assert trashed == [str(old.parent)]
    assert record["selected"] == [old.parent]
    assert record["errors"] == []


def test_delete_button_does_not_loop_when_send2trash_stays_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "send2trash", None)

    old, record = _delete_button(monkeypatch, tmp_path, ready=True)

    assert len(record["offers"]) == 1
    [message] = record["errors"]
    assert "pixi install" in message
    assert record["selected"] == []
    assert (old / "frame.png").is_file()
