# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The fluorescence capture routine against a scripted proxy and a fake
frontend that answers the camera topics: per-entry call order, the
guaranteed restore on success, failure and abort, busy refusal, and wait
timeouts. The mixin is composed onto a stub base standing in for the
controller base's proxy helpers. No Redis, no Qt: the publishers are
patched, and every payload they receive is still validated against the
publisher's own model, so a renamed or missing field fails here too."""

# Standard library imports.
import json
import threading

# Third-party imports.
import pytest

# Enthought library imports.
from traits.api import Any, Bool, HasTraits, List, Str

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    FLUORESCENCE_LED_RAW_MAX,
    FLUORESCENCE_PARK_FILTER,
)
from portable_dropbot_controller.fluorescence_capture import led_raw
from portable_dropbot_controller.services import (
    portable_dropbot_fluorescence_mixin_service as mod,
)


class _Motor:
    def __init__(self, log):
        self.log = log
        #: Filter positions whose move answers no reply (an alarm).
        self.failing = set()

    def fluorescence_ctrl(self, position):
        self.log.append(f"filter {position}")

        return None if position in self.failing else object()


class _Sig:
    def __init__(self, log):
        self.log = log

    def fluorescence_ctrl(self, raw):
        self.log.append(f"led {raw}")

        return raw


class _Session:
    def __init__(self, log):
        self.motor = _Motor(log)
        self.sig = _Sig(log)


class _Base(HasTraits):
    proxy = Any()
    portable_dropbot_connection_active = Bool(True)
    errors = List()
    log = List()
    #: Contexts whose _proxy_call simulates a mid-call disconnect (the
    #: base's own OSError -> on_disconnected_signal path) instead of
    #: running call().
    disconnect_on = List(Str)

    def _proxy_call(self, context, call):
        if context in self.disconnect_on:
            self.portable_dropbot_connection_active = False
            return False, None

        return True, call()

    def _publish_error(self, context, error):
        self.errors.append(f"{context}: {error}")

    def _apply_light_intensity(self):
        self.log.append("light restored")


class _Harness(mod.FluorescenceCaptureMixinService, _Base):
    pass


class _Frontend:
    """The device viewer's side of the seam, answering synchronously (the
    routine registers its wait before it publishes). Flip the flags to
    make the camera refuse, stay silent, or trip an abort/disconnect."""

    def __init__(self, harness, tmp_path):
        self.h = harness
        self.tmp_path = tmp_path
        self.camera_ok = True
        self.answer_camera = True
        self.answer_frame = True
        #: Called after a camera request is answered (e.g. to abort).
        self.after_camera = None
        self.frame_requests = []

    def camera(self, payload, **kwargs):
        request = mod.camera_controls_publisher.validator_class.model_validate(payload)
        self.h.log.append(f"camera {request.exposure_ms} {request.focus_distance}")

        if not request.request_id or not self.answer_camera:
            return

        reply = {"request_id": request.request_id, "ok": self.camera_ok}

        if not self.camera_ok:
            reply["error"] = "no QCamera is selected"

        self.h.on_controls_applied_signal(json.dumps(reply))

        if self.after_camera is not None:
            self.after_camera()

    def raw(self, topic, message):
        assert topic == mod.DEVICE_VIEWER_SCREEN_CAPTURE
        request = json.loads(message)
        self.frame_requests.append(request)
        self.h.log.append(f"frame {request['step_description']}")

        if not self.answer_frame:
            return

        png = self.tmp_path / "captures" / f"{request['step_description']}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"")
        self.h.on_media_captured_signal(
            json.dumps(
                {"path": str(png), "type": "image", "request_id": request["request_id"]}
            )
        )


@pytest.fixture
def rig(monkeypatch, tmp_path):
    h = _Harness()
    h.proxy = _Session(h.log)
    frontend = _Frontend(h, tmp_path)
    out = {"h": h, "frontend": frontend, "progress": [], "done": []}

    monkeypatch.setattr(mod, "FLUORESCENCE_SETTLE_S", 0.0)
    monkeypatch.setattr(mod, "FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S", 0.2)
    monkeypatch.setattr(mod, "FLUORESCENCE_FRAME_TIMEOUT_S", 0.2)
    monkeypatch.setattr(mod, "get_current_experiment_directory", lambda: tmp_path)
    monkeypatch.setattr(mod.camera_controls_publisher, "publish", frontend.camera)
    monkeypatch.setattr(mod, "publish_message", frontend.raw)
    monkeypatch.setattr(
        mod.fluorescence_capture_progress_publisher,
        "publish",
        lambda p, **k: out["progress"].append(
            mod.fluorescence_capture_progress_publisher.validator_class.model_validate(
                p
            ).model_dump()
        ),
    )
    monkeypatch.setattr(
        mod.fluorescence_capture_done_publisher,
        "publish",
        lambda p, **k: out["done"].append(
            mod.fluorescence_capture_done_publisher.validator_class.model_validate(
                p
            ).model_dump()
        ),
    )

    return out


