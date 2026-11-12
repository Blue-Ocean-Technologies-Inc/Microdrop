# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure camera-alignment geometry: the RAW camera pixel <-> video-item
mapping and quad comparison, free of Qt so it is unit-testable alone.

The video item is scene-sized and shows the frame letterboxed (Qt's
default KeepAspectRatio): scaled uniformly to fit, centred along the axis
with room to spare. With IgnoreAspectRatio it is stretched instead."""

# Local imports.
from ..consts import ALIGNMENT_QUAD_TOLERANCE


def camera_to_item_mapping(frame_size, item_size, keep_aspect_ratio=True):
    """Return the affine camera-pixel -> item mapping as
    ``(scale_x, scale_y, offset_x, offset_y)``.

    Parameters
    ----------
    frame_size, item_size : (width, height)
        The camera's native frame size and the video item's size.
    keep_aspect_ratio : bool
        Letterbox the frame (Qt's KeepAspectRatio) rather than stretch it.

    Raises ``ValueError`` for an empty frame size.
    """
    frame_width, frame_height = frame_size
    item_width, item_height = item_size

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError(f"empty camera frame size {frame_size}")

    if not keep_aspect_ratio:
        return item_width / frame_width, item_height / frame_height, 0.0, 0.0

    scale = min(item_width / frame_width, item_height / frame_height)
    offset_x = (item_width - frame_width * scale) / 2
    offset_y = (item_height - frame_height * scale) / 2

    return scale, scale, offset_x, offset_y


def camera_point_to_item(point, mapping):
    """Map a raw camera pixel ``[x, y]`` into item coordinates."""
    scale_x, scale_y, offset_x, offset_y = mapping

    return [offset_x + point[0] * scale_x, offset_y + point[1] * scale_y]


def item_point_to_camera(point, mapping):
    """Map an item-coordinate ``[x, y]`` back to raw camera pixels."""
    scale_x, scale_y, offset_x, offset_y = mapping

    return [(point[0] - offset_x) / scale_x, (point[1] - offset_y) / scale_y]


def quads_close(quad, other, tolerance=ALIGNMENT_QUAD_TOLERANCE):
    """Return whether two quads match point for point, in order, within
    ``tolerance`` per coordinate. A missing quad matches only another."""

    if quad is None or other is None:
        return quad is None and other is None

    if len(quad) != len(other):
        return False

    return all(
        abs(x - other_x) <= tolerance and abs(y - other_y) <= tolerance
        for (x, y), (other_x, other_y) in zip(quad, other)
    )
