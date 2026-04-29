"""Smoke tests for the video_protocol_controls package shell."""


def test_can_import_plugin():
    """Envisage Plugin.id is a Trait — accessible on an instance, not the
    class. (Class-level access raises AttributeError.)"""
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    assert p.id.endswith(".plugin")


def test_plugin_instantiates_with_no_columns_yet():
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    assert hasattr(p, "id")
    assert hasattr(p, "name")


def test_plugin_contributes_zero_columns():
    """The plugin's contributed_protocol_columns default factory yields
    an empty list. Column count will grow as Tasks 3/4/5 land."""
    from video_protocol_controls.plugin import VideoProtocolControlsPlugin
    p = VideoProtocolControlsPlugin()
    cols = p._contributed_protocol_columns_default()
    assert cols == []
    assert len(p.contributed_protocol_columns) == 0
