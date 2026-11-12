# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pure camera-pixel <-> video-item mapping and quad comparison."""

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.utils.alignment_geometry import (
    camera_point_to_item,
    camera_to_item_mapping,
    item_point_to_camera,
    quads_close,
)


def test_wider_item_letterboxes_left_and_right():
    # 640x480 into 1600x960: height-bound, scale 2, 160 px bars each side.
    mapping = camera_to_item_mapping((640, 480), (1600, 960))

    assert mapping == (2.0, 2.0, 160.0, 0.0)
    assert camera_point_to_item([0, 0], mapping) == [160.0, 0.0]
    assert camera_point_to_item([640, 480], mapping) == [1440.0, 960.0]


def test_taller_item_letterboxes_top_and_bottom():
    # 640x480 into 1280x1080: width-bound, scale 2, 60 px bars top and bottom.
    mapping = camera_to_item_mapping((640, 480), (1280, 1080))

    assert mapping == (2.0, 2.0, 0.0, 60.0)
    assert camera_point_to_item([320, 240], mapping) == [640.0, 540.0]


def test_ignore_aspect_ratio_stretches():
    mapping = camera_to_item_mapping((640, 480), (1280, 1080), keep_aspect_ratio=False)

    assert mapping == (2.0, 2.25, 0.0, 0.0)


@pytest.mark.parametrize("item_size", [(1600, 960), (1280, 1080), (333, 777)])
def test_item_to_camera_inverts_camera_to_item(item_size):
    mapping = camera_to_item_mapping((1920, 1080), item_size)

    for point in ([0, 0], [1919.5, 3.25], [960, 540], [12.5, 1079]):
        assert item_point_to_camera(
            camera_point_to_item(point, mapping), mapping
        ) == pytest.approx(point)


def test_empty_frame_size_is_refused():
    with pytest.raises(ValueError):
        camera_to_item_mapping((0, 0), (1280, 1080))


def test_quads_close_within_tolerance_and_in_order():
    quad = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    nudged = [[0.001, 0.0], [10.0, 0.004], [10.0, 10.0], [0.0, 10.0]]

    assert quads_close(quad, nudged)
    assert not quads_close(quad, [[1.0, 0.0], *quad[1:]])
    assert not quads_close(quad, quad[1:] + quad[:1])
    assert quads_close(None, None)
    assert not quads_close(quad, None)
