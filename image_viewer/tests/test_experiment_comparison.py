# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Plotting several experiments: the others' series on the live x axis,
keyed apart from the live ROIs and carrying their own exclusions, and
the plotted set following the viewer's live experiment."""

# Standard library imports.
import json
import math
import os
from pathlib import Path

# Microdrop package imports.
from device_viewer.consts import CAPTURES_DIR_NAME
from image_viewer.analysis.consts import (
    ANALYSIS_DIR_NAME,
    ROI_CONFIG_FILENAME,
    ROI_LINE_WIDTH_PT,
)
from image_viewer.analysis.curve_fit import fit_landmarks, fit_series
from image_viewer.analysis.imported_experiments_model import (
    ImportedExperimentsModel,
    payloads_as_text,
    payloads_from_text,
)
from image_viewer.analysis.imported_series import (
    imported_key,
    imported_series,
    measured_paths,
    run_offset,
    run_paths,
    series_table,
    split_imported_key,
)
from image_viewer.analysis.plot_series import analysed_series
from image_viewer.analysis.roi_model import AnalysisSession, Roi, RoiAnalysisModel
from image_viewer.analysis.roi_store import (
    delete_saved_rois,
    load_session,
    save_roi_stats,
    save_roi_styles,
    save_session,
)

#: The seconds past the hour of each experiment's two captures.
CAPTURE_SECONDS = ("00", "30")


def _roi(name):
    return Roi(name=name, kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])


def _experiment(root, name, hour, rois, means, seconds=CAPTURE_SECONDS):
    """An experiment folder with a capture at each of ``seconds`` past
    ``hour`` and a session whose ``rois`` measure ``means`` ({roi name:
    [mean per capture]}) there."""
    captures = root / name / CAPTURES_DIR_NAME
    captures.mkdir(parents=True)
    paths = []

    for second in seconds:
        path = captures / f"img_2026_07_20-{hour}_00_{second}_raw.png"
        path.write_bytes(b"")
        paths.append(str(path))

    session = AnalysisSession(directory=str(root / name), rois=rois)

    for roi in rois:
        for path, mean in zip(paths, means.get(roi.name, [])):
            session.stats[session.cache_key(path, roi)] = {"mean": mean}

    return session, paths


def _saved(session):
    save_session(session.directory, session)
    save_roi_stats(session.directory, session.stats)


def _plotted_pair(tmp_path, seconds=CAPTURE_SECONDS, means=(7.0, 9.0)):
    """(model, live session, other session) with "yesterday" — saved,
    its "Drop" measuring ``means`` — plotted beside the live "today"."""
    live, live_paths = _experiment(tmp_path, "today", "10", [_roi("Drop")], {}, seconds)
    other, _other_paths = _experiment(
        tmp_path, "yesterday", "11", [_roi("Drop")], {"Drop": list(means)}, seconds
    )
    _saved(live)
    _saved(other)
    analysis = RoiAnalysisModel(session=live, filtered_paths=live_paths)
    model = ImportedExperimentsModel(analysis=analysis)

    assert model.add_experiment(other.directory) == ""

    return model, live, other


def test_measured_paths_follow_capture_order(tmp_path):
    roi = _roi("A")
    session, paths = _experiment(tmp_path, "exp", "10", [roi], {"A": [1.0, 2.0]})

    assert measured_paths(session) == paths


def test_a_run_keeps_its_excluded_images_unmeasured_or_not(tmp_path):
    seconds = ("00", "10", "20")
    session, paths = _experiment(
        tmp_path, "exp", "10", [_roi("A")], {"A": [1.0, 2.0]}, seconds
    )
    session.excluded_images = [
        f"img_2026_07_20-10_00_{second}_raw.png" for second in seconds[1:]
    ]

    # The measured excluded image and the never-measured one, in order.
    assert run_paths(session) == paths


def test_an_imported_key_never_reads_as_a_live_roi_id():
    key = imported_key("C:/runs/yesterday", "ab12cd34")

    assert split_imported_key(key) == ("C:/runs/yesterday", "ab12cd34")
    assert split_imported_key("ab12cd34") == ("", "ab12cd34")


def test_aligned_runs_share_the_run_start(tmp_path):
    primary, primary_paths = _experiment(
        tmp_path, "today", "10", [_roi("Drop")], {"Drop": [5.0, 6.0]}
    )
    other_roi = _roi("Drop")
    other, other_paths = _experiment(
        tmp_path, "yesterday", "11", [other_roi], {"Drop": [7.0, 9.0]}
    )

    aligned, _flags, _excluded, _area_fit = imported_series(
        primary, primary_paths, other, other_paths, "yesterday", True
    )
    as_captured, _flags, _excluded, _area_fit = imported_series(
        primary, primary_paths, other, other_paths, "yesterday", False
    )

    ((key, (name, x_values, values)),) = aligned.items()
    ((_name, shifted, _values),) = as_captured.values()

    assert key == imported_key(other.directory, other_roi.roi_id)
    assert name == "yesterday · Drop"
    assert x_values == [0.0, 30.0]
    assert values == [7.0, 9.0]
    assert shifted == [3600.0, 3630.0]


