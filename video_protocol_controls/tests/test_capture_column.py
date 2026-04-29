"""Tests for the capture column — model, factory, view, handler."""

import json
from unittest.mock import MagicMock, patch

from traits.api import HasTraits

from video_protocol_controls.protocol_columns.capture_column import (
    CaptureColumnModel, CaptureHandler, make_capture_column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from device_viewer.consts import DEVICE_VIEWER_SCREEN_CAPTURE
from protocol_grid.preferences import StepTime


# ---------------------------------------------------------------------------
# 1. Model trait type / default
# ---------------------------------------------------------------------------

def test_capture_column_model_trait_for_row_is_bool_with_default_false():
    """Row trait stores Bool with default False."""
    m = CaptureColumnModel(col_id="capture", col_name="Capture", default_value=False)
    trait = m.trait_for_row()

    class Row(HasTraits):
        capture = trait

    r = Row()
    assert r.capture is False
    r.capture = True
    assert r.capture is True
    r.capture = False
    assert r.capture is False


# ---------------------------------------------------------------------------
# 2. Factory composition
# ---------------------------------------------------------------------------

def test_make_capture_column_returns_column_with_correct_ids():
    """Factory yields a Column with col_id='capture', col_name='Capture'."""
    col = make_capture_column()
    assert col.model.col_id == "capture"
    assert col.model.col_name == "Capture"


def test_make_capture_column_view_is_checkbox():
    col = make_capture_column()
    assert isinstance(col.view, CheckboxColumnView)


def test_make_capture_column_handler_is_capture_handler():
    col = make_capture_column()
    assert isinstance(col.handler, CaptureHandler)


def test_make_capture_column_default_value_is_false():
    col = make_capture_column()
    assert col.model.default_value is False


# ---------------------------------------------------------------------------
# 3. Handler priority
# ---------------------------------------------------------------------------

def test_capture_handler_priority_is_10():
    handler = CaptureHandler()
    assert handler.priority == 10


# ---------------------------------------------------------------------------
# 4. Handler has no wait_for_topics (empty list)
# ---------------------------------------------------------------------------

def test_capture_handler_wait_for_topics_is_empty():
    handler = CaptureHandler()
    assert handler.wait_for_topics == []


# ---------------------------------------------------------------------------
# 5. Pref binding — START: fire_at_start is True when capture_time == START
# ---------------------------------------------------------------------------

def test_make_capture_column_fire_at_start_true_when_pref_is_start():
    """With capture_time=StepTime.START, handler.fire_at_start should be True."""
    mock_prefs = MagicMock()
    mock_prefs.capture_time = StepTime.START

    with patch(
        "video_protocol_controls.protocol_columns.capture_column.ProtocolPreferences",
        return_value=mock_prefs,
    ):
        col = make_capture_column()

    assert col.handler.fire_at_start is True


# ---------------------------------------------------------------------------
# 6. Pref binding — END: fire_at_start is False when capture_time == END
# ---------------------------------------------------------------------------

def test_make_capture_column_fire_at_start_false_when_pref_is_end():
    """With capture_time=StepTime.END, handler.fire_at_start should be False."""
    mock_prefs = MagicMock()
    mock_prefs.capture_time = StepTime.END

    with patch(
        "video_protocol_controls.protocol_columns.capture_column.ProtocolPreferences",
        return_value=mock_prefs,
    ):
        col = make_capture_column()

    assert col.handler.fire_at_start is False


# ---------------------------------------------------------------------------
# 7. on_pre_step fires with correct JSON when fire_at_start=True, capture=True
# ---------------------------------------------------------------------------

def test_on_pre_step_fires_capture_when_fire_at_start_true_and_capture_true():
    """fire_at_start=True, row.capture=True → publish to DEVICE_VIEWER_SCREEN_CAPTURE."""
    handler = CaptureHandler(fire_at_start=True)

    row = MagicMock()
    row.uuid = "step-abc"
    row.name = "Step 1"
    row.capture = True

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/foo"}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.capture_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_pre_step(row, ctx)

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_SCREEN_CAPTURE
    payload = json.loads(published[0]["message"])
    assert payload["step_id"] == "step-abc"
    assert payload["step_description"] == "Step 1"
    assert payload["directory"] == "/tmp/foo"
    assert payload["show_dialog"] is False
    # Confirm legacy key name (not "experiment_dir")
    assert "directory" in payload
    assert "experiment_dir" not in payload


# ---------------------------------------------------------------------------
# 8. on_pre_step does NOT fire when fire_at_start=False (end-time mode)
# ---------------------------------------------------------------------------

def test_on_pre_step_does_not_fire_when_fire_at_start_false():
    """fire_at_start=False → on_pre_step is a no-op regardless of row.capture."""
    handler = CaptureHandler(fire_at_start=False)

    row = MagicMock()
    row.capture = True

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/foo"}

    with patch(
        "video_protocol_controls.protocol_columns.capture_column.publish_message"
    ) as mock_pub:
        handler.on_pre_step(row, ctx)

    mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# 9. on_pre_step does NOT fire when row.capture=False (regardless of timing)
# ---------------------------------------------------------------------------

def test_on_pre_step_does_not_fire_when_capture_false():
    """fire_at_start=True but row.capture=False → no publish."""
    handler = CaptureHandler(fire_at_start=True)

    row = MagicMock()
    row.capture = False

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/foo"}

    with patch(
        "video_protocol_controls.protocol_columns.capture_column.publish_message"
    ) as mock_pub:
        handler.on_pre_step(row, ctx)

    mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# 10. on_post_step fires with correct JSON when fire_at_start=False, capture=True
# ---------------------------------------------------------------------------

def test_on_post_step_fires_capture_when_fire_at_start_false_and_capture_true():
    """fire_at_start=False, row.capture=True → publish to DEVICE_VIEWER_SCREEN_CAPTURE."""
    handler = CaptureHandler(fire_at_start=False)

    row = MagicMock()
    row.uuid = "step-xyz"
    row.name = "Step 2"
    row.capture = True

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/bar"}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.capture_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_post_step(row, ctx)

    assert len(published) == 1
    assert published[0]["topic"] == DEVICE_VIEWER_SCREEN_CAPTURE
    payload = json.loads(published[0]["message"])
    assert payload["step_id"] == "step-xyz"
    assert payload["step_description"] == "Step 2"
    assert payload["directory"] == "/tmp/bar"
    assert payload["show_dialog"] is False
    assert "directory" in payload
    assert "experiment_dir" not in payload


# ---------------------------------------------------------------------------
# 11. on_post_step does NOT fire when fire_at_start=True (start-time mode)
# ---------------------------------------------------------------------------

def test_on_post_step_does_not_fire_when_fire_at_start_true():
    """fire_at_start=True → on_post_step is a no-op regardless of row.capture."""
    handler = CaptureHandler(fire_at_start=True)

    row = MagicMock()
    row.capture = True

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/foo"}

    with patch(
        "video_protocol_controls.protocol_columns.capture_column.publish_message"
    ) as mock_pub:
        handler.on_post_step(row, ctx)

    mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# 12. on_post_step does NOT fire when row.capture=False
# ---------------------------------------------------------------------------

def test_on_post_step_does_not_fire_when_capture_false():
    """fire_at_start=False but row.capture=False → no publish."""
    handler = CaptureHandler(fire_at_start=False)

    row = MagicMock()
    row.capture = False

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/foo"}

    with patch(
        "video_protocol_controls.protocol_columns.capture_column.publish_message"
    ) as mock_pub:
        handler.on_post_step(row, ctx)

    mock_pub.assert_not_called()


# ---------------------------------------------------------------------------
# 13. No cross-step state: calling on_pre_step twice fires two publishes
#     (no change-detection suppression — capture is per-step, not bracketed)
# ---------------------------------------------------------------------------

def test_no_cross_step_state_two_calls_fire_two_publishes():
    """Calling on_pre_step twice with capture=True fires twice (no dedup)."""
    handler = CaptureHandler(fire_at_start=True)

    row = MagicMock()
    row.uuid = "s1"
    row.name = "Step 1"
    row.capture = True

    ctx = MagicMock()
    ctx.protocol.scratch = {"experiment_dir": "/tmp/foo"}

    published = []
    patch_target = (
        "video_protocol_controls.protocol_columns.capture_column.publish_message"
    )

    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row, ctx)
        handler.on_pre_step(row, ctx)

    assert len(published) == 2


def test_capture_handler_has_no_active_scratch_key():
    """CaptureHandler carries no cross-step state attribute.

    Confirms there is no 'active' or similar instance attribute that would
    imply change-detection state (that would be wrong — Capture is per-step).
    """
    handler = CaptureHandler()
    handler_attrs = dir(handler)
    # Spot-check: none of these change-detection names should exist
    for name in ("active", "record_active", "camera_on", "_is_recording",
                 "_is_capturing"):
        assert name not in handler_attrs, (
            f"CaptureHandler unexpectedly has attribute '{name}' — "
            "capture should be stateless (no cross-step dedup)."
        )
