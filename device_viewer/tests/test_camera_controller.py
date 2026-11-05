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
set_controls handshake with its v4l2 fallbacks, and the select_source
reply plus camera-state publishing. No Qt camera, no Redis."""

# Standard library imports.
import math
from pathlib import Path

# Third-party imports.
import numpy as np
import pytest

# Enthought library imports.
from apptools.preferences.api import Preferences, PreferencesHelper
from pyface.qt.QtWidgets import QApplication
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


#: ``v4l2-ctl --list-ctrls`` of a UVC camera with continuous auto focus on.
UVC_FOCUS_CONTROLS = (
    "focus_absolute 0x009a090a (int) : min=0 max=1000 step=1 value=250\n"
    "focus_automatic_continuous 0x009a090c (bool) : default=1 value=1\n"
)

#: ``v4l2-ctl --list-ctrls`` of a Pi CSI camera's lens sub-device (dw9807):
#: focus_absolute only, no auto focus.
LENS_FOCUS_CONTROLS = (
    "focus_absolute 0x009a090a (int) : min=0 max=1023 step=1 default=480 "
    "value=455 flags=has-min-max\n"
)

#: The imx708 lens's calibration from its tuning file: 0 dioptres
#: (infinity) at 420, 35 dioptres (nearest) at 920.
IMX708_LENS_MAP = ((0.0, 420), (35.0, 920))


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


@pytest.fixture(autouse=True)
def states_published(monkeypatch):
    """CameraState payloads, one per selection or on/off change."""
    states = Recorder()
    monkeypatch.setattr(camera_controller, "camera_state_publisher", states)

    return states.calls


@pytest.fixture
def replies(monkeypatch):
    """CameraSourceSelected replies to select_source requests."""
    selected = Recorder()
    monkeypatch.setattr(camera_controller, "camera_source_selected_publisher", selected)

    return selected.calls


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setattr(
        camera_controller, "get_current_experiment_directory", lambda: tmp_path
    )
    monkeypatch.setattr(camera_controller, "is_rpi", lambda: False)
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


def test_rank_formats_never_offers_yv12_on_a_pi(controller, monkeypatch):
    monkeypatch.setattr(camera_controller, "is_rpi", lambda: True)
    formats = [
        (1920, 1080, "PixelFormat.Format_YV12", 30.0),
        (1920, 1080, "PixelFormat.Format_Y8", 30.0),
        (640, 480, "Format_YV12", 30.0),
    ]

    assert controller.rank_formats(formats) == [1]


def test_libcamera_prefers_nv12_without_strict_mode(controller):
    controller.preferences.preferred_video_format = "JPEG"
    controller.preferences.strict_video_format = True
    formats = [
        (1920, 1080, "PixelFormat.Format_Y8", 30.0),
        (1920, 1080, "PixelFormat.Format_NV12", 30.0),
        (640, 480, "PixelFormat.Format_YUYV", 30.0),
    ]

    assert not controller.strict_format_mode(libcamera=True)
    assert controller.rank_formats(formats, libcamera=True) == [1, 2]


def test_rank_formats_falls_back_in_a_fixed_pixel_format_order(controller):
    controller.preferences.preferred_video_format = "JPEG"
    formats = [
        (1920, 1080, "Format_Y8", 30.0),
        (1920, 1080, "Format_BGRX8888", 30.0),
        (1920, 1080, "Format_YUYV", 30.0),
        (1920, 1080, "Format_YUV420P", 30.0),
        (640, 480, "Format_Y16", 30.0),
        (640, 480, "Format_RGBX8888", 30.0),
    ]

    assert controller.rank_formats(formats) == [3, 5]


def test_rank_formats_prefers_frame_rate_over_fallback_order(controller):
    controller.preferences.preferred_video_format = "NV12"
    formats = [(1920, 1080, "Format_YUYV", 5.0), (1920, 1080, "Format_Jpeg", 30.0)]

    assert controller.rank_formats(formats) == [1]


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
# Camera state and select_source requests                                     #
# --------------------------------------------------------------------------- #
DROPDOWN = ["Cam A", "ASI: ZWO ASI183MM", "<No Camera>"]


def _select_request(label, active=None, request_id="r1"):
    return {"label": label, "active": active, "request_id": request_id}


def test_camera_state_is_published_on_every_change(controller, states_published):
    controller.select_source("Cam A", remembered_as="Cam A")
    controller.model.camera_active = True
    controller.model.camera_leased = True
    controller.select_source("")

    assert states_published == [
        {"selected_camera": "Cam A", "active": False, "leased": False},
        {"selected_camera": "Cam A", "active": True, "leased": False},
        {"selected_camera": "Cam A", "active": True, "leased": True},
        {"selected_camera": "", "active": True, "leased": True},
    ]


@pytest.mark.parametrize(
    "label, index",
    [
        ("ASI: ZWO ASI183MM", 1),
        ("asi: zwo asi183mm", 1),
        ("", 2),
        ("<No Camera>", 2),
        ("Cam Z", None),
    ],
)
def test_source_label_matching(label, index):
    assert CameraController.match_source_label(DROPDOWN, label) == index


def test_exact_label_wins_over_a_case_insensitive_one():
    assert CameraController.match_source_label(["cam a", "Cam A"], "Cam A") == 1


def test_unknown_label_is_answered_not_ok(controller, replies, states_published):
    index = controller.find_requested_source(_select_request("Cam Z", True), DROPDOWN)

    assert index is None
    assert replies == [
        {
            "request_id": "r1",
            "label": "Cam Z",
            "ok": False,
            "error": "unknown camera source 'Cam Z' "
            "(available: Cam A, ASI: ZWO ASI183MM, <No Camera>)",
            "active": False,
        }
    ]
    assert states_published[-1] == {
        "selected_camera": "",
        "active": False,
        "leased": False,
    }


def test_selected_source_is_answered_ok_then_state(
    controller, replies, states_published
):
    controller.select_source("ASI: ZWO ASI183MM", provider=True)
    controller.model.camera_active = True
    states_published.clear()

    controller.source_selected(_select_request("asi: zwo asi183mm", True, "r2"))

    assert replies == [
        {
            "request_id": "r2",
            "label": "ASI: ZWO ASI183MM",
            "ok": True,
            "error": "",
            "active": True,
        }
    ]
    assert states_published == [
        {"selected_camera": "ASI: ZWO ASI183MM", "active": True, "leased": False}
    ]


def test_camera_asked_on_but_off_is_answered_not_ok(controller, replies):
    controller.select_source("ASI: ZWO ASI183MM", provider=True)

    controller.source_selected(_select_request("ASI: ZWO ASI183MM", True))

    assert replies[0]["ok"] is False
    assert replies[0]["error"] == (
        "camera source 'ASI: ZWO ASI183MM' failed to start (see the log)"
    )


def test_feed_open_failure_is_answered_with_its_message(controller, replies):
    controller.select_source("ASI: ZWO ASI183MM", provider=True)
    controller.model.feed_error = "ASI camera not found"

    controller.source_selected(_select_request("ASI: ZWO ASI183MM", True))

    assert replies[0]["ok"] is False
    assert replies[0]["error"] == (
        "camera source 'ASI: ZWO ASI183MM' failed to start: ASI camera not found"
    )
    assert replies[0]["active"] is False


def test_no_camera_asked_on_is_answered_not_ok(controller, replies):
    controller.source_selected(_select_request("", True))

    assert replies[0]["ok"] is False
    assert replies[0]["error"] == "no camera source is selected"


def test_switch_error_is_passed_through(controller, replies):
    controller.select_source("Cam A")

    controller.source_selected(_select_request("Cam A", None), "boom")

    assert replies[0]["ok"] is False
    assert replies[0]["error"] == "boom"
    assert replies[0]["label"] == "Cam A"


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


@pytest.fixture
def v4l2_focus(monkeypatch):
    """Fake v4l2 focus device: ``controls`` is its ``--list-ctrls`` text,
    ``position`` its focus_absolute; writes are recorded in ``calls``."""
    device = {"controls": UVC_FOCUS_CONTROLS, "position": 250, "calls": []}
    monkeypatch.setattr(
        camera_controller, "list_v4l2_controls", lambda path: device["controls"]
    )
    monkeypatch.setattr(
        camera_controller,
        "set_v4l2_controls",
        lambda path, **controls: device["calls"].append((path, controls)) or True,
    )
    monkeypatch.setattr(
        camera_controller, "get_v4l2_control", lambda path, name: device["position"]
    )

    return device


def test_v4l2_fallbacks_drive_focus_and_auto_exposure(
    controller, published, v4l2_focus
):
    controller.camera.manual_focus_supported = False
    controller.model.v4l2_device_path = "/dev/video2"
    controller.model.v4l2_focus_device_path = "/dev/video2"

    controller.apply_camera_controls({"request_id": "r6", "focus_distance": 0.25})

    assert v4l2_focus["calls"] == [
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


def test_lens_without_auto_focus_writes_only_focus_absolute(
    controller, published, v4l2_focus
):
    v4l2_focus["controls"] = LENS_FOCUS_CONTROLS
    controller.camera.manual_focus_supported = False
    controller.model.v4l2_focus_device_path = "/dev/v4l-subdev3"

    assert controller.model.v4l2_focus_span == (0, 1023)
    assert not controller.model.v4l2_focus_has_auto

    controller.apply_camera_controls({"request_id": "r8", "focus_distance": 0.5})

    assert v4l2_focus["calls"] == [("/dev/v4l-subdev3", {"focus_absolute": 512})]
    assert controller.model.v4l2_focus_path == "/dev/v4l-subdev3"

    # Auto only releases the lens: there is no auto focus to write.
    controller.apply_camera_controls({"request_id": "r9"})

    assert len(v4l2_focus["calls"]) == 1
    assert controller.model.v4l2_focus_path is None
    assert published[1]["ok"] is True
    assert published[1]["focus_distance"] is None


def test_camera_left_on_manual_focus_is_read_back_at_selection(controller, v4l2_focus):
    v4l2_focus["controls"] = UVC_FOCUS_CONTROLS.replace("value=1", "value=0")
    controller.camera.manual_focus_supported = False

    controller.select_source("DH Camera", v4l2_focus_device_path="/dev/video8")

    assert controller.model.v4l2_focus_path == "/dev/video8"
    assert not controller.model.focus.auto
    assert controller.model.focus.distance == 0.25


# --------------------------------------------------------------------------- #
# Focus row (CameraFocusModel)                                                 #
# --------------------------------------------------------------------------- #
def test_focus_row_shows_lens_position_without_auto(controller, v4l2_focus):
    v4l2_focus["controls"] = LENS_FOCUS_CONTROLS
    v4l2_focus["position"] = 455
    controller.camera.manual_focus_supported = False

    controller.select_source("imx708", v4l2_focus_device_path="/dev/v4l-subdev3")
    focus = controller.model.focus

    assert focus.available
    assert not focus.auto_available
    assert not focus.auto
    assert focus.raw_position == 455
    assert focus.distance == pytest.approx(455 / 1023)


def test_focus_row_edits_drive_uvc_focus_and_auto(controller, v4l2_focus):
    controller.camera.manual_focus_supported = False
    controller.select_source("DH Camera", v4l2_focus_device_path="/dev/video8")
    focus = controller.model.focus

    assert focus.available and focus.auto_available and focus.auto

    controller.set_focus(0.25)

    assert v4l2_focus["calls"][-1] == (
        "/dev/video8",
        {"focus_automatic_continuous": 0, "focus_absolute": 250},
    )
    assert not focus.auto
    assert focus.raw_position == 250

    controller.set_focus(None)

    assert v4l2_focus["calls"][-1] == (
        "/dev/video8",
        {"focus_automatic_continuous": 1},
    )
    assert focus.auto


def test_focus_row_follows_qt_focus(controller):
    controller.select_source("Cam A")
    focus = controller.model.focus

    assert focus.available and focus.auto_available and focus.auto
    assert focus.raw_position is None

    controller.set_focus(0.75)

    assert not focus.auto
    assert focus.distance == 0.75


def test_focus_row_unavailable_without_a_focusable_camera(controller):
    controller.camera.manual_focus_supported = False
    controller.select_source("Cam A")

    assert not controller.model.focus.available

    controller.camera.manual_focus_supported = True
    controller.select_source("ASI: ZWO ASI183MM", provider=True)

    assert not controller.model.focus.available

    controller.select_source("")

    assert not controller.model.focus.available


def test_no_manual_focus_without_v4l2_answers_not_ok(controller, published):
    controller.camera.manual_focus_supported = False

    controller.apply_camera_controls({"request_id": "r7", "focus_distance": 0.5})

    assert published[0]["ok"] is False
    assert published[0]["error"] == "this camera has no manual focus"


# --------------------------------------------------------------------------- #
# Calibrated lens: direction and useful range from the tuning file's map       #
# --------------------------------------------------------------------------- #
@pytest.fixture
def imx708(controller, v4l2_focus):
    """The Pi CSI camera selected, its lens calibrated by IMX708_LENS_MAP."""
    v4l2_focus["controls"] = LENS_FOCUS_CONTROLS
    v4l2_focus["position"] = 670
    controller.camera.manual_focus_supported = False

    controller.select_source(
        "imx708",
        v4l2_focus_device_path="/dev/v4l-subdev3",
        v4l2_focus_lens_map=IMX708_LENS_MAP,
    )

    return controller


def test_lens_map_gives_the_span_near_first(imx708):
    assert imx708.model.v4l2_focus_span == (920, 420)


@pytest.mark.parametrize("distance, raw", [(0.0, 920), (0.5, 670), (1.0, 420)])
def test_calibrated_lens_maps_near_to_the_high_position(
    imx708, v4l2_focus, distance, raw
):
    imx708.set_focus(distance)

    assert v4l2_focus["calls"][-1] == ("/dev/v4l-subdev3", {"focus_absolute": raw})


def test_calibrated_lens_reads_back_round_trip(imx708, v4l2_focus):
    focus = imx708.model.focus

    assert focus.distance == pytest.approx(0.5)
    assert focus.raw_position == 670
    assert focus.position_label == "670 (≈ 6 cm)"

    v4l2_focus["position"] = 545
    imx708.refresh_focus()

    assert imx708._v4l2_focus_raw(focus.distance) == 545


def test_readback_beyond_the_span_is_clamped(imx708, v4l2_focus):
    focus = imx708.model.focus

    # Below the infinity position: farther than far.
    v4l2_focus["position"] = 100
    imx708.refresh_focus()

    assert focus.distance == 1.0
    assert focus.raw_position == 100
    assert focus.position_label == "100 (∞)"

    v4l2_focus["position"] = 1023
    imx708.refresh_focus()

    assert focus.distance == 0.0


def test_uncalibrated_lens_keeps_the_control_range(controller, v4l2_focus):
    v4l2_focus["controls"] = LENS_FOCUS_CONTROLS
    controller.camera.manual_focus_supported = False

    controller.select_source("imx708", v4l2_focus_device_path="/dev/v4l-subdev3")

    assert controller.model.v4l2_focus_span == (0, 1023)
    assert controller.model.focus.position_label == "250"


def test_uvc_camera_keeps_the_control_range(controller, v4l2_focus):
    controller.camera.manual_focus_supported = False

    controller.select_source("DH Camera", v4l2_focus_device_path="/dev/video8")

    assert controller.model.v4l2_focus_span == (0, 1000)


# --------------------------------------------------------------------------- #
# Live slider: coalesced focus writes                                          #
# --------------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    """The Qt application the controller's pyface timers need."""
    return QApplication.instance() or QApplication([])


