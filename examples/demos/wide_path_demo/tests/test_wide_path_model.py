# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The traits models react to their inputs — headless, no Qt."""

# Third-party imports.
import pytest
from shapely.geometry import box

# Microdrop utils imports.
from microdrop_utils.wide_path_geometry import IN_OUT, LEFT_RIGHT

# Local imports.
from ..models import WidePathDemoModel
from ..wide_path import WidePathModel


@pytest.fixture
def device():
    """A 6x6 grid of unit squares: (polygons, neighbours)."""
    n = 6
    polygons = {
        f"e{x}{y}": box(x - 0.5, y - 0.5, x + 0.5, y + 0.5)
        for x in range(n)
        for y in range(n)
    }
    neighbours = {
        f"e{x}{y}": [
            f"e{a}{b}"
            for a, b in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
            if 0 <= a < n and 0 <= b < n
        ]
        for x in range(n)
        for y in range(n)
    }
    return polygons, neighbours


def test_defaults_are_a_locked_block_in_the_in_out_frame(device):
    polygons, neighbours = device
    path = WidePathModel(electrode_polygons=polygons, electrode_neighbours=neighbours)
    assert path.rotation_lock and path.lane_frame == IN_OUT


def test_path_recomputes_phases_when_route_or_shape_changes(device):
    polygons, neighbours = device
    path = WidePathModel(
        electrode_polygons=polygons,
        electrode_neighbours=neighbours,
        rotation_lock=False,
        lane_frame=LEFT_RIGHT,
    )
    assert path.pitch == 1.0 and path.phases == []
    for electrode_id in ("e13", "e23", "e33", "e32"):
        assert path.pick(electrode_id)
    # A 3x1 bar: the corner electrode (head 2) shows both orientations.
    assert [phase.head for phase in path.phases] == [0, 1, 2, 2, 3]
    assert len(path.phases[0].ids) == 3  # 3x1 by default
    path.left = 2
    assert len(path.phases[0].ids) == 4
    path.trail_length = 2  # overlay 0: the block hops two electrodes at a time
    assert [phase.head for phase in path.phases] == [1, 3]
    path.trail_overlay = 1
    assert [phase.head for phase in path.phases] == [1, 2, 3]
    path.soft_start = True  # one ramp phase before the first full block
    assert [phase.head for phase in path.phases] == [1, 1, 2, 3]
    assert "4x2" in path.summary and len(path.footprint_ids) > 0


def test_summary_and_footprint_are_ready_when_phases_fires(device):
    """Observers react to ``phases``; the traits derived from it must not
    lag one update behind (they are assigned first)."""
    polygons, neighbours = device
    path = WidePathModel(electrode_polygons=polygons, electrode_neighbours=neighbours)
    seen = []
    path.observe(
        lambda event: seen.append((path.summary, len(path.footprint_ids))), "phases"
    )
    for electrode_id in ("e13", "e23", "e33"):
        path.pick(electrode_id)
    path.trail_length = 2
    assert seen[-1] == (path.summary, len(path.footprint_ids))
    assert "3x2" in seen[-1][0] and "phases 2" in seen[-1][0]


def test_pick_refuses_non_neighbours_and_allows_revisits(device):
    polygons, neighbours = device
    path = WidePathModel(electrode_polygons=polygons, electrode_neighbours=neighbours)
    notes = []
    path.observe(lambda event: notes.append(event.new), "note")
    path.pick("e13")
    assert not path.pick("e33")  # two away
    assert notes == ["Pick an electrode next to the previous one"]
    assert not path.pick("e13")  # the last electrode itself: a no-op
    assert path.pick("e23") and path.pick("e13")  # back-and-forth is a route
    assert path.route_ids == ["e13", "e23", "e13"]
    path.undo()
    assert path.route_ids == ["e13", "e23"]


def test_demo_model_tracks_the_selected_path(device):
    polygons, neighbours = device
    model = WidePathDemoModel(
        electrode_polygons=polygons, electrode_neighbours=neighbours
    )
    assert model.selected is None and model.phase_label == "no phases"
    path = model.add_path("first")
    assert model.selected is path and model.editing is path
    path.rotation_lock, path.lane_frame = False, LEFT_RIGHT
    for electrode_id in ("e13", "e23", "e33", "e32", "e31"):
        path.pick(electrode_id)
    assert model.phase_titles == ["1 r", "2 r", "3 r", "4 u", "5 u", "6 u"]
    assert model.max_step == 5 and model.path_names == ["first (6 phases)"]
    model.step = 3
    assert model.phase_label == "4 / 6 · 3x1 u"
    assert model.frame.startswith("phase 4 u   3x1 u\n")
    # Shortening the route clamps the step back into range.
    path.undo()
    path.undo()
    assert model.max_step == 2 and model.step == 2
    # Refusals reach the status line; the next route change clears it.
    path.pick("e55")
    assert model.status == "Pick an electrode next to the previous one"
    path.pick("e34")
    assert model.status == ""
    # Deselecting leaves the sidebar bound to a spare path.
    model.selected_index = -1
    assert model.selected is None and model.editing is not path
    assert model.phase_titles == [] and model.max_step == 0


def test_closing_the_route_makes_a_loop_that_repeats(device):
    polygons, neighbours = device
    path = WidePathModel(electrode_polygons=polygons, electrode_neighbours=neighbours)
    for electrode_id in ("e11", "e21", "e22", "e12", "e11"):
        assert path.pick(electrode_id)
    assert path.loop and path.cycle_length == 4
    once = len(path.phases)
    assert path.unrolled_route == ["e11", "e21", "e22", "e12", "e11"]
    path.repetitions = 2
    assert len(path.unrolled_route) == 9 and len(path.phases) > once
    assert "loop ×2" in path.summary
    path.undo()
    assert (
        not path.loop
        and path.cycle_length == 0
        and path.unrolled_route == path.route_ids
    )


def test_invert_reverses_the_route_and_re_decides_the_sides(device):
    polygons, neighbours = device
    path = WidePathModel(
        electrode_polygons=polygons, electrode_neighbours=neighbours, left=0, right=1
    )
    for electrode_id in ("e13", "e23", "e33", "e32"):
        path.pick(electrode_id)
    forward = [sorted(phase.ids) for phase in path.phases]
    path.invert()
    assert path.route_ids == ["e32", "e33", "e23", "e13"]
    # Same electrodes, opposite direction: the outside lane swaps sides, so
    # the phases are not simply the forward ones played backwards.
    assert [sorted(phase.ids) for phase in path.phases] != forward[::-1]
    assert path.phases[-1].head == 3


def test_merge_joins_paths_at_a_shared_endpoint(device):
    polygons, neighbours = device
    model = WidePathDemoModel(
        electrode_polygons=polygons, electrode_neighbours=neighbours
    )
    first, second = model.add_path("first"), model.add_path("second")
    for electrode_id in ("e11", "e21", "e31"):
        first.pick(electrode_id)
    for electrode_id in ("e31", "e32", "e33"):
        second.pick(electrode_id)
    # The selected path must have the other one below it.
    model.selected_index = 1
    model.merge_selected_with_next()
    assert model.status == "Select a path with another one below it to merge"
    model.selected_index = 0
    model.merge_selected_with_next()
    assert first.route_ids == ["e11", "e21", "e31", "e32", "e33"]
    assert model.paths == [first] and model.selected is first
    # No shared endpoint: refused, nothing changes.
    third = model.add_path("third")
    third.pick("e55")
    model.selected_index = 0
    model.merge_selected_with_next()
    assert model.status == "Paths must share an endpoint to merge"
    assert len(model.paths) == 2