def _request(entries, **fields):
    return json.dumps({"entries": entries, **fields})


def _entry(position, led=40, exposure=50.0, focus=None):
    return {
        "filter_position": position,
        "led_percent": led,
        "exposure_ms": exposure,
        "focus_distance": focus,
    }


def _run(h, message):
    """Call the handler, then join the thread it may have started (a
    refusal starts none), so assertions see the finished routine."""
    h.on_fluorescence_capture_request(message)

    if h._fluorescence_thread is not None:
        h._fluorescence_thread.join(timeout=5)


def test_each_entry_runs_filter_led_camera_frame_then_restores(rig, tmp_path):
    h = rig["h"]

    _run(
        h,
        _request(
            [_entry(2, led=40, exposure=50.0), _entry(1, led=100, focus=0.3)],
            request_id="r1",
        ),
    )

    assert h.log == [
        "filter 2",
        f"led {led_raw(40)}",
        "camera 50.0 None",
        "frame flu_manual_f2_CY5",
        "filter 1",
        f"led {FLUORESCENCE_LED_RAW_MAX}",
        "camera 50.0 0.3",
        "frame flu_manual_f1_HEX",
        "light restored",
        "camera None None",
    ]
    done = rig["done"][-1]
    assert done["ok"] is True and done["error"] == ""
    assert done["request_id"] == "r1"
    assert done["directory"] == str(tmp_path / "captures")
    assert [
        f["path"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1] for f in done["frames"]
    ] == ["flu_manual_f2_CY5.png", "flu_manual_f1_HEX.png"]
    assert [f["filter_position"] for f in done["frames"]] == [2, 1]
    stages = [(p["filter_position"], p["stage"]) for p in rig["progress"]]
    assert stages == [
        (2, "filter"),
        (2, "led"),
        (2, "camera"),
        (2, "frame"),
        (1, "filter"),
        (1, "led"),
        (1, "camera"),
        (1, "frame"),
        (1, "teardown"),
    ]
    assert {p["request_id"] for p in rig["progress"]} == {"r1"}
    assert h._fluorescence_capturing is False
    assert h._fluorescence_abort is None


def test_teardown_parks_the_filter_when_requested(rig):
    h = rig["h"]

    _run(h, _request([_entry(1)], park_motor=True))

    assert h.log[-1] == f"filter {FLUORESCENCE_PARK_FILTER}"


def test_led_zero_percent_is_a_valid_dark_frame(rig):
    """led_raw(0) == 0, and an echoing driver returns that same 0 - falsy,
    but not the None that signals no reply."""
    h = rig["h"]

    _run(h, _request([_entry(1, led=0)]))

    done = rig["done"][-1]
    assert done["ok"] is True
    assert "led 0" in h.log
    assert len(done["frames"]) == 1


def test_frame_request_carries_directory_label_and_reply_id(rig, tmp_path):
    h, frontend = rig["h"], rig["frontend"]

    _run(
        h,
        _request(
            [_entry(3)], request_id="row-uuid:end", label="step1.2-end", directory=""
        ),
    )

    assert frontend.frame_requests == [
        {
            "directory": str(tmp_path),
            "step_description": "flu_step1.2-end_f3_White",
            "show_status_message": False,
            "request_id": "row-uuid:end:0",
        }
    ]
    assert rig["done"][-1]["label"] == "step1.2-end"


def test_explicit_directory_is_used_as_given(rig, tmp_path):
    h, frontend = rig["h"], rig["frontend"]
    elsewhere = tmp_path / "elsewhere"

    _run(h, _request([_entry(1)], directory=str(elsewhere)))

    assert frontend.frame_requests[0]["directory"] == str(elsewhere)
    assert rig["done"][-1]["directory"] == str(elsewhere / "captures")


def test_a_pane_request_without_id_still_matches_its_replies(rig):
    h = rig["h"]

    _run(h, _request([_entry(1)], label="manual"))

    done = rig["done"][-1]
    assert done["ok"] is True
    assert done["request_id"] == ""
    assert len(done["frames"]) == 1


def test_filter_failure_skips_the_rest_and_still_restores(rig):
    h = rig["h"]
    h.proxy.motor.failing = {1}

    _run(h, _request([_entry(1), _entry(2)]))

    assert h.log == ["filter 1", "light restored", "camera None None"]
    done = rig["done"][-1]
    assert done["ok"] is False
    assert done["error"].startswith("filter 1: no reply")
    assert done["frames"] == []