def test_slider_drag_is_coalesced_into_the_latest_write(qapp, imx708, v4l2_focus):
    writes_before = len(v4l2_focus["calls"])

    for distance in (0.1, 0.2, 0.3, 0.4):
        imx708.request_focus(distance)

    assert len(v4l2_focus["calls"]) == writes_before
    assert imx708.focus_edits.pending

    imx708.focus_edits.flush()

    assert v4l2_focus["calls"][writes_before:] == [
        ("/dev/v4l-subdev3", {"focus_absolute": 720})
    ]
    assert imx708.model.focus.raw_position == 720


def test_auto_toggle_drops_a_pending_drag_write(qapp, controller, v4l2_focus):
    controller.camera.manual_focus_supported = False
    controller.select_source("DH Camera", v4l2_focus_device_path="/dev/video8")
    controller.set_focus(0.25)

    controller.request_focus(0.4)
    controller.set_focus(None)
    controller.focus_edits.flush()

    assert v4l2_focus["calls"][1:] == [
        ("/dev/video8", {"focus_automatic_continuous": 1})
    ]


# --------------------------------------------------------------------------- #
# One-shot autofocus                                                           #
# --------------------------------------------------------------------------- #
#: The synthetic scene is sharpest at this focus distance.
SHARPEST_DISTANCE = 0.37


