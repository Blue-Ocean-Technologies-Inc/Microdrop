"""Tests for the video column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

from traits.api import HasTraits

from video_protocol_controls.protocol_columns.video_column import (
    VideoColumnModel, VideoHandler, make_video_column, _SCRATCH_KEY,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from device_viewer.consts import DEVICE_VIEWER_CAMERA_ACTIVE


# ---------------------------------------------------------------------------
# 1. Model trait type / default
# ---------------------------------------------------------------------------

def test_video_column_model_trait_for_row_is_bool_with_default_false():
    """Row trait stores Bool with default False."""
    m = VideoColumnModel(col_id="video", col_name="Video", default_value=False)
    trait = m.trait_for_row()

    class Row(HasTraits):
        video = trait

    r = Row()
    assert r.video is False
    r.video = True
    assert r.video is True
    r.video = False
    assert r.video is False


# ---------------------------------------------------------------------------
# 2. Factory composition
# ---------------------------------------------------------------------------

def test_make_video_column_returns_column_with_correct_ids():
    """Factory yields a Column with col_id='video', col_name='Video'."""
    col = make_video_column()
    assert col.model.col_id == "video"
    assert col.model.col_name == "Video"


def test_make_video_column_view_is_checkbox():
    col = make_video_column()
    assert isinstance(col.view, CheckboxColumnView)


def test_make_video_column_handler_is_video_handler():
    col = make_video_column()
    assert isinstance(col.handler, VideoHandler)


def test_make_video_column_default_value_is_false():
    col = make_video_column()
    assert col.model.default_value is False


# ---------------------------------------------------------------------------
# 3. Handler priority
# ---------------------------------------------------------------------------

def test_video_handler_priority_is_10():
    handler = VideoHandler()
    assert handler.priority == 10


# ---------------------------------------------------------------------------
# 4. Handler has no wait_for_topics (empty list)
# ---------------------------------------------------------------------------

def test_video_handler_wait_for_topics_is_empty():
    handler = VideoHandler()
    assert handler.wait_for_topics == []


# ---------------------------------------------------------------------------
# 5. on_pre_step does NOT publish if state is unchanged
# ---------------------------------------------------------------------------

def test_on_pre_step_no_publish_when_state_unchanged_false():
    """video=False and last=False → no publish."""
    handler = VideoHandler()
    row = MagicMock()
    row.video = False

    ctx = MagicMock()
    ctx.protocol.scratch = {_SCRATCH_KEY: False}

    with patch(
        "video_protocol_controls.protocol_columns.video_column.publish_message"
    ) as mock_pub:
        handler.on_pre_step(row, ctx)

    mock_pub.assert_not_called()
    assert ctx.protocol.scratch[_SCRATCH_KEY] is False


# ---------------------------------------------------------------------------
# 6. on_pre_step publishes "true" on flip-on
# ---------------------------------------------------------------------------

def test_on_pre_step_publishes_true_on_flip_on():
    """video=True, last=False → publish 'true'; scratch updated to True."""
    handler = VideoHandler()
    row = MagicMock()
    row.video = True

    ctx = MagicMock()
    ctx.protocol.scratch = {_SCRATCH_KEY: False}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.video_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_pre_step(row, ctx)

    assert published == [{"topic": DEVICE_VIEWER_CAMERA_ACTIVE, "message": "true"}]
    assert ctx.protocol.scratch[_SCRATCH_KEY] is True


# ---------------------------------------------------------------------------
# 7. on_pre_step publishes "false" on flip-off
# ---------------------------------------------------------------------------

def test_on_pre_step_publishes_false_on_flip_off():
    """video=False, last=True → publish 'false'; scratch updated to False."""
    handler = VideoHandler()
    row = MagicMock()
    row.video = False

    ctx = MagicMock()
    ctx.protocol.scratch = {_SCRATCH_KEY: True}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.video_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_pre_step(row, ctx)

    assert published == [{"topic": DEVICE_VIEWER_CAMERA_ACTIVE, "message": "false"}]
    assert ctx.protocol.scratch[_SCRATCH_KEY] is False


# ---------------------------------------------------------------------------
# 8. Re-arming: flip-on → flip-off → flip-on → three publishes total
# ---------------------------------------------------------------------------

def test_on_pre_step_rearming_across_three_calls():
    """Simulate three steps: on, off, on — three publishes, all correct."""
    handler = VideoHandler()

    ctx = MagicMock()
    ctx.protocol.scratch = {}  # empty scratch = last is False

    published = []
    patch_target = "video_protocol_controls.protocol_columns.video_column.publish_message"

    # Step 1: flip on
    row1 = MagicMock(); row1.video = True
    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row1, ctx)

    # Step 2: flip off
    row2 = MagicMock(); row2.video = False
    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row2, ctx)

    # Step 3: flip on again
    row3 = MagicMock(); row3.video = True
    with patch(patch_target, side_effect=lambda **kw: published.append(kw)):
        handler.on_pre_step(row3, ctx)

    assert len(published) == 3
    assert published[0] == {"topic": DEVICE_VIEWER_CAMERA_ACTIVE, "message": "true"}
    assert published[1] == {"topic": DEVICE_VIEWER_CAMERA_ACTIVE, "message": "false"}
    assert published[2] == {"topic": DEVICE_VIEWER_CAMERA_ACTIVE, "message": "true"}
    assert ctx.protocol.scratch[_SCRATCH_KEY] is True


# ---------------------------------------------------------------------------
# 9. on_protocol_end publishes "false" when camera was on
# ---------------------------------------------------------------------------

def test_on_protocol_end_publishes_false_when_camera_was_on():
    """Protocol ends with camera on → publish 'false'; scratch reset to False."""
    handler = VideoHandler()

    # on_protocol_end receives a ProtocolContext; scratch is ctx.scratch directly.
    ctx = MagicMock()
    ctx.scratch = {_SCRATCH_KEY: True}

    published = []
    with patch(
        "video_protocol_controls.protocol_columns.video_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_protocol_end(ctx)

    assert published == [{"topic": DEVICE_VIEWER_CAMERA_ACTIVE, "message": "false"}]
    assert ctx.scratch[_SCRATCH_KEY] is False


# ---------------------------------------------------------------------------
# 10. on_protocol_end is a no-op when camera was already off
# ---------------------------------------------------------------------------

def test_on_protocol_end_noop_when_camera_was_off():
    """Protocol ends with camera off → no publish."""
    handler = VideoHandler()

    ctx = MagicMock()
    ctx.scratch = {_SCRATCH_KEY: False}

    with patch(
        "video_protocol_controls.protocol_columns.video_column.publish_message"
    ) as mock_pub:
        handler.on_protocol_end(ctx)

    mock_pub.assert_not_called()


def test_on_protocol_end_noop_when_scratch_key_absent():
    """Protocol ends with no scratch entry → no publish (defaults to False)."""
    handler = VideoHandler()

    ctx = MagicMock()
    ctx.scratch = {}  # key not present

    with patch(
        "video_protocol_controls.protocol_columns.video_column.publish_message"
    ) as mock_pub:
        handler.on_protocol_end(ctx)

    mock_pub.assert_not_called()
