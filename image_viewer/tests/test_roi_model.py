# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Roi override resolution and AnalysisSession cache keys."""

# Microdrop package imports.
from image_viewer.analysis.roi_model import (
    AnalysisSession,
    Roi,
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
