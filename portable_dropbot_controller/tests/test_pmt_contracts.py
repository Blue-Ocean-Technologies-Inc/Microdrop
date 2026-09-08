# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Contract tests for the PMT capture topics: payload validation and the
publisher/topic pairing. Hardware-free, no Redis."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    DEFAULT_PMT_EXPOSURE_S,
    PMT_CAPTURE,
    PMT_CAPTURE_DONE,
    PMT_CAPTURE_PROGRESS,
    PMT_GAIN_BOUNDS,
    PMT_SPOT_SLOTS,
    PMT_SPOTS_UPDATED,
    PmtCaptureDone,
    PmtCaptureEntry,
    PmtCaptureRequest,
    PmtSpotsUpdated,
    pmt_capture_done_publisher,
    pmt_capture_progress_publisher,
    pmt_capture_publisher,
    pmt_spots_updated_publisher,
)


def test_publishers_are_bound_to_their_topics_and_models():
    assert pmt_spots_updated_publisher.topic == PMT_SPOTS_UPDATED
    assert pmt_spots_updated_publisher.validator_class is PmtSpotsUpdated
    assert pmt_capture_publisher.topic == PMT_CAPTURE
    assert pmt_capture_publisher.validator_class is PmtCaptureRequest
    assert pmt_capture_progress_publisher.topic == PMT_CAPTURE_PROGRESS
    assert pmt_capture_done_publisher.topic == PMT_CAPTURE_DONE
    assert pmt_capture_done_publisher.validator_class is PmtCaptureDone


def test_capture_entry_rejects_out_of_range_values():
    PmtCaptureEntry(slot=1, gain=PMT_GAIN_BOUNDS[1], exposure_s=DEFAULT_PMT_EXPOSURE_S)
    with pytest.raises(ValidationError):
        PmtCaptureEntry(slot=0, gain=10, exposure_s=1.0)
    with pytest.raises(ValidationError):
        PmtCaptureEntry(slot=PMT_SPOT_SLOTS + 1, gain=10, exposure_s=1.0)
    with pytest.raises(ValidationError):
        PmtCaptureEntry(slot=1, gain=PMT_GAIN_BOUNDS[1] + 1, exposure_s=1.0)
    with pytest.raises(ValidationError):
        PmtCaptureEntry(slot=1, gain=10, exposure_s=0.0)


def test_spots_updated_round_trips_through_json():
    payload = {
        "spots": [{"slot": 2, "position_um": 24500}, {"slot": 4, "position_um": 61000}]
    }
    parsed = PmtSpotsUpdated.model_validate_json(
        PmtSpotsUpdated.model_validate(payload).model_dump_json()
    )
    assert [(s.slot, s.position_um) for s in parsed.spots] == [(2, 24500), (4, 61000)]


def test_capture_done_defaults():
    done = PmtCaptureDone(ok=False, aborted=False, directory="", results=[])
    assert done.error == ""
