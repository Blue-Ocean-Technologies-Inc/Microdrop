# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Loading a long plotted set without freezing the window (#1086): saved
analyses read off the GUI thread, a switch touching only the experiments
that changed, and the ROI table building widgets only for rows in view."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtWidgets

# Microdrop package imports.
from image_viewer.analysis import plotted_experiments_reader as reader
from image_viewer.analysis.imported_experiments_model import (
    ImportedExperiment,
    ImportedExperimentsModel,
)
from image_viewer.analysis.roi_model import AnalysisSession, Roi, RoiAnalysisModel
from image_viewer.analysis.roi_store import load_session, save_session
from image_viewer.analysis.roi_table import RoiStatsTable


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _roi(name):
    return Roi(name=name, kind="ellipse", geometry=[5.0, 5.0, 2.0, 2.0, 0.0])


def _saved_experiments(tmp_path, count):
    """``count`` experiment folders, each with one saved ROI."""
    directories = []

    for index in range(count):
        directory = tmp_path / f"run_{index:02d}"
        directory.mkdir()
        save_session(
            directory, AnalysisSession(directory=str(directory), rois=[_roi("Drop")])
        )
        directories.append(str(directory))

    return directories


class _InlineThread:
    """A thread that runs its target as it starts."""

    def __init__(self, target, **kwargs):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def handed_back(monkeypatch):
    """Run the reader's thread inline, and collect what it hands back and
    what it paces, for the test to run in order."""
    calls = []

    def collect(kind):
        return lambda *call: calls.append((kind, call))

    monkeypatch.setattr(reader, "threading", SimpleNamespace(Thread=_InlineThread))
    monkeypatch.setattr(reader, "GUI", SimpleNamespace(invoke_later=collect("later")))
    monkeypatch.setattr(reader, "invoke_paced", collect("paced"))

    return calls


def _run(calls):
    """Run the collected calls, and those they queue, oldest first."""
    while calls:
        _kind, (callable, *args) = calls.pop(0)
        callable(*args)


def test_a_switch_replaces_only_the_experiments_that_changed(tmp_path):
    directories = _saved_experiments(tmp_path, 12)
    model = ImportedExperimentsModel(analysis=RoiAnalysisModel())
    model.restore([{"directory": directory} for directory in directories])
    before = list(model.experiments)
    changes = []
    model.observe(changes.append, "experiments:items")

    model.analysis.session = load_session(directories[3])

    assert model.experiments[3].live
    assert [
        experiment is old
        for experiment, old in zip(model.experiments, before, strict=True)
    ] == [index != 3 for index in range(12)]
    assert [(len(change.removed), len(change.added)) for change in changes] == [(1, 1)]


def test_a_background_restore_lists_them_loading_then_reads_each(tmp_path, handed_back):
    directories = _saved_experiments(tmp_path, 3)
    model = ImportedExperimentsModel(
        analysis=RoiAnalysisModel(), read_in_background=True
    )

    model.restore([{"directory": directory} for directory in directories])
    loading = list(model.experiments)

    assert [experiment.loading for experiment in loading] == [True] * 3
    assert loading[0].summary == "loading…"

    # Changed while it was read: the read one takes the new settings.
    loading[1].align_to_run_start = False
    _run(handed_back)

    assert [experiment.loading for experiment in model.experiments] == [False] * 3
    assert [experiment.directory for experiment in model.experiments] == directories
    assert not model.experiments[1].align_to_run_start
    assert model.experiments[0].summary == "0 images, 1 ROI"


def test_a_read_landing_after_its_experiment_left_the_set_is_dropped(
    tmp_path, handed_back
):
    directories = _saved_experiments(tmp_path, 3)
    model = ImportedExperimentsModel(
        analysis=RoiAnalysisModel(), read_in_background=True
    )
    model.restore([{"directory": directory} for directory in directories])

    # Removed, and another shown in the viewer, before the reads land.
    model.experiments[0].remove = True
    shown = load_session(directories[2])
    model.analysis.session = shown
    _run(handed_back)

    assert [experiment.directory for experiment in model.experiments] == directories[1:]
    assert model.experiments[1].live and model.experiments[1].session is shown
    assert not model.experiments[0].loading


def test_the_roi_table_builds_widgets_only_for_rows_in_view(qapp):
    imports = ImportedExperimentsModel(analysis=RoiAnalysisModel())
    imports.experiments = [
        ImportedExperiment(
            directory=f"C:/runs/{index:02d}",
            session=AnalysisSession(directory=f"C:/runs/{index:02d}", rois=[_roi("A")]),
        )
        for index in range(60)
    ]
    table = RoiStatsTable(imports.analysis, imports)
    table.resize(900, 240)
    table.show()
    qapp.processEvents()

    def built():
        return [
            table.itemWidget(table.topLevelItem(index), 0) is not None
            for index in range(table.topLevelItemCount())
        ]

    # "This experiment" (no widget), then a section per experiment.
    assert built()[1] and not built()[-1]

    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
    qapp.processEvents()

    assert built()[-1]

    table.detach()
    table.deleteLater()
