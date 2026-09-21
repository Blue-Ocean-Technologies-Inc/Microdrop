# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Contract tests for the camera-controls seam: payload validation and the
publisher/topic pairing. No Qt, no Redis."""

# Third-party imports.
import pytest
from pydantic import ValidationError

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED,
    DEVICE_VIEWER_CAMERA_SET_CONTROLS,
    DEVICE_VIEWER_MEDIA_CAPTURED,
    camera_controls_applied_publisher,
    camera_controls_publisher,
    media_captured_publisher,
)
from device_viewer.models.media import (
    CameraControlsApplied,
    CameraControlsRequest,
    MediaCaptureMessageModel,
)


def test_controls_request_defaults_mean_auto():
    request = CameraControlsRequest()

    assert request.request_id == ""
    assert request.exposure_ms is None
    assert request.focus_distance is None


def test_controls_request_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        CameraControlsRequest(exposure_ms=0)

    with pytest.raises(ValidationError):
        CameraControlsRequest(focus_distance=1.5)


def test_controls_applied_round_trips_json():
    applied = CameraControlsApplied(request_id="r1", ok=True, exposure_ms=50.0)
    again = CameraControlsApplied.model_validate_json(applied.model_dump_json())

    assert again == applied
    assert again.error == ""


def test_media_captured_carries_a_request_id(tmp_path):
    png = tmp_path / "frame.png"
    png.write_bytes(b"")

    model = MediaCaptureMessageModel(path=png, type="image", request_id="r1:0")

    assert model.request_id == "r1:0"
    assert MediaCaptureMessageModel(path=png, type="image").request_id == ""


def test_publishers_bind_topics_to_models():
    assert camera_controls_publisher.topic == DEVICE_VIEWER_CAMERA_SET_CONTROLS
    assert camera_controls_publisher.validator_class is CameraControlsRequest
    assert (
        camera_controls_applied_publisher.topic == DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED
    )
    assert camera_controls_applied_publisher.validator_class is CameraControlsApplied
    assert media_captured_publisher.topic == DEVICE_VIEWER_MEDIA_CAPTURED
    assert media_captured_publisher.validator_class is MediaCaptureMessageModel
