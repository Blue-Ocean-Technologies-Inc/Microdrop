# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""ROI mask/stats math against synthetic arrays."""

# Standard library imports.
import math

# Third-party imports.
import cv2
import numpy as np

# Microdrop package imports.
from image_viewer.analysis.roi_compute import (
    _shrink_factor,
    compute_image_stats,
    masked_stats,
    ring_contours,
    roi_masks,
    stats_are_current,
    subtract_rolling_ball,
)


def test_box_interior_stats_on_uniform_patch():
    array = np.zeros((40, 40), dtype=np.uint16)
    array[10:20, 10:20] = 1000
    interior, _outline = roi_masks((40, 40), "box", [10.0, 10.0, 9.0, 9.0])
    stats = masked_stats(array, interior)
    assert stats["mean"] == 1000.0
    assert stats["std"] == 0.0
    assert stats["min"] == stats["max"] == 1000.0
    assert stats["count"] == 100.0  # cv2.rectangle corners are inclusive


def test_circle_mask_is_filled_disk():
    interior, ring = roi_masks((100, 100), "circle", [50.0, 50.0, 10.0])
    area = np.count_nonzero(interior)
    assert abs(area - math.pi * 10**2) / area < 0.15
    assert np.count_nonzero(ring) > 0


# cv2 fills the boundary ring as well as the interior, so a rasterized
# area runs roughly 1/radius high against the analytic one. These use
# shapes big enough for that bias to sit inside the tolerance.
def test_ellipse_mask_area_matches_pi_rx_ry():
    interior, _outline = roi_masks(
        (300, 300), "ellipse", (150.0, 150.0, 60.0, 30.0, 0.0)
    )
    expected = math.pi * 60.0 * 30.0
    assert abs(np.count_nonzero(interior) - expected) / expected < 0.05


def test_rotated_ellipse_swaps_its_extent():
    flat, _ = roi_masks((200, 200), "ellipse", (100.0, 100.0, 40.0, 10.0, 0.0))
    turned, _ = roi_masks((200, 200), "ellipse", (100.0, 100.0, 40.0, 10.0, 90.0))
    rows_flat, columns_flat = np.nonzero(flat)
    rows_turned, columns_turned = np.nonzero(turned)
    assert np.ptp(columns_flat) > np.ptp(rows_flat)
    assert np.ptp(rows_turned) > np.ptp(columns_turned)
    assert abs(np.count_nonzero(flat) - np.count_nonzero(turned)) < 40


def test_rotated_box_covers_its_diagonal_corners():
    interior, _outline = roi_masks((200, 200), "box", (80.0, 90.0, 40.0, 20.0, 45.0))
    # Centre stays inside; the axis-aligned corner leaves the shape.
    assert interior[100, 100] == 255
    assert interior[90, 80] == 0


def test_capsule_mask_area_matches_the_analytic_value():
    interior, _outline = roi_masks(
        (300, 300), "capsule", (150.0, 150.0, 60.0, 20.0, 0.0)
    )
    expected = math.pi * 20.0**2 + 4.0 * 20.0 * 60.0
    assert abs(np.count_nonzero(interior) - expected) / expected < 0.05


def test_capsule_ring_hugs_its_bounding_box():
    _interior, ring = roi_masks(
        (200, 200), "capsule", (100.0, 100.0, 30.0, 8.0, 0.0), gap_px=2, thickness_px=4
    )
    rows, columns = np.nonzero(ring)
    # The ring reaches gap + thickness beyond the capsule's extent.
    assert columns.max() <= 100 + 38 + 6 + 1
    assert rows.max() <= 100 + 8 + 6 + 1


def test_unrotated_equal_radii_reuse_the_legacy_circle_mask():
    # Pixel-identical, so intensities cached before ellipses existed
    # stay comparable with anything computed after.
    legacy = np.zeros((200, 200), dtype=np.uint8)
    cv2.circle(legacy, (100, 100), 30, 255, -1)
    interior, _outline = roi_masks(
        (200, 200), "ellipse", (100.0, 100.0, 30.0, 30.0, 0.0)
    )
    assert np.array_equal(interior, legacy)


def test_legacy_circle_geometry_still_masks():
    interior, _outline = roi_masks((100, 100), "circle", (50.0, 50.0, 30.0))
    expected = math.pi * 30.0**2
    assert abs(np.count_nonzero(interior) - expected) / expected < 0.05


def test_roi_outside_image_yields_nan_stats():
    array = np.zeros((20, 20), dtype=np.uint16)
    interior, _outline = roi_masks((20, 20), "circle", [500.0, 500.0, 5.0])
    stats = masked_stats(array, interior)
    assert stats["count"] == 0.0
    assert math.isnan(stats["mean"])


