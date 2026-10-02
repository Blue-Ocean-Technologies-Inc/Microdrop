# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Series derivation: pure function of (session, filtered paths)."""

# Standard library imports.
import math

# Microdrop package imports.
from image_viewer.analysis.plot_series import (
    analysed_paths,
    background_ref_baseline,
    background_ref_corrected_series,
    derive_series,
    finite_values,
    image_values,
    interpolated_series,
    normalized_series,
    outlier_mask,
    shape_change_values,
    smoothed_values,
    stat_value,
    subtracted_series,
    visible_series,
    without_outliers,
)
from image_viewer.analysis.roi_model import (
    PLOT_STATS,
    AnalysisSession,
    Roi,
    RoiStyle,
)


def _image(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"")
    return str(path)


def test_derive_series_elapsed_axis_and_nan_gaps(tmp_path):
    first = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    second = _image(tmp_path, "b_2026_07_20-10_00_30_raw.png")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi])
    session.stats[session.cache_key(first, roi)] = {"mean": 10.0, "outline_mean": 4.0}

    series = derive_series(session, [first, second])
    name, elapsed, values = series[roi.roi_id]
    assert name == "ROI 1"
    assert elapsed == [0.0, 30.0]
    assert values[0] == 10.0
    assert math.isnan(values[1])  # uncomputed image gaps


def test_derive_series_honors_plot_stat(tmp_path):
    image = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi], plot_stat="bg_corrected")
    session.stats[session.cache_key(image, roi)] = {"mean": 10.0, "outline_mean": 4.0}
    ((_, _, values),) = derive_series(session, [image]).values()
    assert values == [6.0]


def test_derive_series_empty_inputs():
    assert derive_series(AnalysisSession(), []) == {}


def test_stat_value_variants():
    stats = {"mean": 10.0, "median": 9.0, "outline_mean": 4.0}
    assert stat_value(stats, "median") == 9.0
    assert stat_value(stats, "bg_corrected") == 6.0
    assert math.isnan(stat_value(None, "mean"))
    assert math.isnan(stat_value({}, "mean"))
    assert math.isnan(stat_value({"mean": 10.0}, "bg_corrected"))


def test_visible_series_drops_the_hidden_rois():
    shown = Roi(roi_id="a", name="ROI 1", kind="ellipse")
    hidden = Roi(
        roi_id="b", name="ROI 2", kind="ellipse", style=RoiStyle(visible=False)
    )
    session = AnalysisSession(rois=[shown, hidden])
    series = {"a": ("ROI 1", [0.0], [1.0]), "b": ("ROI 2", [0.0], [2.0])}

    assert visible_series(session, series) == {"a": ("ROI 1", [0.0], [1.0])}


def test_visible_series_keeps_everything_by_default():
    session = AnalysisSession(rois=[Roi(roi_id="a", name="ROI 1")])
    series = {"a": ("ROI 1", [0.0], [1.0])}
    assert visible_series(session, series) == series


def test_visible_series_drops_series_without_an_roi():
    # A stale entry cannot be styled, so it cannot be drawn either.
    session = AnalysisSession(rois=[])
    assert visible_series(session, {"gone": ("ROI 9", [], [])}) == {}


def test_plot_alpha_is_the_percentage_as_a_fraction():
    assert RoiStyle().plot_alpha == 1.0
    assert RoiStyle(alpha=40).plot_alpha == 0.4


def test_size_aware_stats_without_a_calibration():
    stats = {"mean": 10.0, "outline_mean": 4.0, "count": 25.0}
    # px² units: area is the pixel count and density is the mean.
    assert stat_value(stats, "area") == 25.0
    assert stat_value(stats, "integrated") == 250.0
    assert stat_value(stats, "bg_integrated") == 150.0
    assert stat_value(stats, "per_area") == 10.0
    assert stat_value(stats, "bg_per_area") == 6.0


def test_size_aware_stats_with_a_calibration():
    stats = {"mean": 10.0, "outline_mean": 4.0, "count": 25.0}
    # 1e-4 mm² per pixel: 25 px is 2.5e-3 mm².
    assert abs(stat_value(stats, "area", 1e-4) - 2.5e-3) < 1e-12
    assert abs(stat_value(stats, "per_area", 1e-4) - 1e5) < 1e-6
    assert abs(stat_value(stats, "bg_per_area", 1e-4) - 6e4) < 1e-6
    # Integrated is a pixel sum, so a calibration cannot change it.
    assert stat_value(stats, "integrated", 1e-4) == 250.0


