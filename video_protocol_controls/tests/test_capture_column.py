# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the capture compound column (#396 / PPT-19) — per-step
capture timing (capture Bool + capture_at Step Start/Step End, new
steps defaulting to Step Start)."""

# Standard library imports.
import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import Qt

# Microdrop package imports.
from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_MEDIA_CAPTURED,
    DEVICE_VIEWER_SCREEN_CAPTURE,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import resolve_columns
from video_protocol_controls.consts import StepTime
from video_protocol_controls.protocol_columns.capture_column import (
    CHOICES,
    CaptureAtComboBoxView,
    CaptureCompoundModel,
    CaptureHandler,
    CaptureLeadSpinBoxView,
    make_capture_column,
)
from video_protocol_controls.protocol_columns.video_column import (
    VideoHandler,
)

CAPTURE_COLUMN_MODULE = "video_protocol_controls.protocol_columns.capture_column"


def _row(
    name="step",
    capture=False,
    capture_at=StepTime.START,
    uuid="u-1",
    capture_lead_ms=0,
):
    # dotted_path() is the step_id source (#396 follow-up: matches the
    # recording scheme) — a bare attribute won't do since the handler
    # calls it.
    return SimpleNamespace(
        name=name,
        uuid=uuid,
        capture=capture,
        capture_at=capture_at,
        capture_lead_ms=capture_lead_ms,
        dotted_path=lambda: uuid,
    )


def _ctx(experiment_dir=""):
    """StepContext stand-in: protocol scratch + recorded sleeps, and a
    wait_for mock standing in for the device viewer's capture ack."""
    scratch = {"experiment_dir": experiment_dir} if experiment_dir else {}
    sleeps = []

    return SimpleNamespace(
        protocol=SimpleNamespace(scratch=scratch, sleep=sleeps.append),
        sleeps=sleeps,
        wait_for=MagicMock(return_value="{}"),
    )


def _capture_manager():
    return RowManager(
        columns=[
            make_type_column(),
            make_name_column(),
            *_expand_compound(make_capture_column()),
        ]
    )


# --- model ----------------------------------------------------------------


def test_field_specs_capture_then_capture_at_then_lead():
    specs = CaptureCompoundModel().field_specs()
    assert [(s.field_id, s.col_name) for s in specs] == [
        ("capture", "Capture"),
        ("capture_at", "Capture At"),
        ("capture_lead_ms", "Camera Lead (ms)"),
    ]
    assert specs[0].default_value is False
    assert specs[1].default_value == StepTime.START
    assert specs[2].default_value == 0


def test_capture_at_default_follows_model_default():
    specs = CaptureCompoundModel(default_capture_at=StepTime.END).field_specs()
    assert specs[1].default_value == StepTime.END


# --- factory ----------------------------------------------------------------


def test_factory_returns_compound_with_checkbox_and_combobox():
    col = make_capture_column()
    assert isinstance(col, ICompoundColumn)
    assert col.model.base_id == "capture"
    at_view = col.view.cell_view_for_field("capture_at")
    assert isinstance(at_view, CaptureAtComboBoxView)
    # The combobox options come from the module's single definition
    # (CHOICES — moved off CaptureCompoundModel so the Enum default and
    # the view can both derive from it without a class reference).
    assert at_view.options == list(CHOICES)
    assert at_view.options == [StepTime.START, StepTime.END]


def test_new_step_defaults_to_step_start_without_overriding_edits():
    manager = _capture_manager()

    manager.add_step(values={"name": "defaulted"})
    manager.add_step(values={"name": "explicit", "capture_at": StepTime.END})

    assert manager.get_row((0,)).capture_at == StepTime.START
    assert manager.get_row((1,)).capture_at == StepTime.END


# --- handler ----------------------------------------------------------------


def test_handler_priority_and_capture_ack():
    handler = make_capture_column().handler
    # One bucket after Video (10), so the lead counts from after the
    # camera-on request.
    assert handler.priority == 11
    assert list(handler.wait_for_topics) == [DEVICE_VIEWER_MEDIA_CAPTURED]
    assert handler.ack_time_s == 15.0


def _patched_fires(monkeypatch):
    fired = []
    monkeypatch.setattr(
        f"{CAPTURE_COLUMN_MODULE}.publish_message",
        lambda topic, message: fired.append((topic, json.loads(message))),
    )
    return fired


def test_capture_at_start_fires_only_in_pre_step(monkeypatch):
    fired = _patched_fires(monkeypatch)
    row = _row(capture=True, capture_at=StepTime.START)
    handler = CaptureHandler()
    handler.on_pre_step(row, _ctx())
    handler.on_post_step(row, _ctx())
    assert len(fired) == 1


