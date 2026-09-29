# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for SAM candidate conversion and filtering (no osam needed)."""

# Third-party imports.
import numpy as np

# Enthought library imports.
from traits.api import TraitError  # noqa: F401  (import check only)

# Microdrop package imports.
from image_viewer.analysis.sam_detect import (
    AI_MODEL_OPTIONS,
    DEFAULT_AI_MODEL,
    Detection,
    candidate_from_detection,
    normalize_to_uint8,
    sam_available,
    suppress_with_votes,
)


def test_default_model_is_one_of_the_options():
    assert DEFAULT_AI_MODEL in {name for name, _ in AI_MODEL_OPTIONS}
    assert isinstance(sam_available(), bool)


def test_normalize_stretches_16bit_to_full_range():
    ramp = np.linspace(1000, 3000, 256 * 256).reshape(256, 256)
    out = normalize_to_uint8(ramp.astype(np.uint16))
    assert out.dtype == np.uint8
    assert out.min() == 0 and out.max() == 255


def test_normalize_of_flat_frame_is_black():
    flat = np.full((16, 16), 500, dtype=np.uint16)
    assert normalize_to_uint8(flat).max() == 0


def _disk_detection(cx=30.0, cy=30.0, r=10, score=0.9):
    size = 2 * r + 1
    mask = np.zeros((size, size), dtype=bool)
    yy, xx = np.mgrid[0:size, 0:size]
    mask[(xx - r) ** 2 + (yy - r) ** 2 <= r**2] = True
    return Detection(bbox=[cx - r, cy - r, cx + r, cy + r], mask=mask, score=score)


def test_disk_mask_becomes_polygon_and_ellipse_candidate():
    candidate = candidate_from_detection(_disk_detection(), prompt=[30.0, 30.0])
    kind, geometry = candidate.geometry_for("ellipse")
    assert kind == "ellipse"
    cx, cy, rx, ry, _angle = geometry
    assert abs(cx - 30.0) < 1.5 and abs(cy - 30.0) < 1.5
    assert abs(rx - 10.0) < 1.5 and abs(ry - 10.0) < 1.5
    kind, polygon = candidate.geometry_for("polygon")
    assert kind == "polygon" and len(polygon) >= 6
    assert abs(candidate.size - 20.0) < 3.0


def test_duplicate_masks_merge_and_sum_votes():
    kept = suppress_with_votes(
        [(_disk_detection(score=0.9), 1), (_disk_detection(score=0.5), 1)]
    )
    assert len(kept) == 1 and kept[0][1] == 2


def test_click_candidates_are_exempt_from_significance():
    clicked = candidate_from_detection(
        _disk_detection(), prompt=[30.0, 30.0], source="click"
    )
    swept = candidate_from_detection(_disk_detection(), votes=1)
    assert clicked.passes(min_votes=2, min_size=0, max_size=500)
    assert not swept.passes(min_votes=2, min_size=0, max_size=500)
    assert not clicked.passes(min_votes=2, min_size=50, max_size=500)
    # The size window's upper edge cuts oversized candidates for every
    # source, clicked ones included (~20 px mean diameter here).
    assert not clicked.passes(min_votes=2, min_size=0, max_size=10)
    assert clicked.passes(min_votes=2, min_size=10, max_size=30)
