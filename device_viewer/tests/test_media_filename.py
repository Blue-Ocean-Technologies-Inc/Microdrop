# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Capture/recording file names: step + id, id only, description only
(a requester's own tag), and free mode. No Qt."""

# Microdrop package imports.
from device_viewer.utils.camera import media_filename

STAMP = "2026-09-21T10-00-00"


def test_step_description_and_id():
    assert (
        media_filename("Wash step", "7", timestamp=STAMP) == f"Wash_step_7_{STAMP}.png"
    )


def test_id_only():
    assert media_filename(None, "7", timestamp=STAMP) == f"step_7_{STAMP}.png"


def test_description_only_keeps_the_description():
    assert (
        media_filename("flu_step12-end_f2", None, timestamp=STAMP)
        == f"flu_step12-end_f2_{STAMP}.png"
    )


def test_description_is_cleaned_of_unsafe_characters():
    assert (
        media_filename("flu_step1.2/end", None, timestamp=STAMP)
        == f"flu_step12end_{STAMP}.png"
    )


def test_free_mode_and_extension():
    assert media_filename(timestamp=STAMP, file_extension=".mp4") == (
        f"free_mode_{STAMP}.mp4"
    )