def test_the_offset_follows_the_time_unit_and_only_the_time_axis(tmp_path):
    primary, primary_paths = _experiment(tmp_path, "a", "10", [_roi("Drop")], {})
    other, other_paths = _experiment(tmp_path, "b", "11", [_roi("Drop")], {})

    primary.figure.time_unit = "min"

    assert run_offset(primary, primary_paths, other, other_paths) == 60.0

    primary.figure.x_axis = "frame"

    assert run_offset(primary, primary_paths, other, other_paths) == 0.0


def test_other_curves_follow_the_live_stat_and_their_own_eyes(tmp_path):
    shown, hidden = _roi("A"), _roi("B")
    hidden.style.visible = False
    primary, primary_paths = _experiment(tmp_path, "today", "10", [_roi("A")], {})
    other, other_paths = _experiment(
        tmp_path,
        "yesterday",
        "11",
        [shown, hidden],
        {"A": [7.0, 9.0], "B": [1.0, 1.0]},
    )
    primary.figure.subtract_first = True

    series, _flags, _excluded, _area_fit = imported_series(
        primary, primary_paths, other, other_paths, "y", True
    )

    ((name, _x_values, values),) = series.values()

    assert name == "y · A"
    assert values == [0.0, 2.0]


def test_series_table_pads_shorter_curves():
    text = series_table(
        {"a": ("A", [0.0, 1.0], [2.0, math.nan]), "b": ("B", [0.0], [5.0])},
        "Time (s)",
    )

    assert text.splitlines() == [
        "A Time (s)\tA\tB Time (s)\tB",
        "0.0\t2.0\t0.0\t5.0",
        "1.0\t\t\t",
    ]


def test_the_plotted_set_round_trips_through_its_text():
    payloads = [
        {"directory": "C:/runs/a", "label": "A", "align_to_run_start": True},
        {"directory": "C:/runs/b", "label": "Run 2", "align_to_run_start": False},
    ]

    assert payloads_from_text(payloads_as_text(payloads)) == payloads
    assert payloads_from_text("") == []
    assert payloads_from_text("not json") == []


def test_the_live_experiment_is_plotted_and_the_others_keyed_apart(tmp_path):
    model, live, other = _plotted_pair(tmp_path)

    assert model.add_experiment(other.directory) != ""  # already plotted
    assert model.add_experiment(live.directory) != ""  # the live one

    live_entry, other_entry = model.experiments
    (other_roi,) = other_entry.session.positive_rois
    key = other_entry.key_of(other_roi)

    assert live_entry.live and live_entry.session is live
    assert not other_entry.live

    series, _flags, _excluded, _area_fit = model.imported_series()

    assert series == {key: ("yesterday · Drop", [0.0, 30.0], [7.0, 9.0])}
    assert model.roi_of(key) is other_roi
    assert model.experiment_of(key) is other_entry
    assert model.experiment_of(live.positive_rois[0].roi_id) is None


def test_an_experiment_s_own_exclusions_are_drawn_excluded(tmp_path):
    live, live_paths = _experiment(tmp_path, "today", "10", [_roi("Drop")], {})
    other, _other_paths = _experiment(
        tmp_path, "yesterday", "11", [_roi("Drop")], {"Drop": [7.0, 9.0]}
    )
    other.excluded_images = ["img_2026_07_20-11_00_00_raw.png"]
    _saved(other)
    model = ImportedExperimentsModel(
        analysis=RoiAnalysisModel(session=live, filtered_paths=live_paths)
    )

    assert model.add_experiment(other.directory) == ""

    series, _flags, excluded, _area_fit = model.imported_series()

    # The whole run's clock: the excluded first image is still t = 0.
    assert [entry[1:] for entry in series.values()] == [([30.0], [9.0])]
    assert [entry[1:] for entry in excluded.values()] == [([0.0], [7.0])]


