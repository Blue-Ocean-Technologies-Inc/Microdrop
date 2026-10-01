# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""CameraController against a stub camera and stub preferences: source and
format selection, media paths, capture/recording bookkeeping, and the
set_controls handshake with its v4l2 fallbacks. No Qt camera, no Redis."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences, PreferencesHelper
from traits.api import Bool, Float, HasTraits, Str, provides

# Microdrop package imports.
from device_viewer.controllers import camera_controller
from device_viewer.controllers.camera_controller import CameraController
from device_viewer.interfaces.i_camera_device import ICameraDevice
from device_viewer.models.camera import CameraModel
from device_viewer.models.media import MediaType


class StubPreferences(PreferencesHelper):
    preferences_path = "device_viewer.camera_test"

    selected_camera = Str()
    resolution = Str()
    camera_state = Bool(False)
    preferred_video_format = Str("NV12")
    strict_video_format = Bool(False)

    def recording_file_extension(self):
        return ".mp4"


@provides(ICameraDevice)
class StubCamera(HasTraits):
    bound = Bool(True)
    active = Bool(False)
    manual_exposure_supported = Bool(True)
    manual_focus_supported = Bool(True)
    manual_exposure = Bool(False)
    manual_focus = Bool(False)
    exposure_ms = Float(0.0)
    manual_exposure_ms = Float(0.0)
    distance = Float(0.0)

    def has_camera(self):
        return self.bound

    def is_active(self):
        return self.active

    def supports_manual_exposure(self):
        return self.manual_exposure_supported

    def set_auto_exposure(self):
        self.manual_exposure = False

    def set_manual_exposure(self, exposure_ms):
        self.manual_exposure = True
        self.manual_exposure_ms = exposure_ms

    def exposure_is_manual(self):
        return self.manual_exposure

    def exposure_time_ms(self):
        return self.exposure_ms

    def manual_exposure_time_ms(self):
        return self.manual_exposure_ms

    def supports_manual_focus(self):
        return self.manual_focus_supported

    def set_auto_focus(self):
        self.manual_focus = False

    def set_manual_focus(self, focus_distance):
        self.manual_focus = True
        self.distance = focus_distance

    def focus_is_manual(self):
        return self.manual_focus

    def focus_distance(self):
        return self.distance


class Recorder:
    """Stands in for a publisher or an actor; records its calls."""

    def __init__(self):
        self.calls = []

    def publish(self, message=None, **kwargs):
        self.calls.append(message if message is not None else kwargs)

    def __call__(self, *args):
        self.calls.append(args)


class RecordingStateStub(HasTraits):
    recording = Bool(False)


class CaptureEventStub(HasTraits):
    captured = Str()


@pytest.fixture
def published(monkeypatch):
    applied = Recorder()
    monkeypatch.setattr(camera_controller, "camera_controls_applied_publisher", applied)

    return applied.calls


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setattr(
        camera_controller, "get_current_experiment_directory", lambda: tmp_path
    )
    camera = StubCamera()

    def turn_camera_on():
        camera.active = True

    return CameraController(
        model=CameraModel(),
        preferences=StubPreferences(preferences=Preferences()),
        camera=camera,
        turn_camera_on=turn_camera_on,
    )


# --------------------------------------------------------------------------- #
# Source and format selection                                                  #
# --------------------------------------------------------------------------- #
def test_preferred_camera_is_selected(controller):
    controller.preferences.selected_camera = "Cam B"

    assert controller.choose_camera_index(["Cam A", "Cam B"], ["ASI"]) == 1


def test_preferred_provider_follows_the_cameras(controller):
    controller.preferences.selected_camera = "ASI"

    assert controller.choose_camera_index(["Cam A", "Cam B"], ["ASI"]) == 2


def test_current_label_is_used_without_a_preference(controller):
    assert controller.choose_camera_index(["Cam A", "Cam B"], [], "Cam B") == 1


def test_missing_camera_falls_back_and_drops_its_resolution(controller):
    controller.preferences.selected_camera = "Gone"
    controller.preferences.resolution = "1920x1080 [NV12] @ 30 fps"

    assert controller.choose_camera_index(["Cam A"], []) == 0
    assert controller.preferences.resolution == ""