def test_size_aware_stats_are_nan_when_a_piece_is_missing():
    assert math.isnan(stat_value({"mean": 10.0}, "integrated"))
    assert math.isnan(stat_value({"count": 25.0}, "per_area"))
    assert math.isnan(stat_value({"mean": 10.0, "count": 25.0}, "bg_integrated"))


def test_derive_series_uses_the_sessions_calibration(tmp_path):
    image = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    # per_area divides by the calibrated pixel area: 10 / 1e-4 mm^2 = 1e5.
    session = AnalysisSession(rois=[roi], plot_stat="per_area")
    session.scale.trait_set(metres_per_pixel=1e-5, unit="mm")
    session.stats[session.cache_key(image, roi)] = {
        "mean": 10.0,
        "outline_mean": 4.0,
        "count": 25.0,
    }

    _name, _elapsed, values = derive_series(session, [image])[roi.roi_id]
    assert abs(values[0] - 1e5) < 1e-6


def test_derive_series_plots_area_in_the_calibrated_unit(tmp_path):
    image = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi], plot_stat="area")
    session.scale.trait_set(metres_per_pixel=1e-5, unit="mm")
    session.stats[session.cache_key(image, roi)] = {"mean": 10.0, "count": 25.0}

    _name, _elapsed, values = derive_series(session, [image])[roi.roi_id]

    # 25 px at 1e-4 mm^2 each.
    assert abs(values[0] - 2.5e-3) < 1e-12


def test_analysed_paths_leave_out_excluded_images(tmp_path):
    first = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    second = _image(tmp_path, "b_2026_07_20-10_00_30_raw.png")
    session = AnalysisSession(excluded_images=["a_2026_07_20-10_00_00_raw.png"])

    assert analysed_paths(session, [first, second]) == [second]


def test_image_values_are_the_series_cross_section_at_an_image():
    series = {
        "a": ("ROI 1", [0.0, 1.0], [10.0, 20.0]),
        "b": ("ROI 2", [0.0, 1.0], [30.0, math.nan]),
    }

    result = image_values(series, ["one.png", "two.png"], "two.png")

    assert result["a"] == ("ROI 1", 20.0)
    assert result["b"][0] == "ROI 2"
    assert math.isnan(result["b"][1])  # uncomputed stays a gap


def test_image_values_are_none_for_an_image_outside_the_series():
    series = {"a": ("ROI 1", [0.0], [10.0])}

    assert image_values(series, ["one.png"], "excluded.png") is None
    assert image_values(series, ["one.png"], "") is None


def test_finite_values_drop_gaps_and_empty_curves():
    series = {
        "a": ("ROI 1", [0.0, 1.0, 2.0], [10.0, math.nan, 30.0]),
        "b": ("ROI 2", [0.0, 1.0, 2.0], [math.nan, math.nan, math.nan]),
    }

    assert finite_values(series) == {"a": ("ROI 1", [10.0, 30.0])}


def test_normalized_series_stretches_each_roi_to_its_own_range():
    series = {
        "a": ("ROI 1", [0.0, 1.0, 2.0], [10.0, 20.0, 30.0]),
        "b": ("ROI 2", [0.0, 1.0, 2.0], [100.0, 300.0, 500.0]),
    }
    result = normalized_series(series)
    assert result["a"][2] == [0.0, 50.0, 100.0]
    assert result["b"][2] == [0.0, 50.0, 100.0]
    # Names and time axes ride through untouched.
    assert result["a"][0] == "ROI 1" and result["a"][1] == [0.0, 1.0, 2.0]


def test_normalized_series_keeps_gaps_as_gaps():
    series = {"a": ("ROI 1", [0.0, 1.0, 2.0], [10.0, math.nan, 30.0])}
    values = normalized_series(series)["a"][2]
    assert values[0] == 0.0 and values[2] == 100.0
    assert math.isnan(values[1])


def test_normalized_series_leaves_a_flat_curve_at_zero():
    series = {"a": ("ROI 1", [0.0, 1.0], [7.0, 7.0])}
    assert normalized_series(series)["a"][2] == [0.0, 0.0]


def test_normalized_series_passes_an_all_nan_curve_through():
    series = {"a": ("ROI 1", [0.0, 1.0], [math.nan, math.nan])}
    assert all(math.isnan(value) for value in normalized_series(series)["a"][2])


