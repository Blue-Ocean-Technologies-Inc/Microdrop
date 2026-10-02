# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""quads_order_matches: the alignment dialog's same-dot-order check."""

# Microdrop package imports.
from device_viewer.utils.quad_order import (
    canonical_quad,
    quads_order_matches,
    signed_area,
    top_left_index,
)

#: TL/TR/BR/BL, clockwise in y-down image coordinates.
QUAD = [[10, 10], [110, 12], [108, 60], [12, 58]]


def test_same_order_matches_even_scaled_and_moved():
    other = [[x * 3 + 500, y * 3 + 40] for x, y in QUAD]

    assert quads_order_matches(QUAD, other)


def test_two_shifted_order_is_a_mismatch():
    shifted = QUAD[2:] + QUAD[:2]

    assert top_left_index(shifted) == 2
    assert not quads_order_matches(QUAD, shifted)


def test_mirrored_order_is_a_mismatch():
    mirrored = [[200 - x, y] for x, y in QUAD]

    assert signed_area(QUAD) > 0 > signed_area(mirrored)
    assert not quads_order_matches(QUAD, mirrored)


def test_canonical_quad_numbers_from_the_top_left_clockwise():
    br_first = QUAD[2:] + QUAD[:2]

    assert canonical_quad(br_first) == QUAD


def test_canonical_quad_leaves_a_canonical_quad_alone():
    assert canonical_quad(QUAD) == QUAD


def test_canonical_quad_reverses_an_anticlockwise_quad():
    anticlockwise = [QUAD[0], QUAD[3], QUAD[2], QUAD[1]]

    assert canonical_quad(anticlockwise) == QUAD
