# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A lead card's two pictures: their cells follow the width, side by side
at equal size or stacked when narrow, always at one aspect."""

# Third-party imports.
import pytest

# Microdrop package imports.
from news.views.card_style import (
    GRID,
    PAIR_ASPECT,
    PAIR_MIN_WIDTH,
    picture_pair_cells,
)

CAPTION = 20


@pytest.mark.parametrize("width", range(PAIR_MIN_WIDTH, 761, 20))
def test_side_by_side_cells_are_equal_halves_with_a_gap(width):
    (first, second), height = picture_pair_cells(width, CAPTION)

    assert first[2:] == second[2:]
    assert second[0] == first[0] + first[2] + GRID
    assert second[0] + second[2] <= width
    assert first[3] == round(first[2] / PAIR_ASPECT)
    assert height == first[3] + CAPTION


@pytest.mark.parametrize("width", range(200, PAIR_MIN_WIDTH, 20))
def test_narrow_cells_stack_at_full_width(width):
    (first, second), height = picture_pair_cells(width, CAPTION)

    assert first[2] == second[2] == width
    assert second[1] == first[3] + CAPTION + GRID
    assert height == second[1] + second[3] + CAPTION


def test_the_height_grows_with_the_width_on_each_side_of_the_threshold():
    heights = [picture_pair_cells(width, 0)[1] for width in range(320, 761, 20)]

    assert heights == sorted(heights)
