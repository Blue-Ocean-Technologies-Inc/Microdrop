# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Which photos one capture card counts, and what the card says."""

# Microdrop package imports.
from device_viewer.models.capture_session import (
    CaptureSession,
    continues_capture_session,
    format_duration,
    photos_card_text,
)

FOLDER = "C:/experiments/2026_11_25/captures"


def _session(run=None, last_saved_at=100.0):
    return CaptureSession(folder=FOLDER, run=run, count=3, last_saved_at=last_saved_at)


def test_the_first_photo_starts_a_session():
    assert not continues_capture_session(None, FOLDER, None, 100.0)


def test_a_manual_photo_soon_after_joins_the_session():
    assert continues_capture_session(_session(), FOLDER, None, 160.0, window_s=300)


def test_a_manual_photo_after_a_long_pause_starts_a_new_session():
    assert not continues_capture_session(_session(), FOLDER, None, 500.0, window_s=300)


def test_a_photo_in_another_folder_starts_a_new_session():
    assert not continues_capture_session(_session(), "C:/elsewhere", None, 101.0)


def test_every_photo_of_a_protocol_run_joins_its_session():
    session = _session(run=2)

    assert continues_capture_session(session, FOLDER, 2, 9000.0, window_s=300)


def test_a_new_protocol_run_starts_a_new_session():
    assert not continues_capture_session(_session(run=2), FOLDER, 3, 101.0)


def test_a_run_starting_ends_the_manual_session():
    assert not continues_capture_session(_session(), FOLDER, 1, 101.0)


def test_the_card_names_one_photo_or_counts_many():
    assert photos_card_text(1, "free_mode.png") == ("Photo captured", "free_mode.png")
    assert photos_card_text(12, "step_3.png") == (
        "12 photos captured",
        "Latest: step_3.png",
    )


def test_a_duration_reads_as_minutes_and_seconds():
    assert format_duration(5.4) == "0:05"
    assert format_duration(65) == "1:05"
    assert format_duration(3725) == "1:02:05"
