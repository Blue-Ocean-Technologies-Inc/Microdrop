# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Rim tracer: follows a droplet from frame to frame by the thin bright
rim at its edge, with no AI model (numpy + cv2 only, Qt-free).

Each frame, per droplet:

1. RIM_RAYS rays are cast from the droplet's centre over its median-
   blurred neighbourhood (polar resampling, 1 px per radial step).
2. Every point on a ray is scored for being the rim: a difference of
   Gaussians ACROSS the rim (along the ray, scaled to the rim width)
   smoothed ALONG it (across rays), so the continuous rim survives while
   isolated specks and speckle clouds average away; plus a signed step
   term that rewards intensity falling outward (the glowing interior
   inside the rim) and penalises it rising outward (the interference
   rings atop the reflection under a droplet have their dark gap
   inside). Scores are in robust-noise units, clipped.
3. A dynamic programme picks the best closed contour r(angle): it may
   move at most a few px per ray, pays for each px it does, and stays
   within a search window around the previous frame's radii — a few px
   normally, wider after a long capture gap or from a drawn shape. On
   the lower rays a small bias prefers the inner of competing ridges
   (the reflection side).
4. Weak rays are interpolated from strong neighbours, then rays far off
   a circular median or off a low-order robust Fourier fit of the
   contour are replaced, and a short circular median finishes it.
5. The contour's centroid is the next frame's centre.

After tracing, a centred per-angle temporal median over RIM_SMOOTH_FRAMES
frames (never across a restart or a long gap) removes transient hops.
The output is the rim itself: the measurement's Measure inside (%)
setting keeps the rim glare out of the mean."""

# Third-party imports.
import cv2
import numpy as np

# Enthought library imports.
from traits.api import Array, Bool, HasTraits, Int, List, Tuple

# Local imports.
from .consts import RIM_GAP_SEARCH_PX, RIM_RAYS, RIM_SMOOTH_FRAMES
from .roi_geometry import normalize, outline_of

#: The ray angles (rad), clockwise from +x in y-down image coordinates.
RAY_ANGLES = np.linspace(0.0, 2.0 * np.pi, RIM_RAYS, endpoint=False)

#: Median blur (px) applied before the rays are sampled: removes hot
#: pixels and single-pixel specks. 5 is cv2's ceiling for 16-bit and
#: float images.
MEDIAN_BLUR_PX = 5

#: Gaussian smoothing along the rim, across rays (degrees).
ANGLE_SMOOTH_DEG = 2.0

#: The difference of Gaussians across the rim and the step term's
#: smoothing, as fractions of the rim width: 1.5 px and 6 px inner and
#: outer sigma, 3 px step sigma at the default 5 px rim.
DOG_INNER_SIGMA_RIMS = 0.3
DOG_OUTER_SIGMA_RIMS = 1.2
STEP_SIGMA_RIMS = 0.6

#: Weights of the step term where intensity falls outward (rewarded)
#: and where it rises outward (penalised), against the ridge term.
FALLING_STEP_WEIGHT = 0.7
RISING_STEP_WEIGHT = 0.7

#: Clip on the robust-noise-scaled scores, so saturated points cannot
#: dominate the contour.
SCORE_CLIP = 20.0

#: A ray whose chosen point scores below this is weak: its radius is
#: interpolated from strong neighbours. Below MIN_GOOD_FRACTION strong
#: rays the frame is not trusted at all and the prior is kept.
WEAK_SCORE = 1.0
MIN_GOOD_FRACTION = 0.15

#: The contour moves at most this many px from one ray to the next, and
#: pays this much score per px it moves.
MAX_STEP_PX = 3
SLOPE_PENALTY = 0.5

#: Inward preference on the lower rays: the penalty (score units) at the
#: outer edge of the search window on the bottom ray, falling to zero at
#: its inner edge and on the upper rays.
INWARD_BIAS_SCORE = 1.8

#: The rays sampled reach from this fraction of the smallest prior
#: radius out to this multiple of the largest (and at least the search
#: window either side), so the noise scale sees the droplet's interior
#: and surroundings, not just the rim.
INNER_RADIUS_FRACTION = 0.2
OUTER_RADIUS_FRACTION = 1.6

#: Clean-up after the contour is found: rays further than OUTLIER_PX
#: from an OUTLIER_MEDIAN_RAYS circular median, then further than
#: FIT_TOLERANCE_PX from the Fourier fit, are replaced; a
#: FINAL_MEDIAN_RAYS median finishes.
OUTLIER_MEDIAN_RAYS = 9
OUTLIER_PX = 6.0
FIT_TOLERANCE_PX = 4.0
FINAL_MEDIAN_RAYS = 5

#: Harmonics in the robust Fourier model of r(angle), and its iterative
#: residual trimming rounds.
FOURIER_HARMONICS = 8
FOURIER_ROUNDS = 4

#: The most vertices a traced rim polygon keeps.
RIM_MAX_VERTICES = 72


# ---------------------------------------------------------------------- #
# Shapes and radii                                                       #
# ---------------------------------------------------------------------- #
def shape_outline(kind, geometry):
    """The closed outline of an ROI shape, (N, 2) image px, with no edge
    longer than a pixel — so radii read off it follow straight sides."""
    kind, values = normalize(kind, geometry)

    if kind == "ellipse":
        cx, cy, rx, ry, angle = values
        radians = np.radians(angle)
        x, y = rx * np.cos(RAY_ANGLES), ry * np.sin(RAY_ANGLES)
        points = np.column_stack(
            [
                cx + x * np.cos(radians) - y * np.sin(radians),
                cy + x * np.sin(radians) + y * np.cos(radians),
            ]
        )
    else:
        points = outline_of(kind, values)

    if len(points) < 3:
        return points

    ends = np.roll(points, -1, axis=0)
    pieces = [
        np.linspace(
            start, end, int(np.ceil(np.hypot(*(end - start)))) or 1, endpoint=False
        )
        for start, end in zip(points, ends)
    ]

    return np.vstack(pieces)


def outline_centre(points):
    """The area centroid (cx, cy) of a closed outline (its vertex mean
    when it encloses no area)."""
    moments = cv2.moments(np.asarray(points, dtype=np.float32))

    if moments["m00"] == 0:
        cx, cy = np.asarray(points, dtype=float).mean(axis=0)

        return float(cx), float(cy)

    return moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]


def outline_radii(points, centre):
    """The outline's radius along every ray from ``centre``."""
    points = np.asarray(points, dtype=float)
    dx, dy = points[:, 0] - centre[0], points[:, 1] - centre[1]
    angles = np.mod(np.arctan2(dy, dx), 2.0 * np.pi)
    order = np.argsort(angles)

    return np.interp(
        RAY_ANGLES, angles[order], np.hypot(dx, dy)[order], period=2.0 * np.pi
    )


