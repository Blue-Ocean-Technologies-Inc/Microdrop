"""Smoke tests for the video_protocol_controls package shell."""


def test_can_import_plugin():
    """Envisage Plugin.id is a Trait — accessible on an instance, not the
    class. (Class-level access raises AttributeError.)"""
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    assert p.id.endswith(".plugin")


def test_plugin_contributes_one_column():
    """Task 3 added the Video column — the default factory now yields one entry.
    Tasks 4 and 5 will bump this to 2 then 3."""
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    cols = p._contributed_protocol_columns_default()
    assert len(cols) == 1
    assert cols[0].model.col_id == "video"
