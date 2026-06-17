"""Tests for the record column — model, factory, view, handler."""

import json
from unittest.mock import MagicMock, patch

from traits.api import HasTraits

from video_protocol_controls.protocol_columns.record_column import (
    RecordColumnModel, RecordHandler, make_record_column, RECORDING_ACTIVE_KEY,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from device_viewer.consts import DEVICE_VIEWER_SCREEN_RECORDING


# ---------------------------------------------------------------------------
# 1. Model trait type / default
# ---------------------------------------------------------------------------

def test_record_column_model_trait_for_row_is_bool_with_default_false():
    """Row trait stores Bool with default False."""
    m = RecordColumnModel(col_id="record", col_name="Record", default_value=False)
    trait = m.trait_for_row()

    class Row(HasTraits):
        record = trait

    r = Row()
    assert r.record is False
    r.record = True
    assert r.record is True
    r.record = False
    assert r.record is False


# ---------------------------------------------------------------------------
# 2. Factory composition
# ---------------------------------------------------------------------------

def test_make_record_column_returns_column_with_correct_ids():
    """Factory yields a Column with col_id='record', col_name='Record'."""
    col = make_record_column()
    assert col.model.col_id == "record"
    assert col.model.col_name == "Record"


def test_make_record_column_view_is_checkbox():
    col = make_record_column()
    assert isinstance(col.view, CheckboxColumnView)


def test_make_record_column_handler_is_record_handler():
    col = make_record_column()
    assert isinstance(col.handler, RecordHandler)


def test_make_record_column_default_value_is_false():
    col = make_record_column()
    assert col.model.default_value is False


# ---------------------------------------------------------------------------
# 3. Handler priority
# ---------------------------------------------------------------------------

def test_record_handler_priority_is_10():
    handler = RecordHandler()
    assert handler.priority == 10


# ---------------------------------------------------------------------------
# 4. Handler has no wait_for_topics (empty list)
# ---------------------------------------------------------------------------

def test_record_handler_wait_for_topics_is_empty():
    handler = RecordHandler()
    assert handler.wait_for_topics == []


# ---------------------------------------------------------------------------
# 5. on_pre_step does NOT publish if state is unchanged (False)
# ---------------------------------------------------------------------------

def test_on_pre_step_no_publish_when_state_unchanged_false():
    """record=False and last=False --> no publish."""
    handler = RecordHandler()
    row = MagicMock()
    row.record = False

    ctx = MagicMock()
    ctx.protocol.scratch = {RECORDING_ACTIVE_KEY: False}

    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message"
    ) as mock_pub:
        handler.on_pre_step(row, ctx)

    mock_pub.assert_not_called()
    assert ctx.protocol.scratch[RECORDING_ACTIVE_KEY] is False


# ---------------------------------------------------------------------------
# 6. on_pre_step does NOT publish if state is unchanged (True)
# ---------------------------------------------------------------------------

def test_on_pre_step_no_publish_when_state_unchanged_true():
    """record=True and last=True → no publish (symmetric to the False case)."""
    handler = RecordHandler()
    row = MagicMock()
    row.record = True

    ctx = MagicMock()
    ctx.protocol.scratch = {RECORDING_ACTIVE_KEY: True}

    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message"
    ) as mock_pub:
        handler.on_pre_step(row, ctx)

    mock_pub.assert_not_called()
    assert ctx.protocol.scratch[RECORDING_ACTIVE_KEY] is True


# ---------------------------------------------------------------------------
# 7. on_pre_step publishes start JSON on flip-on
# ---------------------------------------------------------------------------

def test_on_pre_step_publishes_start_json_on_flip_on():
    """record=True, last=False → publish start JSON; scratch updated to True."""
    handler = RecordHandler()
    row = MagicMock()
    row.uuid = "abc123"
    row.name = "Step 1"
    row.record = True

    ctx = MagicMock()
    ctx.protocol.scratch = {
        RECORDING_ACTIVE_KEY: False,
        "experiment_dir": "/tmp/foo",
    }

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_pre_step(row, ctx)

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_SCREEN_RECORDING
    payload = json.loads(published[0]["message"])
    assert payload["action"] == "start"
    assert payload["step_id"] == "abc123"
    assert payload["step_description"] == "Step 1"
    assert payload["directory"] == "/tmp/foo"
    assert payload["show_dialog"] is False
    assert ctx.protocol.scratch[RECORDING_ACTIVE_KEY] is True


# ---------------------------------------------------------------------------
# 8. on_pre_step publishes stop JSON on flip-off
# ---------------------------------------------------------------------------

def test_on_pre_step_publishes_stop_json_on_flip_off():
    """record=False, last=True → publish stop JSON; scratch updated to False."""
    handler = RecordHandler()
    row = MagicMock()
    row.uuid = "abc123"
    row.name = "Step 1"
    row.record = False

    ctx = MagicMock()
    ctx.protocol.scratch = {RECORDING_ACTIVE_KEY: True}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_pre_step(row, ctx)

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_SCREEN_RECORDING
    payload = json.loads(published[0]["message"])
    assert payload == {"action": "stop"}
    assert ctx.protocol.scratch[RECORDING_ACTIVE_KEY] is False


# ---------------------------------------------------------------------------
# 9. Re-arming: start → stop → start across three calls (three publishes)
# ---------------------------------------------------------------------------