def test_capture_at_end_fires_only_in_post_step(monkeypatch):
    fired = _patched_fires(monkeypatch)
    row = _row(capture=True, capture_at=StepTime.END)
    handler = CaptureHandler()
    handler.on_pre_step(row, _ctx())
    assert fired == []
    handler.on_post_step(row, _ctx())
    assert len(fired) == 1


def test_no_fire_when_capture_false(monkeypatch):
    fired = _patched_fires(monkeypatch)
    handler = CaptureHandler()
    for at in (StepTime.START, StepTime.END):
        row = _row(capture=False, capture_at=at)
        handler.on_pre_step(row, _ctx())
        handler.on_post_step(row, _ctx())
    assert fired == []


def test_mixed_timings_in_one_protocol(monkeypatch):
    """Acceptance: Step 1 fires at START, Step 2 at END, same handler."""
    fired = _patched_fires(monkeypatch)
    handler = CaptureHandler()
    s1 = _row(name="S1", uuid="u1", capture=True, capture_at=StepTime.START)
    s2 = _row(name="S2", uuid="u2", capture=True, capture_at=StepTime.END)

    handler.on_pre_step(s1, _ctx())
    assert [p["step_description"] for _t, p in fired] == ["S1"]
    handler.on_post_step(s1, _ctx())
    assert len(fired) == 1  # S1 only fires at start

    handler.on_pre_step(s2, _ctx())
    assert len(fired) == 1  # S2 silent at start
    handler.on_post_step(s2, _ctx())
    assert [p["step_description"] for _t, p in fired] == ["S1", "S2"]


def test_payload_uses_legacy_directory_key(monkeypatch):
    fired = _patched_fires(monkeypatch)
    row = _row(name="snap", uuid="u-9", capture=True)
    CaptureHandler().on_pre_step(row, _ctx(experiment_dir="exp/dir"))
    _topic, payload = fired[0]
    request_id = payload.pop("request_id")

    assert payload == {
        "directory": "exp/dir",
        "step_description": "snap",
        "step_id": "u-9",
        "show_status_message": False,
    }
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)


def test_no_cross_step_state_two_calls_two_publishes(monkeypatch):
    fired = _patched_fires(monkeypatch)
    row = _row(capture=True)
    handler = CaptureHandler()
    handler.on_pre_step(row, _ctx())
    handler.on_pre_step(row, _ctx())
    assert len(fired) == 2


# --- view (cross-cell editability) ------------------------------------------


def test_capture_at_cell_read_only_until_capture_on():
    view = make_capture_column().view.cell_view_for_field("capture_at")
    off = _row(capture=False)
    on = _row(capture=True)
    assert not (view.get_flags(off) & Qt.ItemIsEditable)
    assert view.get_flags(on) & Qt.ItemIsEditable
    # And the cell reads blank while capture is off.
    assert view.format_display(StepTime.END, off) == ""
    assert view.format_display(StepTime.END, on) == StepTime.END


# --- persistence + legacy migration ------------------------------------------


def test_round_trip_preserves_per_step_capture_at(qapp):
    manager = _capture_manager()
    manager.add_step(
        values={"name": "S1", "capture": True, "capture_at": StepTime.START}
    )
    manager.add_step(values={"name": "S2", "capture": True, "capture_at": StepTime.END})
    data = json.loads(json.dumps(manager.to_json()))
    restored = RowManager.from_json(data, columns=resolve_columns(data))
    assert restored.get_row((0,)).capture_at == StepTime.START
    assert restored.get_row((1,)).capture_at == StepTime.END
    cap_entries = [c for c in data["columns"] if c.get("compound_id") == "capture"]
    assert [c["compound_field_id"] for c in cap_entries] == [
        "capture",
        "capture_at",
        "capture_lead_ms",
    ]


def test_payload_missing_capture_at_fills_with_step_start(qapp):
    """A payload without the capture_at field (e.g. written before the
    column existed) loads with capture flags intact and capture_at
    falling back to the model default, Step Start."""
    manager = _capture_manager()
    manager.add_step(
        values={"name": "captures", "capture": True, "capture_at": StepTime.END}
    )
    manager.add_step(values={"name": "plain", "capture_at": StepTime.END})
    data = _without_field(json.loads(json.dumps(manager.to_json())), "capture_at")

    loaded = RowManager.from_json(data, columns=list(_capture_manager().columns))
    captures, plain = loaded.get_row((0,)), loaded.get_row((1,))

    assert captures.capture is True and plain.capture is False
    assert captures.capture_at == StepTime.START
    assert plain.capture_at == StepTime.START


