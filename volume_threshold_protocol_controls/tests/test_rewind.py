"""Unit tests for the pure Rewind helpers (no Qt, executor, or DropBot)."""

from types import SimpleNamespace

from volume_threshold_protocol_controls.rewind import (
    rewind_target_phase, route_channels, step_route_phases,
)


# Electrode IDs "e0".."e3" map to channels 10..13.
E2C = {"e0": 10, "e1": 11, "e2": 12, "e3": 13}


def _row(routes=None, electrodes=None, **kw):
    return SimpleNamespace(
        routes=routes or [], electrodes=electrodes or [],
        trail_length=kw.get("trail_length", 1),
        trail_overlay=kw.get("trail_overlay", 0),
        soft_start=False, soft_end=False, repeat_duration=0.0,
        repeat_duration_controls=False, linear_repeats=False,
        route_repetitions=kw.get("route_repetitions", 1),
        duration_s=1.0,
    )


# --- rewind_target_phase (pure mapping) -----------------------------------

# trail_length=1: phase P actuates exactly route[P].
_PHASES_T1 = [{"e0"}, {"e1"}, {"e2"}, {"e3"}]


def test_single_on_route_channel_maps_to_its_phase():
    assert rewind_target_phase(_PHASES_T1, E2C, [12]) == 2


def test_off_route_channels_are_ignored():
    # 99 isn't on the route; 11 is -> phase 1.
    assert rewind_target_phase(_PHASES_T1, E2C, [99, 11]) == 1


def test_no_droplet_returns_none():
    assert rewind_target_phase(_PHASES_T1, E2C, []) is None


def test_off_route_only_returns_none():
    assert rewind_target_phase(_PHASES_T1, E2C, [99]) is None


def test_multiple_channels_rewind_to_furthest_leading_edge():
    # A droplet spanning electrodes lights up several channels; rewind to the
    # furthest one along the route (channel 13 -> phase 3), its leading edge.
    assert rewind_target_phase(_PHASES_T1, E2C, [11, 13]) == 3
    assert rewind_target_phase(_PHASES_T1, E2C, [10, 11, 12]) == 2


def test_leading_edge_with_trail_window():
    # With a trail window a channel spans two phases; rewind to where it FIRST
    # appears (its leading edge). e2 (=channel 12) is in phases 2 and 3, so the
    # leading-edge phase is 2.
    phases = [{"e0"}, {"e0", "e1"}, {"e1", "e2"}, {"e2", "e3"}]
    assert rewind_target_phase(phases, E2C, [12]) == 2


# --- route_channels -------------------------------------------------------

def test_route_channels_collects_all_route_electrodes():
    row = _row(routes=[["e0", "e1", "e2"]])
    assert route_channels(row, E2C) == [10, 11, 12]


def test_route_channels_drops_unmapped_electrodes():
    row = _row(routes=[["e0", "eX", "e3"]])
    assert route_channels(row, E2C) == [10, 13]


# --- step_route_phases (integration with iter_phases) ---------------------

def test_step_route_phases_one_pass_trail1():
    # A single 4-electrode route, trail_length=1 -> 4 phases, each one electrode.
    row = _row(routes=[["e0", "e1", "e2", "e3"]])
    phases = step_route_phases(row)
    assert len(phases) == 4
    assert phases[0] == {"e0"}
    assert phases[3] == {"e3"}