def test_camera_refusal_fails_the_entry_without_a_frame(rig):
    h, frontend = rig["h"], rig["frontend"]
    frontend.camera_ok = False

    _run(h, _request([_entry(2)]))

    assert frontend.frame_requests == []
    assert rig["done"][-1]["error"] == "camera: no QCamera is selected"
    assert h.log[-2:] == ["light restored", "camera None None"]


def test_camera_timeout_names_the_stage_and_reply_id(rig):
    h, frontend = rig["h"], rig["frontend"]
    frontend.answer_camera = False

    _run(h, _request([_entry(2)], request_id="r7"))

    error = rig["done"][-1]["error"]
    assert error.startswith("camera: no reply for r7:0")
    assert h.log[-2:] == ["light restored", "camera None None"]


def test_frame_timeout_keeps_earlier_frames(rig, monkeypatch):
    h, frontend = rig["h"], rig["frontend"]

    def answer_first_frame_only(topic, message):
        frontend.answer_frame = not frontend.frame_requests
        frontend.raw(topic, message)

    monkeypatch.setattr(mod, "publish_message", answer_first_frame_only)

    _run(h, _request([_entry(1), _entry(2)], request_id="r8"))

    done = rig["done"][-1]
    assert done["ok"] is False
    assert done["error"].startswith("frame: no reply for r8:1")
    assert len(done["frames"]) == 1


def test_abort_mid_run_stops_before_the_next_stage_and_restores(rig):
    h, frontend = rig["h"], rig["frontend"]
    frontend.after_camera = lambda: h.on_fluorescence_capture_abort_request("")

    _run(h, _request([_entry(1), _entry(2)]))

    done = rig["done"][-1]
    assert done["ok"] is False and done["error"] == "aborted"
    assert done["frames"] == []
    assert "filter 2" not in h.log
    assert h.log[-2:] == ["light restored", "camera None None"]


def test_abort_interrupts_a_wait_on_the_frontend(rig, monkeypatch):
    h, frontend = rig["h"], rig["frontend"]
    frontend.answer_camera = False
    monkeypatch.setattr(mod, "FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S", 30.0)

    h.on_fluorescence_capture_request(_request([_entry(1)]))
    threading.Timer(0.1, h.on_fluorescence_capture_abort_request, ("",)).start()
    h._fluorescence_thread.join(timeout=5)

    assert not h._fluorescence_thread.is_alive()
    assert rig["done"][-1]["error"] == "aborted"


def test_disconnect_aborts_the_capture(rig):
    h, frontend = rig["h"], rig["frontend"]

    def disconnect():
        h.portable_dropbot_connection_active = False

    frontend.after_camera = disconnect

    _run(h, _request([_entry(1)]))

    assert rig["done"][-1]["error"] == "aborted"
    assert h.log[-2:] == ["light restored", "camera None None"]


def test_disconnect_mid_filter_move_is_reported_as_aborted(rig):
    """A disconnect _proxy_call catches during the filter move must not fall
    through to the "no reply" stage error — Tasks 8-10 match on "aborted"
    for both an explicit abort and a disconnect."""
    h = rig["h"]
    h.disconnect_on = ["fluorescence capture: filter 1"]

    _run(h, _request([_entry(1), _entry(2)]))

    done = rig["done"][-1]
    assert done["ok"] is False and done["error"] == "aborted"
    assert done["frames"] == []
    assert "filter 2" not in h.log
    assert h.log[-2:] == ["light restored", "camera None None"]


def test_request_while_capturing_is_refused_as_busy(rig):
    h = rig["h"]
    h._fluorescence_capturing = True

    h.on_fluorescence_capture_request(
        _request([_entry(1)], request_id="r9", label="step2-start")
    )

    assert rig["done"] == [
        {
            "request_id": "r9",
            "ok": False,
            "label": "step2-start",
            "directory": "",
            "frames": [],
            "error": "busy",
        }
    ]
    assert h.log == []


def test_empty_request_is_refused(rig):
    h = rig["h"]

    h.on_fluorescence_capture_request(_request([]))

    assert rig["done"][-1]["error"] == "no filter positions ticked"
    assert h._fluorescence_thread is None


def test_malformed_request_still_publishes_a_done_refusal(rig):
    h = rig["h"]

    h.on_fluorescence_capture_request(
        _request([_entry(9)], request_id="r10", label="step3-end")
    )

    done = rig["done"][-1]
    assert done["ok"] is False and done["error"] != ""
    assert (done["request_id"], done["label"]) == ("r10", "step3-end")
    assert h.errors


def test_replies_nobody_waits_for_are_ignored(rig):
    h = rig["h"]

    h.on_controls_applied_signal(json.dumps({"request_id": "stranger", "ok": True}))
    h.on_media_captured_signal("not json")
    h.on_media_captured_signal(json.dumps({"path": "x.png", "type": "image"}))

    assert rig["done"] == []
