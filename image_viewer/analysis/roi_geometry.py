# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Canonical ROI geometry: what each kind's flat float list means, how
the older shorter lists migrate onto it, and the polygons cv2 and Qt
draw from it. Qt-free (numpy only) so the worker processes that compute
statistics can import it."""

# Third-party imports.
import numpy as np

# Local imports.
from .consts import MIN_POLYGON_POINTS

#: Values in every canonical geometry list:
#:   ellipse [cx, cy, rx, ry, angle]
#:   box     [x, y, width, height, angle, corner_radius]
#:                                      (x, y = top-left corner)
#:   capsule [cx, cy, half_length, radius, angle]
#: half_length reaches the cap CENTRE, so a capsule spans
#: 2 * (half_length + radius). Angles are degrees clockwise, the
#: convention cv2.ellipse and QGraphicsItem.setRotation share in y-down
#: image coordinates.
#: A contour is the exception, and has no fixed length or angle:
#:   polygon [x1, y1, x2, y2, ...]  (rotation already in the vertices)
GEOMETRY_LENGTH = 5
GEOMETRY_LENGTHS = {"box": 6}

#: Points sampled along each rounded corner of a box. Chords cut inside
#: the true arc, so this is set where that error is under a fifth of a
#: pixel for the corner radii a 400-px frame allows.
BOX_CORNER_SAMPLES = 12

#: Points sampled along each of a capsule's semicircular caps.
#: Chord error at the radii the canvas allows stays under a
#: pixel, matching BOX_CORNER_SAMPLES' reasoning.
CAPSULE_CAP_SAMPLES = 32

#: Pre-rotation kind that could only ever be a circle.
_LEGACY_KINDS = {"circle": "ellipse"}


def normalize(kind, geometry):
    """(kind, geometry) in canonical form: "circle" becomes "ellipse"
    with equal radii, a 4-value box gains its angle and a 5-value one
    its (zero) corner radius, and canonical input passes through
    unchanged. Never raises — a corrupt entry degrades to a placeable
    shape instead of a traceback."""
    kind = _LEGACY_KINDS.get(kind, kind)
    values = [float(value) for value in geometry]
    if kind == "polygon":
        # A contour is a vertex list, so it has no fixed length to pad
        # to and no angle: rotating one rewrites its coordinates.
        return kind, values[: len(values) - len(values) % 2]
    if kind == "ellipse" and len(values) == 3:
        values = [values[0], values[1], values[2], values[2], 0.0]
    length = GEOMETRY_LENGTHS.get(kind, GEOMETRY_LENGTH)
    values = (values + [0.0] * length)[:length]
    if kind == "box":
        # Clamped here so no consumer has to defend against a radius
        # wider than the shape it rounds.
        values[5] = min(max(values[5], 0.0), min(abs(values[2]), abs(values[3])) / 2.0)
    return kind, values


def translated(kind, geometry, offset_x, offset_y):
    """``geometry`` moved by (offset_x, offset_y) — every coordinate
    pair for a contour, the anchor point for everything else."""
    kind, values = normalize(kind, geometry)
    if kind == "polygon":
        return [
            value + (offset_x if index % 2 == 0 else offset_y)
            for index, value in enumerate(values)
        ]
    values[0] += offset_x
    values[1] += offset_y
    return values


def centre_of(kind, geometry):
    """The (x, y) the shape rotates about — its middle, which the box
    stores only implicitly (it is anchored at its top-left corner)."""
    kind, values = normalize(kind, geometry)
    if kind == "polygon":
        points = np.asarray(values, dtype=float).reshape(-1, 2)
        return float(points[:, 0].mean()), float(points[:, 1].mean())
    if kind == "box":
        return values[0] + values[2] / 2.0, values[1] + values[3] / 2.0
    return values[0], values[1]


def _rotated(points, centre, angle_degrees):
    """``points`` (N, 2) turned clockwise about ``centre``."""
    radians = np.radians(float(angle_degrees))
    cosine, sine = np.cos(radians), np.sin(radians)
    matrix = np.array([[cosine, -sine], [sine, cosine]])
    centre = np.asarray(centre, dtype=float)
    return (np.asarray(points, dtype=float) - centre) @ matrix.T + centre


def _corner_arc(centre_x, centre_y, radius, start_radians):
    """One quarter-circle corner, swept clockwise in image (y-down)
    coordinates from ``start_radians``."""
    sweep = np.linspace(start_radians, start_radians + np.pi / 2.0, BOX_CORNER_SAMPLES)
    return np.column_stack(
        [centre_x + radius * np.cos(sweep), centre_y + radius * np.sin(sweep)]
    )


def box_polygon(geometry):
    """The box's outline, clockwise from its top-left: four rotated
    corners, or four sampled quarter-circle arcs once the corner radius
    is non-zero."""
    _, values = normalize("box", geometry)
    x, y, width, height, angle, corner_radius = values
    if corner_radius <= 0.0:
        points = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    else:
        right, bottom = x + width, y + height
        inset = corner_radius
        points = np.vstack(
            [
                _corner_arc(x + inset, y + inset, inset, np.pi),
                _corner_arc(right - inset, y + inset, inset, -np.pi / 2.0),
                _corner_arc(right - inset, bottom - inset, inset, 0.0),
                _corner_arc(x + inset, bottom - inset, inset, np.pi / 2.0),
            ]
        )
    return _rotated(points, centre_of("box", values), angle)


def capsule_polygon(geometry, samples=CAPSULE_CAP_SAMPLES):
    """The stadium outline: both semicircular caps sampled with
    ``samples`` points each and joined by the flanks, in one winding."""
    _, values = normalize("capsule", geometry)
    centre_x, centre_y, half_length, radius, angle = values
    sweep = np.linspace(-np.pi / 2.0, np.pi / 2.0, samples)
    right = np.column_stack(
        [half_length + radius * np.cos(sweep), radius * np.sin(sweep)]
    )
    left = np.column_stack(
        [-half_length - radius * np.cos(sweep), -radius * np.sin(sweep)]
    )
    points = np.vstack([right, left]) + (centre_x, centre_y)
    return _rotated(points, (centre_x, centre_y), angle)


def outline_of(kind, geometry):
    """The polygon cv2 fills and strokes for a box, capsule or
    contour, (N, 2) in image pixels. Empty for a contour with too few
    vertices — callers draw nothing rather than raising."""
    kind, values = normalize(kind, geometry)
    if kind == "box":
        return box_polygon(values)
    if kind == "capsule":
        return capsule_polygon(values)
    points = np.asarray(values, dtype=float).reshape(-1, 2)
    if len(points) < MIN_POLYGON_POINTS:
        return np.empty((0, 2), dtype=float)
    return points
