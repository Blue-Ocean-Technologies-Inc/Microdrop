# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""measured_pixels hands the Histogram view the very pixels
compute_image_stats reduces — or, in the RGB channel mode, a colour
frame's channels through the same mask — and the frame/mask refactor
behind it leaves compute_image_stats's numbers where they were."""

# Third-party imports.
import cv2
import numpy as np
import pytest

# Microdrop package imports.
from image_viewer.analysis.roi_compute import compute_image_stats, measured_pixels
from image_viewer.analysis.shape_descriptors import ROI_SHAPE_STATS

#: Two ROIs over two droplets; "b" loses a corner to the negative mask.
ROIS = {
    "a": ("ellipse", (20.0, 20.0, 12.0, 12.0, 0.0)),
    "b": ("ellipse", (44.0, 42.0, 13.0, 10.0, 30.0)),
}
NEGATIVES = (("ellipse", (50.0, 46.0, 4.0, 4.0, 0.0)),)

#: compute_image_stats's (gap, thickness, ball radius, perspective,
#: negatives, inside percent): a rolling ball, a cut-out and an inset,
#: so every step of the measured-pixel pipeline is exercised.
CORRECTION = (2, 4, 15, (), NEGATIVES, 80)

#: compute_image_stats's intensity and ring stats on the frame below,
#: computed with the function as it stood before the frame and mask
#: preparation were factored out.
GOLDEN_STATS = {
    "a": {
        "mean": 558.217665615142,
        "std": 430.7787679812534,
        "median": 879.0,
        "min": 0.0,
        "max": 924.0,
        "count": 317.0,
        "outline_mean": 10.027777777777779,
        "outline_std": 10.40623046234638,
        "outline_median": 7.0,
        "outline_min": 0.0,
        "outline_max": 32.0,
        "outline_count": 396.0,
    },
    "b": {
        "mean": 300.0536398467433,
        "std": 293.6488066446714,
        "median": 31.0,
        "min": 0.0,
        "max": 624.0,
        "count": 261.0,
        "outline_mean": 13.848866498740554,
        "outline_std": 13.047957655014981,
        "outline_median": 11.0,
        "outline_min": 0.0,
        "outline_max": 49.0,
        "outline_count": 397.0,
    },
}

#: The shape stats from the same run — float results of contour
#: moments, so compared to a tolerance rather than bit for bit.
GOLDEN_SHAPE_STATS = {
    "a": {
        "circularity": 0.9344252261690101,
        "axis_ratio": 1.0,
        "eccentricity": 0.0,
        "solidity": 0.9354838709677419,
        "extent": 0.6020761245674741,
        "orientation_deg": 0.0,
    },
    "b": {
        "circularity": 0.7215078817001485,
        "axis_ratio": 1.259438474553235,
        "eccentricity": 0.6079116895693283,
        "solidity": 0.8365019011406845,
        "extent": 0.4888888888888889,
        "orientation_deg": -56.825001715832414,
    },
}


def _droplet_frame(tmp_path):
    """A 64x64 16-bit frame: a sloped, textured background under two
    bright droplets, saved where compute_image_stats can read it."""
    rows, columns = np.mgrid[0:64, 0:64]
    array = 100 + 3 * rows + 2 * columns + (rows * 7 + columns * 13) % 50
    array[(rows - 20) ** 2 + (columns - 20) ** 2 <= 64] += 900
    array[(rows - 42) ** 2 + (columns - 44) ** 2 <= 49] += 600

    path = tmp_path / "img_2026_07_20-17_46_24_raw.png"
    cv2.imwrite(str(path), array.astype(np.uint16))

    return path


#: A droplet's (R, G, B) on the colour frame below, over a black field.
DROPLET_RGB = (200, 120, 40)
#: One ROI well inside the droplet, so every pixel it measures is the
#: droplet's colour.
COLOUR_ROIS = {"drop": ("ellipse", (32.0, 32.0, 10.0, 10.0, 0.0))}


def _colour_frame(tmp_path):
    """A 64x64 8-bit RGB capture: a droplet of DROPLET_RGB, radius 16,
    on black, written as cv2 writes a camera frame (BGR order)."""
    rows, columns = np.mgrid[0:64, 0:64]
    array = np.zeros((64, 64, 3), dtype=np.uint8)
    array[(rows - 32) ** 2 + (columns - 32) ** 2 <= 256] = DROPLET_RGB

    path = tmp_path / "img_2026_07_20-17_46_24.png"
    cv2.imwrite(str(path), cv2.cvtColor(array, cv2.COLOR_RGB2BGR))

    return path


def test_compute_image_stats_is_unchanged_by_the_refactor(tmp_path):
    result = compute_image_stats(_droplet_frame(tmp_path), ROIS, *CORRECTION)

    assert result["error"] is None

    for roi_id, golden in GOLDEN_STATS.items():
        stats = result["stats"][roi_id]

        assert {name: stats[name] for name in golden} == golden
        assert {name: stats[name] for name in ROI_SHAPE_STATS} == pytest.approx(
            GOLDEN_SHAPE_STATS[roi_id]
        )


def test_measured_pixels_are_the_pixels_the_stats_reduce(tmp_path):
    path = _droplet_frame(tmp_path)
    stats = compute_image_stats(path, ROIS, *CORRECTION)["stats"]
    measured = measured_pixels(path, ROIS, *CORRECTION)

    assert measured["error"] is None
    assert measured["mtime"] > 0
    assert set(measured["pixels"]) == set(ROIS)

    for roi_id, pixels in measured["pixels"].items():
        assert pixels.ndim == 1
        assert pixels.size == stats[roi_id]["count"]
        assert float(np.mean(pixels)) == stats[roi_id]["mean"]
        assert float(np.median(pixels)) == stats[roi_id]["median"]


def test_rgb_mode_splits_a_colour_frame_into_its_channels(tmp_path):
    measured = measured_pixels(_colour_frame(tmp_path), COLOUR_ROIS, channel_mode="rgb")
    pixels = measured["pixels"]["drop"]

    assert measured["error"] is None
    assert measured["colour"] is True
    assert pixels.ndim == 2 and pixels.shape[1] == 3 and pixels.shape[0] > 0
    assert tuple(float(mean) for mean in pixels.mean(axis=0)) == DROPLET_RGB


def test_luma_mode_on_a_colour_frame_is_the_stats_tables_pixels(tmp_path):
    path = _colour_frame(tmp_path)
    stats = compute_image_stats(path, COLOUR_ROIS)["stats"]["drop"]
    measured = measured_pixels(path, COLOUR_ROIS)
    pixels = measured["pixels"]["drop"]

    assert measured["colour"] is False
    assert pixels.ndim == 1
    assert pixels.size == stats["count"]
    assert float(np.mean(pixels)) == stats["mean"]


def test_rgb_mode_reads_a_mono_frame_as_luma(tmp_path):
    path = _droplet_frame(tmp_path)
    luma = measured_pixels(path, ROIS, *CORRECTION)
    rgb = measured_pixels(path, ROIS, *CORRECTION, channel_mode="rgb")

    assert rgb["error"] is None
    assert rgb["colour"] is False

    for roi_id, pixels in rgb["pixels"].items():
        assert pixels.ndim == 1
        assert np.array_equal(pixels, luma["pixels"][roi_id])


def test_measured_pixels_report_an_unreadable_file(tmp_path):
    path = tmp_path / "broken_raw.png"
    path.write_bytes(b"not a png")

    measured = measured_pixels(path, ROIS, *CORRECTION)

    assert measured["error"]
    assert measured["pixels"] == {}