def rim_points(centre, radii):
    """The contour (RIM_RAYS, 2) the radii describe about ``centre``."""
    return np.column_stack(
        [
            centre[0] + radii * np.cos(RAY_ANGLES),
            centre[1] + radii * np.sin(RAY_ANGLES),
        ]
    )


def rim_polygon(centre, radii, max_vertices=RIM_MAX_VERTICES):
    """The rim as a polygon of at most ``max_vertices`` vertices, (M, 2)
    image px: the coarsest simplification that fits."""
    contour = rim_points(centre, radii).astype(np.float32)
    epsilon = 0.75

    while True:
        approx = cv2.approxPolyDP(contour, epsilon, True)

        if len(approx) <= max_vertices:
            break

        epsilon *= 1.25

    return approx.reshape(-1, 2).astype(float)


def rim_ellipse(centre, radii):
    """The ellipse fitted to the rim: [cx, cy, rx, ry, angle_deg], the
    canonical ellipse geometry."""
    (cx, cy), (width, height), angle = cv2.fitEllipse(
        rim_points(centre, radii).astype(np.float32)
    )

    return [float(cx), float(cy), width / 2.0, height / 2.0, float(angle)]


# ---------------------------------------------------------------------- #
# One frame                                                              #
# ---------------------------------------------------------------------- #
def rim_score(polar, rim_width_px):
    """(score, ridge) for every point of the rays ``polar`` (rays x
    radii): the rim score the contour is chosen by, and the ridge filter
    alone, which peaks on the rim's centre line."""
    rays = len(polar)
    tiled = np.vstack([polar, polar, polar])
    angle_sigma = ANGLE_SMOOTH_DEG * RIM_RAYS / 360.0

    def blurred(sigma_rims):
        return cv2.GaussianBlur(
            tiled, (0, 0), sigmaX=sigma_rims * rim_width_px, sigmaY=angle_sigma
        )

    ridge = (blurred(DOG_INNER_SIGMA_RIMS) - blurred(DOG_OUTER_SIGMA_RIMS))[
        rays : 2 * rays
    ]
    falling = -cv2.Sobel(blurred(STEP_SIGMA_RIMS), cv2.CV_32F, 1, 0, ksize=3)[
        rays : 2 * rays
    ]

    signed_step = _noise_scaled(falling, low=-SCORE_CLIP)
    weighted_step = np.where(
        signed_step > 0,
        FALLING_STEP_WEIGHT * signed_step,
        RISING_STEP_WEIGHT * signed_step,
    )

    return np.maximum(_noise_scaled(ridge) + weighted_step, 0.0), ridge


