# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""delete_experiment: removes a browsed experiment, never the current one."""

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from image_viewer import discovery


def _experiment(root, name):
    captures = root / name / CAPTURES_DIR_NAME
    captures.mkdir(parents=True)
    (captures / "frame.png").write_bytes(b"")

    return captures


def test_delete_experiment_removes_its_folder(tmp_path, monkeypatch):
    current = _experiment(tmp_path, "current").parent
    old = _experiment(tmp_path, "old")
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: current)

    removed = discovery.delete_experiment(old)

    assert removed == old.parent
    assert not removed.exists()
    assert current.is_dir()


def test_delete_experiment_refuses_the_current_experiment(tmp_path, monkeypatch):
    captures = _experiment(tmp_path, "current")
    monkeypatch.setattr(
        discovery, "get_current_experiment_directory", lambda: captures.parent
    )

    with pytest.raises(ValueError, match="current experiment"):
        discovery.delete_experiment(captures)

    assert (captures / "frame.png").is_file()
