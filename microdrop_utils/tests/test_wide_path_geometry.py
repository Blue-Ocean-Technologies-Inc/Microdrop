# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The geometry helpers and the notation, on a synthetic square grid."""

# Standard library imports.
import math
from textwrap import dedent

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.wide_path_geometry import (
    block_cells,
    block_footprint,
    lattice_pitch,
    left_normal,
    nearest_electrode,
    route_headings,
    slug_phases,
)
from microdrop_utils.wide_path_notation import (
    frame_text,
    heading_letter,
    lattice_cells,
    parse,
    render_phases,
    shorthand,
    window_around,
)


@pytest.fixture
def grid():
    """An 11x11 unit lattice with 4-neighbourhood: (centroids, neighbours)."""
    n = 11
    centroids = {
        f"e{x:02d}{y:02d}": (float(x), float(y)) for x in range(n) for y in range(n)
    }
    neighbours = {
        f"e{x:02d}{y:02d}": [
            f"e{a:02d}{b:02d}"
            for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            if 0 <= a < n and 0 <= b < n
        ]
        for x in range(n)
        for y in range(n)
    }
    return centroids, neighbours


# Right along y=5 from x=2 to the corner at (5, 5), then up to y=3.
L_ROUTE = ["e0205", "e0305", "e0405", "e0505", "e0504", "e0503"]


def test_pitch_is_the_median_neighbour_distance(grid):
    centroids, neighbours = grid
    assert lattice_pitch(centroids, neighbours) == 1.0
    assert lattice_pitch({}, {}) == 1.0


def test_screen_left_of_heading_right_is_up():
    # SVG y grows downward, so "up" is negative y.
    assert left_normal((1.0, 0.0)) == (0.0, -1.0)
    assert left_normal((0.0, -1.0)) == (-1.0, 0.0)


def test_headings_are_the_direction_the_route_arrives_by(grid):
    centroids, _neighbours = grid
    headings = route_headings(L_ROUTE, centroids)
    assert headings[0] == (1.0, 0.0)  # the first takes its leaving direction
    assert headings[3] == (1.0, 0.0)  # arriving at the corner
    assert headings[4] == (0.0, -1.0)  # first electrode after the turn
    assert route_headings(["e0505"], centroids) == [(1.0, 0.0)]


def test_nearest_electrode_snaps_within_half_a_pitch(grid):
    centroids, _neighbours = grid
    assert nearest_electrode((5.3, 5.2), centroids, 1.0) == "e0505"
    assert nearest_electrode((5.5, 5.5), centroids, 1.0) is None  # between four
    assert nearest_electrode((-1.0, 5.0), centroids, 1.0) is None  # off the grid


def test_block_hangs_behind_its_anchor(grid):
    centroids, _neighbours = grid
    hung = block_footprint("e0505", (1.0, 0.0), 1, 1, 2, centroids, 1.0)
    assert sorted(hung) == ["e0404", "e0405", "e0406", "e0504", "e0505", "e0506"]
    # An anchor need not be an electrode: one cell past e0505 gives the
    # block centred on it.
    centred = block_cells((6.0, 5.0), (1.0, 0.0), 1, 1, 3, centroids, 1.0)
    assert sorted(centred) == sorted(
        f"e{x:02d}{y:02d}" for x in (4, 5, 6) for y in (4, 5, 6)
    )


def test_block_drops_positions_with_no_electrode(grid):
    centroids, _neighbours = grid
    # Heading right along the top row: the left lane is off the grid.
    ids = block_footprint("e0500", (1.0, 0.0), 1, 1, 1, centroids, 1.0)
    assert sorted(ids) == ["e0500", "e0501"]


def test_frames_of_a_direct_corner(grid):
    centroids, neighbours = grid
    phases = slug_phases(L_ROUTE, centroids, neighbours, 1, 1, 1, 0, pitch=1.0)
    frames = dict(render_phases(phases, L_ROUTE, centroids, 1.0))
    # Phases are numbered from 1: the corner (head 3) is the 4th phase
    # arriving and the 5th departing; head 4 is the 6th.
    assert frames["4 r"] == dedent(
        """
        . . . . . . .
        . . . . . . .
        . . . . # . .
        . . . . # . .
        . . . . # . .
        . . . . . . .
        """
    ).strip("\n")
    assert frames["6 u"] == dedent(
        """
        . . . . . . .
        . . . . . . .
        . . . # # # .
        . . . . . . .
        . . . . . . .
        . . . . . . .
        """
    ).strip("\n")


def test_parse_reads_back_what_render_wrote(grid):
    centroids, neighbours = grid
    phases = slug_phases(L_ROUTE, centroids, neighbours, 1, 1, 1, 0, pitch=1.0)
    cells = lattice_cells(centroids, 1.0)
    window = window_around({i for p in phases for i in p.ids} | set(L_ROUTE), cells)
    frames = dict(render_phases(phases, L_ROUTE, centroids, 1.0))
    assert parse(frames["6 u"], window) == {(4, 4), (5, 4), (6, 4)}


def test_frame_text_lays_frames_side_by_side():
    text = frame_text([("0 r", "# .\n. ."), ("1 r", ". #\n. .")])
    assert text == "0 r   1 r\n# .   . #\n. .   . ."


def test_shorthand_and_heading_letters():
    assert shorthand(1, 1, 2, (1.0, 0.0)) == "3x2 r"
    assert shorthand(0, 0, 2, (0.0, -1.0)) == "1x2 u"
    assert heading_letter((0.0, 1.0)) == "d"
    assert heading_letter((math.cos(0.7), math.sin(0.7))) == "?"
