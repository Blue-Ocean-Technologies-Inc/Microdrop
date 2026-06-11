"""Tests for the capture compound column (#396 / PPT-19) — per-step
capture timing (capture Bool + capture_at Step Start/Step End), the
preference acting as default-only, and migration of legacy flat-capture
protocols."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from pyface.qt.QtCore import Qt

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.preferences import StepTime
from pluggable_protocol_tree.session import resolve_columns
from video_protocol_controls.protocol_columns.capture_column import (
    CaptureAtComboBoxView, CaptureColumnModel, CaptureCompoundModel,
    CaptureHandler, make_capture_column,
)

CAPTURE_COLUMN_MODULE = "video_protocol_controls.protocol_columns.capture_column"


def _row(name="step", capture=False, capture_at=StepTime.START, uuid="u-1"):
    return SimpleNamespace(name=name, uuid=uuid, capture=capture,
                           capture_at=capture_at)


def _ctx(experiment_dir=""):
    scratch = {"experiment_dir": experiment_dir} if experiment_dir else {}
    return SimpleNamespace(protocol=SimpleNamespace(scratch=scratch))


def _capture_manager():
    return RowManager(columns=[
        make_type_column(), make_name_column(),
        *_expand_compound(make_capture_column()),
    ])


# --- model ----------------------------------------------------------------

def test_field_specs_capture_then_capture_at():
    specs = CaptureCompoundModel().field_specs()
    assert [(s.field_id, s.col_name) for s in specs] == [
        ("capture", "Capture"), ("capture_at", "Capture At"),
    ]
    assert specs[0].default_value is False
    assert specs[1].default_value == StepTime.START


def test_capture_at_default_follows_model_default():
    specs = CaptureCompoundModel(
        default_capture_at=StepTime.END).field_specs()
    assert specs[1].default_value == StepTime.END


def test_legacy_class_name_is_the_compound_model():
    """Pre-#396 protocols recorded CaptureColumnModel as the cls qualname;
    the alias keeps them resolvable."""
    assert CaptureColumnModel is CaptureCompoundModel


# --- factory ----------------------------------------------------------------

def test_factory_returns_compound_with_checkbox_and_combobox():
    col = make_capture_column()
    assert isinstance(col, ICompoundColumn)
    assert col.model.base_id == "capture"
    at_view = col.view.cell_view_for_field("capture_at")
    assert isinstance(at_view, CaptureAtComboBoxView)
    assert at_view.options == [StepTime.START, StepTime.END]


def test_factory_seeds_capture_at_default_from_pref():
    for pref_value in (StepTime.START, StepTime.END):
        with patch(f"{CAPTURE_COLUMN_MODULE}.ProtocolPreferences") as P:
            P.return_value = SimpleNamespace(capture_time=pref_value)
            col = make_capture_column()
        assert col.model.default_capture_at == pref_value


def test_new_step_gets_pref_default_without_overriding_edits():
    """The pref is the DEFAULT for new steps; per-step values stand."""
    with patch(f"{CAPTURE_COLUMN_MODULE}.ProtocolPreferences") as P:
        P.return_value = SimpleNamespace(capture_time=StepTime.END)
        manager = _capture_manager()
    manager.add_step(values={"name": "defaulted"})
    manager.add_step(values={"name": "explicit", "capture_at": StepTime.START})
    assert manager.get_row((0,)).capture_at == StepTime.END
    assert manager.get_row((1,)).capture_at == StepTime.START


# --- handler ----------------------------------------------------------------

def test_handler_priority_and_fire_and_forget():
    handler = make_capture_column().handler
    assert handler.priority == 10
    assert list(handler.wait_for_topics) == []


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
    assert len(fired) == 1                      # S1 only fires at start

    handler.on_pre_step(s2, _ctx())
    assert len(fired) == 1                      # S2 silent at start
    handler.on_post_step(s2, _ctx())
    assert [p["step_description"] for _t, p in fired] == ["S1", "S2"]


def test_payload_uses_legacy_directory_key(monkeypatch):
    fired = _patched_fires(monkeypatch)
    row = _row(name="snap", uuid="u-9", capture=True)
    CaptureHandler().on_pre_step(row, _ctx(experiment_dir="exp/dir"))
    _topic, payload = fired[0]
    assert payload == {
        "directory": "exp/dir",
        "step_description": "snap",
        "step_id": "u-9",
        "show_dialog": False,
    }


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
    manager.add_step(values={"name": "S1", "capture": True,
                             "capture_at": StepTime.START})
    manager.add_step(values={"name": "S2", "capture": True,
                             "capture_at": StepTime.END})
    data = json.loads(json.dumps(manager.to_json()))
    restored = RowManager.from_json(data, columns=resolve_columns(data))
    assert restored.get_row((0,)).capture_at == StepTime.START
    assert restored.get_row((1,)).capture_at == StepTime.END
    cap_entries = [c for c in data["columns"]
                   if c.get("compound_id") == "capture"]
    assert [c["compound_field_id"] for c in cap_entries] == [
        "capture", "capture_at",
    ]


def _legacy_payload(manager):
    """Downgrade a current to_json payload to the pre-#396 shape: one flat
    'capture' column entry (CaptureColumnModel qualname, no compound_id)
    and no capture_at field/values."""
    data = json.loads(json.dumps(manager.to_json()))
    at_idx = data["fields"].index("capture_at")
    cap_idx = data["fields"].index("capture")
    data["columns"] = [
        c for c in data["columns"] if c.get("compound_id") != "capture"
    ] + [{
        "id": "capture",
        "cls": f"{CAPTURE_COLUMN_MODULE}.CaptureColumnModel",
    }]
    data["rows"] = [
        row[:4] + [v for i, v in enumerate(row[4:], start=4)
                   if i not in (at_idx, cap_idx)] + [row[cap_idx]]
        for row in data["rows"]
    ]
    data["fields"] = [f for f in data["fields"]
                      if f not in ("capture", "capture_at")] + ["capture"]
    return data


def test_legacy_flat_capture_protocol_migrates(qapp):
    """Acceptance: loading a pre-#396 protocol keeps every step's capture
    flag and fills capture_at from the current pref."""
    manager = _capture_manager()
    manager.add_step(values={"name": "captures", "capture": True})
    manager.add_step(values={"name": "plain"})
    legacy = _legacy_payload(manager)

    with patch(f"{CAPTURE_COLUMN_MODULE}.ProtocolPreferences") as P:
        P.return_value = SimpleNamespace(capture_time=StepTime.END)
        columns = resolve_columns(legacy)

    col_ids = [c.model.col_id for c in columns]
    assert "capture" in col_ids and "capture_at" in col_ids

    migrated = RowManager.from_json(legacy, columns=columns)
    captures, plain = migrated.get_row((0,)), migrated.get_row((1,))
    assert captures.capture is True and plain.capture is False
    assert captures.capture_at == StepTime.END    # filled from the pref
    assert plain.capture_at == StepTime.END
