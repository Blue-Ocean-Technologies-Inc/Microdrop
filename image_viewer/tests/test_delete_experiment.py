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

# Third-party imports.
import pytest
from send2trash import TrashPermissionError

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from image_viewer import controller as viewer_controller
from image_viewer import discovery
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
    monkeypatch.setattr(discovery, "send2trash", calls.append)

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
    monkeypatch.setattr(discovery, "send2trash", refuse)

    with pytest.raises(TrashPermissionError) as raised:
        discovery.delete_experiment(old)

    # No permanent-delete fallback: the folder is still on disk.
    assert raised.value is failure
    assert (old / "frame.png").is_file()


def test_delete_experiment_without_send2trash_deletes_nothing(tmp_path, monkeypatch):
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)
    monkeypatch.setattr(discovery, "send2trash", None)

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
    monkeypatch.setattr(discovery, "send2trash", None)
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
    assert message == (
        "Sending experiments to the Recycle Bin needs the send2trash package, "
        "which this environment does not have. Update the pixi-microdrop "
        "repository to install it."
    )
    assert kwargs["ok_label"] == "Update and relaunch"
    assert kwargs["cancel_label"] == "Not now"
    assert (old / "frame.png").is_file()
