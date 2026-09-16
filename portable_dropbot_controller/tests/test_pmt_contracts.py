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
    PMT_ACQUIRE,
    PMT_ACQUIRE_DONE,
    PMT_ADC_UPDATED,
    PMT_CAPTURE,
    PMT_CAPTURE_DONE,
    PMT_CAPTURE_PROGRESS,
    PMT_GAIN_BOUNDS,
    PMT_RF_OHMS_BOUNDS,
    PMT_SPOT_SLOTS,
    PMT_SPOTS_UPDATED,
    PMT_STREAM_START,
    PMT_STREAM_UPDATED,
    PmtAcquireDone,
    PmtAcquireRequest,
    PmtAdcUpdated,
    PmtCaptureDone,
    PmtCaptureEntry,
    PmtCaptureRequest,
    PmtSpotsUpdated,
    PmtStreamRequest,
    PmtStreamUpdated,
    pmt_acquire_done_publisher,
    pmt_acquire_publisher,
    pmt_adc_updated_publisher,
    pmt_capture_done_publisher,
    pmt_capture_progress_publisher,
    pmt_capture_publisher,
    pmt_spots_updated_publisher,
    pmt_stream_start_publisher,
    pmt_stream_updated_publisher,
)


def test_publishers_are_bound_to_their_topics_and_models():
    assert pmt_spots_updated_publisher.topic == PMT_SPOTS_UPDATED
    assert pmt_spots_updated_publisher.validator_class is PmtSpotsUpdated
    assert pmt_capture_publisher.topic == PMT_CAPTURE
    assert pmt_capture_publisher.validator_class is PmtCaptureRequest
    assert pmt_capture_progress_publisher.topic == PMT_CAPTURE_PROGRESS
    assert pmt_capture_done_publisher.topic == PMT_CAPTURE_DONE
    assert pmt_capture_done_publisher.validator_class is PmtCaptureDone
    assert pmt_stream_start_publisher.topic == PMT_STREAM_START
    assert pmt_stream_start_publisher.validator_class is PmtStreamRequest
    assert pmt_stream_updated_publisher.topic == PMT_STREAM_UPDATED
    assert pmt_stream_updated_publisher.validator_class is PmtStreamUpdated
    assert pmt_adc_updated_publisher.topic == PMT_ADC_UPDATED
    assert pmt_adc_updated_publisher.validator_class is PmtAdcUpdated
    assert pmt_acquire_publisher.topic == PMT_ACQUIRE
    assert pmt_acquire_publisher.validator_class is PmtAcquireRequest
    assert pmt_acquire_done_publisher.topic == PMT_ACQUIRE_DONE
    assert pmt_acquire_done_publisher.validator_class is PmtAcquireDone


def test_capture_request_carries_stream_settings():
    request = PmtCaptureRequest(
        entries=[PmtCaptureEntry(slot=1, gain=10, exposure_s=1.0)]
    )
    assert (request.avg, request.osr, request.rf_ohms) == (16, 6, 499_000.0)


def test_stream_request_rejects_out_of_range_rf_ohms():
    PmtStreamRequest(gain=10, rf_ohms=PMT_RF_OHMS_BOUNDS[1])
    with pytest.raises(ValidationError):
        PmtStreamRequest(gain=10, rf_ohms=PMT_RF_OHMS_BOUNDS[1] + 1)


def test_acquire_request_defaults_and_old_payload_still_validates():
    # The pre-#601 single-acquire payload had only "gain"; rf_ohms's
    # default keeps it valid so an unmigrated caller still works.
    request = PmtAcquireRequest.model_validate_json('{"gain": 50}')
    assert request.gain == 50
    assert request.rf_ohms == pytest.approx(499_000.0)


def test_acquire_done_defaults():
    done = PmtAcquireDone(ok=False, gain=50)
    assert done.n_samples == 0
    assert done.error == ""


def test_stream_updated_defaults_to_not_streaming_with_no_samples():
    updated = PmtStreamUpdated(streaming=False)
    assert updated.samples == []
    assert updated.packets == 0


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
    assert done.request_id == ""
    assert done.label == ""


def test_capture_request_defaults_request_id_label_stop_live_stream():
    request = PmtCaptureRequest(
        entries=[PmtCaptureEntry(slot=1, gain=10, exposure_s=1.0)]
    )
    assert request.request_id == ""
    assert request.label == ""
    assert request.stop_live_stream is False


def test_capture_request_rejects_invalid_label():
    PmtCaptureRequest(
        entries=[PmtCaptureEntry(slot=1, gain=10, exposure_s=1.0)],
        label="step1.2-end",
    )
    with pytest.raises(ValidationError):
        PmtCaptureRequest(
            entries=[PmtCaptureEntry(slot=1, gain=10, exposure_s=1.0)],
            label="bad label!",
        )
    with pytest.raises(ValidationError):
        PmtCaptureRequest(
            entries=[PmtCaptureEntry(slot=1, gain=10, exposure_s=1.0)],
            label="x" * 65,
        )


def test_capture_done_echoes_request_id_and_label():
    done = PmtCaptureDone(
        ok=True,
        aborted=False,
        directory="d",
        results=[],
        request_id="row-uuid:end",
        label="step1.2-end",
    )
    assert done.request_id == "row-uuid:end"
    assert done.label == "step1.2-end"
