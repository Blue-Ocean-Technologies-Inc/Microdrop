# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Contract tests for the fluorescence capture topics: payload validation,
the publisher/topic pairing, and the backend's camera-reply subscriptions.
Hardware-free, no Redis."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED,
    DEVICE_VIEWER_MEDIA_CAPTURED,
)
from portable_dropbot_controller.consts import (
    ACTOR_TOPIC_DICT,
    FILTER_POSITIONS,
    FLUORESCENCE_CAPTURE,
    FLUORESCENCE_CAPTURE_ABORT,
    FLUORESCENCE_CAPTURE_DONE,
    FLUORESCENCE_CAPTURE_PROGRESS,
    FLUORESCENCE_DEFAULT_EXPOSURE_MS,
    FLUORESCENCE_DEFAULT_LED_PERCENT,
    FLUORESCENCE_EXPOSURE_MS_BOUNDS,
    FLUORESCENCE_LED_PERCENT_BOUNDS,
    PKG,
    FluorescenceCapturedFrame,
    FluorescenceCaptureDone,
    FluorescenceCaptureEntry,
    FluorescenceCaptureProgress,
    FluorescenceCaptureRequest,
    FluorescenceStepCapture,
    FluorescenceStepCaptureEntry,
    fluorescence_capture_done_publisher,
    fluorescence_capture_progress_publisher,
    fluorescence_capture_publisher,
)


def _entry(**overrides):
    fields = {"filter_position": 2, "led_percent": 40, "exposure_ms": 50.0}
    fields.update(overrides)

    return fields


def test_publishers_are_bound_to_their_topics_and_models():
    assert fluorescence_capture_publisher.topic == FLUORESCENCE_CAPTURE
    assert fluorescence_capture_publisher.validator_class is FluorescenceCaptureRequest
    assert fluorescence_capture_progress_publisher.topic == (
        FLUORESCENCE_CAPTURE_PROGRESS
    )
    assert fluorescence_capture_progress_publisher.validator_class is (
        FluorescenceCaptureProgress
    )
    assert fluorescence_capture_done_publisher.topic == FLUORESCENCE_CAPTURE_DONE
    assert fluorescence_capture_done_publisher.validator_class is (
        FluorescenceCaptureDone
    )


def test_topic_strings_are_exact():
    assert FLUORESCENCE_CAPTURE == "portable_dropbot/requests/fluorescence_capture"
    assert FLUORESCENCE_CAPTURE_ABORT == (
        "portable_dropbot/requests/fluorescence_capture_abort"
    )
    assert FLUORESCENCE_CAPTURE_PROGRESS == (
        "portable_dropbot/signals/fluorescence_capture_progress"
    )
    assert FLUORESCENCE_CAPTURE_DONE == (
        "portable_dropbot/signals/fluorescence_capture_done"
    )


def test_backend_listener_subscribes_to_the_camera_replies():
    topics = ACTOR_TOPIC_DICT[f"{PKG}_listener"]

    assert DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED in topics
    assert DEVICE_VIEWER_MEDIA_CAPTURED in topics
    assert "portable_dropbot/requests/#" in topics


def test_defaults_sit_inside_their_bounds():
    low, high = FLUORESCENCE_LED_PERCENT_BOUNDS

    assert low <= FLUORESCENCE_DEFAULT_LED_PERCENT <= high

    low, high = FLUORESCENCE_EXPOSURE_MS_BOUNDS

    assert low <= FLUORESCENCE_DEFAULT_EXPOSURE_MS <= high


def test_entry_defaults_to_auto_focus():
    entry = FluorescenceCaptureEntry(**_entry())

    assert entry.focus_distance is None


@pytest.mark.parametrize("position", FILTER_POSITIONS)
def test_entry_accepts_every_filter_position(position):
    assert FluorescenceCaptureEntry(**_entry(filter_position=position))


@pytest.mark.parametrize(
    "overrides",
    [
        {"filter_position": -1},
        {"filter_position": 5},
        {"led_percent": -1},
        {"led_percent": 101},
        {"exposure_ms": 0.05},
        {"exposure_ms": 10_000.5},
        {"focus_distance": -0.1},
        {"focus_distance": 1.5},
    ],
)
def test_entry_rejects_out_of_range_values(overrides):
    with pytest.raises(ValidationError):
        FluorescenceCaptureEntry(**_entry(**overrides))


def test_request_defaults():
    request = FluorescenceCaptureRequest(entries=[_entry()])

    assert (request.request_id, request.label, request.directory) == ("", "", "")


def test_request_label_is_filename_safe_and_bounded():
    assert FluorescenceCaptureRequest(entries=[], label="step1.2-end").label == (
        "step1.2-end"
    )

    with pytest.raises(ValidationError):
        FluorescenceCaptureRequest(entries=[], label="step 1/2")

    with pytest.raises(ValidationError):
        FluorescenceCaptureRequest(entries=[], label="x" * 65)


def test_step_capture_round_trips_json_with_ticks():
    cell = FluorescenceStepCapture(
        entries=[
            FluorescenceStepCaptureEntry(**_entry(at_start=True)),
            FluorescenceStepCaptureEntry(**_entry(filter_position=4, at_end=True)),
        ]
    )
    again = FluorescenceStepCapture.model_validate_json(cell.model_dump_json())

    assert again == cell
    assert [(e.at_start, e.at_end) for e in again.entries] == [
        (True, False),
        (False, True),
    ]
    assert FluorescenceStepCapture().entries == []


def test_done_defaults_to_no_frames_and_no_error():
    done = FluorescenceCaptureDone(request_id="r1", ok=True)

    assert (done.label, done.directory, done.frames, done.error) == ("", "", [], "")


def test_done_round_trips_a_frame_through_json():
    done = FluorescenceCaptureDone(
        request_id="r1",
        ok=True,
        frames=[FluorescenceCapturedFrame(filter_position=2, path="/tmp/f2.png")],
    )
    again = FluorescenceCaptureDone.model_validate_json(done.model_dump_json())

    assert again.frames == [
        FluorescenceCapturedFrame(filter_position=2, path="/tmp/f2.png")
    ]


def test_progress_requires_its_position_fields():
    with pytest.raises(ValidationError):
        FluorescenceCaptureProgress(request_id="r1", stage="filter")

    progress = FluorescenceCaptureProgress(
        request_id="r1", index=0, total=2, filter_position=3, stage="filter"
    )

    assert progress.detail == ""
