# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure per-image ROI statistics (Qt-free and importable by spawned
worker processes): each ROI's interior mask, the background annulus
outside it, the inner part of the interior that is measured, and the
summary stats of the masked pixels. Ported from the standalone
fluorescence app's ROIManager (image_tools.py); the ring and the inset
are this app's own, built from distance transforms so the ring never
overlaps the shape and the inset never leaves it."""

# Standard library imports.
import math
import os

# Third-party imports.
import cv2
import numpy as np

# Local imports.
from .consts import (
    MASK_ON,
    MEASURE_INSIDE_PERCENT_DEFAULT,
    MIN_POLYGON_POINTS,
    OUTLINE_STATS_PREFIX,
    RING_GAP_PX,
    RING_THICKNESS_PX,
)
from .perspective import warp_frame
from .roi_geometry import normalize, outline_of
from .shape_descriptors import ROI_SHAPE_KEYS, roi_shape_stats

#: Stats computed for every mask, in column order.
STAT_NAMES = ("mean", "std", "median", "min", "max", "count")

#: Sweep passed to cv2.ellipse for a whole ellipse rather than an arc.
_FULL_SWEEP_DEGREES = (0, 360)

#: How far a rolling ball's estimate is shrunk before it is computed,
#: by ball radius: (radius at or below which, shrink factor). ImageJ's
#: own ladder, and for its reason — the estimate can only follow the
#: background as finely as the ball is wide, so shrinking below that
#: costs nothing and saves the work, while a small ball needs the
#: pixels kept or the shrink becomes the coarser of the two.
_SHRINK_LADDER = ((10, 1), (30, 2), (100, 4))
_SHRINK_FACTOR_MAX = 8


def interior_mask(shape, kind, geometry):
    """The uint8 mask (MASK_ON inside) of one ROI on an image of ``shape``
    (height, width); cv2 clips to the image bounds. Geometry is
    normalized first, so a pre-rotation config still computes the same
    pixels it always did."""
    interior = np.zeros(shape, dtype=np.uint8)
    kind, geometry = normalize(kind, geometry)
    if kind == "ellipse":
        centre_x, centre_y, radius_x, radius_y, angle = geometry
        centre = (int(round(centre_x)), int(round(centre_y)))
        if radius_x == radius_y and angle == 0.0:
            # cv2 does not rasterize the same disk both ways (~3% more
            # pixels through ellipse at r=30), so a plain circle keeps
            # the call every already-cached statistic was computed
            # with: reopening an experiment cannot shift its numbers,
            # nor leave one series half in each convention.
            cv2.circle(interior, centre, int(round(radius_x)), MASK_ON, cv2.FILLED)
        else:
            axes = (int(round(radius_x)), int(round(radius_y)))
            cv2.ellipse(
                interior, centre, axes, angle, *_FULL_SWEEP_DEGREES, MASK_ON, cv2.FILLED
            )
    else:
        polygon = outline_of(kind, geometry)
        if len(polygon):
            cv2.fillPoly(interior, [np.round(polygon).astype(np.int32)], MASK_ON)
    return interior


def negative_union(shape, negatives):
    """The uint8 mask (MASK_ON inside) covering every negative mask in
    ``negatives`` ((kind, geometry), ...) on an image of ``shape`` —
    all-zero when there are none."""
    union = np.zeros(shape, dtype=np.uint8)

    for kind, geometry in negatives:
        cv2.bitwise_or(union, interior_mask(shape, kind, geometry), union)

    return union


def _disk(radius):
    """A disk-shaped structuring element of ``radius``. Odd-sized —
    diameter plus the centre pixel — so it has a centre to sit on."""
    size = 2 * radius + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def ring_mask(interior, gap_px=RING_GAP_PX, thickness_px=RING_THICKNESS_PX):
    """The annulus outside ``interior``: every pixel more than gap and
    at most gap + thickness from the shape, by exact Euclidean distance.

    A distance transform gives each pixel its distance to the nearest
    interior pixel in one O(pixels) pass, so the ring is the annulus a
    disk dilation would grow, at a cost that does not climb with the
    gap — a disk kernel costs O(radius²) per pixel, and the large gaps
    a wide frame needs to clear a droplet's halo took seconds per ROI.
    Interior pixels sit at distance 0, so even with gap 0 the inner
    edge is the shape's own boundary and the ring can never contain
    interior pixels. It works for a traced contour as readily as an
    ellipse."""
    gap_px = max(int(gap_px), 0)
    thickness_px = max(int(thickness_px), 1)
    ring = np.zeros_like(interior)
    rows, columns = np.nonzero(interior)

    if not len(rows):
        return ring

    # Measure on a crop, so cost tracks the ROI rather than the frame.
    # One pixel past the ring's own reach, so nothing in the ring is
    # clipped by the crop's edge.
    pad = gap_px + thickness_px + 1
    top = max(int(rows.min()) - pad, 0)
    bottom = min(int(rows.max()) + pad + 1, interior.shape[0])
    left = max(int(columns.min()) - pad, 0)
    right = min(int(columns.max()) + pad + 1, interior.shape[1])
    outside = cv2.bitwise_not(interior[top:bottom, left:right])

    # Distance from each outside pixel to the nearest interior one.
    distance = cv2.distanceTransform(outside, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    band = (distance > gap_px) & (distance <= gap_px + thickness_px)
    ring[top:bottom, left:right][band] = MASK_ON

    return ring


def inset_mask(interior, inside_percent=MEASURE_INSIDE_PERCENT_DEFAULT):
    """``interior`` less a band of constant width along its boundary:
    the part of the ROI whose intensity is measured.

    The band is a share of the shape's equivalent radius, the radius of
    the circle with the same area::

        inset_px = round((1 - inside_percent / 100) * sqrt(area_px / pi))

    so for a circle, 90 keeps the concentric circle at 90% of its
    radius, and for any other shape it is the outer ring run in
    reverse: every interior pixel more than inset_px from the nearest
    exterior pixel, by exact Euclidean distance. The frame's edge
    counts as exterior, so a shape cut off by it is inset there too.
    100 returns ``interior`` itself."""
    if inside_percent >= MEASURE_INSIDE_PERCENT_DEFAULT:
        return interior

    rows, columns = np.nonzero(interior)

    if not len(rows):
        return interior

    equivalent_radius = math.sqrt(len(rows) / math.pi)
    inset_px = round((1 - inside_percent / 100) * equivalent_radius)

    # Measure on the shape's bounding box, so cost tracks the ROI rather
    # than the frame, bordered by one exterior pixel so every interior
    # pixel has an exterior one to be measured from.
    top, bottom = int(rows.min()), int(rows.max()) + 1
    left, right = int(columns.min()), int(columns.max()) + 1
    crop = cv2.copyMakeBorder(
        interior[top:bottom, left:right], 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0
    )

    # Distance from each interior pixel to the nearest exterior one.
    distance = cv2.distanceTransform(crop, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    inset = np.zeros_like(interior)
    inset[top:bottom, left:right][distance[1:-1, 1:-1] > inset_px] = MASK_ON

    return inset


def _contours_of(mask):
    """The boundaries of ``mask`` as (N, 2) image-pixel arrays, each
    with enough points to draw as a closed outline."""
    found, _hierarchy = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    return [
        points.reshape(-1, 2).astype(float)
        for points in found
        if len(points) >= MIN_POLYGON_POINTS
    ]


def roi_masks(
    shape, kind, geometry, gap_px=RING_GAP_PX, thickness_px=RING_THICKNESS_PX
):
    """(interior, ring) uint8 masks for one ROI: the shape itself and
    the background annulus outside it."""
    interior = interior_mask(shape, kind, geometry)
    return interior, ring_mask(interior, gap_px, thickness_px)


def ring_contours(
    shape,
    kind,
    geometry,
    gap_px=RING_GAP_PX,
    thickness_px=RING_THICKNESS_PX,
    negatives=(),
):
    """The annulus's boundaries as (N, 2) image-pixel arrays — the
    canvas draws these, taken from the very mask that is averaged, so
    the two cannot disagree. ``negatives`` are cut out of it, as
    compute_image_stats cuts them."""
    _interior, ring = roi_masks(shape, kind, geometry, gap_px, thickness_px)

    if negatives:
        ring = cv2.subtract(ring, negative_union(shape, negatives))

    return _contours_of(ring)


def inset_contours(
    shape, kind, geometry, inside_percent=MEASURE_INSIDE_PERCENT_DEFAULT
):
    """The boundary of the measured part of one ROI (inset_mask) as
    (N, 2) image-pixel arrays — taken from the very mask whose
    intensity is averaged, like ring_contours."""
    interior = interior_mask(shape, kind, geometry)

    return _contours_of(inset_mask(interior, inside_percent))


def _shrink_factor(radius_px):
    """How far to shrink the image before rolling the ball over it.

    ImageJ's own ladder, and for its reason: the estimate can only
    follow the background as finely as the ball is wide, so shrinking
    below that costs nothing and saves the work. It backs off for small
    radii, where the shrink would start to be the coarser of the two."""
    for limit, factor in _SHRINK_LADDER:
        if radius_px <= limit:
            return factor
    return _SHRINK_FACTOR_MAX


def rolling_ball_background(array, radius_px):
    """The uneven background under ``array``, by grey-scale opening with
    a disk — the rolling-ball estimate ImageJ popularised.

    Measured against a known background, estimating it on a shrunken
    image and interpolating back up is both ~13x faster and closer than
    working at full scale: the interpolation gives a smooth surface
    where the full-scale opening follows the flat facets of the disk.

    Only the ESTIMATE is shrunk. It is subtracted from every original
    pixel, so an ROI still averages exactly the pixels it covers."""
    radius_px = max(int(radius_px), 1)
    factor = _shrink_factor(radius_px)
    working = array
    if factor > 1:
        working = cv2.resize(
            array, None, fx=1.0 / factor, fy=1.0 / factor, interpolation=cv2.INTER_AREA
        )
    kernel = _disk(max(radius_px // factor, 1))
    background = cv2.morphologyEx(working, cv2.MORPH_OPEN, kernel)
    if factor > 1:
        background = cv2.resize(
            background, (array.shape[1], array.shape[0]), interpolation=cv2.INTER_LINEAR
        )
    return background


def subtract_rolling_ball(array, radius_px):
    """``array`` less its rolling-ball background, clipped at zero and
    kept in the image's own dtype — the numbers stay counts, so a
    16-bit frame is still measured as one."""
    background = rolling_ball_background(array, radius_px)
    # cv2.subtract saturates instead of wrapping, which matters: an
    # unsigned pixel below its background would otherwise come back
    # near the top of the range.
    return cv2.subtract(array, background)


def masked_stats(array, mask):
    """mean/std/median/min/max/count of ``array`` under ``mask`` — NaN
    stats with count 0 for an empty mask (ROI fully outside the image)."""
    pixels = array[mask == MASK_ON]
    if pixels.size == 0:
        stats = {name: float("nan") for name in STAT_NAMES}
        stats["count"] = 0.0
        return stats
    return {
        "mean": float(np.mean(pixels)),
        "std": float(np.std(pixels)),
        "median": float(np.median(pixels)),
        "min": float(np.min(pixels)),
        "max": float(np.max(pixels)),
        "count": float(np.count_nonzero(mask)),
    }


def stats_are_current(stats):
    """True when ``stats`` (one cached (image, ROI) entry, or None)
    carries everything a fresh compute stores — an entry cached before
    the shape stats existed is measured again rather than left showing
    gaps for them."""
    return stats is not None and all(key in stats for key in ROI_SHAPE_KEYS)


def compute_image_stats(
    image_path,
    effective_rois,
    gap_px=RING_GAP_PX,
    thickness_px=RING_THICKNESS_PX,
    ball_radius_px=0,
    perspective=(),
    negatives=(),
    inside_percent=MEASURE_INSIDE_PERCENT_DEFAULT,
):
    """Stats for every ROI on one image — the process-pool work unit.

    ``effective_rois``: roi_id -> (kind, geometry tuple), the geometries
    in force for THIS image. Returns {"path", "mtime", "stats":
    {roi_id: {mean..., outline_mean...}}, "error"}; a load failure fills
    "error" and leaves "stats" empty (the caller counts it as failed).
    Every ROI's background ring excludes every other ROI's interior: a
    droplet sitting close by is not background, however near it is.

    ``ball_radius_px`` above 0 flattens the frame with the rolling-ball
    estimate BEFORE any ROI is measured, so every stat downstream — the
    ring included — is read off the corrected image.

    ``perspective`` (a flattened homography, () for none) warps the frame
    first, so the ROIs — drawn on the warped frame — land where they were
    drawn.

    The droplet's shape (``roi_shape_stats``) is read off the same
    corrected frame, inside the whole interior mask.

    ``inside_percent`` below 100 takes the intensity stats, ``count``
    included, over the inner part of each ROI only (inset_mask), leaving
    out the band along the boundary where a droplet's bright rim sits.
    The ring is still grown from the whole interior, and the shape stats
    still read the whole interior: both describe the droplet, not the
    region sampled inside it.

    ``negatives`` ((kind, geometry), ...) are negative masks: their
    union is cut out of every ROI's interior before anything is
    measured, and out of every ring — excluded pixels are not
    background either. The ring is still grown from the ROI's whole
    interior, so its outer edge never follows a hole. An ROI covered
    entirely measures count 0 and NaN everywhere else."""
    result = {"path": str(image_path), "mtime": 0.0, "stats": {}, "error": None}
    try:
        result["mtime"] = os.path.getmtime(image_path)
        array = cv2.imread(str(image_path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
        if array is None:
            raise ValueError("unreadable image")
        array = warp_frame(array, perspective)

        if ball_radius_px:
            array = subtract_rolling_ball(array, ball_radius_px)

        interiors, rings = {}, {}

        for roi_id, (kind, geometry) in effective_rois.items():
            interiors[roi_id], rings[roi_id] = roi_masks(
                array.shape[:2], kind, geometry, gap_px, thickness_px
            )

        union = np.zeros(array.shape[:2], dtype=np.uint8)

        for interior in interiors.values():
            cv2.bitwise_or(union, interior, union)

        excluded = negative_union(array.shape[:2], negatives)

        for roi_id, ring in rings.items():
            interior = interiors[roi_id]
            others = cv2.subtract(union, interior)
            ring[others == MASK_ON] = 0
            ring[excluded == MASK_ON] = 0
            effective = cv2.subtract(interior, excluded)
            measured = cv2.subtract(inset_mask(interior, inside_percent), excluded)

            stats = masked_stats(array, measured)

            for name, value in masked_stats(array, ring).items():
                stats[OUTLINE_STATS_PREFIX + name] = value

            stats.update(roi_shape_stats(array, effective))
            result["stats"][roi_id] = stats
    except Exception as error:
        result["error"] = str(error)
        result["stats"] = {}
    return result