@pytest.fixture
def sweeping(qapp, imx708, monkeypatch):
    """imx708 streaming, each frame as sharp as the lens's focus distance
    is close to SHARPEST_DISTANCE."""
    focus = imx708.model.focus

    def sharpness(grey):
        return 100.0 * math.exp(-(((focus.distance - SHARPEST_DISTANCE) / 0.1) ** 2))

    monkeypatch.setattr(camera_controller, "laplacian_variance", sharpness)
    imx708.model.camera_active = True

    return imx708


def _run_frames(controller, frames=500):
    for _ in range(frames):
        if not controller.model.focus.autofocusing:
            break

        controller.autofocus_frame(np.zeros((4, 4), np.uint8))


def test_autofocus_settles_on_the_sharpest_position(sweeping, v4l2_focus):
    focus = sweeping.model.focus

    assert focus.autofocus_available

    focus.autofocus_button = True

    assert focus.autofocusing
    assert focus.autofocus_label == "Focusing…"

    _run_frames(sweeping)

    assert not focus.autofocusing
    assert focus.autofocus_label == "Autofocus"
    assert focus.distance == pytest.approx(SHARPEST_DISTANCE, abs=0.02)
    assert v4l2_focus["calls"][-1] == (
        "/dev/v4l-subdev3",
        {"focus_absolute": sweeping._v4l2_focus_raw(focus.distance)},
    )
    assert len(sweeping.autofocus.scores) == 20


