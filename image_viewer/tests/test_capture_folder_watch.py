# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The single-walk discovery and CaptureFolderWatch's skip-when-unchanged."""

# Standard library imports.
import os

# Microdrop package imports.
from image_viewer.discovery import (
    CaptureFolderWatch,
    discover_captures,
    discover_image_groups,
)


def _make(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    os.utime(path, (mtime, mtime))

    return path


def test_one_walk_finds_every_pattern_oldest_first(tmp_path):
    tif = _make(tmp_path / "session" / "16bit_raw" / "a.tif", 3_000)
    png = _make(tmp_path / "b.png", 1_000)
    jpeg = _make(tmp_path / "session" / "c.jpeg", 2_000)
    _make(tmp_path / "notes.txt", 500)

    assert discover_captures(tmp_path) == [png, jpeg, tif]


def test_unchanged_tree_reuses_the_last_result(tmp_path):
    _make(tmp_path / "Mix_1" / "16bit_raw" / "a_raw.png", 1_000)
    watch = CaptureFolderWatch()

    first = watch.image_groups(tmp_path)

    assert watch.image_groups(tmp_path) is first
    assert first == discover_image_groups(tmp_path)


def test_new_file_in_a_subfolder_is_discovered(tmp_path):
    raw_dir = tmp_path / "Mix_1" / "16bit_raw"
    _make(raw_dir / "a_raw.png", 1_000)
    watch = CaptureFolderWatch()
    watch.image_groups(tmp_path)

    added = _make(raw_dir / "b_raw.png", 2_000)
    # Pin the folder's mtime forward: some filesystems tick coarsely
    # enough that two writes within a test share one mtime.
    os.utime(raw_dir, (5_000, 5_000))

    assert watch.image_groups(tmp_path)["16bit_raw"][0][1][-1] == added


def test_full_walk_interval_catches_unannounced_changes(tmp_path):
    raw_dir = tmp_path / "Mix_1" / "16bit_raw"
    _make(raw_dir / "a_raw.png", 1_000)
    watch = CaptureFolderWatch(full_walk_interval_s=0.0)
    first = watch.image_groups(tmp_path)

    assert watch.image_groups(tmp_path) is not first
