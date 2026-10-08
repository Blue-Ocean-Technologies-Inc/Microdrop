# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Incremental heater-log reading: a log the heater is still writing is
read by its appended lines (through truncation and rollover to a new
file), the sibling search runs once, and the controller loads samples
only for a shown plot on the temperature axis."""

# Standard library imports.
import json
from datetime import datetime, timedelta

# Enthought library imports.
from traits.api import List

# Microdrop package imports.
from image_viewer.analysis import heater_log
from image_viewer.analysis.consts import HEATER_LOGS_DIR_NAME
from image_viewer.analysis.heater_loader import HeaterSamplesLoader
from image_viewer.analysis.heater_log import (
    HeaterLogReader,
    TailedHeaterLog,
    heater_log_span,
    resolve_heater_samples,
)
from image_viewer.analysis.roi_controller import RoiAnalysisController
from image_viewer.analysis.roi_model import RoiAnalysisModel
from image_viewer.model import ImageViewerModel

DAY = datetime(2026, 10, 5)


def _at(hour, minute=0, second=0):
    return DAY + timedelta(hours=hour, minutes=minute, seconds=second)


def _temp_line(moment, value=25.0):
    record = {
        "_frame": "TEMP",
        "timestamp": moment.isoformat(),
        "temperatures": {"T1": value},
    }

    return json.dumps(record) + "\n"


def _append(path, *moments):
    with path.open("a", encoding="utf-8") as stream:
        stream.writelines(_temp_line(moment) for moment in moments)


def _log_path(folder, start):
    folder.mkdir(parents=True, exist_ok=True)

    return folder / f"{start:%Y%m%d_%H%M%S}.jsonl"


def test_tail_reads_only_the_appended_lines(tmp_path):
    path = _log_path(tmp_path, _at(10))
    _append(path, _at(10), _at(10, 0, 1))
    log = TailedHeaterLog(path=path)

    log.read()
    first_offset = log.offset
    _append(path, _at(10, 0, 2))
    log.read()

    assert first_offset < log.offset == path.stat().st_size
    assert [epoch for epoch, _readings in log.samples] == [
        _at(10).timestamp(),
        _at(10, 0, 1).timestamp(),
        _at(10, 0, 2).timestamp(),
    ]
    assert log.last_epoch == _at(10, 0, 2).timestamp()


def test_tail_waits_for_a_half_written_line(tmp_path):
    path = _log_path(tmp_path, _at(10))
    whole = _temp_line(_at(10, 0, 1))
    _append(path, _at(10))

    with path.open("a", encoding="utf-8") as stream:
        stream.write(whole[:20])

    log = TailedHeaterLog(path=path)
    log.read()

    assert len(log.samples) == 1

    with path.open("a", encoding="utf-8") as stream:
        stream.write(whole[20:])

    log.read()

    assert len(log.samples) == 2
    assert log.offset == path.stat().st_size


def test_tail_takes_an_unterminated_but_whole_last_line(tmp_path):
    path = _log_path(tmp_path, _at(10))
    path.write_text(_temp_line(_at(10)).rstrip("\n"), encoding="utf-8")
    log = TailedHeaterLog(path=path)

    log.read()

    assert len(log.samples) == 1
    assert log.offset == path.stat().st_size


def test_tail_starts_over_after_truncation(tmp_path):
    path = _log_path(tmp_path, _at(10))
    _append(path, *(_at(10, 0, second) for second in range(5)))
    log = TailedHeaterLog(path=path)
    log.read()

    path.write_text("", encoding="utf-8")
    _append(path, _at(11), _at(11, 0, 1))
    log.read()

    assert [epoch for epoch, _readings in log.samples] == [
        _at(11).timestamp(),
        _at(11, 0, 1).timestamp(),
    ]


def test_reader_follows_a_rollover_to_a_new_log(tmp_path):
    first = _log_path(tmp_path, _at(10))
    _append(first, _at(10), _at(10, 10))
    reader = HeaterLogReader()
    capture_range = (_at(10).timestamp(), _at(10, 30).timestamp())

    before = reader.resolve(tmp_path, None, *capture_range)
    second = _log_path(tmp_path, _at(10, 20))
    _append(second, _at(10, 20), _at(10, 30))
    after = reader.resolve(tmp_path, None, *capture_range)

    assert len(before.samples) == 2
    assert len(after.samples) == 4
    assert after.span == (_at(10).timestamp(), _at(10, 30).timestamp())
    assert after.fingerprint != before.fingerprint


def test_reader_agrees_with_the_one_shot_helpers(tmp_path):
    current = tmp_path / "20261005_113000"
    (current / HEATER_LOGS_DIR_NAME).mkdir(parents=True)
    sibling = tmp_path / "20261005_110000" / HEATER_LOGS_DIR_NAME
    _append(_log_path(sibling, _at(11)), *(_at(11, minute) for minute in range(60)))
    folder = current / HEATER_LOGS_DIR_NAME
    capture_range = (_at(11, 30).timestamp(), _at(11, 45).timestamp())

    result = HeaterLogReader().resolve(folder, current, *capture_range)
    samples, fallback, match_count = resolve_heater_samples(
        folder, current, *capture_range
    )

    assert result.samples == samples
    assert (result.fallback, result.match_count) == (fallback, match_count)
    assert result.span == heater_log_span(folder)


def test_reader_searches_the_siblings_once(tmp_path, monkeypatch):
    current = tmp_path / "20261005_113000"
    (current / HEATER_LOGS_DIR_NAME).mkdir(parents=True)
    searches = []
    search = heater_log.sibling_heater_log_spans

    def counted(experiment_directory, *arguments):
        searches.append(experiment_directory)

        return search(experiment_directory, *arguments)

    monkeypatch.setattr(heater_log, "sibling_heater_log_spans", counted)
    reader = HeaterLogReader()
    folder = current / HEATER_LOGS_DIR_NAME

    for minute in (40, 50):
        reader.resolve(
            folder, current, _at(11).timestamp(), _at(11, minute).timestamp()
        )

    assert len(searches) == 1


class _RecordingLoader(HeaterSamplesLoader):
    """Records requests instead of starting a worker."""

    requests = List()

    def request(self, *arguments):
        self.requests.append(arguments)


def _gated_controller(tmp_path, x_axis, plot_visible):
    loader = _RecordingLoader()
    controller = RoiAnalysisController(
        viewer_model=ImageViewerModel(),
        analysis_model=RoiAnalysisModel(),
        _heater_loader=loader,
    )
    controller.session.heater_log_dir = str(tmp_path)
    controller.session.figure.x_axis = x_axis
    controller.analysis_model.plot_visible = plot_visible
    controller.viewer_model.paths = [tmp_path / "capture.png"]

    return controller, loader


def test_time_axis_loads_no_heater_samples(tmp_path):
    _controller, loader = _gated_controller(tmp_path, "time", plot_visible=True)

    assert loader.requests == []


def test_hidden_plot_loads_none_until_shown(tmp_path):
    controller, loader = _gated_controller(tmp_path, "temperature", False)

    assert loader.requests == []

    controller.analysis_model.plot_visible = True

    assert [request[0] for request in loader.requests] == [str(tmp_path)]


def test_shown_temperature_plot_loads_on_new_captures(tmp_path):
    controller, loader = _gated_controller(tmp_path, "temperature", True)
    loader.requests = []

    controller.viewer_model.paths = [tmp_path / "a.png", tmp_path / "b.png"]

    assert len(loader.requests) == 1