def test_autofocus_waits_for_a_streaming_camera(qapp, imx708, v4l2_focus):
    writes_before = len(v4l2_focus["calls"])

    imx708.model.focus.autofocus_button = True

    assert not imx708.model.focus.autofocusing
    assert len(v4l2_focus["calls"]) == writes_before


@pytest.mark.parametrize(
    "interrupt",
    [
        lambda controller: setattr(controller.model, "camera_active", False),
        lambda controller: controller.request_focus(0.2),
        lambda controller: controller.set_focus(None),
        lambda controller: controller.select_source("Cam A"),
    ],
    ids=["camera stopped", "slider edit", "auto toggled", "camera changed"],
)
def test_autofocus_is_cancelled_cleanly(sweeping, interrupt):
    focus = sweeping.model.focus
    focus.autofocus_button = True

    _run_frames(sweeping, frames=10)
    interrupt(sweeping)

    assert not focus.autofocusing
    assert not sweeping.autofocus.running

    # Frames still arriving change nothing.
    distance = focus.distance
    sweeping.autofocus_frame(np.zeros((4, 4), np.uint8))

    assert focus.distance == distance


def test_failed_lens_write_cancels_autofocus(sweeping, monkeypatch):
    focus = sweeping.model.focus
    monkeypatch.setattr(
        camera_controller, "set_v4l2_controls", lambda path, **controls: False
    )

    focus.autofocus_button = True

    assert not focus.autofocusing
