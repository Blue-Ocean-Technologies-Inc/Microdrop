# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A lead card's pictures: shown whole at their own aspect up to a cap; a
pair side by side at equal size and one shared aspect, or stacked when
narrow, each whole at its own aspect."""

# Third-party imports.
import pytest

# Microdrop package imports.
from news.views.card_style import (
    GRID,
    MAX_UPSCALE,
    PAIR_ASPECT,
    PAIR_ASPECT_RANGE,
    PAIR_MIN_WIDTH,
    pair_aspect,
    picture_cap,
    picture_pair_cells,
    whole_picture_box,
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


def test_a_wide_picture_fills_the_width_uncropped():
    height, (x, y, width, shown_height) = whole_picture_box(400, 1600, 600)

    assert (x, y, width) == (0, 0, 400)
    assert height == shown_height == 150


def test_a_square_picture_is_fitted_in_whole_and_centred():
    height, (x, _y, width, shown_height) = whole_picture_box(400, 1000, 1000)

    assert height == shown_height == round(picture_cap(400)) == 300
    assert width == 300
    assert x == 50


def test_a_small_picture_is_not_blown_up():
    height, (x, _y, width, _h) = whole_picture_box(800, 200, 100)

    assert (width, height) == (round(200 * MAX_UPSCALE), round(100 * MAX_UPSCALE))
    assert x == (800 - width) // 2


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