def ridge_centres(ridge, path, reach):
    """Sub-pixel index of the ridge's peak on every ray within ``reach``
    of ``path``. The step term pulls the score's peak towards the rim's
    falling flank; the contour reports the rim's centre line instead."""
    rays, depth = ridge.shape
    offsets = np.arange(-reach, reach + 1)
    candidates = np.clip(path[:, None] + offsets[None, :], 0, depth - 1)
    rows = np.arange(rays)
    peak = candidates[rows, np.argmax(ridge[rows[:, None], candidates], axis=1)]

    # A parabola through the peak and its neighbours places it between
    # samples: integer radii would step the area by a pixel ring.
    before = ridge[rows, np.clip(peak - 1, 0, depth - 1)]
    at = ridge[rows, peak]
    after = ridge[rows, np.clip(peak + 1, 0, depth - 1)]
    curvature = before - 2.0 * at + after
    shift = np.where(
        curvature < 0,
        0.5 * (before - after) / np.where(curvature < 0, curvature, -1.0),
        0.0,
    )

    return peak + np.clip(shift, -0.5, 0.5)


def _noise_scaled(response, low=0.0):
    """``response`` in units of three robust standard deviations, clipped."""
    spread = np.median(np.abs(response - np.median(response))) * 1.4826 + 1e-6

    return np.clip(response / spread / 3.0, low, SCORE_CLIP)


def closed_path(score, low, high):
    """The best smooth closed path through ``score`` (rays x radii): one
    radius index per ray, each within [low, high] of its ray, moving at
    most MAX_STEP_PX between neighbouring rays. The rays are tiled three
    times and the middle copy kept, so the path closes on itself."""
    rays, depth = score.shape
    index = np.arange(depth)
    allowed = (index[None, :] >= low[:, None]) & (index[None, :] <= high[:, None])
    tiled = np.tile(np.where(allowed, score, -1e6), (3, 1))
    total = tiled[0].copy()
    back = np.zeros(tiled.shape, dtype=np.int32)

    # Row k of ``shifted`` holds each radius's predecessor ``steps[k]``
    # px further in, minus the price of the move: one view per row over
    # a padded copy of the running totals instead of a loop over steps.
    steps = np.arange(-MAX_STEP_PX, MAX_STEP_PX + 1)
    price = SLOPE_PENALTY * np.abs(steps)[:, None]
    padded = np.full(depth + 2 * MAX_STEP_PX, -np.inf)
    previous = np.lib.stride_tricks.sliding_window_view(padded, depth)[::-1]

    for row in range(1, len(tiled)):
        padded[MAX_STEP_PX : MAX_STEP_PX + depth] = total
        shifted = previous - price
        choice = np.argmax(shifted, axis=0)
        total = shifted[choice, index] + tiled[row]
        back[row] = index - steps[choice]

    path = np.zeros(len(tiled), dtype=np.int32)
    path[-1] = int(np.argmax(total))

    for row in range(len(tiled) - 1, 0, -1):
        path[row - 1] = back[row, path[row]]

    return path[rays : 2 * rays]


def circular_median(values, window):
    """Median filter of ``window`` (odd) over a circular 1-D array."""
    half = window // 2
    padded = np.concatenate([values[-half:], values, values[:half]])
    stacked = np.stack([padded[i : i + len(values)] for i in range(window)])

    return np.median(stacked, axis=0)


def circular_interpolate(values, good):
    """``values`` with the entries where ``good`` is False filled from
    their circular neighbours."""
    if good.all() or not good.any():
        return values

    index = np.arange(len(values))
    good_index = index[good]
    known_at = np.concatenate(
        [good_index - len(values), good_index, good_index + len(values)]
    )

    return np.where(good, values, np.interp(index, known_at, np.tile(values[good], 3)))


