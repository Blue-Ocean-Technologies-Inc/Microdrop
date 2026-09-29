# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The image-group filter's "All" choice mirrors the image filter's."""

# Standard library imports.
from pathlib import Path

# Microdrop package imports.
from image_viewer.model import (
    BURST_FILTER_ALL,
    ImageViewerModel,
)


def _model_with_two_bursts():
    model = ImageViewerModel()
    model.bursts = [
        (
            "burst_a",
            [Path("a/16bit_raw/img1_raw.png"), Path("a/16bit_raw/img2_raw.png")],
        ),
        ("burst_b", [Path("b/16bit_raw/img3_raw.png")]),
    ]
    return model


def test_burst_names_prepend_all():
    model = _model_with_two_bursts()
    assert model.burst_names == [BURST_FILTER_ALL, "burst_a", "burst_b"]


def test_burst_names_empty_without_bursts():
    assert ImageViewerModel().burst_names == []


def test_burst_paths_all_flattens_groups_in_order():
    model = _model_with_two_bursts()
    assert [path.name for path in model.burst_paths(BURST_FILTER_ALL)] == [
        "img1_raw.png",
        "img2_raw.png",
        "img3_raw.png",
    ]


def test_position_text_spans_all_when_all_selected():
    model = _model_with_two_bursts()
    model.selected_burst = BURST_FILTER_ALL
    model.burst_index = 0
    model.paths = model.burst_paths(BURST_FILTER_ALL)
    model.current_path = str(model.paths[2])
    assert model.position_text == "3/3"


def test_position_text_counts_prior_groups_for_specific_burst():
    model = _model_with_two_bursts()
    model.selected_burst = "burst_b"
    model.burst_index = 2  # [All, burst_a, burst_b]
    model.paths = model.burst_paths("burst_b")
    model.current_path = str(model.paths[0])
    assert model.position_text == "3/3"