def test_payload_missing_capture_lead_fills_with_zero(qapp):
    """A protocol saved before the lead cell existed loads with no lead."""
    manager = _capture_manager()
    manager.add_step(
        values={"name": "captures", "capture": True, "capture_at": StepTime.END}
    )
    data = _without_field(json.loads(json.dumps(manager.to_json())), "capture_lead_ms")

    loaded = RowManager.from_json(data, columns=list(_capture_manager().columns))
    step = loaded.get_row((0,))

    assert step.capture is True
    assert step.capture_at == StepTime.END
    assert step.capture_lead_ms == 0


def _without_field(data, field_id):
    """Strip one field from a saved payload, as if written before it existed.

    Values deserialize against the saved columns list, so the column entry
    goes too — not just the fields header and the row cells.
    """
    value_idx = data["fields"].index(field_id)
    data["fields"].remove(field_id)
    data["columns"] = [c for c in data["columns"] if c["id"] != field_id]
    data["rows"] = [row[:value_idx] + row[value_idx + 1 :] for row in data["rows"]]

    return data


def test_capture_at_view_declares_capture_dependency():
    """CaptureAtComboBoxView gates flags + display on row.capture; without
    this declaration its grey-out only refreshed on an incidental
    repaint (issue #541 latent bug)."""
    from video_protocol_controls.protocol_columns.capture_column import (
        CaptureAtComboBoxView,
    )

    assert list(CaptureAtComboBoxView().depends_on_row_traits) == ["capture"]


# --- camera lead -------------------------------------------------------------


def _fake_clock(monkeypatch, start=100.0):
    """Freeze the handler's monotonic clock; return a setter to advance it."""
    now = [start]
    monkeypatch.setattr(f"{CAPTURE_COLUMN_MODULE}.time.monotonic", lambda: now[0])

    def advance(seconds):
        now[0] += seconds

    return advance


def test_factory_registers_lead_spinbox():
    view = make_capture_column().view.cell_view_for_field("capture_lead_ms")

    assert isinstance(view, CaptureLeadSpinBoxView)
    assert (view.low, view.high) == (0, 60000)
    assert list(view.depends_on_row_traits) == ["capture"]


def test_lead_cell_read_only_and_blank_until_capture_on():
    view = make_capture_column().view.cell_view_for_field("capture_lead_ms")
    off = _row(capture=False, capture_lead_ms=500)
    on = _row(capture=True, capture_lead_ms=500)

    assert not (view.get_flags(off) & Qt.ItemIsEditable)
    assert view.get_flags(on) & Qt.ItemIsEditable
    assert view.format_display(500, off) == ""
    assert view.format_display(500, on) == "500"


def test_zero_lead_publishes_only_capture(monkeypatch):
    fired = _patched_fires(monkeypatch)
    handler = CaptureHandler()

    for at in (StepTime.START, StepTime.END):
        ctx = _ctx()
        row = _row(capture=True, capture_at=at, capture_lead_ms=0)
        handler.on_pre_step(row, ctx)
        handler.on_post_step(row, ctx)

        assert ctx.sleeps == []

    assert [topic for topic, _payload in fired] == [DEVICE_VIEWER_SCREEN_CAPTURE] * 2


def test_lead_at_step_start_waits_full_lead_without_camera_publish(monkeypatch):
    fired = _patched_fires(monkeypatch)
    _fake_clock(monkeypatch)
    ctx = _ctx()
    row = _row(capture=True, capture_at=StepTime.START, capture_lead_ms=1500)

    CaptureHandler().on_pre_step(row, ctx)

    # The Video column publishes camera state; Capture only waits.
    assert [topic for topic, _payload in fired] == [DEVICE_VIEWER_SCREEN_CAPTURE]
    assert ctx.sleeps == [1.5]


def test_lead_at_step_end_waits_only_the_remainder(monkeypatch):
    fired = _patched_fires(monkeypatch)
    advance = _fake_clock(monkeypatch)
    handler = CaptureHandler()
    ctx = _ctx()
    row = _row(capture=True, capture_at=StepTime.END, capture_lead_ms=2000)

    handler.on_pre_step(row, ctx)

    assert fired == []
    assert ctx.sleeps == []

    advance(0.5)
    handler.on_post_step(row, ctx)

    assert [topic for topic, _payload in fired] == [DEVICE_VIEWER_SCREEN_CAPTURE]
    assert ctx.sleeps == [1.5]


def test_lead_at_step_end_no_wait_when_step_outlasts_lead(monkeypatch):
    _patched_fires(monkeypatch)
    advance = _fake_clock(monkeypatch)
    handler = CaptureHandler()
    ctx = _ctx()
    row = _row(capture=True, capture_at=StepTime.END, capture_lead_ms=2000)

    handler.on_pre_step(row, ctx)
    advance(5.0)
    handler.on_post_step(row, ctx)

    assert ctx.sleeps == [0.0]