def test_select_source_remembers_only_named_sources(controller):
    controller.select_source(
        "/dev/video2", remembered_as="DH Camera", v4l2_device_path="/dev/video2"
    )

    assert controller.preferences.selected_camera == "DH Camera"
    assert controller.model.v4l2_device_path == "/dev/video2"

    controller.select_source("")

    assert controller.preferences.selected_camera == "DH Camera"
    assert controller.model.selected_camera == ""
    assert controller.model.v4l2_device_path is None


def test_rank_formats_keeps_the_best_format_per_resolution(controller):
    formats = [
        (640, 480, "Format_YUYV", 30.0),
        (1920, 1080, "Format_YUYV", 5.0),
        (1920, 1080, "Format_NV12", 30.0),
        (640, 480, "Format_NV12", 30.0),
    ]

    assert controller.rank_formats(formats) == [2, 3]


def test_rank_formats_strict_mode_drops_other_pixel_formats(controller):
    controller.preferences.strict_video_format = True
    formats = [(1920, 1080, "Format_YUYV", 30.0), (640, 480, "Format_NV12", 30.0)]

    assert controller.rank_formats(formats) == [1]
    assert controller.rank_formats(formats, allow_strict_mode=False) == [0, 1]


def test_saved_resolution_is_restored_else_middle(controller):
    labels = ["a", "b", "c", "d"]
    controller.preferences.resolution = "c"

    assert controller.choose_resolution_index(labels) == 2

    controller.preferences.resolution = "gone"

    assert controller.choose_resolution_index(labels) == 2
    assert controller.choose_resolution_index(labels[:3]) == 1


def test_select_resolution_updates_preferences_and_model(controller):
    controller.select_resolution("1280x720 [NV12] @ 30 fps", 1280, 720, 30.0)

    assert controller.preferences.resolution == "1280x720 [NV12] @ 30 fps"
    assert controller.model.resolution == (1280, 720)
    assert controller.model.frame_rate == 30.0


def test_camera_state_is_remembered(controller):
    controller.model.camera_active = True

    assert controller.preferences.camera_state is True


# --------------------------------------------------------------------------- #
# Capture and recording                                                        #
# --------------------------------------------------------------------------- #
def test_capture_target_for_a_protocol_step(controller, tmp_path):
    save_path, show_status_message, request_id = controller.capture_target(
        {
            "directory": str(tmp_path / "run"),
            "step_description": "Wash step",
            "step_id": "7",
            "show_status_message": False,
            "request_id": 42,
        }
    )

    assert save_path.parent == tmp_path / "run" / "captures"
    assert save_path.name.startswith("Wash_step_7_")
    assert save_path.suffix == ".png"
    assert show_status_message is False
    assert request_id == "42"


def test_capture_target_for_the_button(controller, tmp_path):
    save_path, show_status_message, request_id = controller.capture_target(None)

    assert save_path.parent == tmp_path / "captures"
    assert save_path.name.startswith("free_mode_")
    assert show_status_message is True
    assert request_id == ""


def test_image_saved_caches_and_announces_the_capture(controller, monkeypatch):
    cache = Recorder()
    event_model = CaptureEventStub()
    monkeypatch.setattr(camera_controller, "_cache_media_capture", cache)
    monkeypatch.setattr(camera_controller, "media_capture_event_model", event_model)

    controller.image_saved("C:/captures/frame.png", "r1:0")

    assert cache.calls == [(MediaType.IMAGE, "C:/captures/frame.png", "r1:0")]
    assert event_model.captured == "C:/captures/frame.png"
    assert controller.model.last_capture_path == "C:/captures/frame.png"


def test_prepare_recording_creates_the_folder(controller, tmp_path):
    path = controller.prepare_recording(
        str(tmp_path), "Mix", "3", show_status_message=False, camera_was_on=False
    )

    assert Path(path).parent == tmp_path / "recordings"
    assert Path(path).parent.is_dir()
    assert Path(path).suffix == ".mp4"
    assert controller.model.recording.output_path == path
    assert controller.model.recording.show_status_message is False


