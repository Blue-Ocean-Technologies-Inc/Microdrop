# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Persistence tests: session config round-trip (v2 + v1 fallback),
stats-store round-trip, and the CSV export layout."""

# Standard library imports.
import csv
import json
import math
import shutil

# Microdrop package imports.
from image_viewer.analysis.roi_model import (
    AnalysisSession,
    Roi,
    RoiStyle,
)
from image_viewer.analysis.roi_store import (
    load_fit_equations,
    load_roi_stats,
    load_session,
    save_fit_equations,
    save_roi_stats,
    save_session,
    write_intensity_csv,
)


def test_session_round_trip_preserves_rois_styles_and_figure(tmp_path):
    roi = Roi(
        name="Cell body",
        kind="box",
        geometry=[1.0, 2.0, 30.0, 40.0, 15.0],
        base_anchor=100.0,
        overrides={200.0: [5.0, 6.0, 30.0, 40.0, 15.0]},
        style=RoiStyle(
            color="#d62728",
            line_style="dashed",
            marker="o",
            marker_size=7.0,
            visible=False,
            alpha=40,
        ),
    )
    session = AnalysisSession(
        directory=str(tmp_path), rois=[roi], plot_stat="bg_corrected"
    )
    session.figure.y_auto = False
    session.figure.y_max = 4096.0
    save_session(tmp_path, session)

    loaded = load_session(tmp_path)
    assert loaded.directory == str(tmp_path)
    assert loaded.plot_stat == "bg_corrected"
    assert loaded.figure.y_auto is False and loaded.figure.y_max == 4096.0
    (back,) = loaded.rois
    assert back.roi_id == roi.roi_id and back.name == "Cell body"
    assert back.geometry == [1.0, 2.0, 30.0, 40.0, 15.0, 0.0]
    assert back.overrides == {200.0: [5.0, 6.0, 30.0, 40.0, 15.0, 0.0]}
    assert back.style.color == "#d62728"
    assert back.style.line_style == "dashed"
    assert back.style.marker == "o" and back.style.marker_size == 7.0
    assert back.style.visible is False and back.style.alpha == 40


def test_figure_fit_settings_round_trip(tmp_path):
    session = AnalysisSession()
    session.figure.fit_method = "exponential"
    session.figure.show_legend = False
    session.figure.show_second_derivative_max = True
    session.figure.view_mode = "fastest_change"
    session.figure.trim_poor_fit = True
    session.figure.log_x = True
    session.figure.normalize = True
    save_session(tmp_path, session)

    loaded = load_session(tmp_path)
    assert loaded.figure.fit_method == "exponential"
    assert loaded.figure.show_legend is False
    assert loaded.figure.show_second_derivative_max is True
    assert loaded.figure.view_mode == "fastest_change"
    assert loaded.figure.trim_poor_fit is True
    assert loaded.figure.log_x is True and loaded.figure.log_y is False
    assert loaded.figure.normalize is True


def test_load_session_accepts_v1_bare_list(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_config.json").write_text(
        json.dumps(
            [
                {
                    "roi_id": "abcd1234",
                    "name": "ROI 1",
                    "kind": "circle",
                    "geometry": [10.0, 10.0, 5.0],
                    "base_anchor": 0.0,
                    "overrides": {},
                }
            ]
        )
    )
    loaded = load_session(tmp_path)
    (roi,) = loaded.rois
    assert roi.roi_id == "abcd1234" and roi.kind == "ellipse"
    assert loaded.plot_stat == "mean"  # defaults fill in
    assert roi.style.line_style == "solid"


def test_load_session_bad_plot_stat_keeps_parsed_roi(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plot_stat": "sparkle",
                "rois": [
                    {
                        "roi_id": "abcd1234",
                        "name": "ROI 1",
                        "kind": "circle",
                        "geometry": [10.0, 10.0, 5.0],
                        "base_anchor": 0.0,
                        "overrides": {},
                    }
                ],
            }
        )
    )
    loaded = load_session(tmp_path)
    (roi,) = loaded.rois
    assert roi.roi_id == "abcd1234"
    assert loaded.plot_stat == "mean"


def test_load_session_missing_or_corrupt_is_empty(tmp_path):
    assert load_session(tmp_path).rois == []
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_config.json").write_text("{nope")
    assert load_session(tmp_path).rois == []


def test_stats_store_round_trip_including_nan(tmp_path):
    key = (
        str(tmp_path / "a_raw.png"),
        123.5,
        "abcd1234",
        "ellipse",
        (10.0, 10.0, 5.0, 5.0, 0.0),
        (2, 4, 0, ()),
    )
    stats = {"mean": 42.5, "std": float("nan"), "count": 9.0}
    save_roi_stats(tmp_path, {key: stats})

    loaded = load_roi_stats(tmp_path)
    assert set(loaded) == {key}
    assert loaded[key]["mean"] == 42.5
    assert math.isnan(loaded[key]["std"])


def test_legacy_circle_config_loads_as_a_migrated_ellipse(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plot_stat": "mean",
                "figure": {},
                "rois": [
                    {
                        "roi_id": "abcd1234",
                        "name": "ROI 1",
                        "kind": "circle",
                        "geometry": [50.0, 60.0, 10.0],
                        "base_anchor": 0.0,
                        "overrides": {"120.0": [52.0, 61.0, 11.0]},
                        "style": {},
                    }
                ],
            }
        )
    )

    (roi,) = load_session(tmp_path).rois
    assert roi.kind == "ellipse"
    assert roi.geometry == [50.0, 60.0, 10.0, 10.0, 0.0]
    assert roi.overrides == {120.0: [52.0, 61.0, 11.0, 11.0, 0.0]}


def test_legacy_stats_keys_migrate_with_their_roi(tmp_path):
    # The no-recompute guarantee: a store written before rotation must
    # still resolve against the migrated ROI's cache key.
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_stats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "path": str(tmp_path / "a_raw.png"),
                        "mtime": 123.5,
                        "roi_id": "abcd1234",
                        "kind": "circle",
                        "geometry": [50.0, 60.0, 10.0],
                        "stats": {"mean": 7.0},
                    }
                ],
            }
        )
    )
    session = AnalysisSession(
        directory=str(tmp_path),
        rois=[
            Roi(
                roi_id="abcd1234",
                name="ROI 1",
                kind="ellipse",
                geometry=[50.0, 60.0, 10.0, 10.0, 0.0],
            )
        ],
    )

    # An entry predating the background annulus is dropped: its
    # outline stats came from a stroke straddling the boundary, and
    # keeping it would also break the next save.
    assert load_roi_stats(tmp_path) == {}
    assert session.roi_by_id("abcd1234").kind == "ellipse"


def test_a_pre_rounding_box_keeps_its_cached_stats(tmp_path):
    # Boxes gained a corner radius, so their geometry grew a sixth
    # value. Config and stats keys migrate through the same normalize(),
    # so an existing experiment's numbers must still be found rather
    # than silently recomputed.
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    image = tmp_path / "a_raw.png"
    image.write_bytes(b"")
    (analysis / "roi_stats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "path": str(image),
                        "mtime": image.stat().st_mtime,
                        "roi_id": "abcd1234",
                        "kind": "box",
                        "geometry": [10.0, 20.0, 30.0, 40.0, 0.0],
                        # Two values: written before the rolling ball existed.
                        "ring": [2, 4],
                        "stats": {"mean": 7.0},
                    }
                ],
            }
        )
    )
    (analysis / "roi_config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plot_stat": "mean",
                "figure": {},
                "rois": [
                    {
                        "roi_id": "abcd1234",
                        "name": "ROI 1",
                        "kind": "box",
                        "geometry": [10.0, 20.0, 30.0, 40.0, 0.0],
                        "overrides": {},
                        "base_anchor": 0.0,
                    }
                ],
            }
        )
    )
    session = load_session(tmp_path)
    session.stats = load_roi_stats(tmp_path)

    (roi,) = session.rois
    assert session.stats[session.cache_key(image, roi)] == {"mean": 7.0}


def test_stats_from_before_the_rolling_ball_still_match(tmp_path):
    # Those numbers were computed with no ball, which is what radius 0
    # means now — they must not be silently recomputed.
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    image = tmp_path / "a_raw.png"
    image.write_bytes(b"")
    (analysis / "roi_stats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "path": str(image),
                        "mtime": image.stat().st_mtime,
                        "roi_id": "abcd1234",
                        "kind": "ellipse",
                        "geometry": [5.0, 5.0, 2.0, 2.0, 0.0],
                        "ring": [2, 4],
                        "stats": {"mean": 7.0},
                    }
                ],
            }
        )
    )
    session = AnalysisSession(
        rois=[
            Roi(
                roi_id="abcd1234",
                name="ROI 1",
                kind="ellipse",
                geometry=[5.0, 5.0, 2.0, 2.0, 0.0],
            )
        ]
    )
    session.stats = load_roi_stats(tmp_path)
    (roi,) = session.rois
    assert session.stats[session.cache_key(image, roi)] == {"mean": 7.0}


def test_load_roi_stats_missing_or_corrupt_is_empty(tmp_path):
    assert load_roi_stats(tmp_path) == {}
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_stats.json").write_text("[not the schema]")
    assert load_roi_stats(tmp_path) == {}


def test_write_intensity_csv_layout(tmp_path):
    roi = Roi(name="ROI 1", kind="box", geometry=[1.0, 1.0, 5.0, 5.0])
    rows = [
        {
            "filename": "img_raw.png",
            "time_utc": "2026_07_20-17_46_24",
            "elapsed_sec": 0.0,
            "capture_session": "burst_a",
            "filter": "Green 540 nm",
            "stats": {
                roi.roi_id: {
                    "mean": 10.0,
                    "std": 1.0,
                    "median": 10.0,
                    "min": 8.0,
                    "max": 12.0,
                    "count": 25.0,
                    "outline_mean": 9.0,
                    "outline_std": 1.0,
                    "outline_median": 9.0,
                    "outline_min": 8.0,
                    "outline_max": 10.0,
                    "outline_count": 16.0,
                }
            },
        },
        {
            "filename": "img2_raw.png",
            "time_utc": "2026_07_20-17_46_25",
            "elapsed_sec": 1.0,
            "capture_session": "burst_a",
            "filter": "Green 540 nm",
            "stats": {},  # not computed: blank cells
        },
    ]
    csv_path = tmp_path / "out.csv"
    write_intensity_csv(csv_path, rows, [roi])
    with open(csv_path, newline="", encoding="utf-8") as handle:
        records = list(csv.reader(handle))
    # Long form: the ROI is a value in a column, so the width does
    # not grow with the ROI count and every stat is named once.
    assert records[0][:9] == [
        "index",
        "time_utc",
        "elapsed_sec",
        "temperature_c",
        "filename",
        "capture_session",
        "filter",
        "roi",
        "is_background_ref",
    ]
    assert "mean" in records[0] and "outline_count" in records[0]
    assert not [name for name in records[0] if name.startswith("ROI 1")]
    mean_column = records[0].index("mean")
    roi_column = records[0].index("roi")
    assert records[1][roi_column] == "ROI 1"
    assert records[1][mean_column] == "10.0"
    assert records[2][mean_column] == ""  # not computed


def test_contour_round_trips_its_vertex_list(tmp_path):
    roi = Roi(
        name="Cell edge",
        kind="polygon",
        geometry=[10.0, 10.0, 40.0, 12.0, 35.0, 50.0, 8.0, 44.0],
        base_anchor=0.0,
        overrides={90.0: [11.0, 11.0, 41.0, 13.0, 36.0, 51.0, 9.0, 45.0]},
    )
    save_session(tmp_path, AnalysisSession(directory=str(tmp_path), rois=[roi]))

    (back,) = load_session(tmp_path).rois
    assert back.kind == "polygon"
    assert back.geometry == roi.geometry
    assert back.overrides == roi.overrides


def test_scale_calibration_round_trips(tmp_path):
    session = AnalysisSession(directory=str(tmp_path))
    session.scale.trait_set(metres_per_pixel=1e-5, value=2.0, unit="mm")
    save_session(tmp_path, session)

    loaded = load_session(tmp_path)
    assert loaded.scale.metres_per_pixel == 1e-5
    assert loaded.scale.value == 2.0
    assert loaded.scale.unit == "mm"


def test_config_without_a_scale_loads_uncalibrated(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plot_stat": "mean",
                "figure": {},
                "rois": [],
            }
        )
    )

    scale = load_session(tmp_path).scale
    assert scale.metres_per_pixel == 0.0
    assert scale.unit == "mm"  # the default, not the first unit


def test_write_intensity_csv_includes_the_derived_columns(tmp_path):
    roi = Roi(name="ROI 1", kind="box", geometry=[1.0, 1.0, 5.0, 5.0])
    rows = [
        {
            "filename": "img_raw.png",
            "time_utc": "2026_07_20-17_46_24",
            "elapsed_sec": 0.0,
            "capture_session": "burst_a",
            "filter": "Green 540 nm",
            "stats": {roi.roi_id: {"mean": 10.0, "outline_mean": 4.0, "count": 25.0}},
        }
    ]
    csv_path = tmp_path / "out.csv"
    write_intensity_csv(csv_path, rows, [roi], pixel_area=1e-4, area_unit_label="mm²")
    with open(csv_path, newline="", encoding="utf-8") as handle:
        records = list(csv.reader(handle))

    for name in ("area_mm²", "integrated", "bg_integrated", "per_area", "bg_per_area"):
        assert name in records[0], name
    area = records[1][records[0].index("area_mm²")]
    assert abs(float(area) - 25.0 * 1e-4) < 1e-12
    integrated = records[1][records[0].index("integrated")]
    assert float(integrated) == 250.0


def test_write_intensity_csv_adds_the_normalised_column(tmp_path):
    roi = Roi(name="ROI 1", kind="box", geometry=[1.0, 1.0, 5.0, 5.0])
    rows = [
        {
            "filename": f"img{index}_raw.png",
            "time_utc": "2026_07_20-17_46_24",
            "elapsed_sec": float(index),
            "capture_session": "burst_a",
            "filter": "Green 540 nm",
            "stats": {roi.roi_id: {"mean": mean, "count": 4.0}},
        }
        for index, mean in enumerate((10.0, 20.0, 30.0))
    ]
    csv_path = tmp_path / "out.csv"
    write_intensity_csv(csv_path, rows, [roi], normalize_stat="mean")
    with open(csv_path, newline="", encoding="utf-8") as handle:
        records = list(csv.reader(handle))

    column = records[0].index("mean_norm_pct")
    assert [records[row][column] for row in (1, 2, 3)] == ["0.0", "50.0", "100.0"]


def test_write_intensity_csv_writes_a_row_per_image_and_roi(tmp_path):
    # Three ROIs over two images is six rows of a fixed width, where
    # the wide layout was two rows of ever-growing width.
    rois = [
        Roi(
            name=f"ROI {index}",
            kind="box",
            geometry=[1.0, 1.0, 5.0, 5.0],
            is_background_ref=index == 3,
        )
        for index in (1, 2, 3)
    ]
    rows = [
        {
            "filename": f"img{image}_raw.png",
            "time_utc": "2026_07_20-17_46_24",
            "elapsed_sec": float(image),
            "capture_session": "burst_a",
            "filter": "Green 540 nm",
            "stats": {
                roi.roi_id: {"mean": 10.0 * position, "count": 4.0}
                for position, roi in enumerate(rois, start=1)
            },
        }
        for image in (0, 1)
    ]
    csv_path = tmp_path / "out.csv"
    write_intensity_csv(csv_path, rows, rois, correction=(2, 4, 60, ()))
    with open(csv_path, newline="", encoding="utf-8") as handle:
        records = list(csv.reader(handle))

    assert len(records) == 1 + 6
    header, body = records[0], records[1:]
    roi_column = header.index("roi")
    # Each image's ROIs sit together, in the order the session has them.
    assert [row[roi_column] for row in body] == ["ROI 1", "ROI 2", "ROI 3"] * 2
    assert [row[header.index("index")] for row in body] == ["0"] * 3 + ["1"] * 3
    # The reference flag rides with its ROI, not in a separate
    # file.
    background_ref_column = header.index("is_background_ref")
    assert [row[background_ref_column] for row in body[:3]] == ["0", "0", "1"]
    # And every row says what it was measured with — including that
    # no heater sensor read the (absent) temperature column.
    for row in body:
        assert row[-5:] == ["2", "4", "60", "0", ""]


def test_write_intensity_csv_omits_the_column_when_not_normalising(tmp_path):
    roi = Roi(name="ROI 1", kind="box", geometry=[1.0, 1.0, 5.0, 5.0])
    rows = [
        {
            "filename": "img_raw.png",
            "time_utc": "2026_07_20-17_46_24",
            "elapsed_sec": 0.0,
            "capture_session": "burst_a",
            "filter": "Green 540 nm",
            "stats": {roi.roi_id: {"mean": 10.0, "count": 4.0}},
        }
    ]
    csv_path = tmp_path / "out.csv"
    write_intensity_csv(csv_path, rows, [roi])
    with open(csv_path, newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert not [name for name in header if name.endswith("_norm_pct")]


def test_background_ring_round_trips(tmp_path):
    session = AnalysisSession(directory=str(tmp_path))
    session.ring.trait_set(gap_px=3, thickness_px=7, show_on_canvas=False)
    save_session(tmp_path, session)

    ring = load_session(tmp_path).ring
    assert ring.gap_px == 3 and ring.thickness_px == 7
    assert ring.show_on_canvas is False


def test_stats_survive_a_save_after_loading_pre_ring_entries(tmp_path):
    # Regression: a dropped entry used to reach save_roi_stats with a
    # None ring, whose list() raised and lost the whole file.
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_stats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "path": str(tmp_path / "old_raw.png"),
                        "mtime": 1.0,
                        "roi_id": "abcd1234",
                        "kind": "ellipse",
                        "geometry": [5.0, 5.0, 2.0, 2.0, 0.0],
                        "stats": {"mean": 7.0},
                    }
                ],
            }
        )
    )
    store = load_roi_stats(tmp_path)
    fresh = (
        str(tmp_path / "new_raw.png"),
        2.0,
        "abcd1234",
        "ellipse",
        (5.0, 5.0, 2.0, 2.0, 0.0),
        (2, 4, 0, ()),
    )
    store[fresh] = {"mean": 9.0}
    save_roi_stats(tmp_path, store)

    assert load_roi_stats(tmp_path)[fresh] == {"mean": 9.0}


def _stats_key_for(image, roi_id="abcd1234", geometry=(5.0, 5.0, 2.0, 2.0, 0.0)):
    return (
        str(image),
        image.stat().st_mtime,
        roi_id,
        "ellipse",
        geometry,
        (2, 4, 60, ()),
    )


def test_stats_are_grouped_by_image_one_measurement_per_line(tmp_path):
    image = tmp_path / "a_raw.png"
    image.write_bytes(b"")
    store = {
        _stats_key_for(image, "roi_a"): {"mean": 1.0},
        _stats_key_for(image, "roi_b"): {"mean": 2.0},
    }
    save_roi_stats(tmp_path, store)
    text = (tmp_path / "analysis" / "roi_stats.json").read_text(encoding="utf-8")
    payload = json.loads(text)

    # One image entry carrying both measurements: the path and mtime
    # are written once, not once per ROI per settings combination.
    assert payload["version"] == 2
    (entry,) = payload["images"]
    assert len(entry["measurements"]) == 2
    assert text.count(entry["file"]) == 1
    # Readable: a line per measurement rather than the whole store on
    # one line.
    assert len(text.splitlines()) > 5
    assert load_roi_stats(tmp_path) == store


def test_a_flat_version_1_stats_file_still_loads(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    image = tmp_path / "a_raw.png"
    image.write_bytes(b"")
    (analysis / "roi_stats.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "path": str(image),
                        "mtime": image.stat().st_mtime,
                        "roi_id": "abcd1234",
                        "kind": "ellipse",
                        "geometry": [5.0, 5.0, 2.0, 2.0, 0.0],
                        "ring": [2, 4, 60],
                        "stats": {"mean": 7.0},
                    }
                ],
            }
        )
    )
    loaded = load_roi_stats(tmp_path)
    assert loaded[_stats_key_for(image)] == {"mean": 7.0}
    # Saving migrates it to the grouped form without losing anything.
    save_roi_stats(tmp_path, loaded)
    assert load_roi_stats(tmp_path) == loaded


def test_moving_the_experiment_folder_keeps_the_cache(tmp_path):
    # Paths are stored against the experiment folder, so copying or
    # renaming it no longer throws every computed intensity away.
    source = tmp_path / "before"
    (source / "captures").mkdir(parents=True)
    image = source / "captures" / "a_raw.png"
    image.write_bytes(b"")
    save_roi_stats(source, {_stats_key_for(image): {"mean": 7.0}})

    moved = tmp_path / "after"
    shutil.copytree(source, moved)
    moved_image = moved / "captures" / "a_raw.png"
    assert load_roi_stats(moved)[_stats_key_for(moved_image)] == {"mean": 7.0}


def _fit_entry(params, r_squared=0.99, fitted=(0.0, 190.0), trimmed=False):
    return {
        "params": params,
        "r_squared": r_squared,
        "fitted_range_sec": list(fitted),
        "trimmed": trimmed,
    }


def test_fit_equations_are_keyed_by_equation_then_roi(tmp_path):
    save_fit_equations(
        tmp_path,
        "a*x + b",
        {
            "ROI 1": _fit_entry({"a": 2.0, "b": 3.0}),
            "ROI 2": _fit_entry({"a": 5.0, "b": 7.0}),
        },
    )
    payload = load_fit_equations(tmp_path)
    assert list(payload) == ["a*x + b"]
    roi = payload["a*x + b"]["ROI 1"]
    assert roi["params"] == {"a": 2.0, "b": 3.0}
    assert roi["r_squared"] == 0.99
    assert roi["fitted_range_sec"] == [0.0, 190.0]
    assert roi["trimmed"] is False
    # Parameters keep their own key: an equation may name one
    # "r_squared", and a fitted value must not be read as the quality
    # of the fit that produced it.
    assert "r_squared" not in roi["params"]
    # Readable on purpose: this one is small enough to indent whole.
    text = (tmp_path / "analysis" / "fit_equations.json").read_text(encoding="utf-8")
    assert len(text.splitlines()) > 5


def test_fitting_a_second_equation_keeps_the_first(tmp_path):
    # Keyed by equation so the file becomes the record of every model
    # tried on the experiment, not only the last one.
    save_fit_equations(tmp_path, "a*x + b", {"ROI 1": _fit_entry({"a": 2.0, "b": 3.0})})
    save_fit_equations(
        tmp_path, "a*exp(-b*x)", {"ROI 1": _fit_entry({"a": 9.0, "b": 0.1})}
    )
    payload = load_fit_equations(tmp_path)
    assert sorted(payload) == ["a*exp(-b*x)", "a*x + b"]


def test_refitting_one_equation_replaces_its_rois(tmp_path):
    # The entry is the fit of the ROIs that exist now; one deleted
    # since must not linger under the same equation.
    save_fit_equations(
        tmp_path,
        "a*x + b",
        {
            "ROI 1": _fit_entry({"a": 1.0, "b": 1.0}),
            "ROI 2": _fit_entry({"a": 2.0, "b": 2.0}),
        },
    )
    save_fit_equations(tmp_path, "a*x + b", {"ROI 1": _fit_entry({"a": 9.0, "b": 9.0})})
    assert list(load_fit_equations(tmp_path)["a*x + b"]) == ["ROI 1"]


def test_nothing_to_record_writes_no_fit_file(tmp_path):
    save_fit_equations(tmp_path, "", {"ROI 1": _fit_entry({"a": 1.0})})
    save_fit_equations(tmp_path, "a*x + b", {})
    assert not (tmp_path / "analysis" / "fit_equations.json").exists()
    assert load_fit_equations(tmp_path) == {}


def test_an_unreadable_fit_file_is_no_fits(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "fit_equations.json").write_text("{not json")
    assert load_fit_equations(tmp_path) == {}


def test_a_config_written_before_the_rename_keeps_its_references(tmp_path):
    # These were called "standards" until the rename; an experiment
    # marked before it must not quietly lose the marking.
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "roi_config.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plot_stat": "mean",
                "figure": {"subtract_standard": True},
                "rois": [
                    {
                        "roi_id": "abcd1234",
                        "name": "Blank",
                        "kind": "ellipse",
                        "geometry": [5.0, 5.0, 2.0, 2.0, 0.0],
                        "overrides": {},
                        "base_anchor": 0.0,
                        "is_standard": True,
                    }
                ],
            }
        )
    )
    session = load_session(tmp_path)
    (roi,) = session.rois
    assert roi.is_background_ref is True
    assert session.figure.subtract_background_ref is True