def test_no_wait_when_capture_false(monkeypatch):
    fired = _patched_fires(monkeypatch)
    ctx = _ctx()
    row = _row(capture=False, capture_lead_ms=1000)

    CaptureHandler().on_pre_step(row, ctx)
    CaptureHandler().on_post_step(row, ctx)

    assert fired == []
    assert ctx.sleeps == []


# --- Video + Capture: one camera publisher ------------------------------------


def _camera_messages(monkeypatch):
    """Record (source, message) for camera publishes from Video and Capture."""
    published = []

    def recorder(source):
        def publish(topic, message):
            if topic == DEVICE_VIEWER_CAMERA_ACTIVE:
                published.append((source, message))

        return publish

    monkeypatch.setattr(
        "video_protocol_controls.protocol_columns.video_column.publish_message",
        recorder("video"),
    )
    monkeypatch.setattr(f"{CAPTURE_COLUMN_MODULE}.publish_message", recorder("capture"))

    return published


def _run_steps(rows):
    """Run each row through Video then Capture in executor order (10, 11)."""
    video, capture = VideoHandler(), CaptureHandler()
    ctx = _ctx()

    for row in rows:
        video.on_pre_step(row, ctx)
        capture.on_pre_step(row, ctx)
        capture.on_post_step(row, ctx)


def _lead_step(uuid, video=False, capture=True, capture_lead_ms=5000):
    row = _row(
        uuid=uuid,
        capture=capture,
        capture_at=StepTime.END,
        capture_lead_ms=capture_lead_ms,
    )
    row.video = video

    return row


def test_consecutive_lead_steps_publish_one_camera_on(monkeypatch):
    """Regression (#845 live test): a lead's camera-on must never be
    followed by a "false" on the next lead step."""
    published = _camera_messages(monkeypatch)
    _fake_clock(monkeypatch)

    _run_steps([_lead_step("u1"), _lead_step("u2")])

    assert published == [("video", "true")]


def test_video_then_lead_step_keeps_camera_on(monkeypatch):
    """Live failure: Video on (no lead), then Video off with a lead. The
    old two-publisher design sent "false" then "true" on one step, and
    concurrent delivery left the camera off for the whole lead."""
    published = _camera_messages(monkeypatch)
    _fake_clock(monkeypatch)

    _run_steps(
        [
            _lead_step("a", video=True, capture=False, capture_lead_ms=0),
            _lead_step("b"),
        ]
    )

    assert published == [("video", "true")]


def test_camera_off_once_a_step_wants_neither(monkeypatch):
    published = _camera_messages(monkeypatch)
    _fake_clock(monkeypatch)

    _run_steps(
        [
            _lead_step("a", video=True, capture=False, capture_lead_ms=0),
            _lead_step("b"),
            _lead_step("c", capture=False, capture_lead_ms=0),
        ]
    )

    assert published == [("video", "true"), ("video", "false")]


# --- acknowledged capture ------------------------------------------------------


def test_capture_waits_for_its_own_media_ack(monkeypatch):
    fired = _patched_fires(monkeypatch)
    handler = CaptureHandler()
    ctx = _ctx()

    handler.on_pre_step(_row(capture=True), ctx)

    request_id = fired[0][1]["request_id"]
    ctx.wait_for.assert_called_once()
    (topic,), kwargs = ctx.wait_for.call_args

    assert topic == DEVICE_VIEWER_MEDIA_CAPTURED
    assert kwargs["timeout"] == handler.ack_time_s

    predicate = kwargs["predicate"]
    ack = {"path": "captures/step.png", "type": "image"}

    assert predicate(json.dumps({**ack, "request_id": request_id}))
    assert not predicate(json.dumps({**ack, "request_id": "someone-else"}))


def test_each_capture_gets_a_fresh_request_id(monkeypatch):
    fired = _patched_fires(monkeypatch)
    handler = CaptureHandler()
    row = _row(capture=True)

    handler.on_pre_step(row, _ctx())
    handler.on_pre_step(row, _ctx())

    assert fired[0][1]["request_id"] != fired[1][1]["request_id"]


def test_zero_ack_time_is_fire_and_forget(monkeypatch):
    fired = _patched_fires(monkeypatch)
    handler = CaptureHandler(ack_time_s=0)
    ctx = _ctx()

    handler.on_pre_step(_row(capture=True), ctx)

    assert len(fired) == 1
    ctx.wait_for.assert_not_called()


def test_ack_timeout_propagates(monkeypatch):
    _patched_fires(monkeypatch)
    ctx = _ctx()
    ctx.wait_for.side_effect = TimeoutError("no media ack")

    with pytest.raises(TimeoutError):
        CaptureHandler().on_post_step(_row(capture=True, capture_at=StepTime.END), ctx)
