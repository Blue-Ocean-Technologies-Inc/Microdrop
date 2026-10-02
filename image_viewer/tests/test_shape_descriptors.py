# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Shape descriptors against analytic shapes drawn with cv2."""

# Standard library imports.
import math

# Third-party imports.
import cv2
import numpy as np
import pytest

# Microdrop package imports.
from image_viewer.analysis.consts import MASK_ON
from image_viewer.analysis.shape_descriptors import (
    HU_ROOT_KEY,
    ROI_SHAPE_KEYS,
    add_shape_deviation,
    describe_droplet,
    roi_shape_stats,
    shape_deviation,
)

SIZE = 200
CENTRE = (100, 100)
BACKGROUND, DROPLET = 20, 220


def _frame(*ellipses):
    """A dark frame with bright filled (centre, (a, b), angle) ellipses."""
    frame = np.full((SIZE, SIZE), BACKGROUND, dtype=np.uint8)

    for centre, axes, angle in ellipses:
        cv2.ellipse(frame, centre, axes, angle, 0, 360, DROPLET, -1, cv2.LINE_AA)

    return frame


def _whole_roi():
    """An ROI mask covering most of the frame."""
    mask = np.zeros((SIZE, SIZE), dtype=np.uint8)
    cv2.circle(mask, CENTRE, 90, MASK_ON, -1)

    return mask


def test_circle_is_round_and_convex():
    descriptors = describe_droplet(_frame((CENTRE, (40, 40), 0)), _whole_roi())

    assert descriptors["circularity"] == pytest.approx(1.0, abs=0.05)
    # The smoothed perimeter, not the pixel staircase (which reads ~0.90).
    assert descriptors["circularity"] > 0.95
    assert descriptors["axis_ratio"] == pytest.approx(1.0, abs=0.02)
    assert descriptors["solidity"] == pytest.approx(1.0, abs=0.02)
    assert descriptors["area"] == pytest.approx(math.pi * 40**2, rel=0.03)


@pytest.mark.parametrize("angle", [0, 30, -60])
def test_two_to_one_ellipse_axis_ratio_and_orientation(angle):
    frame = _frame((CENTRE, (60, 30), angle))
    descriptors = describe_droplet(frame, _whole_roi())

    assert descriptors["axis_ratio"] == pytest.approx(2.0, abs=0.05)
    assert descriptors["eccentricity"] == pytest.approx(math.sqrt(0.75), abs=0.01)
    assert descriptors["orientation_deg"] == pytest.approx(angle, abs=1.0)
    assert descriptors["circularity"] == pytest.approx(0.84, abs=0.03)
    assert descriptors["solidity"] == pytest.approx(1.0, abs=0.02)


def test_rotated_copy_has_the_same_hu_vector():
    mask = _whole_roi()
    reference = describe_droplet(_frame((CENTRE, (60, 30), 10)), mask)
    rotated = describe_droplet(_frame((CENTRE, (60, 30), 75)), mask)

    assert shape_deviation(rotated, reference) < 0.02
    assert rotated["orientation_deg"] - reference["orientation_deg"] == (
        pytest.approx(65, abs=1.0)
    )


def test_bump_lowers_solidity_and_raises_shape_deviation():
    mask = _whole_roi()
    plain = describe_droplet(_frame((CENTRE, (40, 40), 0)), mask)
    bumped = describe_droplet(
        _frame((CENTRE, (40, 40), 0), ((150, 100), (18, 18), 0)), mask
    )
    series = add_shape_deviation([plain, bumped])

    assert bumped["solidity"] < plain["solidity"] - 0.03
    assert series[1]["shape_deviation"] > 0.2


def test_empty_roi_gives_nan():
    descriptors = describe_droplet(_frame(), _whole_roi())
    series = add_shape_deviation([descriptors])

    assert math.isnan(descriptors["area"])
    assert math.isnan(descriptors["axis_ratio"])
    assert math.isnan(series[0]["shape_deviation"])


def test_roi_shape_stats_match_the_whole_frame_descriptors():
    frame = _frame((CENTRE, (60, 30), 20))
    mask = _whole_roi()
    whole = describe_droplet(frame, mask)
    stats = roi_shape_stats(frame, mask)

    assert set(stats) == set(ROI_SHAPE_KEYS)
    assert stats["axis_ratio"] == pytest.approx(whole["axis_ratio"])
    assert stats["eccentricity"] == pytest.approx(math.sqrt(0.75), abs=0.01)
    assert stats["circularity"] == pytest.approx(whole["circularity"])
    assert stats["solidity"] == pytest.approx(whole["solidity"])
    # A list, as the JSON stats store holds it — and still comparable.
    assert isinstance(stats[HU_ROOT_KEY], list)
    assert shape_deviation(stats, whole) == pytest.approx(0.0, abs=1e-9)


def test_roi_shape_stats_without_a_droplet_are_nan():
    empty_mask = np.zeros((SIZE, SIZE), dtype=np.uint8)

    for stats in (
        roi_shape_stats(_frame(), _whole_roi()),
        roi_shape_stats(_frame((CENTRE, (40, 40), 0)), empty_mask),
    ):
        assert math.isnan(stats["circularity"])
        assert math.isnan(stats["axis_ratio"])
        assert math.isnan(stats["eccentricity"])
        assert math.isnan(stats["solidity"])
        assert stats[HU_ROOT_KEY] is None


def test_roi_shape_stats_read_a_sixteen_bit_frame():
    frame = _frame((CENTRE, (60, 30), 0)).astype(np.uint16) * 200
    stats = roi_shape_stats(frame, _whole_roi())

    assert stats["axis_ratio"] == pytest.approx(2.0, abs=0.05)
