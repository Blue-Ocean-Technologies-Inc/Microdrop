# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A lead card's pictures: always the card's full width, at their own aspect
up to a cap, then cropped (never padded); a pair side by side at equal size
and one shared aspect, or stacked when narrow, each full width."""

# Third-party imports.
import pytest

# Microdrop package imports.
from news.views.card_style import (
    GRID,
    PAIR_ASPECT,
    PAIR_ASPECT_RANGE,
    PAIR_MIN_WIDTH,
    PICTURE_CEILING,
    full_width_picture_height,
    pair_aspect,
    picture_cap,
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


@pytest.mark.parametrize("width", range(240, 761, 40))
def test_a_wide_banner_is_never_cropped(width):
    assert full_width_picture_height(width, 2700, 1000) == round(width / 2.7)


def test_a_square_picture_is_capped_and_cropped_not_padded():
    assert full_width_picture_height(400, 1000, 1000) == round(0.62 * 400)


def test_the_cap_has_a_ceiling():
    assert full_width_picture_height(760, 1000, 1000) == PICTURE_CEILING


def test_a_small_picture_still_fills_the_width():
    assert full_width_picture_height(800, 200, 100) == 400


def test_a_pair_shares_the_less_extreme_aspect_within_range():
    assert pair_aspect((16 / 9, 1.0)) == 1.0
    assert pair_aspect((3.0, 2.5)) == PAIR_ASPECT_RANGE[1]
    assert pair_aspect((0.4, 0.5)) == PAIR_ASPECT_RANGE[0]


def test_stacked_pictures_each_keep_their_own_aspect():
    width = PAIR_MIN_WIDTH - 40
    (first, second), height = picture_pair_cells(width, 0, (2.0, 1.0))

    assert first[3] == round(width / 2.0)
    assert second[3] == round(min(width / 1.0, picture_cap(width)))
    assert second[1] == first[3] + GRID
    assert height == second[1] + second[3]