def robust_fourier_fit(radii, good):
    """Low-order Fourier model of r(angle): the smooth droplet shape
    notches are judged against. Weighted towards the strong rays, with a
    curvature-style penalty on the higher harmonics so a long weak gap
    cannot make it oscillate, and trimmed of large residuals over
    FOURIER_ROUNDS rounds."""
    columns, penalty = [np.ones(RIM_RAYS)], [0.0]

    for harmonic in range(1, FOURIER_HARMONICS + 1):
        columns += [np.cos(harmonic * RAY_ANGLES), np.sin(harmonic * RAY_ANGLES)]
        penalty += [0.05 * harmonic**2] * 2

    design = np.stack(columns, axis=1)
    regulariser = np.diag(penalty) * RIM_RAYS / 100.0
    weight = np.where(good, 1.0, 0.05)

    for _ in range(FOURIER_ROUNDS):
        weighted = design * weight[:, None]
        coefficients = np.linalg.solve(
            design.T @ weighted + regulariser, weighted.T @ radii
        )
        residual = np.abs(radii - design @ coefficients)
        trusted = weight > 0.5
        scale = 1.4826 * np.median(residual[trusted]) if trusted.any() else 1.0
        weight = np.where(residual < 2.5 * max(scale, 1.0), weight, weight * 0.05)

    return design @ coefficients


def find_rim(image, centre, previous_radii, window, rim_width_px, inward_bias=False):
    """Trace the rim on ``image`` from the prior ``previous_radii``
    (per ray, about ``centre``), each ray searched ``window`` px either
    side of it. ``inward_bias`` prefers the inner of competing ridges on
    the lower rays — for frame-to-frame tracking, not across a gap where
    the droplet may have spread.

    Returns (radii, centre, good): the rim's radii about its own
    centroid ``centre`` — the next frame's prior — and which rays found
    a strong rim. A frame with too few strong rays keeps the prior."""
    previous = np.asarray(previous_radii, dtype=float)
    smallest, largest = previous.min(), previous.max()
    inner = max(
        1, int(np.floor(min(INNER_RADIUS_FRACTION * smallest, smallest - window)))
    )
    outer = int(np.ceil(max(OUTER_RADIUS_FRACTION * largest, largest + window))) + 1
    radii_axis = np.arange(inner, outer + 1, dtype=np.float32)
    nothing_found = previous.copy(), tuple(centre), np.zeros(RIM_RAYS, dtype=bool)

    # A crop just big enough for the rays (plus the median blur's reach),
    # so the blur does not run over the whole frame for every droplet.
    reach = outer + MEDIAN_BLUR_PX
    height, width = image.shape[:2]
    x0, y0 = max(0, int(centre[0] - reach)), max(0, int(centre[1] - reach))
    x1 = min(width, int(centre[0] + reach) + 1)
    y1 = min(height, int(centre[1] + reach) + 1)

    if x1 - x0 < MEDIAN_BLUR_PX or y1 - y0 < MEDIAN_BLUR_PX:
        return nothing_found

    crop = cv2.medianBlur(
        np.ascontiguousarray(image[y0:y1, x0:x1], dtype=np.float32), MEDIAN_BLUR_PX
    )
    map_x = centre[0] - x0 + np.cos(RAY_ANGLES)[:, None] * radii_axis[None, :]
    map_y = centre[1] - y0 + np.sin(RAY_ANGLES)[:, None] * radii_axis[None, :]
    polar = cv2.remap(
        crop,
        map_x.astype(np.float32),
        map_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderValue=0,
    )
    score, ridge = rim_score(polar, rim_width_px)

    expected = previous - inner
    last = len(radii_axis) - 1
    low = np.clip(np.round(expected - window), 0, last).astype(int)
    high = np.clip(np.round(expected + window), 0, last).astype(int)
    searched = score

    if inward_bias:
        lower_rays = np.clip(np.sin(RAY_ANGLES), 0.0, None)[:, None]
        depth = np.clip(np.arange(len(radii_axis))[None, :] - low[:, None], 0, None)
        per_px = INWARD_BIAS_SCORE / max(2 * window, 1)
        searched = score - per_px * lower_rays * depth

    path = closed_path(searched, low, high)
    good = score[np.arange(RIM_RAYS), path] >= WEAK_SCORE
    radii = inner + ridge_centres(ridge, path, int(np.ceil(rim_width_px / 2)) + 1)

    if good.mean() < MIN_GOOD_FRACTION:
        return nothing_found

    radii = circular_interpolate(radii, good)
    filtered = circular_median(radii, OUTLIER_MEDIAN_RAYS)
    radii = np.where(np.abs(radii - filtered) > OUTLIER_PX, filtered, radii)
    fit = robust_fourier_fit(radii, good)
    radii = np.where(np.abs(radii - fit) > FIT_TOLERANCE_PX, fit, radii)
    radii = circular_median(radii, FINAL_MEDIAN_RAYS)

    points = rim_points(centre, radii)
    rim_centre = outline_centre(points)

    return outline_radii(points, rim_centre), rim_centre, good


