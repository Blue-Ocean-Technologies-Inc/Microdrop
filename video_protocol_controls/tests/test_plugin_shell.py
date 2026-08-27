# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

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