def test_subtracted_series_starts_every_curve_at_zero():
    series = {
        "a": ("ROI 1", [0.0, 1.0], [10.0, 30.0]),
        "b": ("ROI 2", [0.0, 1.0], [100.0, 90.0]),
    }
    result = subtracted_series(series)
    assert result["a"][2] == [0.0, 20.0]
    assert result["b"][2] == [0.0, -10.0]


def test_subtracted_series_uses_the_first_finite_value():
    series = {"a": ("ROI 1", [0.0, 1.0, 2.0], [math.nan, 10.0, 15.0])}
    values = subtracted_series(series)["a"][2]
    assert math.isnan(values[0])
    assert values[1] == 0.0 and values[2] == 5.0


def test_subtracted_series_passes_an_all_nan_curve_through():
    series = {"a": ("ROI 1", [0.0], [math.nan])}
    assert math.isnan(subtracted_series(series)["a"][2][0])


def _background_refs_session():
    """Two samples and two background references, on a series of
    three images."""
    rois = [
        Roi(roi_id="s1", name="Sample 1", kind="ellipse"),
        Roi(roi_id="s2", name="Sample 2", kind="ellipse"),
        Roi(roi_id="b1", name="Blank 1", kind="ellipse", is_background_ref=True),
        Roi(roi_id="b2", name="Blank 2", kind="ellipse", is_background_ref=True),
    ]
    series = {
        "s1": ("Sample 1", [0.0, 1.0, 2.0], [100.0, 200.0, 300.0]),
        "s2": ("Sample 2", [0.0, 1.0, 2.0], [150.0, 250.0, 350.0]),
        "b1": ("Blank 1", [0.0, 1.0, 2.0], [10.0, 20.0, 30.0]),
        "b2": ("Blank 2", [0.0, 1.0, 2.0], [30.0, 40.0, 50.0]),
    }
    return AnalysisSession(rois=rois), series


def test_the_baseline_is_the_mean_of_the_marked_rois():
    session, series = _background_refs_session()
    assert background_ref_baseline(session, series) == [20.0, 30.0, 40.0]


def test_the_correction_subtracts_that_baseline_from_every_roi():
    session, series = _background_refs_session()
    corrected = background_ref_corrected_series(session, series)
    assert corrected["s1"][2] == [80.0, 170.0, 260.0]
    assert corrected["s2"][2] == [130.0, 220.0, 310.0]
    # The references are corrected too, and straddle zero — a flat pair
    # about zero is the visible evidence the control behaved.
    assert corrected["b1"][2] == [-10.0, -10.0, -10.0]
    assert corrected["b2"][2] == [10.0, 10.0, 10.0]


def test_nothing_marked_leaves_the_series_untouched():
    session, series = _background_refs_session()
    for roi in session.rois:
        roi.is_background_ref = False
    assert background_ref_baseline(session, series) is None
    assert background_ref_corrected_series(session, series) == series


def test_a_reference_missing_a_value_averages_the_others():
    session, series = _background_refs_session()
    series["b1"] = ("Blank 1", [0.0, 1.0, 2.0], [math.nan, 20.0, math.nan])
    series["b2"] = ("Blank 2", [0.0, 1.0, 2.0], [30.0, 40.0, math.nan])
    baseline = background_ref_baseline(session, series)
    assert baseline[0] == 30.0  # only the one that has a value
    assert baseline[1] == 30.0  # both
    assert baseline[2] != baseline[2]  # neither: a gap, not a guess
    corrected = background_ref_corrected_series(session, series)["s1"][2]
    assert corrected[0] == 70.0 and corrected[1] == 170.0
    assert corrected[2] != corrected[2]


def test_a_hidden_reference_still_corrects():
    # The references are exactly the curves a user hides once they are
    # flat; that click must not switch the correction off.
    session, series = _background_refs_session()
    session.roi_by_id("b1").style = RoiStyle(visible=False)
    session.roi_by_id("b2").style = RoiStyle(visible=False)
    corrected = background_ref_corrected_series(session, series)
    assert corrected["s1"][2] == [80.0, 170.0, 260.0]
    # Hiding is applied after, and drops only what is drawn.
    shown = visible_series(session, corrected)
    assert set(shown) == {"s1", "s2"}


def test_background_ref_and_subtract_first_stack_and_commute():
    session, series = _background_refs_session()
    stacked = subtracted_series(background_ref_corrected_series(session, series))
    # Sample 1 corrected is [80, 170, 260]; less its own first value.
    assert stacked["s1"][2] == [0.0, 90.0, 180.0]
    # Both are subtractions of a constant per point, so on complete
    # data the order they are applied in cannot change the answer —
    # ticking the two boxes in either order gives the same curve.
    # (Only where a curve's first finite value falls on a different
    # image can they diverge.)
    other_way = background_ref_corrected_series(session, subtracted_series(series))
    assert other_way["s1"][2] == stacked["s1"][2]