# ---------------------------------------------------------------------- #
# Frame to frame                                                         #
# ---------------------------------------------------------------------- #
class RimChain(HasTraits):
    """One droplet's trace, carried from frame to frame."""

    #: Centre the next frame's rays are cast from (image px).
    centre = Tuple(0.0, 0.0)

    #: Rim radius along each ray about ``centre``: the next frame's prior.
    radii = Array(dtype=float)

    #: Changed whenever the chain restarts or crosses a long capture
    #: gap, so the temporal median never mixes frames across either.
    segment = Int(0)

    #: Whether the prior is a drawn shape rather than a traced rim: the
    #: next frame is then searched wide and the trace refined once.
    from_shape = Bool(True)


def chain_from_shape(kind, geometry, segment):
    """A chain restarting from an ROI shape (a start shape or the user's
    correction): its outline's radii about its centroid are the prior."""
    outline = shape_outline(kind, geometry)
    centre = outline_centre(outline)

    return RimChain(
        centre=centre, radii=outline_radii(outline, centre), segment=segment
    )


def trace_chain(image, chain, search_px, rim_width_px, after_gap=False):
    """Trace ``chain``'s droplet on ``image``: (radii, centre, good) as
    find_rim's. A shape prior or a long capture gap widens the search to
    at least RIM_GAP_SEARCH_PX; a shape prior is then refined once from
    the rim it found, with the normal window about the rim's centroid."""
    widened = chain.from_shape or after_gap
    window = max(search_px, RIM_GAP_SEARCH_PX) if widened else search_px
    radii, centre, good = find_rim(
        image, chain.centre, chain.radii, window, rim_width_px, inward_bias=not widened
    )

    if chain.from_shape and good.any():
        radii, centre, good = find_rim(
            image, centre, radii, search_px, rim_width_px, inward_bias=True
        )

    return radii, centre, good


class RimTemporalMedian(HasTraits):
    """Streaming centred per-angle temporal median over traced rims.

    Frames are pushed in order as {roi_id: (segment, centre, radii)};
    a frame comes back once half a window more has been pushed (or on
    flush), each droplet's rim the median of its neighbours in the same
    segment: the median centre, and per ray the median radius of each
    neighbour's rim seen from that centre."""

    #: Frames in each median (odd: centred on the frame it is for).
    window = Int(RIM_SMOOTH_FRAMES)

    #: Pushed frames still to emit plus the half window before them
    #: that the next emission reads: [(key, traces), ...].
    _frames = List()

    #: How many of ``_frames`` are already emitted.
    _emitted = Int(0)

    def push(self, key, traces):
        """Add one frame; return the frames now final, as
        [(key, {roi_id: (centre, radii)}), ...]."""
        self._frames.append((key, traces))

        return self._emit(len(self._frames) - self.window // 2)

    def flush(self):
        """Return every frame not yet emitted (their windows end early)."""
        return self._emit(len(self._frames))

    def _emit(self, stop):
        half = self.window // 2
        emitted = []

        while self._emitted < stop:
            key, traces = self._frames[self._emitted]
            neighbours = self._frames[
                max(0, self._emitted - half) : self._emitted + half + 1
            ]
            emitted.append(
                (
                    key,
                    {
                        roi_id: _median_rim(roi_id, segment, neighbours)
                        for roi_id, (segment, _centre, _radii) in traces.items()
                    },
                )
            )
            self._emitted += 1

        spent = max(0, self._emitted - half)
        del self._frames[:spent]
        self._emitted -= spent

        return emitted


def _median_rim(roi_id, segment, neighbours):
    """(centre, radii): the median of ``roi_id``'s rims in ``segment``
    across ``neighbours``."""
    rims = [
        traces[roi_id][1:]
        for _key, traces in neighbours
        if roi_id in traces and traces[roi_id][0] == segment
    ]

    if len(rims) == 1:
        return rims[0]

    cx, cy = np.median([centre for centre, _radii in rims], axis=0)
    centre = (float(cx), float(cy))
    radii = np.median([outline_radii(rim_points(*rim), centre) for rim in rims], axis=0)

    return centre, radii
