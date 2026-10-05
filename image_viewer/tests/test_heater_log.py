# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater-log lookup tests: a log span, the sibling-experiment fallback
for a log the heater plugin filed under another experiment, and the
rule that an auto-found folder is never persisted as the user's."""

# Standard library imports.
import json
import os
from datetime import datetime, timedelta

# Microdrop package imports.
from image_viewer.analysis.consts import HEATER_LOGS_DIR_NAME
from image_viewer.analysis.heater_log import (
    heater_log_span,
    resolve_heater_samples,
    sibling_heater_log_folders,
)
from image_viewer.analysis.roi_model import AnalysisSession
from image_viewer.analysis.roi_store import load_session, save_session

DAY = datetime(2026, 10, 5)


def _at(hour, minute=0):
    return DAY + timedelta(hours=hour, minutes=minute)


def _write_log(experiment, start, end, mtime=None):
    """A 1-per-minute TEMP log in the heater plugin's format, named by
    its first line's local time, under ``experiment/heater_logs``."""
    folder = experiment / HEATER_LOGS_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    rows = [json.dumps({"_frame": "STATUS", "timestamp": start.isoformat()})]
    moment = start

    while moment <= end:
        rows.append(
            json.dumps(
                {
                    "_frame": "TEMP",
                    "timestamp": moment.isoformat(),
                    "temperatures": {"T1": 25.0, "T2": 27.0},
                }
            )
        )
        moment += timedelta(minutes=1)

    (folder / f"{start:%Y%m%d_%H%M%S}.jsonl").write_text(
        "\n".join(rows), encoding="utf-8"
    )

    if mtime is not None:
        os.utime(experiment, (mtime, mtime))

    return folder


def _current_experiment(root):
    experiment = root / "20261005_113000"
    (experiment / HEATER_LOGS_DIR_NAME).mkdir(parents=True)

    return experiment


def test_span_runs_from_first_stamp_to_newest_logs_last_sample(tmp_path):
    experiment = tmp_path / "experiment"
    _write_log(experiment, _at(9), _at(9, 20))
    folder = _write_log(experiment, _at(10), _at(10, 45))

    assert heater_log_span(folder) == (_at(9).timestamp(), _at(10, 45).timestamp())


def test_span_of_a_folder_without_logs_is_none(tmp_path):
    assert heater_log_span(tmp_path / "missing") is None


def test_sibling_search_finds_only_the_experiment_covering_the_captures(tmp_path):
    current = _current_experiment(tmp_path)
    _write_log(tmp_path / "20261005_100000", _at(10), _at(10, 30))
    covering = _write_log(tmp_path / "20261005_110000", _at(11), _at(12, 30))

    matches = sibling_heater_log_folders(
        current, _at(11, 30).timestamp(), _at(11, 45).timestamp()
    )

    assert [folder for folder, _overlap in matches] == [covering]


def test_sibling_search_ranks_several_matches_by_overlap(tmp_path):
    current = _current_experiment(tmp_path)
    partial = _write_log(tmp_path / "20261005_114000", _at(11, 40), _at(11, 50))
    covering = _write_log(tmp_path / "20261005_110000", _at(11), _at(12, 30))

    matches = sibling_heater_log_folders(
        current, _at(11, 30).timestamp(), _at(12).timestamp()
    )

    assert [folder for folder, _overlap in matches] == [covering, partial]
    assert matches[0][1] > matches[1][1]


def test_sibling_search_is_bounded_to_the_most_recent_experiments(tmp_path):
    current = _current_experiment(tmp_path)
    older = _at(8).timestamp()
    newer = _at(9).timestamp()
    _write_log(tmp_path / "old", _at(11), _at(12), mtime=older)
    recent = _write_log(tmp_path / "recent", _at(11, 20), _at(11, 50), mtime=newer)

    matches = sibling_heater_log_folders(
        current, _at(11, 30).timestamp(), _at(11, 40).timestamp(), limit=1
    )

    assert [folder for folder, _overlap in matches] == [recent]


def test_resolve_falls_back_to_the_covering_sibling(tmp_path):
    current = _current_experiment(tmp_path)
    covering = _write_log(tmp_path / "20261005_110000", _at(11), _at(12, 30))

    samples, fallback, match_count = resolve_heater_samples(
        current / HEATER_LOGS_DIR_NAME,
        current,
        _at(11, 30).timestamp(),
        _at(11, 45).timestamp(),
    )

    assert fallback == str(covering)
    assert match_count == 1
    assert samples
    assert samples[0][1] == {"T1": 25.0, "T2": 27.0}


def test_resolve_keeps_a_configured_folder_that_covers(tmp_path):
    current = _current_experiment(tmp_path)
    own = _write_log(current, _at(11, 20), _at(12))
    _write_log(tmp_path / "20261005_110000", _at(11), _at(12, 30))

    samples, fallback, match_count = resolve_heater_samples(
        own, current, _at(11, 30).timestamp(), _at(11, 45).timestamp()
    )

    assert samples
    assert (fallback, match_count) == ("", 0)


def test_resolve_without_any_coverage_reports_no_fallback(tmp_path):
    current = _current_experiment(tmp_path)
    _write_log(tmp_path / "20261005_100000", _at(10), _at(10, 30))

    samples, fallback, match_count = resolve_heater_samples(
        current / HEATER_LOGS_DIR_NAME,
        current,
        _at(11, 30).timestamp(),
        _at(11, 45).timestamp(),
    )

    assert (samples, fallback, match_count) == ([], "", 0)


def test_auto_found_folder_is_shown_but_never_persisted(tmp_path):
    session = AnalysisSession(heater_log_dir=str(tmp_path / HEATER_LOGS_DIR_NAME))
    session.heater_log_fallback_dir = str(
        tmp_path.parent / "20261005_110000" / HEATER_LOGS_DIR_NAME
    )

    assert session.heater_log_hint == "(found in 20261005_110000)"

    save_session(tmp_path, session)
    loaded = load_session(tmp_path)

    assert loaded.heater_log_dir == session.heater_log_dir
    assert loaded.heater_log_fallback_dir == ""
    assert loaded.heater_log_hint == ""