def test_switching_the_live_experiment_keeps_the_set_and_its_order(tmp_path):
    model, live, other = _plotted_pair(tmp_path)
    model.experiments[1].align_to_run_start = False
    payloads = [experiment.as_payload() for experiment in model.experiments]

    # The viewer shows "yesterday": it goes live where it is listed,
    # and "today" is read back from disk with what it saved.
    live.rois[0].name = "Renamed"
    _saved(live)
    shown = load_session(other.directory)
    model.analysis.session = shown

    today, yesterday = model.experiments

    assert [experiment.as_payload() for experiment in model.experiments] == payloads
    assert yesterday.live and yesterday.session is shown
    assert not today.live and today.session is not live
    assert today.session.positive_rois[0].name == "Renamed"

    # A set restored from the preferences lists the live one in place.
    restored = ImportedExperimentsModel(analysis=model.analysis)
    restored.restore(payloads)

    assert [experiment.live for experiment in restored.experiments] == [False, True]


def test_a_restore_lists_each_folder_once_however_it_is_spelled(tmp_path, monkeypatch):
    plotted, live, other = _plotted_pair(tmp_path)
    model = ImportedExperimentsModel(analysis=plotted.analysis)
    monkeypatch.chdir(tmp_path)
    gone = str(tmp_path / "gone")
    payloads = [
        {"directory": other.directory, "label": "Other"},
        {"directory": str(tmp_path / "today" / ".." / "yesterday")},
        {"directory": gone},
        {"directory": "today", "label": "Live"},
        {"directory": gone},
        {"directory": other.directory + os.sep},
    ]

    model.restore(payloads)

    # The duplicates and the missing folder left out; the live folder
    # spelled relatively is still live, in place, as spelled.
    assert [experiment.as_payload() for experiment in model.experiments] == [
        {"directory": other.directory, "label": "Other", "align_to_run_start": True},
        {"directory": "today", "label": "Live", "align_to_run_start": True},
    ]
    assert [experiment.live for experiment in model.experiments] == [False, True]
    assert model.experiments[1].session is live


def test_a_restore_with_no_experiment_shown_marks_none_live(tmp_path):
    _live, live_paths = _experiment(tmp_path, "today", "10", [_roi("Drop")], {})
    model = ImportedExperimentsModel(
        analysis=RoiAnalysisModel(session=AnalysisSession(), filtered_paths=live_paths)
    )
    today = str(tmp_path / "today")

    model.restore([{"directory": today}, {"directory": today + os.sep}])

    assert [experiment.directory for experiment in model.experiments] == [today]
    assert not model.experiments[0].live


def test_restoring_resolves_each_folder_once(tmp_path, monkeypatch):
    """Not each folder against every other: the plotted set grows with
    every experiment shown, and a restore runs at launch."""
    count = 40
    directories = []

    for index in range(count):
        folder = tmp_path / f"experiment_{index:02d}"
        folder.mkdir()
        directories.append(str(folder))

    model = ImportedExperimentsModel(analysis=RoiAnalysisModel())
    payloads = [{"directory": directory} for directory in directories]
    resolves = []
    resolve = Path.resolve

    def counted_resolve(path, *args, **kwargs):
        resolves.append(path)

        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", counted_resolve)

    # Restored with no experiment shown, as the pane mounts; then the
    # viewer shows the last one, which goes live in place.
    model.restore(payloads)
    mount_resolves = len(resolves)
    model.analysis.session = load_session(directories[-1])

    assert mount_resolves <= count + 1
    assert len(resolves) - mount_resolves <= count + 1
    assert len(model.experiments) == count
    assert model.live_experiment is model.experiments[-1]


def test_an_experiment_shown_outside_the_set_joins_it_last(tmp_path):
    model, _live, _other = _plotted_pair(tmp_path)
    third, _paths = _experiment(tmp_path, "tomorrow", "12", [_roi("Drop")], {})
    _saved(third)

    model.analysis.session = load_session(third.directory)

    assert [experiment.label for experiment in model.experiments] == [
        "today",
        "yesterday",
        "tomorrow",
    ]
    assert model.experiments[-1].live

    model.keep_live_only()

    assert [experiment.label for experiment in model.experiments] == ["tomorrow"]


def test_a_removed_experiment_leaves_the_set(tmp_path):
    model, _live, _other = _plotted_pair(tmp_path)

    model.experiments[1].remove = True

    assert [experiment.live for experiment in model.experiments] == [True]


def test_another_experiment_s_curve_has_its_own_series_landmarks(tmp_path):
    seconds = ("00", "10", "20", "30", "40", "50")
    means = (1.0, 2.0, 6.0, 7.0, 7.5, 12.0)
    model, _live, _other = _plotted_pair(tmp_path, seconds, means)
    experiment = model.experiments[1]
    metrics = ["zero", "max", "min"]

    series, _flags, _excluded, _area_fit = model.imported_series()
    ((_name, x_values, values),) = series.values()
    direct, _flags = analysed_series(experiment.session, experiment.paths, False)
    ((_name, direct_x, direct_values),) = direct.values()

    def landmarks(x, y):
        return fit_landmarks(fit_series(x, y, "poly3"), min(x), max(x), metrics)

    assert values == list(means)
    assert landmarks(x_values, values) == landmarks(direct_x, direct_values)
    assert set(landmarks(x_values, values)) == set(metrics)