def _rising(count=21, spike_at=None, spike=900.0):
    values = [100.0 + 10.0 * index for index in range(count)]
    if spike_at is not None:
        values[spike_at] = spike
    return ("ROI 1", [float(index) for index in range(count)], values)


def test_the_hampel_test_finds_a_spike_and_leaves_a_trend_alone():
    _name, _elapsed, clean = _rising()
    _name, _elapsed, spiked = _rising(spike_at=10)
    assert not any(outlier_mask(clean))
    flags = outlier_mask(spiked)
    assert flags[10] is True
    assert sum(flags) == 1


def test_an_isolated_spike_is_found_on_any_shape_of_baseline():
    spike = 900.0
    baselines = {
        "flat": [100.0] * 21,
        "noisy": [100.0 + (2.0 if index % 2 else -2.0) for index in range(21)],
        "rising": [100.0 + 10.0 * index for index in range(21)],
        "sigmoid": [
            100.0 + 800.0 / (1.0 + math.exp(-0.3 * (index - 10))) for index in range(21)
        ],
    }
    for label, values in baselines.items():
        assert not any(outlier_mask(values, window=7)), (
            f"{label}: a clean baseline has no outliers"
        )
        # Index 3, where each of these baselines is still flat-ish.
        # A spike at the sigmoid's midpoint would NOT be found, the
        # curve moving as much across that window as the spike does.
        spiked = list(values)
        spiked[3] = spike
        flags = outlier_mask(spiked, window=7)
        assert flags[3] is True, label
        assert sum(flags) == 1, f"{label}: nothing else flagged"


def test_outliers_packed_into_one_window_stop_being_outliers():
    # The known limit of a windowed test, worth pinning rather than
    # discovering: three spikes inside a seven-point window are no
    # longer unusual relative to each other.
    values = [100.0] * 21
    for index in (8, 10, 12):
        values[index] = 900.0
    assert not any(outlier_mask(values, window=7))
    # Spread them out and each is isolated again.
    values = [100.0] * 21
    for index in (2, 10, 18):
        values[index] = 900.0
    assert [
        index for index, flag in enumerate(outlier_mask(values, window=7)) if flag
    ] == [2, 10, 18]


def test_an_alternating_signal_is_not_all_outliers():
    # Half its values are identical, so the median deviation is zero
    # while the data plainly has spread — the case that made an
    # earlier version flag seventeen points of twenty-one.
    sawtooth = [100.0 + (2.0 if index % 2 else -2.0) for index in range(21)]
    assert not any(outlier_mask(sawtooth, window=7))


def test_gaps_are_not_outliers_and_survive_removal():
    values = [1.0, 2.0, math.nan, 4.0, 5.0]
    assert outlier_mask(values) == [False] * 5
    series = {"a": ("ROI 1", [0.0, 1.0, 2.0, 3.0, 4.0], values)}
    cleaned, flags = without_outliers(series)
    assert cleaned["a"][2][2] != cleaned["a"][2][2]  # still a gap
    assert not any(flags["a"])


def test_removal_replaces_the_point_with_a_gap():
    series = {"a": _rising(spike_at=10)}
    cleaned, flags = without_outliers(series)
    values = cleaned["a"][2]
    assert values[10] != values[10], "dropped, not replaced by a guess"
    assert values[9] == 190.0 and values[11] == 210.0
    assert flags["a"][10] is True


def test_the_threshold_and_window_are_the_users_to_set():
    _name, _elapsed, spiked = _rising(spike_at=10)
    assert outlier_mask(spiked, threshold=3.0)[10] is True
    assert not outlier_mask(spiked, threshold=30.0)[10], (
        "a laxer threshold must keep the point"
    )


def test_smoothing_reduces_the_wiggle_without_moving_the_level():
    noisy = [100.0 + (5.0 if index % 2 else -5.0) for index in range(31)]
    for method in ("savgol", "butterworth"):
        smoothed = smoothed_values(noisy, method, window=7, order=2, cutoff=0.2)
        middle = smoothed[5:-5]
        assert max(middle) - min(middle) < 4.0, method
        assert abs(sum(middle) / len(middle) - 100.0) < 1.0, method


