"""Persistence round-trip test for the 3 video_protocol_controls columns
(Video, Record, Capture). Confirms the Bool values survive save -> load
through RowManager.to_json() / from_json(), and that the persisted column
class paths point at video_protocol_controls.protocol_columns.* (so the
JSON identifies the contributing plugin correctly)."""

import json
from unittest.mock import MagicMock, patch

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column

from video_protocol_controls.protocol_columns import (
    make_video_column,
    make_record_column,
    make_capture_column,
)
from protocol_grid.preferences import StepTime


def _build_columns():
    """Build the 7-column set used by the video_protocol_controls plugin.

    Patches ProtocolPreferences so make_capture_column() doesn't need
    a live envisage application.
    """
    mock_prefs = MagicMock()
    mock_prefs.capture_time = StepTime.START
    with patch(
        "video_protocol_controls.protocol_columns.capture_column.ProtocolPreferences",
        return_value=mock_prefs,
    ):
        return [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
            make_video_column(),
            make_record_column(),
            make_capture_column(),
        ]


# ---------------------------------------------------------------------------
# 1. All-False round-trip
# ---------------------------------------------------------------------------

def test_all_false_round_trip():
    """A step with all three capture flags False survives to_json -> from_json."""
    cols = _build_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "video": False, "record": False, "capture": False})

    payload = rm.to_json()
    json_str = json.dumps(payload)   # confirms JSON-serialisable
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=_build_columns())
    step = rm2.root.children[0]

    assert step.video is False
    assert step.record is False
    assert step.capture is False


# ---------------------------------------------------------------------------
# 2. All-True round-trip
# ---------------------------------------------------------------------------

def test_all_true_round_trip():
    """A step with all three capture flags True survives to_json -> from_json."""
    cols = _build_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "video": True, "record": True, "capture": True})

    payload = rm.to_json()
    json_str = json.dumps(payload)
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=_build_columns())
    step = rm2.root.children[0]

    assert step.video is True
    assert step.record is True
    assert step.capture is True


# ---------------------------------------------------------------------------
# 3. Mixed round-trip across multiple steps
# ---------------------------------------------------------------------------

def test_mixed_round_trip_multiple_steps():
    """Three steps with varied flag combinations all restore exactly."""
    cols = _build_columns()
    rm = RowManager(columns=cols)

    # Cover a representative spread of the 2^3 combinations
    step_combos = [
        {"name": "S1", "video": False, "record": False, "capture": True},
        {"name": "S2", "video": True,  "record": False, "capture": False},
        {"name": "S3", "video": True,  "record": True,  "capture": True},
    ]
    for combo in step_combos:
        rm.add_step(values=combo)

    payload = rm.to_json()
    json_str = json.dumps(payload)
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=_build_columns())
    steps = rm2.root.children
    assert len(steps) == 3

    assert steps[0].video is False
    assert steps[0].record is False
    assert steps[0].capture is True

    assert steps[1].video is True
    assert steps[1].record is False
    assert steps[1].capture is False

    assert steps[2].video is True
    assert steps[2].record is True
    assert steps[2].capture is True


# ---------------------------------------------------------------------------
# 4. Column class paths in JSON output
# ---------------------------------------------------------------------------

def test_column_class_paths_in_json():
    """The JSON columns array carries the correct fully-qualified cls for each
    video_protocol_controls column so the file identifies its plugin origin."""
    cols = _build_columns()
    rm = RowManager(columns=cols)
    rm.add_step()

    payload = rm.to_json()

    # Build a lookup of col_id -> cls string from the serialised columns list
    col_cls_by_id = {
        entry["id"]: entry["cls"]
        for entry in payload["columns"]
    }

    assert col_cls_by_id["video"] == (
        "video_protocol_controls.protocol_columns.video_column.VideoColumnModel"
    )
    assert col_cls_by_id["record"] == (
        "video_protocol_controls.protocol_columns.record_column.RecordColumnModel"
    )
    assert col_cls_by_id["capture"] == (
        "video_protocol_controls.protocol_columns.capture_column.CaptureColumnModel"
    )
