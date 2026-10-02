# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Synthetic droplet series with known shape behaviour, one droplet per
fixed circular ROI:

- A "circle": stays a circle (the control).
- B "elongate": circle -> ellipse, axis ratio 1 -> 2.5 at constant area.
- C "bump": a satellite blob grows next to the droplet and merges in,
  so the outline gains a lobe and a neck (irregular).
- D "rotate": a 2:1 ellipse of fixed shape turning 90° (-45° -> +45°).
- E "shrink": a circle losing 3/4 of its area, shape unchanged.

Frames are 8-bit grey: dark background, bright droplets with a soft
(blurred) edge and mild Gaussian noise. Shapes are drawn supersampled and
area-averaged down, so edges are anti-aliased rather than staircased.
"""

# Standard library imports.
import json
import math
from pathlib import Path

# Third-party imports.
import cv2
import numpy as np

DEFAULT_FRAMES = 40
DEFAULT_SIZE = 320

BACKGROUND_LEVEL = 30
DROPLET_LEVEL = 200
NOISE_SIGMA = 4.0
EDGE_BLUR_SIGMA = 1.5
SUPERSAMPLE = 4
SEED = 0

#: Radius (px) of every droplet's circular ROI.
ROI_RADIUS = 50

#: Droplet name -> ROI centre (x, y) on a DEFAULT_SIZE frame.
ROI_CENTRES = {
    "A_circle": (80, 80),
    "B_elongate": (240, 80),
    "C_bump": (80, 240),
    "D_rotate": (240, 240),
    "E_shrink": (160, 160),
}

#: Radius (px) of the round droplets at the start of the series.
BASE_RADIUS = 22.0

B_FINAL_AXIS_RATIO = 2.5

#: C's satellite: distance of its centre from the droplet centre, its
#: final radius, and the direction it sits in (degrees, screen clockwise).
C_BUMP_OFFSET = 31.0
C_BUMP_FINAL_RADIUS = 13.0
C_BUMP_DIRECTION_DEG = 30.0

D_SEMI_AXES = (28.0, 14.0)
D_ANGLE_RANGE_DEG = (-45.0, 45.0)

E_FINAL_RADIUS = 11.0


def _ellipse(centre, semi_axes, angle_deg):
    """One ellipse primitive (centre, (a, b) semi-axes, angle)."""
    return {"centre": centre, "semi_axes": semi_axes, "angle_deg": angle_deg}


def droplet_parameters(name, progress):
    """Ground truth for droplet ``name`` at ``progress`` (0..1 through the
    series): its ellipse primitives plus the analytic descriptors."""
    centre = ROI_CENTRES[name]

    if name == "A_circle":
        primitives = [_ellipse(centre, (BASE_RADIUS, BASE_RADIUS), 0.0)]
        truth = {"axis_ratio": 1.0, "orientation_deg": None}
    elif name == "B_elongate":
        ratio = 1.0 + (B_FINAL_AXIS_RATIO - 1.0) * progress
        major = BASE_RADIUS * math.sqrt(ratio)
        primitives = [_ellipse(centre, (major, BASE_RADIUS**2 / major), 0.0)]
        truth = {"axis_ratio": ratio, "orientation_deg": 0.0}
    elif name == "C_bump":
        bump_radius = C_BUMP_FINAL_RADIUS * progress
        direction = math.radians(C_BUMP_DIRECTION_DEG)
        bump_centre = (
            centre[0] + C_BUMP_OFFSET * math.cos(direction),
            centre[1] + C_BUMP_OFFSET * math.sin(direction),
        )
        primitives = [_ellipse(centre, (BASE_RADIUS, BASE_RADIUS), 0.0)]

        if bump_radius > 0:
            primitives.append(_ellipse(bump_centre, (bump_radius, bump_radius), 0.0))

        truth = {
            "bump_radius": bump_radius,
            "merged": bump_radius + BASE_RADIUS > C_BUMP_OFFSET,
        }
    elif name == "D_rotate":
        low, high = D_ANGLE_RANGE_DEG
        angle = low + (high - low) * progress
        primitives = [_ellipse(centre, D_SEMI_AXES, angle)]
        truth = {
            "axis_ratio": D_SEMI_AXES[0] / D_SEMI_AXES[1],
            "orientation_deg": angle,
        }
    else:
        radius = BASE_RADIUS + (E_FINAL_RADIUS - BASE_RADIUS) * progress
        primitives = [_ellipse(centre, (radius, radius), 0.0)]
        truth = {"axis_ratio": 1.0, "orientation_deg": None}

    truth["area"] = sum(
        math.pi * primitive["semi_axes"][0] * primitive["semi_axes"][1]
        for primitive in primitives
    )

    return {"primitives": primitives, "truth": truth}


def _draw_primitives(canvas, primitives):
    """Fill every ellipse primitive on the supersampled ``canvas``."""
    for primitive in primitives:
        centre = tuple(round(value * SUPERSAMPLE) for value in primitive["centre"])
        axes = tuple(round(value * SUPERSAMPLE) for value in primitive["semi_axes"])
        cv2.ellipse(canvas, centre, axes, primitive["angle_deg"], 0, 360, 1.0, -1)


def render_frame(parameters, size, rng):
    """One 8-bit frame of every droplet in ``parameters`` (name -> params)."""
    canvas = np.zeros((size * SUPERSAMPLE, size * SUPERSAMPLE), dtype=np.float32)

    for droplet in parameters.values():
        _draw_primitives(canvas, droplet["primitives"])

    coverage = cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)
    coverage = cv2.GaussianBlur(coverage, (0, 0), EDGE_BLUR_SIGMA)
    frame = BACKGROUND_LEVEL + (DROPLET_LEVEL - BACKGROUND_LEVEL) * coverage
    frame += rng.normal(0.0, NOISE_SIGMA, frame.shape)

    return np.clip(np.rint(frame), 0, 255).astype(np.uint8)


def roi_mask(shape, roi):
    """uint8 mask (255 inside) of one circular ROI definition."""
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.circle(mask, tuple(roi["centre"]), roi["radius"], 255, -1)

    return mask


def generate_series(out_dir, frames=DEFAULT_FRAMES, size=DEFAULT_SIZE):
    """Write ``frames`` PNGs plus ``series.json`` (ROI definitions and
    per-frame ground truth) into ``out_dir``.

    Returns
    -------
    (list of Path, dict)
        The frame paths in order, and the JSON content.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    rois = {
        name: {"kind": "circle", "centre": list(centre), "radius": ROI_RADIUS}
        for name, centre in ROI_CENTRES.items()
    }
    ground_truth = []
    paths = []

    for index in range(frames):
        progress = index / max(frames - 1, 1)
        parameters = {name: droplet_parameters(name, progress) for name in ROI_CENTRES}
        path = out_dir / f"frame_{index:03d}.png"
        cv2.imwrite(str(path), render_frame(parameters, size, rng))

        paths.append(path)
        ground_truth.append(
            {
                "frame": index,
                "file": path.name,
                "progress": progress,
                "droplets": parameters,
            }
        )

    series = {
        "size": size,
        "background_level": BACKGROUND_LEVEL,
        "droplet_level": DROPLET_LEVEL,
        "noise_sigma": NOISE_SIGMA,
        "rois": rois,
        "frames": ground_truth,
    }
    (out_dir / "series.json").write_text(json.dumps(series, indent=1))

    return paths, series
