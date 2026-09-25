# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the fluorescence capture column — model normalisation, the
display summary, and the handler's step execution. Hardware-free:
publish_message and fluorescence_capture_publisher.publish are patched, no
Redis/proxy needed. Mirrors test_pmt_capture_column.py."""

# Standard library imports.
import json
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.execution.exceptions import AbortError
from pluggable_protocol_tree.models.column import Column
from portable_dropbot_controller.consts import (
    FLUORESCENCE_CAPTURE_ABORT,
    FLUORESCENCE_CAPTURE_DONE,
    FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S,
    FLUORESCENCE_STEP_TIMEOUT_MARGIN_S,
)
from portable_dropbot_protocol_controls.consts import (
    FLUORESCENCE_CAPTURE_COLUMN_ID,
    PMT_CAPTURE_COLUMN_ID,
)
from portable_dropbot_protocol_controls.protocol_columns.fluorescence_capture_column import (  # noqa: E501
    FluorescenceCaptureHandler,
    FluorescenceStepCaptureColumnModel,
    FluorescenceStepCaptureColumnView,
    make_fluorescence_capture_column,
)

MODULE = (
    "portable_dropbot_protocol_controls.protocol_columns.fluorescence_capture_column"
)

ENTRY_START = {
    "filter_position": 1,
    "led_percent": 50,
    "exposure_ms": 50.0,
    "focus_distance": None,
    "at_start": True,
    "at_end": False,
}
ENTRY_END = {
    "filter_position": 2,
    "led_percent": 60,
    "exposure_ms": 40.0,
    "focus_distance": 0.5,
    "at_start": False,
    "at_end": True,
}
ENTRY_BOTH = {
    "filter_position": 3,
    "led_percent": 70,
    "exposure_ms": 30.0,
    "focus_distance": None,
    "at_start": True,
    "at_end": True,
}
ENTRY_NEITHER = {
    "filter_position": 4,
    "led_percent": 10,
    "exposure_ms": 20.0,
    "focus_distance": None,
    "at_start": False,
    "at_end": False,
}

STEP_VALUE = {"park_motor": False, "entries": [ENTRY_START, ENTRY_END, ENTRY_BOTH]}


def _row(value=None, uuid="row-uuid", dotted_path="1.2"):
    row = MagicMock()
    setattr(row, FLUORESCENCE_CAPTURE_COLUMN_ID, value)
    # The sibling capture column is empty on a real row; a bare MagicMock
    # auto-creates a truthy attribute for it, tripping check_single_capture.
    setattr(row, PMT_CAPTURE_COLUMN_ID, None)
    row.uuid = uuid
    row.dotted_path.return_value = dotted_path

    return row


def _ctx(preview_mode=False):
    ctx = MagicMock()
    ctx.protocol.preview_mode = preview_mode
    return ctx


# --- model -----------------------------------------------------------


def test_set_value_drops_unticked_entries():
    model = FluorescenceStepCaptureColumnModel()
    row = _row()
    model.set_value(row, {"entries": [ENTRY_START, ENTRY_NEITHER]})
    stored = getattr(row, FLUORESCENCE_CAPTURE_COLUMN_ID)
    assert [e["filter_position"] for e in stored["entries"]] == [1]


def test_set_value_all_entries_unticked_collapses_to_none():
    model = FluorescenceStepCaptureColumnModel()
    row = _row()
    model.set_value(row, {"entries": [ENTRY_NEITHER]})
    assert getattr(row, FLUORESCENCE_CAPTURE_COLUMN_ID) is None


def test_set_value_none_stays_none():
    model = FluorescenceStepCaptureColumnModel()
    row = _row()
    model.set_value(row, None)
    assert getattr(row, FLUORESCENCE_CAPTURE_COLUMN_ID) is None


def test_deserialize_invalid_cell_reads_as_none():
    model = FluorescenceStepCaptureColumnModel()
    assert model.deserialize({"entries": [{"filter_position": "bad"}]}) is None


def test_deserialize_round_trips_a_valid_cell():
    model = FluorescenceStepCaptureColumnModel()
    assert model.deserialize(STEP_VALUE) == STEP_VALUE


# --- view --------------------------------------------------------------


def test_view_depends_on_fluorescence_capture_column():
    view = FluorescenceStepCaptureColumnView()
    assert list(view.depends_on_row_traits) == [FLUORESCENCE_CAPTURE_COLUMN_ID]


def test_view_summary_text_and_blank_for_none():
    view = FluorescenceStepCaptureColumnView()
    assert view.format_display(None, _row()) == ""
    assert view.format_display(STEP_VALUE, _row()) == "3 filters · 2 start / 2 end"


def test_view_has_no_editor():
    view = FluorescenceStepCaptureColumnView()
    assert view.create_editor(None, None) is None


# --- factory -------------------------------------------------------------


def test_make_fluorescence_capture_column():
    col = make_fluorescence_capture_column()
    assert isinstance(col, Column)
    assert col.model.col_id == FLUORESCENCE_CAPTURE_COLUMN_ID
    assert col.handler.wait_for_topics == [FLUORESCENCE_CAPTURE_DONE]
    assert col.handler.priority == 20


# --- handler: phase filtering / preview / empty -------------------------


def test_pre_step_publishes_only_start_ticked_entries():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True, "request_id": "row-uuid:start"})

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert [e["filter_position"] for e in payload["entries"]] == [1, 3]


def test_post_step_publishes_only_end_ticked_entries():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True, "request_id": "row-uuid:end"})

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_post_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert [e["filter_position"] for e in payload["entries"]] == [2, 3]


def test_no_capture_cell_is_a_noop():
    handler = FluorescenceCaptureHandler()
    row = _row(None)
    ctx = _ctx()

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    publisher.publish.assert_not_called()
    ctx.wait_for.assert_not_called()


def test_phase_with_no_ticked_entries_is_a_noop():
    handler = FluorescenceCaptureHandler()
    row = _row({"entries": [ENTRY_START]})
    ctx = _ctx()

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_post_step(row, ctx)  # only a start-ticked entry present

    publisher.publish.assert_not_called()
    ctx.wait_for.assert_not_called()


def test_preview_mode_skips_publish_and_wait():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx(preview_mode=True)

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    publisher.publish.assert_not_called()
    ctx.wait_for.assert_not_called()


# --- handler: request payload / timeout / correlation -------------------


def test_request_payload_includes_request_id_label_and_directory():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert payload["request_id"] == "row-uuid:start"
    assert payload["label"] == "step1.2-start"
    assert payload["directory"] == ""
    assert payload["entries"][0] == {
        "filter_position": 1,
        "led_percent": 50,
        "exposure_ms": 50.0,
        "focus_distance": None,
    }


def test_label_is_sanitised_to_the_pmt_capture_label_pattern():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE, dotted_path="1/2")
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert payload["label"] == "step12-start"


def test_computed_timeout_is_per_entry_overhead_plus_margin():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.fluorescence_capture_publisher"):
        handler.on_pre_step(row, ctx)

    expected = (
        2 * FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S + FLUORESCENCE_STEP_TIMEOUT_MARGIN_S
    )
    _, kwargs = ctx.wait_for.call_args
    assert kwargs["timeout"] == expected


def test_predicate_accepts_own_request_id_and_rejects_a_foreign_one():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.fluorescence_capture_publisher"):
        handler.on_pre_step(row, ctx)

    _, kwargs = ctx.wait_for.call_args
    predicate = kwargs["predicate"]
    assert predicate(json.dumps({"request_id": "row-uuid:start"})) is True
    assert predicate(json.dumps({"request_id": "other-row:start"})) is False


def test_zero_ack_time_publishes_without_waiting():
    handler = FluorescenceCaptureHandler()
    handler.ack_time_s = 0.0
    row = _row(STEP_VALUE)
    ctx = _ctx()

    with patch(f"{MODULE}.fluorescence_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    publisher.publish.assert_called_once()
    ctx.wait_for.assert_not_called()


# --- handler: done / abort outcomes --------------------------------------


def test_done_ok_false_raises_runtime_error():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": False, "error": "busy"})

    with patch(f"{MODULE}.fluorescence_capture_publisher"):
        with pytest.raises(RuntimeError, match="busy"):
            handler.on_pre_step(row, ctx)


def test_abort_publishes_fluorescence_capture_abort_and_reraises():
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.side_effect = AbortError("stop pressed")

    published = []

    with patch(f"{MODULE}.fluorescence_capture_publisher"):
        with patch(
            f"{MODULE}.publish_message",
            side_effect=lambda **kw: published.append(kw),
        ):
            with pytest.raises(AbortError):
                handler.on_pre_step(row, ctx)

    assert published == [{"topic": FLUORESCENCE_CAPTURE_ABORT, "message": ""}]


def test_on_post_protocol_end_publishes_abort_unconditionally():
    handler = FluorescenceCaptureHandler()
    ctx = type("Ctx", (), {"preview_mode": False})()

    published = []

    with patch(
        f"{MODULE}.publish_message", side_effect=lambda **kw: published.append(kw)
    ):
        handler.on_post_protocol_end(ctx)

    assert published == [{"topic": FLUORESCENCE_CAPTURE_ABORT, "message": ""}]


def test_on_post_protocol_end_publishes_abort_even_in_preview_mode():
    # Unlike PmtCaptureHandler, the spec calls this unconditional: an
    # abort with nothing running is a no-op on the backend side, so there
    # is no preview_mode gate here.
    handler = FluorescenceCaptureHandler()
    ctx = type("Ctx", (), {"preview_mode": True})()

    published = []

    with patch(
        f"{MODULE}.publish_message", side_effect=lambda **kw: published.append(kw)
    ):
        handler.on_post_protocol_end(ctx)

    assert published == [{"topic": FLUORESCENCE_CAPTURE_ABORT, "message": ""}]


# --- handler: report contribution ---------------------------------------


@pytest.fixture(autouse=True)
def _report_publisher():
    """The done path contributes the captures folder to the run report;
    keep that publisher off the wire and hand its payloads back."""
    sent = []

    with patch(f"{MODULE}.protocol_logging_metadata_contribution_publisher") as pub:
        pub.publish.side_effect = lambda p, **k: sent.append(p)
        yield sent


def test_done_contributes_the_captures_folder(_report_publisher):
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps(
        {
            "ok": True,
            "directory": "/exp/captures",
            "frames": [
                {
                    "filter_position": 1,
                    "path": "/exp/captures/flu_step1.2-start_f1_x.png",
                }
            ],
        }
    )

    with patch(f"{MODULE}.fluorescence_capture_publisher"):
        handler.on_pre_step(row, ctx)

    assert _report_publisher == [{"Fluorescence Captures Folder": "/exp/captures"}]


def test_failed_capture_still_contributes_before_raising(_report_publisher):
    handler = FluorescenceCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps(
        {"ok": False, "error": "filter stalled", "directory": "/exp/captures"}
    )

    with patch(f"{MODULE}.fluorescence_capture_publisher"):
        with pytest.raises(RuntimeError, match="filter stalled"):
            handler.on_pre_step(row, ctx)

    assert _report_publisher == [{"Fluorescence Captures Folder": "/exp/captures"}]
