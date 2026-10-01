# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""capture_timestamp: filename UTC stamp preferred, mtime fallback."""

# Standard library imports.
import calendar
import time

# Microdrop package imports.
from image_viewer.discovery import capture_timestamp


def test_timestamp_parsed_from_filename(tmp_path):
    path = tmp_path / "gfp_Green_540_nm_2_2026_07_20-17_46_24_raw.png"
    path.write_bytes(b"")
    expected = calendar.timegm(
        time.strptime("2026_07_20-17_46_24", "%Y_%m_%d-%H_%M_%S")
    )
    assert capture_timestamp(path) == expected


def test_falls_back_to_mtime_without_stamp(tmp_path):
    path = tmp_path / "legacy_capture_raw.png"
    path.write_bytes(b"")
    assert capture_timestamp(path) == path.stat().st_mtime


def test_missing_file_without_stamp_is_zero(tmp_path):
    assert capture_timestamp(tmp_path / "nope.png") == 0.0