def test_a_style_saved_with_one_alpha_gives_its_lines_that_alpha(tmp_path):
    session = AnalysisSession(directory=str(tmp_path), rois=[_roi("Drop")])
    save_session(tmp_path, session)
    config = tmp_path / ANALYSIS_DIR_NAME / ROI_CONFIG_FILENAME
    payload = json.loads(config.read_text())
    payload["rois"][0]["style"] = {"color": "#123456", "alpha": 40}
    config.write_text(json.dumps(payload))

    (roi,) = load_session(tmp_path).rois

    assert roi.style.trait_get("alpha", "line_alpha", "line_width") == {
        "alpha": 40,
        "line_alpha": 40,
        "line_width": ROI_LINE_WIDTH_PT,
    }


def test_saved_roi_styles_carry_the_line_width_and_both_alphas(tmp_path):
    session = AnalysisSession(directory=str(tmp_path), rois=[_roi("Drop")])
    save_session(tmp_path, session)
    session.rois[0].style.trait_set(line_width=3.0, line_alpha=30, alpha=70)

    save_roi_styles(tmp_path, session.rois)
    (roi,) = load_session(tmp_path).rois

    assert roi.style.trait_get("line_width", "line_alpha", "alpha") == {
        "line_width": 3.0,
        "line_alpha": 30,
        "alpha": 70,
    }


def test_deleting_saved_rois_keeps_the_rest_of_their_file(tmp_path):
    kept, deleted, also = _roi("Kept"), _roi("Deleted"), _roi("Also deleted")
    session = AnalysisSession(
        directory=str(tmp_path), rois=[kept, deleted, also], excluded_images=["a.png"]
    )
    save_session(tmp_path, session)
    config = tmp_path / ANALYSIS_DIR_NAME / ROI_CONFIG_FILENAME
    before = json.loads(config.read_text())

    delete_saved_rois(tmp_path, [deleted.roi_id, also.roi_id])
    after = json.loads(config.read_text())

    assert after["rois"] == [before["rois"][0]]
    assert {**after, "rois": before["rois"]} == before
    assert [roi.name for roi in load_session(tmp_path).rois] == ["Kept"]


def test_a_stored_roi_deleted_leaves_its_session_and_its_curves(tmp_path):
    model, _live, other = _plotted_pair(tmp_path)
    experiment = model.experiments[1]
    (roi,) = experiment.session.rois

    experiment.delete_rois([roi])
    series, _flags, _excluded, _area_fit = model.imported_series()

    assert experiment.session.rois == []
    assert series == {}
    assert load_session(other.directory).rois == []


def test_a_section_eye_shows_or_hides_every_roi_but_masks(tmp_path):
    model, _live, other = _plotted_pair(tmp_path)
    experiment = model.experiments[1]
    mask = _roi("Mask")
    mask.is_negative = True
    experiment.session.rois.append(mask)
    (roi,) = experiment.session.positive_rois

    assert experiment.any_roi_shown

    experiment.toggle_rois_shown()

    assert not roi.style.visible and mask.style.visible
    assert not experiment.any_roi_shown
    assert not load_session(other.directory).rois[0].style.visible

    experiment.toggle_rois_shown()

    assert roi.style.visible and experiment.any_roi_shown


def test_a_bulk_restyle_reaches_every_experiment_and_saves_each_once(
    tmp_path, monkeypatch
):
    model, live, other = _plotted_pair(tmp_path)
    experiment = model.experiments[1]
    mask = _roi("Mask")
    mask.is_negative = True
    live.rois.append(mask)
    (other_roi,) = experiment.session.rois
    keys = [
        live.rois[0].roi_id,
        mask.roi_id,
        experiment.key_of(other_roi),
        "missing",
    ]
    saves = []
    monkeypatch.setattr(
        "image_viewer.analysis.imported_experiments_model.save_roi_styles",
        lambda directory, rois: saves.append(directory),
    )

    grouped = model.rois_by_experiment(keys)

    assert grouped == {
        model.live_experiment: [live.rois[0], mask],
        experiment: [other_roi],
    }

    model.restyle_rois(keys, line_width=3.0, alpha=40, visible=False)

    for roi in (live.rois[0], other_roi):
        assert roi.style.trait_get("line_width", "alpha", "visible") == {
            "line_width": 3.0,
            "alpha": 40,
            "visible": False,
        }

    # A mask takes the eye alone; the live experiment is the viewer's to
    # save; the other is written once for the three changes.
    assert mask.style.line_width != 3.0 and not mask.style.visible
    assert saves == [experiment.directory]
