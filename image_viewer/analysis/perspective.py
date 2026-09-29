# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Perspective correction for captured frames: the 4-point homography the
user defines (device-viewer camera-alignment parity) and the warp every
consumer of pixel data runs before reading a frame. Qt-free, so the stats
process pool can run it."""

# Standard library imports.
import math

# Third-party imports.
import cv2
import numpy as np


def perspective_matrix(source_quad, target_quad):
    """The 3x3 homography taking ``source_quad`` onto ``target_quad`` (four
    (x, y) image-pixel points each), flattened row-major into a tuple of
    nine floats — hashable, picklable and JSON-able, so it can ride the
    stats cache key and the process-pool work item as it stands. () when
    the quads are incomplete or degenerate."""

    if len(source_quad) != 4 or len(target_quad) != 4:
        return ()

    matrix = cv2.getPerspectiveTransform(
        np.array(source_quad, dtype=np.float32),
        np.array(target_quad, dtype=np.float32),
    )

    if not np.all(np.isfinite(matrix)) or abs(np.linalg.det(matrix)) < 1e-12:
        return ()

    return tuple(float(value) for value in matrix.ravel())


def warp_frame(array, matrix):
    """``array`` warped by the flattened homography ``matrix`` into a frame
    of the same size and dtype (uncovered pixels read 0); the frame itself
    when ``matrix`` is ()."""

    if not matrix or array is None:
        return array

    height, width = array.shape[:2]

    return cv2.warpPerspective(
        array,
        np.array(matrix, dtype=np.float64).reshape(3, 3),
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def rotated_quad(quad, degrees):
    """``quad`` rotated by ``degrees`` about its centroid (the device
    viewer's rotate-output buttons)."""

    if not quad:
        return list(quad)

    centre_x = sum(x for x, _y in quad) / len(quad)
    centre_y = sum(y for _x, y in quad) / len(quad)
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)

    return [
        (
            centre_x + (x - centre_x) * cosine - (y - centre_y) * sine,
            centre_y + (x - centre_x) * sine + (y - centre_y) * cosine,
        )
        for x, y in quad
    ]


def embedding_id(path, matrix):
    """The AI encoder's cache key for ``path`` as warped by ``matrix``: a
    warped frame is a different image to encode than the raw file."""
    return f"{path}@{hash(tuple(matrix)):x}" if matrix else str(path)
