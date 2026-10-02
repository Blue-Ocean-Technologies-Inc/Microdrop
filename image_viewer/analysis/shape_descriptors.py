# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Shape descriptors of the droplet inside one ROI, from OpenCV moments.

Pure numpy/cv2 and Qt-free, so the pane's spawned stats workers can import
it: ``describe_droplet`` maps one (image, ROI mask) pair to a dict of
scalars, and ``roi_shape_stats`` is the subset ``compute_image_stats``
stores beside each ROI's intensities. The shape-moments prototype
(``examples/shape_moments``) reads every descriptor from here too.

The droplet is segmented with Otsu's threshold computed from the ROI's
own pixels only, then the largest external contour is taken (holes and
smaller specks are ignored). Every descriptor is computed from that
contour's polygon moments.

Descriptors, in plain language:

- ``area`` — droplet area in px² (the contour's polygon area). Unlike the
  pane's existing "Area" stat (the ROI's own pixel count) this follows the
  droplet, not the drawn ROI.
- ``centroid_x`` / ``centroid_y`` — the droplet's centre of mass in image
  pixels; drifts when the droplet moves inside its ROI.
- ``axis_ratio`` — major / minor axis of the moment-equivalent ellipse,
  always >= 1. 1.0 is round (or any shape with equal spread in every
  direction, e.g. a square); rises as the droplet stretches. 2.0 means
  twice as long as wide.
- ``eccentricity`` — the same ellipse's eccentricity, 0 (circle) to
  1 (a line). sqrt(1 - 1/axis_ratio²): carries the same information as
  ``axis_ratio`` on a compressed scale.
- ``orientation_deg`` — angle of the major axis from the image x axis,
  -90..90, positive clockwise on screen (image y points down; the same
  convention as ``cv2.ellipse``). Meaningless (noise) when the droplet is
  round; wraps from +90 to -90.
- ``circularity`` — 4πA / P². 1.0 for a perfect circle; drops for
  elongation AND for a ragged or lumpy outline (a 2:1 ellipse is ~0.84).
  P is ``cv2.arcLength`` of the contour simplified by
  ``PERIMETER_SMOOTHING_PX``: the raw pixel staircase overstates the
  perimeter, and a digitised circle would read ~0.90 instead of ~0.98.
- ``solidity`` — A / convex-hull area. 1.0 for any convex shape (circle,
  ellipse, rotated or not); drops only when the outline gains dents,
  bumps or necks — the "irregular" signal, blind to plain elongation.
- ``extent`` — A / axis-aligned bounding-box area. π/4 ≈ 0.785 for a
  circle; depends on orientation, so it changes when a droplet only
  rotates (included for comparison, not recommended).
- ``hu1`` .. ``hu7`` — the seven Hu invariant moments, log-scaled as
  -sign(h)·log10|h| (the usual presentation). Unchanged by translation,
  scale and rotation.
- ``shape_deviation`` — ONE "how much has the shape changed since the
  start" number: the Euclidean distance between a frame's
  root-normalised Hu vector and a reference frame's (normally the ROI's
  first frame). 0 when the shape is the same, whatever its size,
  position or rotation; ~0.6 for a circle that grew a large lobe, ~1.2
  for a circle stretched to 2.5:1. Each Hu moment is taken to the root
  that makes it scale like a second moment (sign kept) and the vector is
  scaled so a disk's hu1 is 1 — so the terms are comparable and a value
  near 0 stays near 0.
- ``hu_log_deviation`` — the same distance over the log-scaled Hu
  vector, kept for comparison. NOT recommended: for round or elliptical
  droplets hu2..hu7 are ~0, and log10 of ~0 is pure pixel noise, so a
  droplet that does not change at all reads 0.5..2.

Both deviations need a reference frame, so they are series quantities
(``add_shape_deviation``), not per-image ones.

