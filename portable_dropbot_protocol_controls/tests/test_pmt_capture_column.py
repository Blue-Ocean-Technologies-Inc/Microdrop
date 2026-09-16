# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the PMT capture column — model normalisation, the display
summary, and the handler's step execution. Hardware-free: publish_message
and pmt_capture_publisher.publish are patched, no Redis/proxy needed."""

# Standard library imports.
import json
from unittest.mock import MagicMock, patch

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.execution.exceptions import AbortError
from pluggable_protocol_tree.models.column import Column
from portable_dropbot_controller.consts import (
    PMT_CAPTURE_ABORT,
    PMT_CAPTURE_DONE,
    PMT_STEP_PER_SPOT_OVERHEAD_S,
    PMT_STEP_TIMEOUT_MARGIN_S,
)
from portable_dropbot_protocol_controls.consts import PMT_CAPTURE_COLUMN_ID
from portable_dropbot_protocol_controls.protocol_columns.pmt_capture_column import (
    PmtCaptureHandler,
    PmtStepCaptureColumnModel,
    PmtStepCaptureColumnView,
    make_pmt_capture_column,
)

MODULE = "portable_dropbot_protocol_controls.protocol_columns.pmt_capture_column"

ENTRY_START = {
    "slot": 1,
    "gain": 100,
    "exposure_s": 5.0,
    "at_start": True,
    "at_end": False,
}
ENTRY_END = {
    "slot": 2,
    "gain": 150,
    "exposure_s": 8.0,
    "at_start": False,
    "at_end": True,
}
ENTRY_BOTH = {
    "slot": 3,
    "gain": 200,
    "exposure_s": 3.0,
    "at_start": True,
    "at_end": True,
}
ENTRY_NEITHER = {
    "slot": 4,
    "gain": 50,
    "exposure_s": 1.0,
    "at_start": False,
    "at_end": False,
}

STEP_VALUE = {
    "avg": 16,
    "osr": 6,
    "rf_ohms": 499000.0,
    "entries": [ENTRY_START, ENTRY_END, ENTRY_BOTH],
}


def _row(value=None, uuid="row-uuid", dotted_path="1.2"):
    row = MagicMock()
    setattr(row, PMT_CAPTURE_COLUMN_ID, value)
    row.uuid = uuid
    row.dotted_path.return_value = dotted_path

    return row


def _ctx(preview_mode=False):
    ctx = MagicMock()
    ctx.protocol.preview_mode = preview_mode
    return ctx


# --- model -----------------------------------------------------------


def test_set_value_drops_untitcked_entries():
    model = PmtStepCaptureColumnModel()
    row = _row()
    model.set_value(row, {**STEP_VALUE, "entries": [ENTRY_START, ENTRY_NEITHER]})
    stored = getattr(row, PMT_CAPTURE_COLUMN_ID)
    assert [e["slot"] for e in stored["entries"]] == [1]


def test_set_value_all_entries_unticked_collapses_to_none():
    model = PmtStepCaptureColumnModel()
    row = _row()
    model.set_value(row, {**STEP_VALUE, "entries": [ENTRY_NEITHER]})
    assert getattr(row, PMT_CAPTURE_COLUMN_ID) is None


def test_set_value_none_stays_none():
    model = PmtStepCaptureColumnModel()
    row = _row()
    model.set_value(row, None)
    assert getattr(row, PMT_CAPTURE_COLUMN_ID) is None


def test_deserialize_invalid_cell_reads_as_none():
    model = PmtStepCaptureColumnModel()
    assert model.deserialize({"entries": [{"slot": "not-an-int"}]}) is None
    assert model.deserialize({"avg": -1}) is None


def test_deserialize_round_trips_a_valid_cell():
    model = PmtStepCaptureColumnModel()
    assert model.deserialize(STEP_VALUE) == STEP_VALUE


# --- view --------------------------------------------------------------


def test_view_depends_on_pmt_capture_column():
    view = PmtStepCaptureColumnView()
    assert list(view.depends_on_row_traits) == [PMT_CAPTURE_COLUMN_ID]


def test_view_summary_text_and_blank_for_none():
    view = PmtStepCaptureColumnView()
    assert view.format_display(None, _row()) == ""
    assert view.format_display(STEP_VALUE, _row()) == "3 spots · 2 start / 2 end"


def test_view_has_no_editor():
    view = PmtStepCaptureColumnView()
    assert view.create_editor(None, None) is None


# --- factory -------------------------------------------------------------


def test_make_pmt_capture_column():
    col = make_pmt_capture_column()
    assert isinstance(col, Column)
    assert col.model.col_id == PMT_CAPTURE_COLUMN_ID
    assert col.handler.wait_for_topics == [PMT_CAPTURE_DONE]
    assert col.handler.priority == 20


# --- handler: phase filtering / preview / empty -------------------------


def test_pre_step_publishes_only_start_ticked_entries():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True, "request_id": "row-uuid:start"})

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert [e["slot"] for e in payload["entries"]] == [1, 3]


def test_post_step_publishes_only_end_ticked_entries():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True, "request_id": "row-uuid:end"})

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_post_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert [e["slot"] for e in payload["entries"]] == [2, 3]


def test_no_capture_cell_is_a_noop():
    handler = PmtCaptureHandler()
    row = _row(None)
    ctx = _ctx()

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    publisher.publish.assert_not_called()
    ctx.wait_for.assert_not_called()


def test_phase_with_no_ticked_entries_is_a_noop():
    handler = PmtCaptureHandler()
    row = _row({**STEP_VALUE, "entries": [ENTRY_START]})
    ctx = _ctx()

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_post_step(row, ctx)  # only a start-ticked entry present

    publisher.publish.assert_not_called()
    ctx.wait_for.assert_not_called()


def test_preview_mode_skips_publish_and_wait():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx(preview_mode=True)

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    publisher.publish.assert_not_called()
    ctx.wait_for.assert_not_called()


# --- handler: request payload / timeout / correlation -------------------


def test_request_payload_includes_request_id_label_and_stop_live_stream():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert payload["request_id"] == "row-uuid:start"
    assert payload["label"] == "step1.2-start"
    assert payload["stop_live_stream"] is True
    assert payload["avg"] == 16
    assert payload["osr"] == 6
    assert payload["rf_ohms"] == 499000.0
    # Only slot/gain/exposure_s travel on the request entries.
    assert payload["entries"][0] == {"slot": 1, "gain": 100, "exposure_s": 5.0}


def test_label_is_sanitised_to_the_pmt_capture_label_pattern():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE, dotted_path="1/2")
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    payload = publisher.publish.call_args[0][0]
    assert payload["label"] == "step12-start"


def test_computed_timeout_is_exposure_sum_plus_per_spot_overhead_and_margin():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.pmt_capture_publisher"):
        handler.on_pre_step(row, ctx)

    expected = (
        (5.0 + 3.0) + 2 * PMT_STEP_PER_SPOT_OVERHEAD_S + PMT_STEP_TIMEOUT_MARGIN_S
    )
    _, kwargs = ctx.wait_for.call_args
    assert kwargs["timeout"] == expected


def test_predicate_accepts_own_request_id_and_rejects_a_foreign_one():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": True})

    with patch(f"{MODULE}.pmt_capture_publisher"):
        handler.on_pre_step(row, ctx)

    _, kwargs = ctx.wait_for.call_args
    predicate = kwargs["predicate"]
    assert predicate(json.dumps({"request_id": "row-uuid:start"})) is True
    assert predicate(json.dumps({"request_id": "other-row:start"})) is False


def test_zero_ack_time_publishes_without_waiting():
    handler = PmtCaptureHandler()
    handler.ack_time_s = 0.0
    row = _row(STEP_VALUE)
    ctx = _ctx()

    with patch(f"{MODULE}.pmt_capture_publisher") as publisher:
        handler.on_pre_step(row, ctx)

    publisher.publish.assert_called_once()
    ctx.wait_for.assert_not_called()


# --- handler: done / abort outcomes --------------------------------------


def test_done_ok_false_raises_runtime_error():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.return_value = json.dumps({"ok": False, "error": "no proxy"})

    with patch(f"{MODULE}.pmt_capture_publisher"):
        with pytest.raises(RuntimeError, match="no proxy"):
            handler.on_pre_step(row, ctx)


def test_abort_publishes_pmt_capture_abort_and_reraises():
    handler = PmtCaptureHandler()
    row = _row(STEP_VALUE)
    ctx = _ctx()
    ctx.wait_for.side_effect = AbortError("stop pressed")

    published = []

    with patch(f"{MODULE}.pmt_capture_publisher"):
        with patch(
            f"{MODULE}.publish_message",
            side_effect=lambda **kw: published.append(kw),
        ):
            with pytest.raises(AbortError):
                handler.on_pre_step(row, ctx)

    assert published == [{"topic": PMT_CAPTURE_ABORT, "message": ""}]


def test_on_post_protocol_end_publishes_abort_unconditionally():
    handler = PmtCaptureHandler()
    ctx = type("Ctx", (), {"preview_mode": False})()

    published = []

    with patch(
        f"{MODULE}.publish_message", side_effect=lambda **kw: published.append(kw)
    ):
        handler.on_post_protocol_end(ctx)

    assert published == [{"topic": PMT_CAPTURE_ABORT, "message": ""}]


def test_on_post_protocol_end_skips_in_preview_mode():
    handler = PmtCaptureHandler()
    ctx = type("Ctx", (), {"preview_mode": True})()

    published = []

    with patch(
        f"{MODULE}.publish_message", side_effect=lambda **kw: published.append(kw)
    ):
        handler.on_post_protocol_end(ctx)

    assert published == []