def test_compute_image_stats_reads_16bit_png(tmp_path):
    array = np.full((30, 30), 500, dtype=np.uint16)
    array[5:15, 5:15] = 2000
    path = tmp_path / "img_2026_07_20-17_46_24_raw.png"
    cv2.imwrite(str(path), array)
    result = compute_image_stats(str(path), {"roi1": ("box", (5.0, 5.0, 9.0, 9.0))})
    assert result["error"] is None
    assert result["stats"]["roi1"]["mean"] == 2000.0
    assert "outline_mean" in result["stats"]["roi1"]
    assert result["mtime"] > 0


def test_compute_image_stats_measures_the_droplet_shape(tmp_path):
    array = np.full((200, 200), 500, dtype=np.uint16)
    cv2.ellipse(array, (100, 100), (40, 20), 30, 0, 360, 3000, -1)
    path = tmp_path / "img_2026_07_20-17_46_24_raw.png"
    cv2.imwrite(str(path), array)

    result = compute_image_stats(
        str(path), {"roi1": ("ellipse", (100.0, 100.0, 70.0, 70.0, 0.0))}
    )
    stats = result["stats"]["roi1"]

    assert abs(stats["axis_ratio"] - 2.0) < 0.05
    assert abs(stats["eccentricity"] - math.sqrt(0.75)) < 0.01
    assert abs(stats["orientation_deg"] - 30.0) < 2.0
    assert 0.0 < stats["extent"] < 1.0
    assert stats["solidity"] > 0.98
    assert len(stats["hu_root"]) == 7
    assert stats_are_current(stats)


def test_stats_cached_before_the_shape_stats_are_not_current():
    assert not stats_are_current(None)
    assert not stats_are_current({"mean": 10.0, "count": 25.0})


def test_compute_image_stats_reports_unreadable_file(tmp_path):
    path = tmp_path / "broken_raw.png"
    path.write_bytes(b"not a png")
    result = compute_image_stats(str(path), {"roi1": ("circle", (5.0, 5.0, 2.0))})
    assert result["error"] is not None
    assert result["stats"] == {}


def test_contour_mask_area_matches_the_triangle():
    interior, outline = roi_masks(
        (200, 200), "polygon", (20.0, 20.0, 120.0, 20.0, 20.0, 100.0)
    )
    expected = 0.5 * 100.0 * 80.0
    assert abs(np.count_nonzero(interior) - expected) / expected < 0.05
    assert 0 < np.count_nonzero(outline) < np.count_nonzero(interior)


def test_contour_below_minimum_vertices_masks_nothing():
    array = np.full((50, 50), 7, dtype=np.uint16)
    interior, _outline = roi_masks((50, 50), "polygon", (10.0, 10.0, 20.0, 20.0))
    stats = masked_stats(array, interior)
    assert np.count_nonzero(interior) == 0
    assert stats["count"] == 0.0 and math.isnan(stats["mean"])


def test_ring_never_touches_the_interior():
    interior, ring = roi_masks((200, 200), "ellipse", (100.0, 100.0, 30.0, 30.0, 0.0))
    assert np.count_nonzero((interior == 255) & (ring == 255)) == 0


def test_ring_area_matches_the_annulus():
    gap, thickness = 2, 4
    _interior, ring = roi_masks(
        (300, 300), "ellipse", (150.0, 150.0, 40.0, 40.0, 0.0), gap, thickness
    )
    inner, outer = 40.0 + gap, 40.0 + gap + thickness
    expected = math.pi * (outer**2 - inner**2)
    assert abs(np.count_nonzero(ring) - expected) / expected < 0.10


def test_gap_pushes_the_ring_outwards():
    centre = (150.0, 150.0, 40.0, 40.0, 0.0)
    _interior, tight = roi_masks((300, 300), "ellipse", centre, 0, 3)
    _interior, spaced = roi_masks((300, 300), "ellipse", centre, 6, 3)
    rows, columns = np.nonzero(tight)
    tight_inner = np.min(np.hypot(columns - 150.0, rows - 150.0))
    rows, columns = np.nonzero(spaced)
    spaced_inner = np.min(np.hypot(columns - 150.0, rows - 150.0))
    assert abs(tight_inner - 40.0) < 2.0
    assert abs(spaced_inner - 46.0) < 2.0


def test_background_correction_recovers_the_true_signal():
    # The regression this cycle exists for: the old boundary-stroke
    # ring read 1569 where the answer is 2900.
    image = np.full((200, 200), 100, dtype=np.uint16)
    cv2.circle(image, (100, 100), 30, 3000, -1)
    interior, ring = roi_masks((200, 200), "ellipse", (100.0, 100.0, 30.0, 30.0, 0.0))
    corrected = (
        masked_stats(image, interior)["mean"] - masked_stats(image, ring)["mean"]
    )
    assert abs(corrected - 2900.0) < 30.0


