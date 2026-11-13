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
from ..consts import (
    ALIGNMENT_ASPECT_RATIO_TOLERANCE,
    ALIGNMENT_DEVICE_RENDER_MARGIN,
    ALIGNMENT_QUAD_TOLERANCE,
)


def camera_to_item_mapping(frame_size, item_size, keep_aspect_ratio=True):
    """Return the affine camera-pixel -> item mapping as
    ``(scale_x, scale_y, offset_x, offset_y)``.

    Parameters
    ----------
    frame_size, item_size : (width, height)
        The camera's native frame size and the video item's size.
    keep_aspect_ratio : bool
        Letterbox the frame (Qt's KeepAspectRatio) rather than stretch it.

    Raises ``ValueError`` for an empty frame or item size (the mapping
    could not be inverted).
    """
    frame_width, frame_height = frame_size
    item_width, item_height = item_size

    if not valid_frame_size(frame_size):
        raise ValueError(f"empty camera frame size {frame_size}")

    if item_width <= 0 or item_height <= 0:
        raise ValueError(f"empty video item size {item_size}")

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


def valid_frame_size(size):
    """Whether ``size`` is a usable (width, height): two positive numbers."""
    return (
        size is not None
        and len(size) == 2
        and all(isinstance(side, (int, float)) and side > 0 for side in size)
    )


def same_aspect_ratio(size, other, tolerance=ALIGNMENT_ASPECT_RATIO_TOLERANCE):
    """Whether two valid frame sizes have the same picture shape: their
    width/height ratios differ by less than ``tolerance`` (relative)."""
    ratio = size[0] / size[1]
    other_ratio = other[0] / other[1]

    return abs(ratio - other_ratio) <= tolerance * other_ratio


def camera_quad_in_frame(quad, saved_size, live_size):
    """Return ``quad`` (pixels of a ``saved_size`` frame) in pixels of a
    ``live_size`` frame, scaled axis by axis; None when the picture shape
    differs or either size is unusable, since no scaling places it then.

    An unknown ``saved_size`` (None) leaves the quad as it is.
    """

    if saved_size is None:
        return [list(point) for point in quad]

    if not (valid_frame_size(saved_size) and valid_frame_size(live_size)):
        return None

    if not same_aspect_ratio(saved_size, live_size):
        return None

    scale_x = live_size[0] / saved_size[0]
    scale_y = live_size[1] / saved_size[1]

    return [[x * scale_x, y * scale_y] for x, y in quad]


def device_render_rect(bounding_rect):
    """Return a device's scene rect as the alignment window renders it:
    its electrodes' bounding rect ``[x, y, w, h]`` with a margin of
    ALIGNMENT_DEVICE_RENDER_MARGIN of its larger side all round."""
    x, y, width, height = bounding_rect
    margin = ALIGNMENT_DEVICE_RENDER_MARGIN * max(width, height)

    return [x - margin, y - margin, width + 2 * margin, height + 2 * margin]


def quad_between_scene_rects(quad, source_rect, target_rect):
    """Return ``quad`` (scene points of a device whose scene rect is
    ``source_rect``) at the same relative place in ``target_rect``, or None
    when either rect is unknown or empty. Rects are ``[x, y, w, h]``."""

    if source_rect is None or target_rect is None:
        return None

    source_x, source_y, source_width, source_height = source_rect
    target_x, target_y, target_width, target_height = target_rect

    if min(source_width, source_height, target_width, target_height) <= 0:
        return None

    return [
        [
            target_x + (x - source_x) / source_width * target_width,
            target_y + (y - source_y) / source_height * target_height,
        ]
        for x, y in quad
    ]
