# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Which plotted experiments the preferences keep: those worth plotting,
so one read with nothing measured does not pile up launch after launch
(#1072), while one whose read failed is not dropped for good."""

# Third-party imports.
import pytest

# Microdrop package imports.
from image_viewer.analysis.imported_experiments_model import (
    ImportedExperiment,
    ImportedExperimentsModel,
)
from image_viewer.analysis.roi_model import RoiAnalysisModel


@pytest.mark.parametrize(
    "traits, kept",
    [
        ({"live": True}, True),
        ({"loading": True}, True),
        ({"paths": ["C:/runs/00/captures/a.png"]}, True),
        ({}, False),
    ],
    ids=["live", "loading", "has paths", "read with empty paths"],
)
def test_an_experiment_is_worth_plotting_while_it_may_hold_data(traits, kept):
    experiment = ImportedExperiment(directory="C:/runs/00", **traits)

    assert experiment.worth_plotting is kept


def test_an_experiment_whose_read_failed_stays_worth_plotting():
    model = ImportedExperimentsModel(analysis=RoiAnalysisModel())
    loading = ImportedExperiment(directory="C:/runs/00", loading=True)
    model.experiments = [loading]

    model._swap_in_read([(loading, None)])

    (failed,) = model.experiments

    assert failed is not loading and not failed.loading
    assert failed.read_failed and failed.worth_plotting