def test_ring_excludes_a_neighbouring_roi(tmp_path):
    array = np.full((200, 200), 100, dtype=np.uint16)
    cv2.circle(array, (100, 100), 20, 3000, -1)
    cv2.circle(array, (135, 100), 20, 3000, -1)  # neighbour, close by
    path = tmp_path / "img_2026_07_20-17_46_24_raw.png"
    cv2.imwrite(str(path), array)
    result = compute_image_stats(
        str(path),
        {
            "a": ("ellipse", (100.0, 100.0, 20.0, 20.0, 0.0)),
            "b": ("ellipse", (135.0, 100.0, 20.0, 20.0, 0.0)),
        },
    )
    # Without the exclusion the neighbour's 3000 would drag this up.
    assert result["stats"]["a"]["outline_mean"] < 200.0


def test_ring_contours_trace_the_annulus():
    contours = ring_contours(
        (300, 300), "ellipse", (150.0, 150.0, 40.0, 40.0, 0.0), 2, 4
    )
    assert len(contours) == 2  # an outer and an inner boundary
    extents = sorted(
        np.max(np.hypot(points[:, 0] - 150.0, points[:, 1] - 150.0))
        for points in contours
    )
    assert abs(extents[0] - 42.0) < 2.0  # inner edge: radius + gap
    assert abs(extents[1] - 46.0) < 2.0  # outer: + thickness


def _uneven_frame(height=240, width=320, signal=800.0, radius=12):
    """A 16-bit frame: a smooth ramp-and-swell background with a
    bright disk on it, and the disk's mask."""
    y, x = np.mgrid[0:height, 0:width].astype(float)
    background = 400.0 + 2.0 * x + 900.0 * np.sin(y / height * 2.0)
    mask = (x - width / 2) ** 2 + (y - height / 2) ** 2 <= radius**2
    frame = background + mask * signal
    return (np.clip(frame, 0, 65535).astype(np.uint16), background, mask)


def test_the_rolling_ball_flattens_a_16_bit_frame():
    frame, background, mask = _uneven_frame()
    assert frame.dtype == np.uint16
    corrected = subtract_rolling_ball(frame, 40)
    assert corrected.dtype == np.uint16, "16-bit in, 16-bit out"
    # The background spanned hundreds of counts and is now near zero,
    # while the disk keeps most of its height.
    away = ~mask
    assert frame[away].std() > 200.0
    assert corrected[away].mean() < 60.0
    assert corrected[mask].mean() > 700.0


def test_the_ball_leaves_a_flat_frame_alone():
    flat = np.full((120, 160), 5000, dtype=np.uint16)
    assert int(subtract_rolling_ball(flat, 30).max()) == 0


def test_a_ball_smaller_than_the_signal_eats_it():
    # The failure mode worth knowing: a ball that fits inside the
    # droplet rolls over it and calls it background.
    frame, _background, mask = _uneven_frame(signal=800.0, radius=30)
    kept_big = subtract_rolling_ball(frame, 60)[mask].mean()
    kept_small = subtract_rolling_ball(frame, 8)[mask].mean()
    assert kept_big > 700.0
    assert kept_small < kept_big / 2.0


def test_the_estimate_shrinks_but_the_measurement_does_not():
    frame, _background, mask = _uneven_frame()
    corrected = subtract_rolling_ball(frame, 40)
    # Same shape, so an ROI still averages exactly its own pixels —
    # the shrink applies to the background estimate alone.
    assert corrected.shape == frame.shape
    assert int(np.count_nonzero(mask)) == int(np.count_nonzero(mask))
    assert _shrink_factor(8) == 1  # small ball: no shrink
    assert _shrink_factor(50) == 4
    assert _shrink_factor(400) == 8


def test_compute_image_stats_measures_the_corrected_frame(tmp_path):
    frame, _background, _mask = _uneven_frame()
    path = tmp_path / "uneven_raw.png"
    cv2.imwrite(str(path), frame)
    rois = {"a": ("ellipse", (160.0, 120.0, 12.0, 12.0, 0.0))}
    raw = compute_image_stats(str(path), rois)["stats"]["a"]
    flattened = compute_image_stats(str(path), rois, ball_radius_px=40)["stats"]["a"]
    assert raw["count"] == flattened["count"], "same pixels measured"
    # The background sat under the ROI; flattening takes it away.
    assert raw["mean"] > flattened["mean"] + 300.0
    assert flattened["mean"] > 700.0