def test_on_pre_step_rearming_across_three_calls():
    """Simulate three steps: on, off, on — three publishes, all correct."""
    handler = RecordHandler()

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/bar"}  # no RECORDING_ACTIVE_KEY → False

    published = []
    patch_target = "video_protocol_controls.protocol_columns.record_column.publish_message"

    # Step 1: flip on
    row1 = MagicMock(); row1.uuid = "s1"; row1.name = "Step 1"; row1.record = True
    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row1, ctx)

    # Step 2: flip off
    row2 = MagicMock(); row2.uuid = "s2"; row2.name = "Step 2"; row2.record = False
    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row2, ctx)

    # Step 3: flip on again
    row3 = MagicMock(); row3.uuid = "s3"; row3.name = "Step 3"; row3.record = True
    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row3, ctx)

    assert len(published) == 3
    assert json.loads(published[0]["message"])["action"] == "start"
    assert json.loads(published[1]["message"]) == {"action": "stop"}
    assert json.loads(published[2]["message"])["action"] == "start"
    assert ctx.protocol.scratch[RECORDING_ACTIVE_KEY] is True


# ---------------------------------------------------------------------------
# 10. on_protocol_end publishes stop when recording was active
# ---------------------------------------------------------------------------

def test_on_protocol_end_publishes_stop_when_recording_was_active():
    """Protocol ends with recording on → publish stop; scratch reset to False."""
    handler = RecordHandler()

    # on_protocol_end receives a ProtocolContext; scratch is ctx.scratch directly.
    ctx = MagicMock()
    ctx.scratch = {RECORDING_ACTIVE_KEY: True}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_protocol_end(ctx)

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_SCREEN_RECORDING
    assert json.loads(published[0]["message"]) == {"action": "stop"}
    assert ctx.scratch[RECORDING_ACTIVE_KEY] is False


# ---------------------------------------------------------------------------
# 11. on_protocol_end is a no-op when recording was already off
# ---------------------------------------------------------------------------

def test_on_protocol_end_noop_when_recording_was_off():
    """Protocol ends with recording off → no publish."""
    handler = RecordHandler()

    ctx = MagicMock()
    ctx.scratch = {RECORDING_ACTIVE_KEY: False}

    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message"
    ) as mock_pub:
        handler.on_protocol_end(ctx)

    mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# 12. on_protocol_end is a no-op when scratch key absent
# ---------------------------------------------------------------------------

def test_on_protocol_end_noop_when_scratch_key_absent():
    """Protocol ends with no scratch entry → no publish (defaults to False)."""
    handler = RecordHandler()

    ctx = MagicMock()
    ctx.scratch = {}  # key not present

    with patch(
        "video_protocol_controls.protocol_columns.record_column.publish_message"
    ) as mock_pub:
        handler.on_protocol_end(ctx)

    mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# 13. Pre-protocol recording-active dialog gate (issue #398 acceptance)
# ---------------------------------------------------------------------------

import threading

from microdrop_application.dialogs.pyface_wrapper import YES, NO
from device_viewer.consts import DEVICE_VIEWER_RECORDING_ACTIVE_KEY

_RECORD_MOD = "video_protocol_controls.protocol_columns.record_column"


class _ProtoCtx:
    """Minimal ProtocolContext stand-in: prompt_gui runs the callable inline,
    exactly as the real ProtocolContext does headlessly (signals is None)."""

    def __init__(self):
        self.stop_event = threading.Event()

    def prompt_gui(self, fn, **kwargs):
        return fn()


def test_dialog_gate_idle_proceeds_without_dialog():
    """No recording active → proceed, and the confirm dialog never shows."""
    handler = RecordHandler()
    with patch(f"{_RECORD_MOD}.app_globals") as ag, \
         patch(f"{_RECORD_MOD}.confirm") as mock_confirm:
        ag.get.return_value = False
        assert handler._check_video_recording_and_show_dialog() is True
        mock_confirm.assert_not_called()


def test_dialog_gate_active_confirm_publishes_stop_and_proceeds():
    """Recording active + Continue → publish stop to DEVICE_VIEWER_SCREEN_RECORDING
    and proceed."""
    handler = RecordHandler()
    published = []
    with patch(f"{_RECORD_MOD}.app_globals") as ag, \
         patch(f"{_RECORD_MOD}.confirm", return_value=YES), \
         patch(f"{_RECORD_MOD}.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        ag.get.return_value = True
        assert handler._check_video_recording_and_show_dialog() is True
    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_SCREEN_RECORDING
    assert json.loads(published[0]["message"]) == {"action": "stop"}


def test_dialog_gate_active_cancel_does_not_publish_or_proceed():
    """Recording active + Cancel → no publish, do not proceed."""
    handler = RecordHandler()
    with patch(f"{_RECORD_MOD}.app_globals") as ag, \
         patch(f"{_RECORD_MOD}.confirm", return_value=NO), \
         patch(f"{_RECORD_MOD}.publish_message") as mock_pub:
        ag.get.return_value = True
        assert handler._check_video_recording_and_show_dialog() is False
        mock_pub.assert_not_called()


def test_on_pre_protocol_start_cancel_sets_stop_event():
    """Cancelling the dialog stops the run (stop_event set)."""
    handler = RecordHandler()
    ctx = _ProtoCtx()
    with patch(f"{_RECORD_MOD}.app_globals") as ag, \
         patch(f"{_RECORD_MOD}.confirm", return_value=NO), \
         patch(f"{_RECORD_MOD}.publish_message"):
        ag.get.return_value = True
        handler.on_pre_protocol_start(ctx)
    assert ctx.stop_event.is_set() is True


def test_on_pre_protocol_start_idle_does_not_stop():
    """No recording active → run proceeds (stop_event stays clear)."""
    handler = RecordHandler()
    ctx = _ProtoCtx()
    with patch(f"{_RECORD_MOD}.app_globals") as ag, \
         patch(f"{_RECORD_MOD}.confirm") as mock_confirm:
        ag.get.return_value = False
        handler.on_pre_protocol_start(ctx)
    assert ctx.stop_event.is_set() is False
    mock_confirm.assert_not_called()
