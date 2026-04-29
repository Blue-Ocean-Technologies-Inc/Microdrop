"""Smoke tests for the video_protocol_controls package shell."""


def test_can_import_plugin():
    """Envisage Plugin.id is a Trait — accessible on an instance, not the
    class. (Class-level access raises AttributeError.)"""
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    assert p.id.endswith(".plugin")


def test_plugin_contributes_three_columns():
    """Tasks 3-5 added Video, Record, and Capture — the default factory yields three entries."""
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    cols = p._contributed_protocol_columns_default()
    assert len(cols) == 3
    assert [c.model.col_id for c in cols] == ["video", "record", "capture"]
