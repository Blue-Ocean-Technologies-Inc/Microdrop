# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""CaptureReadiness: files still being written stay out of discovery."""

# Standard library imports.
import os
import time

# Microdrop package imports.
from image_viewer.discovery import (
    NO_IMAGE_GROUP,
    UNGROUPED_BURST,
    CaptureReadiness,
    discover_image_groups,
)

#: The settle time the tests run with, and a clock reading well past it.
SETTLE_SECONDS = 2.0
MTIME = 1_000.0


def _write(path, payload, mtime=MTIME):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    os.utime(path, (mtime, mtime))

    return path


def test_settled_file_is_ready_on_first_sight(tmp_path):
    path = _write(tmp_path / "old.png", b"done")
    readiness = CaptureReadiness(settle_seconds=SETTLE_SECONDS)

    assert readiness.ready_paths([path], now=MTIME + 60) == [path]


def test_freshly_modified_file_waits_for_the_settle_time(tmp_path):
    path = _write(tmp_path / "fresh.png", b"part")
    readiness = CaptureReadiness(settle_seconds=SETTLE_SECONDS)

    assert readiness.ready_paths([path], now=MTIME + 0.5) == []
    assert readiness.ready_paths([path], now=MTIME + SETTLE_SECONDS) == [path]


def test_file_that_changed_since_the_previous_scan_waits(tmp_path):
    path = _write(tmp_path / "growing.png", b"part")
    readiness = CaptureReadiness(settle_seconds=SETTLE_SECONDS)
    readiness.ready_paths([path], now=MTIME + 60)

    # Grew between scans while keeping an old mtime: still held once.
    _write(path, b"part and more")

    assert readiness.ready_paths([path], now=MTIME + 60) == []
    assert readiness.ready_paths([path], now=MTIME + 60) == [path]


def test_file_reported_complete_skips_the_wait(tmp_path):
    path = _write(tmp_path / "snap.png", b"done")
    readiness = CaptureReadiness(settle_seconds=SETTLE_SECONDS)
    readiness.mark_complete(str(path))

    assert readiness.ready_paths([path], now=MTIME) == [path]


def test_image_groups_leave_out_files_still_being_written(tmp_path):
    captures = tmp_path / "captures"
    settled = _write(captures / "settled.png", b"done")
    _write(captures / "writing.png", b"part", mtime=time.time())
    readiness = CaptureReadiness(settle_seconds=SETTLE_SECONDS)

    groups = discover_image_groups(captures, readiness)

    assert groups == {NO_IMAGE_GROUP: [(UNGROUPED_BURST, [settled])]}
