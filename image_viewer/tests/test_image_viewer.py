# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Hardware-free tests for the 16-bit image viewer display helpers and
capture discovery."""

# Standard library imports.
import os

# Third-party imports.
import cv2
import numpy as np
from PySide6.QtGui import QImage

# Microdrop package imports.
from image_viewer import controller as viewer_controller_mod
from image_viewer import discovery
from image_viewer.controller import (
    ImageViewerController,
)
from image_viewer.display import (
    qimage_to_array,
    stretch_to_8bit,
)
from image_viewer.model import (
    IMAGE_FILTER_ALL,
    ImageViewerModel,
)


def test_16bit_png_round_trip_is_lossless(tmp_path):
    raw = np.arange(40 * 30, dtype=np.uint16).reshape(30, 40) * 50
    path = str(tmp_path / "raw.png")
    assert cv2.imwrite(path, raw)
    back = qimage_to_array(QImage(path))
    assert back.dtype == np.uint16
    assert np.array_equal(back, raw)


def test_auto_contrast_windows_dim_frames():
    # dark field + small bright blob: naive full-range display is ~black.
    raw = np.full((60, 80), 400, dtype=np.uint16)
    raw[20:30, 30:40] = 3200
    naive = stretch_to_8bit(raw, auto_contrast=False)
    auto = stretch_to_8bit(raw, auto_contrast=True)
    assert naive.max() <= 12
    assert auto.min() == 0 and auto.max() == 255


def test_flat_frame_does_not_divide_by_zero():
    flat = np.full((8, 8), 1234, dtype=np.uint16)
    out = stretch_to_8bit(flat, auto_contrast=True)
    assert out.dtype == np.uint8


def test_8bit_grayscale_passthrough_shape():
    img = np.random.default_rng(0).integers(0, 255, (16, 16), dtype=np.uint8)
    out = stretch_to_8bit(img, auto_contrast=False)
    assert out.shape == img.shape and out.dtype == np.uint8


def test_manual_window_maps_low_to_black_high_to_white():
    raw = np.array([[100, 200], [300, 400]], dtype=np.uint16)
    out = stretch_to_8bit(raw, auto_contrast=False, window=(200, 400))
    assert out[0, 0] == 0  # below the window clips to black
    assert out[0, 1] == 0  # window low edge
    assert out[1, 1] == 255  # window high edge
    assert 0 < out[1, 0] < 255  # mid-window stays mid-gray


def test_manual_window_inverted_renders_black_not_crash():
    raw = np.full((4, 4), 300, dtype=np.uint16)
    out = stretch_to_8bit(raw, auto_contrast=False, window=(400, 200))
    assert out.dtype == np.uint8 and out.max() == 0


def test_manual_window_ignored_while_auto_contrast_on():
    raw = np.full((60, 80), 400, dtype=np.uint16)
    raw[20:30, 30:40] = 3200
    auto = stretch_to_8bit(raw, auto_contrast=True, window=(0, 65535))
    assert auto.max() == 255  # percentile window, not the manual one


def test_viewer_model_positions():
    from pathlib import Path

    from image_viewer.model import (
        ImageViewerModel,
    )

    model = ImageViewerModel()
    assert model.position_text == ""  # nothing discovered

    paths = [Path("a.png"), Path("b.png"), Path("c.png")]
    model.bursts = [("session", paths)]
    model.selected_burst = "session"
    model.paths = paths
    assert model.position_text == "–/3"  # showing an outside image
    assert model.image_names == ["a.png", "b.png", "c.png"]
    assert model.max_image_index == 2

    model.current_path = str(Path("c.png"))
    assert model.position_text == "3/3"
    assert model.path_index() == 2


def test_discover_captures_oldest_first_by_save_time(tmp_path):
    assert discovery.discover_captures(None) == []
    assert discovery.discover_captures(tmp_path / "absent") == []
    # Any image under the folder counts, whatever subfolder it is in.
    raw_dir = tmp_path / "16bit_raw"
    raw_dir.mkdir()
    older, newer = raw_dir / "b_older.png", raw_dir / "a_newer.png"
    older.write_bytes(b"")
    newer.write_bytes(b"")
    os.utime(older, (1_000, 1_000))
    os.utime(newer, (2_000, 2_000))
    assert discovery.discover_captures(tmp_path) == [older, newer]


def test_current_captures_directory_returns_captures_folder(tmp_path, monkeypatch):
    # The renamed function returns <exp>/captures (not <exp>/captures/16bit_raw).
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: tmp_path)
    assert discovery.current_captures_directory() == tmp_path / "captures"


def test_current_captures_directory_tolerates_no_experiment(monkeypatch):
    def unavailable():
        raise RuntimeError("no redis")

    monkeypatch.setattr(discovery, "get_current_experiment_directory", unavailable)
    assert discovery.current_captures_directory() is None


def test_discover_captures_finds_nested_burst_raw_captures(tmp_path, monkeypatch):
    # Nested burst raw captures: captures/Mix_1.2_x/16bit_raw/GFP_raw.png
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: tmp_path)

    captures_dir = tmp_path / "captures"
    burst_dir = captures_dir / "Mix_1.2_x" / "16bit_raw"
    burst_dir.mkdir(parents=True, exist_ok=True)

    burst_raw = burst_dir / "GFP_raw.png"
    burst_raw.write_bytes(b"")

    discovered = discovery.discover_captures(captures_dir)
    assert burst_raw in discovered


def test_discover_captures_finds_old_flat_layout(tmp_path, monkeypatch):
    # Old flat layout: captures/16bit_raw/old_raw.png
    monkeypatch.setattr(discovery, "get_current_experiment_directory", lambda: tmp_path)

    captures_dir = tmp_path / "captures"
    flat_dir = captures_dir / "16bit_raw"
    flat_dir.mkdir(parents=True, exist_ok=True)

    flat_raw = flat_dir / "old_raw.png"
    flat_raw.write_bytes(b"")

    discovered = discovery.discover_captures(captures_dir)
    assert flat_raw in discovered


def test_image_groups_split_display_pngs_from_raws(tmp_path):
    # captures/Mix_1.2_x/GFP.png is the session's "None" group,
    # captures/Mix_1.2_x/16bit_raw/GFP_raw.png its "16bit_raw" group, and
    # captures/snap.png sits outside any session.
    captures = tmp_path / "captures"
    raw_dir = captures / "Mix_1.2_x" / "16bit_raw"
    raw_dir.mkdir(parents=True)

    display_png = captures / "Mix_1.2_x" / "GFP.png"
    raw_png = raw_dir / "GFP_raw.png"
    snap_png = captures / "snap.png"

    for path in (display_png, raw_png, snap_png):
        path.write_bytes(b"")

    groups = discovery.discover_image_groups(captures)

    assert groups["16bit_raw"] == [("Mix_1.2_x", [raw_png])]
    assert dict(groups[discovery.NO_IMAGE_GROUP]) == {
        "Mix_1.2_x": [display_png],
        discovery.UNGROUPED_BURST: [snap_png],
    }


# --- burst discovery (issue #6 viewer rework) -----------------------------


def _make_raw(directory, name, mtime):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"")
    os.utime(path, (mtime, mtime))
    return path


def test_image_group_sessions_by_folder_oldest_first(tmp_path):
    captures = tmp_path / "captures"
    b1 = _make_raw(
        captures / "Mix_1.2_x" / "16bit_raw", "Blue_460_nm_1_ts_raw.png", 1_000
    )
    b2a = _make_raw(
        captures / "Rinse_2_y" / "16bit_raw", "Green_540_nm_1_ts_raw.png", 2_000
    )
    b2b = _make_raw(
        captures / "Rinse_2_y" / "16bit_raw", "Blue_460_nm_2_ts_raw.png", 3_000
    )
    legacy = _make_raw(captures / "16bit_raw", "old_raw.png", 500)

    bursts = discovery.discover_image_groups(captures)["16bit_raw"]
    assert [name for name, _ in bursts] == [
        discovery.UNGROUPED_BURST,
        "Mix_1.2_x",
        "Rinse_2_y",
    ]
    as_dict = dict(bursts)
    assert as_dict["Mix_1.2_x"] == [b1]
    assert as_dict["Rinse_2_y"] == [b2a, b2b]
    assert as_dict[discovery.UNGROUPED_BURST] == [legacy]


def test_discover_image_groups_empty_and_missing(tmp_path):
    assert discovery.discover_image_groups(None) == {}
    assert discovery.discover_image_groups(tmp_path / "absent") == {}


# --- burst/filter navigation (controller level, no Qt) ---------------------


class _ColourFilter:
    """A contributed IMAGE_FILTERS stand-in: the filename's leading word."""

    name = "Colour"
    tooltip = "Leading filename word"

    def classify(self, path):
        return path.name.split("_")[0]