Every value is NaN when the ROI is empty, has no contrast, or yields no
contour of at least ``min_area_px``.
"""

# Standard library imports.
import math

# Third-party imports.
import cv2
import numpy as np

# Local imports.
from .consts import MASK_ON

#: Scalar descriptor keys, in CSV / plot order.
SCALAR_DESCRIPTORS = (
    "area",
    "centroid_x",
    "centroid_y",
    "axis_ratio",
    "eccentricity",
    "orientation_deg",
    "circularity",
    "solidity",
    "extent",
)

#: Log-scaled Hu moment keys.
HU_KEYS = tuple(f"hu{index}" for index in range(1, 8))

#: Key of the root-normalised Hu vector (``root_hu``) in a descriptor
#: dict and in the pane's stats — what ``shape_deviation`` compares.
HU_ROOT_KEY = "hu_root"

#: Shape scalars the pane stores per ROI per image beside its
#: intensities, and the full stored set with the Hu vector (see
#: ``roi_shape_stats``). Shape change is not stored: it needs a
#: reference image, so the plot derives it from the Hu vectors.
ROI_SHAPE_STATS = (
    "circularity",
    "axis_ratio",
    "eccentricity",
    "solidity",
    "extent",
    "orientation_deg",
)
ROI_SHAPE_KEYS = ROI_SHAPE_STATS + (HU_ROOT_KEY,)

#: Series descriptors, measured against the ROI's reference frame.
DEVIATION_DESCRIPTORS = ("shape_deviation", "hu_log_deviation")

#: Root taken of each Hu moment so all seven scale like a second-order
#: moment: hu1 is second order, hu2 and hu3/hu4 are squares, hu5/hu7
#: fourth powers and hu6 a cube of the underlying normalised moments.
HU_ROOTS = (1, 2, 2, 2, 4, 3, 4)

#: hu1 of a uniform disk, 1/(2π): the root-normalised vector is divided
#: by it so a disk reads (1, 0, 0, ...).
DISK_HU1 = 1.0 / (2.0 * math.pi)

#: Contour simplification tolerance (px) before measuring the perimeter.
PERIMETER_SMOOTHING_PX = 1.0

#: Smallest contour (px²) accepted as a droplet rather than noise.
DEFAULT_MIN_AREA_PX = 20.0

#: Smallest |h| fed to the log scaling, so an exactly-zero moment maps
#: to a finite value instead of infinity.
_HU_FLOOR = 1e-30


def nan_descriptors():
    """Every descriptor as NaN — the result for an ROI with no droplet."""
    descriptors = {key: math.nan for key in SCALAR_DESCRIPTORS + HU_KEYS}
    descriptors["contour"] = None
    descriptors[HU_ROOT_KEY] = None

    return descriptors


def _to_uint8(pixels):
    """``pixels`` stretched to 0..255 uint8 (Otsu in cv2 is 8-bit only;
    16-bit camera frames are rescaled over the ROI's own range)."""
    if pixels.dtype == np.uint8:
        return pixels

    low, high = float(pixels.min()), float(pixels.max())
    scaled = (pixels.astype(np.float64) - low) * (255.0 / (high - low))

    return scaled.astype(np.uint8)


def segment_droplet(image, mask, polarity="bright"):
    """The binary droplet mask (MASK_ON = droplet) inside ``mask``, by
    Otsu's threshold over the ROI's pixels only. ``polarity`` is "bright"
    for a droplet brighter than its surroundings (fluorescence) or "dark"
    for one darker (back-lit). None when the ROI is empty or flat."""
    inside = mask == MASK_ON
    pixels = image[inside]

    if pixels.size == 0 or pixels.min() == pixels.max():
        return None

    pixels = _to_uint8(pixels)
    threshold, _ = cv2.threshold(
        pixels.reshape(-1, 1), 0, MASK_ON, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    foreground = pixels > threshold if polarity == "bright" else pixels <= threshold

    binary = np.zeros(image.shape[:2], dtype=np.uint8)
    binary[inside] = np.where(foreground, MASK_ON, 0)

    return binary


def largest_contour(binary):
    """The largest external contour of ``binary``, or None."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    if not contours:
        return None

    return max(contours, key=cv2.contourArea)


def log_hu(hu):
    """The seven Hu moments ``hu``, log-scaled -sign(h)·log10|h|."""
    return -np.sign(hu) * np.log10(np.maximum(np.abs(hu), _HU_FLOOR))


def root_hu(hu):
    """The seven Hu moments ``hu``, each to its ``HU_ROOTS`` root (sign
    kept), in units of a disk's hu1."""
    roots = np.array(HU_ROOTS, dtype=np.float64)

    return np.sign(hu) * np.abs(hu) ** (1.0 / roots) / DISK_HU1


def ellipse_axes(moments):
    """(axis_ratio, eccentricity, orientation_deg) of the ellipse with
    the same second central moments as the shape."""
    mu20 = moments["mu20"] / moments["m00"]
    mu02 = moments["mu02"] / moments["m00"]
    mu11 = moments["mu11"] / moments["m00"]

    # Eigenvalues of the covariance matrix [[mu20, mu11], [mu11, mu02]].
    half_trace = (mu20 + mu02) / 2.0
    spread = math.sqrt(((mu20 - mu02) / 2.0) ** 2 + mu11**2)
    major, minor = half_trace + spread, half_trace - spread

    if minor <= 0:
        return math.inf, 1.0, math.nan

    axis_ratio = math.sqrt(major / minor)
    eccentricity = math.sqrt(1.0 - minor / major)
    orientation_deg = math.degrees(0.5 * math.atan2(2.0 * mu11, mu20 - mu02))

    return axis_ratio, eccentricity, orientation_deg


def describe_contour(contour):
    """Every descriptor of one droplet contour (see the module docstring)."""
    moments = cv2.moments(contour)
    area = moments["m00"]
    perimeter = cv2.arcLength(
        cv2.approxPolyDP(contour, PERIMETER_SMOOTHING_PX, True), True
    )
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    _x, _y, box_width, box_height = cv2.boundingRect(contour)
    axis_ratio, eccentricity, orientation_deg = ellipse_axes(moments)

    descriptors = {
        "area": area,
        "centroid_x": moments["m10"] / area,
        "centroid_y": moments["m01"] / area,
        "axis_ratio": axis_ratio,
        "eccentricity": eccentricity,
        "orientation_deg": orientation_deg,
        "circularity": 4.0 * math.pi * area / perimeter**2,
        "solidity": area / hull_area if hull_area else math.nan,
        "extent": area / (box_width * box_height),
    }
    hu = cv2.HuMoments(moments).flatten()
    descriptors.update(zip(HU_KEYS, log_hu(hu).tolist()))
    descriptors["contour"] = contour
    descriptors[HU_ROOT_KEY] = root_hu(hu)

    return descriptors


def describe_droplet(image, mask, polarity="bright", min_area_px=DEFAULT_MIN_AREA_PX):
    """Shape descriptors of the droplet inside one ROI.

    Parameters
    ----------
    image : ndarray
        Grey frame, uint8 or uint16.
    mask : ndarray
        uint8 ROI mask, MASK_ON inside (the pane's ``interior_mask``).
    polarity : str
        "bright" or "dark" droplet, see ``segment_droplet``.
    min_area_px : float
        Contours smaller than this are treated as no droplet.

    Returns
    -------
    dict
        ``SCALAR_DESCRIPTORS`` + ``HU_KEYS`` floats (NaN when there is no
        droplet), plus "contour" (the cv2 contour, or None) for drawing
        and "hu_root" (the root-normalised Hu vector, or None) for
        ``shape_deviation``.
    """
    binary = segment_droplet(image, mask, polarity)

    if binary is None:
        return nan_descriptors()

    contour = largest_contour(binary)

    if contour is None or cv2.contourArea(contour) < min_area_px:
        return nan_descriptors()

    return describe_contour(contour)


def shape_deviation(descriptors, reference):
    """Distance between two descriptor (or pane stats) dicts'
    root-normalised Hu vectors — 0 for the same shape at any size,
    position or rotation. NaN when either side has no droplet."""
    current = descriptors.get(HU_ROOT_KEY)
    baseline = reference.get(HU_ROOT_KEY)

    if current is None or baseline is None:
        return math.nan

    return float(np.linalg.norm(np.subtract(current, baseline)))


def hu_log_deviation(descriptors, reference):
    """Distance between two descriptor dicts' log-Hu vectors (comparison
    only — noisy for round droplets, see the module docstring)."""
    current = np.array([descriptors[key] for key in HU_KEYS])
    baseline = np.array([reference[key] for key in HU_KEYS])

    return float(np.linalg.norm(current - baseline))


def add_shape_deviation(series):
    """Set ``DEVIATION_DESCRIPTORS`` on every descriptor dict of one ROI's
    time-ordered ``series``, against its first frame with a droplet (all
    NaN when no frame has one)."""
    reference = next(
        (descriptors for descriptors in series if descriptors["contour"] is not None),
        None,
    )

    for descriptors in series:
        if reference is None:
            descriptors.update(dict.fromkeys(DEVIATION_DESCRIPTORS, math.nan))
            continue

        descriptors["shape_deviation"] = shape_deviation(descriptors, reference)
        descriptors["hu_log_deviation"] = hu_log_deviation(descriptors, reference)

    return series


def roi_shape_stats(image, mask):
    """``ROI_SHAPE_KEYS`` of the droplet inside one ROI, JSON-ready for
    the stats store: floats (NaN without a droplet) and the Hu vector as
    a list, or None.

    Measured on the mask's bounding box rather than the whole frame —
    the same pixels, without a frame-sized binary per ROI. Bright
    droplet on a darker background (``segment_droplet``'s default)."""
    left, top, width, height = cv2.boundingRect(mask)
    crop = (slice(top, top + height), slice(left, left + width))
    descriptors = describe_droplet(image[crop], mask[crop])
    hu_root = descriptors[HU_ROOT_KEY]

    stats = {key: float(descriptors[key]) for key in ROI_SHAPE_STATS}
    stats[HU_ROOT_KEY] = None if hu_root is None else hu_root.tolist()

    return stats
