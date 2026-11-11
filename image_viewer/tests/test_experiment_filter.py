# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Experiment search: the filter narrows only the dropdown's choices."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop package imports.
from image_viewer.model import ImageViewerModel, matches_experiment_filter

#: Experiment folder names, oldest first, as discover_experiments lists them.
NAMES = [
    "2026_10_27-09_12_03",
    "2026_10_29-15_06_46",
    "2026_10_29-16_40_10_Calibration",
]


def _model(selected=NAMES[0]):
    experiments = [(name, Path(name) / "captures") for name in NAMES]

    return ImageViewerModel(experiments=experiments, selected_experiment=selected)


@pytest.mark.parametrize(
    "filter_text, expected",
    [
        ("", True),
        ("   ", True),
        ("calibration", True),
        ("CALIBRATION", True),
        ("10_29 16_40", True),
        ("16_40 10_29", True),
        ("10_29 09_12", False),
        ("10-29", False),
    ],
)
def test_matches_experiment_filter(filter_text, expected):
    assert matches_experiment_filter(NAMES[2], filter_text) is expected


def test_empty_filter_lists_every_experiment():
    assert _model().filtered_experiment_names == NAMES


def test_filter_keeps_chronological_order():
    model = _model(selected=NAMES[1])

    model.experiment_filter = "10_29"

    assert model.filtered_experiment_names == NAMES[1:]


def test_filter_keeps_the_unmatched_selection_listed_and_selected():
    model = _model(selected=NAMES[0])

    model.experiment_filter = "calibration"

    assert model.filtered_experiment_names == [NAMES[0], NAMES[2]]
    assert model.selected_experiment == NAMES[0]
    assert model.experiment_index == 0


def test_moving_the_selection_drops_the_old_unmatched_one():
    model = _model(selected=NAMES[0])
    model.experiment_filter = "calibration"

    model.selected_experiment = NAMES[2]

    assert model.filtered_experiment_names == [NAMES[2]]


def test_filter_leaves_experiment_names_whole():
    model = _model()

    model.experiment_filter = "no such experiment"

    assert model.experiment_names == NAMES
    assert model.filtered_experiment_names == [NAMES[0]]
    assert model.max_experiment_number == len(NAMES)