def _viewer(monkeypatch, tmp_path):
    """Model + controller over a synthetic two-burst captures tree, with
    image loading stubbed out (navigation is under test, not decoding)."""
    captures = tmp_path / "captures"
    paths = {
        "old_blue": _make_raw(
            captures / "Mix_1.2_a" / "16bit_raw", "Blue_460_nm_1_t1_raw.png", 1_000
        ),
        "old_green": _make_raw(
            captures / "Mix_1.2_a" / "16bit_raw", "Green_540_nm_2_t2_raw.png", 1_500
        ),
        "new_blue": _make_raw(
            captures / "Rinse_3_b" / "16bit_raw", "Blue_460_nm_1_t3_raw.png", 2_000
        ),
    }
    monkeypatch.setattr(
        viewer_controller_mod,
        "load_image_array",
        lambda path: np.zeros((2, 2), dtype=np.uint16),
    )
    model = ImageViewerModel()
    model.directory = ""  # follow-the-experiment mode
    ctrl = ImageViewerController(
        model=model, image_filters_source=lambda: [_ColourFilter()]
    )
    monkeypatch.setattr(ctrl, "_scan_directory", lambda: captures)
    return ctrl, model, paths


def test_rescan_follows_newest_burst_and_populates_filter(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    assert model.burst_names == ["All", "Mix_1.2_a", "Rinse_3_b"]
    assert model.selected_burst == "Rinse_3_b"
    assert model.burst_index == 2
    assert model.current_path == str(paths["new_blue"])
    assert model.filter_label == "Colour"
    assert model.filter_names == [IMAGE_FILTER_ALL, "Blue", "Green"]


def test_selecting_older_burst_shows_its_first_image(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    model.selected_burst = "Mix_1.2_a"
    assert model.burst_index == 1
    assert [p.name for p in model.paths] == [
        "Blue_460_nm_1_t1_raw.png",
        "Green_540_nm_2_t2_raw.png",
    ]
    assert model.current_path == str(paths["old_blue"])


def test_burst_slider_drives_selection(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    model.burst_index = 0
    assert model.selected_burst == "All"
    model.burst_index = 1
    assert model.selected_burst == "Mix_1.2_a"


def test_image_group_switch_keeps_the_session(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    display = _make_raw(paths["old_blue"].parent.parent, "Blue_460_nm_1_t1.png", 1_100)
    ctrl.rescan()
    assert model.image_group_names == ["All", "None", "16bit_raw"]
    assert model.selected_image_group == "All"  # the default

    model.selected_burst = "Mix_1.2_a"
    assert [p.name for p in model.paths] == [
        "Blue_460_nm_1_t1_raw.png",
        "Blue_460_nm_1_t1.png",
        "Green_540_nm_2_t2_raw.png",
    ]

    model.selected_image_group = "None"
    assert model.burst_names == ["All", "Mix_1.2_a"]
    assert model.selected_burst == "Mix_1.2_a"
    assert model.current_path == str(display)


def test_image_filter_narrows_and_keeps_surviving_image(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    model.selected_burst = "Mix_1.2_a"  # shows old_blue
    model.selected_filter = "Blue"
    assert [p.name for p in model.paths] == ["Blue_460_nm_1_t1_raw.png"]
    assert model.current_path == str(paths["old_blue"])  # survived

    model.selected_filter = "Green"
    assert [p.name for p in model.paths] == ["Green_540_nm_2_t2_raw.png"]
    assert model.current_path == str(paths["old_green"])  # fell to first


def test_parked_user_stays_parked_when_new_burst_lands(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    model.selected_burst = "Mix_1.2_a"
    captures = paths["old_blue"].parent.parent.parent
    _make_raw(captures / "Zap_4_c" / "16bit_raw", "Red_630_nm_1_t4_raw.png", 3_000)
    ctrl.rescan()
    assert model.selected_burst == "Mix_1.2_a"  # still parked
    assert "Zap_4_c" in model.burst_names  # but discovered
    assert "Red" in model.filter_names


def test_seek_sliders_are_one_based_twins(monkeypatch, tmp_path):
    """The sliders bind to 1-based `*_number` twins; setting a number
    drives the 0-based index and vice versa."""
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    assert model.burst_number == model.burst_index + 1 == 3
    assert model.max_burst_number == 3
    model.burst_number = 2
    assert model.burst_index == 1 and model.selected_burst == "Mix_1.2_a"
    assert model.max_image_number == len(model.paths) == 2
    model.image_number = 2
    assert model.image_index == 1
    assert model.current_path == str(paths["old_green"])


def test_rescan_records_the_browsed_directory(monkeypatch, tmp_path):
    ctrl, model, paths = _viewer(monkeypatch, tmp_path)
    ctrl.rescan()
    assert model.browsed_directory == str(tmp_path / "captures")


def test_dock_pane_title_names_the_browsed_folder():
    from pathlib import Path

    from image_viewer.dock_pane import _title_for

    assert _title_for("", "") == "Image Viewer"
    # Default (experiment) captures dir: the experiment folder names it.
    assert (
        _title_for(str(Path("Experiments/2026_07_20-17_41_31/captures")), "")
        == "Image Viewer\t-\t2026_07_20-17_41_31"
    )
    # A user-picked folder shows its own name, then the loaded image.
    assert (
        _title_for(str(Path("D:/some/album")), "a.png - 4x4 16-bit gray")
        == "Image Viewer\t-\talbum\t-\ta.png - 4x4 16-bit gray"
    )


def test_the_pane_puts_the_analysis_model_in_its_ui_context():
    """TraitsUI checks every enabled_when when a trait changes on an
    object IN the context, not on one reached through it. The
    rolling-ball controls are enabled by a trait on the analysis model,
    so it has to be a context object in its own right — otherwise the
    toolbar toggle leaves them stale until an unrelated edit to the
    viewer model (hovering the image writes the pixel readout) happens
    to trigger the check."""
    from image_viewer.dock_pane import (
        ImageViewerDockPane,
    )

    pane = ImageViewerDockPane(model=ImageViewerModel())
    context = pane.trait_context()
    assert context["object"] is pane.model
    assert context["analysis"] is pane.model.roi_analysis
