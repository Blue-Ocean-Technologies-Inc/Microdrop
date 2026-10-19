# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Roi override resolution, AnalysisSession cache keys, and the
Expected table's rows."""

# Standard library imports.
import math

# Microdrop package imports.
from image_viewer.analysis.consts import (
    COPY_TREND_CALIBRATED,
    COPY_TREND_FLIPPED,
    COPY_TREND_NO_TREND,
    COPY_TREND_NOT_TEMPERATURE,
    COPY_TREND_TOOLTIP,
)
from image_viewer.analysis.roi_model import (
    AnalysisSession,
    Roi,
    RoiAnalysisModel,
)


def _roi():
    return Roi(
        name="ROI 1",
        kind="ellipse",
        geometry=[50.0, 50.0, 10.0, 10.0, 0.0],
        base_anchor=100.0,
    )


def test_effective_geometry_is_base_without_overrides():
    assert _roi().effective_geometry(500.0) == [50.0, 50.0, 10.0, 10.0, 0.0]


def test_override_applies_from_its_anchor_forward():
    roi = _roi()
    roi.apply_edit(200.0, [60.0, 60.0, 12.0])
    assert roi.effective_geometry(150.0) == [50.0, 50.0, 10.0, 10.0, 0.0]
    assert roi.effective_geometry(200.0) == [60.0, 60.0, 12.0]
    assert roi.effective_geometry(999.0) == [60.0, 60.0, 12.0]


def test_latest_applicable_override_wins():
    roi = _roi()
    roi.apply_edit(200.0, [60.0, 60.0, 12.0])
    roi.apply_edit(300.0, [70.0, 70.0, 14.0])
    assert roi.effective_geometry(250.0) == [60.0, 60.0, 12.0]
    assert roi.effective_geometry(350.0) == [70.0, 70.0, 14.0]


def test_edit_at_or_before_base_anchor_updates_base():
    roi = _roi()
    roi.apply_edit(100.0, [55.0, 55.0, 11.0])
    assert roi.geometry == [55.0, 55.0, 11.0]
    assert roi.overrides == {}


def test_clear_overrides_restores_base_everywhere():
    roi = _roi()
    roi.apply_edit(200.0, [60.0, 60.0, 12.0])
    roi.clear_overrides()
    assert roi.effective_geometry(999.0) == [50.0, 50.0, 10.0, 10.0, 0.0]


def test_cache_key_changes_only_with_effective_geometry(tmp_path):
    path = tmp_path / "img_2026_07_20-17_46_24_raw.png"
    path.write_bytes(b"")
    session = AnalysisSession()
    roi = _roi()
    session.rois = [roi]
    key_before = session.cache_key(path, roi)
    # An override anchored AFTER this image's capture time: key unchanged.
    roi.apply_edit(9e12, [60.0, 60.0, 12.0])
    assert session.cache_key(path, roi) == key_before
    # An override covering it: key changes.
    roi.apply_edit(0.0, [61.0, 61.0, 12.0])
    assert session.cache_key(path, roi) != key_before


def test_roi_ids_are_unique_and_names_sequence():
    session = AnalysisSession()
    first, second = Roi(), Roi()
    assert first.roi_id != second.roi_id
    first.name = "ROI 1"
    session.rois = [first]
    assert session.next_roi_name() == "ROI 2"


def test_a_mask_applies_from_its_base_anchor_and_a_positive_everywhere():
    mask = Roi(is_negative=True, base_anchor=100.0)
    positive = Roi(base_anchor=100.0)

    assert not mask.applies_at(99.0)
    assert mask.applies_at(100.0)
    assert mask.applies_at(500.0)
    assert positive.applies_at(0.0)
    assert positive.applies_at(500.0)


def test_expected_rows_are_one_per_positive_roi_per_compared_metric():
    first, second = Roi(name="ROI 1"), Roi(name="ROI 2")
    model = RoiAnalysisModel(
        session=AnalysisSession(rois=[first, Roi(is_negative=True), second])
    )
    model.session.figure.compare_second_derivative_min = True
    model.expected_actuals = {first.roi_id: {"zero": 10.0, "min": 20.0}}

    rows = model.expected_rows

    assert [(row.roi, row.metric) for row in rows] == [
        (first, "zero"),
        (first, "min"),
        (second, "zero"),
        (second, "min"),
    ]
    assert [row.label for row in rows[:2]] == ["d² zero", "d² min"]

    # Unset reads as the actual; a write lands on the metric's own trait.
    assert rows[1].expected == 20.0
    assert math.isnan(rows[2].actual)

    rows[1].expected = 25.0

    assert first.expected_second_derivative_min == 25.0
    assert math.isnan(first.expected_fastest_change)
    assert rows[0].expected == 10.0


def test_a_mask_drawn_with_no_image_shown_applies_everywhere():
    mask = Roi(is_negative=True)

    assert mask.base_anchor == 0.0
    assert mask.applies_at(0.0)
    assert mask.applies_at(1e9)


def test_the_trend_follows_the_fitted_landmarks():
    model = RoiAnalysisModel()
    model.session = AnalysisSession(
        rois=[Roi(roi_id="a", name="A"), Roi(roi_id="b", name="B")]
    )
    model.session.figure.fit_method = "sigmoid"
    model.expected_actuals = {"a": {"zero": 50.0}, "b": {"zero": 60.0}}
    assert model.session.trend.method == "linear"
    model.session.figure.trend_method = "poly2"
    assert model.session.trend is None  # two points cannot fix a quadratic
    model.session.figure.trend_method = "linear"
    model.session.figure.fit_method = "none"
    assert model.session.trend is None


def test_copy_needs_a_trend_on_an_unflipped_uncalibrated_temperature_axis():
    model = RoiAnalysisModel()
    model.session = AnalysisSession(
        rois=[Roi(roi_id="a", name="A"), Roi(roi_id="b", name="B")]
    )
    figure = model.session.figure
    assert model.copy_trend_blocker == COPY_TREND_NO_TREND
    figure.fit_method = "sigmoid"
    model.expected_actuals = {"a": {"zero": 50.0}, "b": {"zero": 60.0}}
    assert model.copy_trend_blocker == COPY_TREND_NOT_TEMPERATURE
    figure.x_axis = "temperature"
    figure.flip_actual_expected = True
    assert model.copy_trend_blocker == COPY_TREND_FLIPPED
    figure.flip_actual_expected = False
    figure.temperature_expression = "2*x - 5"
    assert model.copy_trend_blocker == COPY_TREND_CALIBRATED
    assert model.copy_trend_tooltip == COPY_TREND_CALIBRATED
    figure.temperature_expression = "x"
    assert model.copy_trend_blocker == ""
    assert model.copy_trend_tooltip == COPY_TREND_TOOLTIP
