# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Session-object unit tests: defaults, name sequencing, and the
geometry-hashed cache keys on the session."""

# Microdrop package imports.
from image_viewer.analysis.roi_model import (
    PLOT_STATS,
    AnalysisSession,
    Roi,
    RoiAnalysisModel,
)
from image_viewer.discovery import capture_timestamp


def test_session_defaults_are_empty_and_mean():
    session = AnalysisSession()
    assert session.directory == ""
    assert session.rois == []
    assert session.stats == {}
    assert session.plot_stat == "mean"
    assert session.figure.x_auto and session.figure.y_auto
    assert session.figure.export_dpi == 300
    assert session.figure.export_format == "png"
    assert "bg_corrected" in PLOT_STATS


def test_roi_default_style_and_session_name_sequence():
    session = AnalysisSession()
    roi = Roi(
        name=session.next_roi_name(),
        kind="ellipse",
        geometry=[10.0, 10.0, 5.0, 5.0, 0.0],
    )
    assert roi.style.line_style == "solid"
    assert roi.style.marker == "none"
    session.rois.append(roi)
    assert session.next_roi_name() == "ROI 2"
    assert session.roi_by_id(roi.roi_id) is roi
    assert session.roi_by_id("nope") is None


def test_session_cache_key_uses_effective_geometry(tmp_path):
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi])
    key = session.cache_key(str(image), roi)
    assert key[2] == roi.roi_id and key[3] == "ellipse"
    assert key[4] == (5.0, 5.0, 2.0, 2.0, 0.0)


def test_cache_key_includes_the_ring(tmp_path):
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi])
    before = session.cache_key(str(image), roi)
    session.ring.gap_px = 5
    after = session.cache_key(str(image), roi)
    assert before != after
    assert after[5] == (5, session.ring.thickness_px, 0, (), ())


def test_cache_key_includes_the_rolling_ball(tmp_path):
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi])
    before = session.cache_key(str(image), roi)
    session.ball.enabled = True
    after = session.cache_key(str(image), roi)
    assert before != after, "flattening the frame changes the numbers"
    assert after[5][2] == session.ball.radius_px
    # A radius set while the ball is off changes nothing measured.
    session.ball.enabled = False
    session.ball.radius_px = 123
    assert session.cache_key(str(image), roi) == before


def test_model_gains_session_and_mirrors():
    model = RoiAnalysisModel()
    assert isinstance(model.session, AnalysisSession)
    assert model.filtered_paths == []
    assert model.current_image_path == ""


def test_experiment_switch_saves_and_reloads_stats(tmp_path, monkeypatch):
    """The headline behavior: stats computed in one visit are on disk
    and come back on the next visit to that experiment."""
    from image_viewer.analysis.roi_controller import (
        RoiAnalysisController,
    )
    from image_viewer.analysis.roi_store import (
        load_roi_stats,
    )
    from image_viewer.model import (
        ImageViewerModel,
    )

    exp_a = tmp_path / "ExpA"
    exp_b = tmp_path / "ExpB"
    (exp_a / "captures").mkdir(parents=True)
    (exp_b / "captures").mkdir(parents=True)

    viewer = ImageViewerModel()
    controller = RoiAnalysisController(
        viewer_model=viewer, analysis_model=viewer.roi_analysis
    )
    viewer.browsed_directory = str(exp_a / "captures")

    # A key as the app builds them: the absolute path of a file under
    # the experiment folder, which is what the store writes relative to.
    key = (
        str(exp_a / "captures" / "img.png"),
        1.0,
        "abcd1234",
        "ellipse",
        (5.0, 5.0, 2.0, 2.0, 0.0),
        (2, 4, 0, (), ()),
    )
    controller.session.stats[key] = {"mean": 7.0, "count": 4.0}
    controller._mark_stats_dirty()

    viewer.browsed_directory = str(exp_b / "captures")  # forces flush
    assert load_roi_stats(exp_a)[key]["mean"] == 7.0
    assert controller.session.stats == {}  # B starts empty

    viewer.browsed_directory = str(exp_a / "captures")  # come back
    assert controller.session.stats[key]["count"] == 4.0


def _mask(geometry=(5.0, 5.0, 2.0, 2.0, 0.0), **traits):
    return Roi(
        name="Mask 1",
        kind="ellipse",
        geometry=list(geometry),
        is_negative=True,
        **traits,
    )


def test_positive_and_negative_rois_split_the_list():
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[9.0, 9.0, 2.0, 2.0, 0.0])
    mask = _mask()
    session = AnalysisSession(rois=[roi, mask])
    assert session.positive_rois == [roi]
    assert session.negative_rois == [mask]

    mask.is_negative = False
    assert session.positive_rois == [roi, mask]
    assert session.negative_rois == []


def test_masks_are_numbered_apart_from_rois():
    session = AnalysisSession(
        rois=[Roi(name="ROI 1"), Roi(name="ROI 2"), _mask()],
    )
    assert session.next_roi_name() == "ROI 3"
    assert session.next_roi_name("Mask") == "Mask 2"


def test_effective_for_flags_the_negative_masks(tmp_path):
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[9.0, 9.0, 2.0, 2.0, 0.0])
    mask = _mask()
    session = AnalysisSession(rois=[roi, mask])
    rows = session.effective_for(str(image))
    assert [row[4] for row in rows] == [False, True]
    assert rows[1][:4] == (mask.roi_id, "Mask 1", "ellipse", list(mask.geometry))


def test_negatives_for_applies_drift_overrides(tmp_path):
    early = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    late = tmp_path / "a_2026_07_20-10_05_00_raw.png"
    for image in (early, late):
        image.write_bytes(b"")
    mask = _mask()
    mask.apply_edit(capture_timestamp(late), [7.0, 7.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[mask])

    assert session.negatives_for(str(early)) == (
        ("ellipse", (5.0, 5.0, 2.0, 2.0, 0.0)),
    )
    assert session.negatives_for(str(late)) == (("ellipse", (7.0, 7.0, 2.0, 2.0, 0.0)),)
    assert session.correction_for(str(late)) == session.correction_key() + (
        session.negatives_for(str(late)),
    )


def test_a_hidden_mask_is_left_out_of_the_calculation(tmp_path):
    """The mask's eye compares the numbers with and without it; each
    state has its own cache key, so both stay cached."""
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[9.0, 9.0, 2.0, 2.0, 0.0])
    mask = _mask()
    session = AnalysisSession(rois=[roi, mask])
    shown_key = session.cache_key(str(image), roi)

    mask.style.visible = False
    assert session.negatives_for(str(image)) == ()
    hidden_key = session.cache_key(str(image), roi)
    assert hidden_key != shown_key

    mask.style.visible = True
    assert session.negatives_for(str(image)) == (
        ("ellipse", (5.0, 5.0, 2.0, 2.0, 0.0)),
    )
    assert session.cache_key(str(image), roi) == shown_key


def test_cache_key_follows_the_masks(tmp_path):
    image = tmp_path / "a_2026_07_20-10_00_00_raw.png"
    image.write_bytes(b"")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[9.0, 9.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi])
    unmasked = session.cache_key(str(image), roi)
    # No masks: an empty fifth element, the same key every time.
    assert unmasked[5][4] == ()
    assert session.cache_key(str(image), roi) == unmasked

    mask = _mask()
    session.rois.append(mask)
    masked = session.cache_key(str(image), roi)
    assert masked != unmasked

    mask.geometry = [6.0, 5.0, 2.0, 2.0, 0.0]
    moved = session.cache_key(str(image), roi)
    assert moved != masked

    session.rois.remove(mask)
    assert session.cache_key(str(image), roi) == unmasked


def _images(tmp_path, *stamps):
    """Empty images whose filenames carry the given capture stamps."""
    paths = []

    for stamp in stamps:
        image = tmp_path / f"a_2026_07_20-{stamp}_raw.png"
        image.write_bytes(b"")
        paths.append(str(image))

    return paths


def test_a_mask_starts_at_the_image_it_was_drawn_on(tmp_path):
    before, drawn_on, after = _images(tmp_path, "10_00_00", "10_05_00", "10_10_00")
    mask = _mask(base_anchor=capture_timestamp(drawn_on))
    session = AnalysisSession(rois=[mask])
    expected = (("ellipse", (5.0, 5.0, 2.0, 2.0, 0.0)),)

    assert session.negatives_for(before) == ()
    assert session.effective_for(before) == []

    for path in (drawn_on, after):
        assert session.negatives_for(path) == expected
        assert [row[0] for row in session.effective_for(path)] == [mask.roi_id]


def test_a_mask_leaves_the_cache_keys_before_its_image_alone(tmp_path):
    before, drawn_on = _images(tmp_path, "10_00_00", "10_05_00")
    roi = Roi(name="ROI 1", kind="ellipse", geometry=[9.0, 9.0, 2.0, 2.0, 0.0])
    session = AnalysisSession(rois=[roi])
    unmasked_before = session.cache_key(before, roi)
    unmasked_drawn_on = session.cache_key(drawn_on, roi)

    session.rois.append(_mask(base_anchor=capture_timestamp(drawn_on)))

    assert session.cache_key(before, roi) == unmasked_before
    assert session.cache_key(drawn_on, roi) != unmasked_drawn_on


def test_a_positive_roi_applies_before_its_anchor_too(tmp_path):
    before, drawn_on = _images(tmp_path, "10_00_00", "10_05_00")
    roi = Roi(
        name="ROI 1",
        kind="ellipse",
        geometry=[9.0, 9.0, 2.0, 2.0, 0.0],
        base_anchor=capture_timestamp(drawn_on),
    )
    session = AnalysisSession(rois=[roi])

    for path in (before, drawn_on):
        assert [row[0] for row in session.effective_for(path)] == [roi.roi_id]
