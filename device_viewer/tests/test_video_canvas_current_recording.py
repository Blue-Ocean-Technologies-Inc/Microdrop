# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Recording Viewer's canvas is built on the pane's first show, after its
model picked a recording: it opens that recording, not only the next one
(#1085)."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QUrl

# Microdrop package imports.
from device_viewer.consts import RECORDING_TRANSFORM_SIDECAR_SUFFIX
from device_viewer.views.video_viewer.model import VideoViewerModel
from device_viewer.views.video_viewer.video_canvas import VideoPlaybackCanvas


@pytest.fixture
def qapp():
    from pyface.qt.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_a_canvas_opens_the_recording_its_model_already_holds(qapp, tmp_path):
    recording = tmp_path / "recording.mp4"
    recording.write_bytes(b"")
    recording.with_suffix(RECORDING_TRANSFORM_SIDECAR_SUFFIX).write_text(
        json.dumps({"transform": [], "bounding_rect": [], "scene_bounding_rect": []})
    )
    model = VideoViewerModel(current_path=str(recording))

    canvas = VideoPlaybackCanvas(model)

    assert canvas._player.source() == QUrl.fromLocalFile(str(recording))
    assert model.has_transform


def test_a_canvas_without_a_recording_opens_nothing(qapp):
    model = VideoViewerModel()

    canvas = VideoPlaybackCanvas(model)

    assert canvas._player.source().isEmpty()
    assert not model.has_transform