def test_recording_state_is_published_and_camera_restored(controller, monkeypatch):
    publisher = Recorder()
    state = RecordingStateStub()
    monkeypatch.setattr(
        camera_controller, "device_viewer_recording_state_publisher", publisher
    )
    monkeypatch.setattr(camera_controller, "recording_state_model", state)
    controller.model.recording.camera_was_on = False

    controller.recording_started()

    assert state.recording is True
    assert controller.model.recording.active is True

    assert controller.recording_ended() is True
    assert state.recording is False
    assert publisher.calls == [{"state": True}, {"state": False}]


def test_recording_needs_the_minimum_frame_rate(controller):
    assert controller.recording_frame_rate_supported(30.0)
    assert not controller.recording_frame_rate_supported(5.0)


# --------------------------------------------------------------------------- #
# set_controls -> controls_applied                                             #
# --------------------------------------------------------------------------- #
def test_no_camera_answers_not_ok(controller, published):
    controller.camera.bound = False

    controller.apply_camera_controls({"request_id": "r1"})

    assert published == [
        {"request_id": "r1", "ok": False, "error": "no QCamera is selected"}
    ]


def test_provider_feed_answers_not_ok(controller, published):
    controller.model.provider_feed_active = True

    controller.apply_camera_controls({"request_id": "r1"})

    assert published[0]["ok"] is False


def test_manual_controls_turn_the_camera_on_and_read_back(controller, published):
    controller.apply_camera_controls(
        {"request_id": "r2", "exposure_ms": 25.0, "focus_distance": 0.5}
    )

    assert controller.camera.active is True
    assert published == [
        {
            "request_id": "r2",
            "ok": True,
            "exposure_ms": 25.0,
            "exposure_auto": False,
            "focus_distance": 0.5,
        }
    ]


def test_auto_controls_read_back_auto_pick(controller, published):
    controller.camera.exposure_ms = 12.0

    controller.apply_camera_controls({"request_id": "r3"})

    assert published[0]["exposure_auto"] is True
    assert published[0]["exposure_ms"] == 12.0
    assert published[0]["focus_distance"] is None


def test_hold_auto_exposure_fails_when_unreported(controller, published):
    controller.apply_camera_controls({"request_id": "r4", "hold_auto_exposure": True})

    assert published[0]["ok"] is False
    assert "does not report" in published[0]["error"]


def test_no_manual_exposure_answers_not_ok(controller, published):
    controller.camera.manual_exposure_supported = False

    controller.apply_camera_controls({"request_id": "r5", "exposure_ms": 10.0})

    assert published[0] == {
        "request_id": "r5",
        "ok": False,
        "error": "this camera has no manual exposure",
    }


def test_v4l2_fallbacks_drive_focus_and_auto_exposure(
    controller, published, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        camera_controller,
        "set_v4l2_controls",
        lambda path, **controls: calls.append((path, controls)) or True,
    )
    monkeypatch.setattr(
        camera_controller, "get_v4l2_control_range", lambda path, name: (0, 1000)
    )
    monkeypatch.setattr(camera_controller, "get_v4l2_control", lambda path, name: 250)
    controller.camera.manual_focus_supported = False
    controller.model.v4l2_device_path = "/dev/video2"

    controller.apply_camera_controls({"request_id": "r6", "focus_distance": 0.25})

    assert calls == [
        ("/dev/video2", {"auto_exposure": 3}),
        ("/dev/video2", {"focus_automatic_continuous": 0, "focus_absolute": 250}),
    ]
    assert published[0]["ok"] is True
    assert published[0]["exposure_auto"] is True
    # The fallback's auto does not report its pick.
    assert published[0]["exposure_ms"] is None
    assert published[0]["focus_distance"] == 0.25
    assert controller.model.v4l2_focus_path == "/dev/video2"
    assert controller.model.v4l2_auto_exposure_path == "/dev/video2"


def test_no_manual_focus_without_v4l2_answers_not_ok(controller, published):
    controller.camera.manual_focus_supported = False

    controller.apply_camera_controls({"request_id": "r7", "focus_distance": 0.5})

    assert published[0]["ok"] is False
    assert published[0]["error"] == "this camera has no manual focus"