def test_smoothing_keeps_gaps_and_length():
    values = [float(index) for index in range(21)]
    values[7] = math.nan
    for method in ("savgol", "butterworth"):
        smoothed = smoothed_values(values, method)
        assert len(smoothed) == len(values), method
        assert smoothed[7] != smoothed[7], f"{method} invented a value"


def test_a_series_too_short_to_filter_is_returned_as_it_is():
    short = [1.0, 2.0, 3.0]
    assert smoothed_values(short, "butterworth") == short
    assert smoothed_values(short, "none") == short
    assert smoothed_values([], "savgol") == []


def test_interpolation_bridges_an_internal_gap_linearly():
    series = {"a": ("ROI 1", [0.0, 1.0, 2.0, 3.0], [10.0, math.nan, math.nan, 40.0])}
    ((_, _, values),) = interpolated_series(series).values()
    assert values == [10.0, 20.0, 30.0, 40.0]


def test_interpolation_leaves_the_open_ends_open():
    series = {"a": ("ROI 1", [0.0, 1.0, 2.0, 3.0], [math.nan, 1.0, 2.0, math.nan])}
    ((_, _, values),) = interpolated_series(series).values()
    assert math.isnan(values[0]) and math.isnan(values[3]), (
        "an end gap has no far side to bridge to"
    )
    assert values[1:3] == [1.0, 2.0]


def test_interpolation_passes_curves_it_cannot_bridge_through():
    series = {
        "a": ("ROI 1", [0.0, 1.0], [math.nan, math.nan]),
        "b": ("ROI 2", [0.0, 1.0], [math.nan, 5.0]),
        "c": ("ROI 3", [0.0, 1.0], [1.0, 2.0]),
    }
    bridged = interpolated_series(series)
    assert all(value != value for value in bridged["a"][2])
    assert math.isnan(bridged["b"][2][0]) and bridged["b"][2][1] == 5.0
    assert bridged["c"][2] == [1.0, 2.0]


def _shape_stats(*hu_root):
    """Pane stats carrying a shape (a short Hu vector is enough here)."""
    return {"circularity": 0.98, "hu_root": list(hu_root)}


def test_shape_quantities_are_plot_stats():
    for stat in (
        "circularity",
        "shape_change",
        "axis_ratio",
        "eccentricity",
        "solidity",
        "extent",
        "orientation_deg",
    ):
        assert stat in PLOT_STATS


def test_shape_change_is_measured_from_the_first_image_with_a_droplet():
    no_droplet = {"circularity": math.nan, "hu_root": None}
    values = shape_change_values(
        [None, no_droplet, _shape_stats(1.0, 0.0), _shape_stats(1.0, 0.5)]
    )

    assert math.isnan(values[0])  # uncomputed
    assert math.isnan(values[1])  # no droplet: no shape to compare
    assert values[2] == 0.0
    assert abs(values[3] - 0.5) < 1e-12


def test_shape_change_without_any_droplet_is_all_nan():
    values = shape_change_values([None, {"hu_root": None}])

    assert all(math.isnan(value) for value in values)


def test_shape_change_rebaselines_when_the_first_image_is_excluded(tmp_path):
    first = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    second = _image(tmp_path, "b_2026_07_20-10_00_30_raw.png")
    third = _image(tmp_path, "c_2026_07_20-10_01_00_raw.png")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi], plot_stat="shape_change")

    for path, hu_root in (
        (first, (1.0, 0.0)),
        (second, (1.0, 0.3)),
        (third, (1.0, 0.4)),
    ):
        session.stats[session.cache_key(path, roi)] = _shape_stats(*hu_root)

    _name, _x, values = derive_series(session, [first, second, third])[roi.roi_id]

    assert [round(value, 9) for value in values] == [0.0, 0.3, 0.4]

    session.excluded_images = ["a_2026_07_20-10_00_00_raw.png"]
    _name, _x, values = derive_series(session, [first, second, third])[roi.roi_id]

    assert [round(value, 9) for value in values] == [0.0, 0.1]


def test_per_image_shape_stats_plot_as_stored(tmp_path):
    image = _image(tmp_path, "a_2026_07_20-10_00_00_raw.png")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi], plot_stat="axis_ratio")
    # Unitless: the calibration must not scale it.
    session.scale.trait_set(metres_per_pixel=1e-5, unit="mm")
    session.stats[session.cache_key(image, roi)] = {"axis_ratio": 2.0}

    _name, _x, values = derive_series(session, [image])[roi.roi_id]

    assert values == [2.0]
