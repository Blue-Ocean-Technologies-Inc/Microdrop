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
    assert after[5] == (5, session.ring.thickness_px, 0, ())


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
        (2, 4, 0, ()),
    )
    controller.session.stats[key] = {"mean": 7.0, "count": 4.0}
    controller._mark_stats_dirty()

    viewer.browsed_directory = str(exp_b / "captures")  # forces flush
    assert load_roi_stats(exp_a)[key]["mean"] == 7.0
    assert controller.session.stats == {}  # B starts empty

    viewer.browsed_directory = str(exp_a / "captures")  # come back
    assert controller.session.stats[key]["count"] == 4.0
