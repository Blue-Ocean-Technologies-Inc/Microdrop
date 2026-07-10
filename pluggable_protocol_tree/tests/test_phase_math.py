"""Tests for services.phase_math.

Pure-function unit tests — no Traits, no Qt, no broker. phase_math is a
thin adapter over the centralized ``PathExecutionService``
(``microdrop_utils.route_execution``), so these tests pin the DELEGATION
contract (protocol-run phases exactly mirror the device viewer's
execution plan) plus the tree-local dynamic-loop helpers.
"""

from microdrop_utils.route_execution import PathExecutionService

from pluggable_protocol_tree.services.phase_math import (
    another_loop_fits, duration_loop_parts, effective_repetitions_for_duration,
    estimate_repeat_duration_s, idle_cell_index, iter_phases,
    loop_completion_fits, unit_cycle_len,
)


# --- iter_phases mirrors the centralized execution plan -------------------

def test_iter_phases_equals_central_execution_plan():
    """The delegation contract: phase sets are exactly the centralized
    plan's activated-electrode sets, in order."""
    kwargs = dict(trail_length=2, trail_overlay=1, soft_start=True,
                  soft_end=True, repeat_duration_s=0.0, linear_repeats=True,
                  n_repeats=2, step_duration_s=0.5)
    phases = list(iter_phases(["s"], [["a", "b", "c", "d"]], **kwargs))
    plan = PathExecutionService.calculate_execution_plan_from_params(
        duration=0.5, repetitions=2, repeat_duration=0.0,
        trail_length=2, trail_overlay=1, paths=[["a", "b", "c", "d"]],
        activated_electrodes=["s"], repeat_duration_mode=False,
        soft_start=True, soft_terminate=True, linear_repeats=True)
    assert phases == [set(item["activated_electrodes"]) for item in plan]
    assert phases   # non-empty


# --- iter_phases behavior ---

def test_iter_phases_no_routes_static_only():
    out = list(iter_phases(static_electrodes=["a", "b"], routes=[]))
    assert out == [{"a", "b"}]


def test_iter_phases_no_routes_no_static_one_empty_phase():
    out = list(iter_phases(static_electrodes=[], routes=[]))
    assert out == [set()]


def test_iter_phases_one_open_route_with_static():
    out = list(iter_phases(
        static_electrodes=["x"], routes=[["a", "b", "c"]],
        trail_length=1, trail_overlay=0,
    ))
    assert out == [{"a", "x"}, {"b", "x"}, {"c", "x"}]


def test_iter_phases_one_loop_route():
    """Loop closes with a return-to-start phase."""
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b", "c", "a"]],
        trail_length=1, trail_overlay=0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}]


def test_iter_phases_four_electrode_loop_yields_five_phases():
    """Loop with 4 unique electrodes, trail=1, one square at a time:
    A-->B-->C-->D-->A. Five phases total (4 forward + 1 return), same as
    the device viewer's route playback."""
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b", "c", "d", "a"]],
        trail_length=1, trail_overlay=0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"d"}, {"a"}]


def test_iter_phases_two_routes_zip_with_static():
    out = list(iter_phases(
        static_electrodes=["x"],
        routes=[["a", "b"], ["p", "q"]],
        trail_length=1, trail_overlay=0,
    ))
    assert out == [{"a", "p", "x"}, {"b", "q", "x"}]


def test_iter_phases_soft_start_prepends_ramp():
    """trail_length=3 + soft_start: {a},{a,b},{a,b,c},{b,c,d},{c,d,e}.
    Five phases for a 5-electrode line: 2 ramps + 3 windows."""
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b", "c", "d", "e"]],
        trail_length=3, trail_overlay=2, soft_start=True,
    ))
    assert len(out) == 5
    assert len(out[0]) == 1   # ramp
    assert len(out[1]) == 2   # ramp
    assert all(len(p) == 3 for p in out[2:])    # full windows


def test_iter_phases_soft_end_appends_ramp():
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b", "c", "d", "e"]],
        trail_length=3, trail_overlay=2, soft_end=True,
    ))
    assert len(out) == 5
    assert all(len(p) == 3 for p in out[:3])
    assert len(out[3]) == 2
    assert len(out[4]) == 1


def test_iter_phases_repeat_duration_caps_loop_cycles_with_idle():
    """Loop with cycle=3, step_duration=1, budget=6.5. Like the device
    viewer: effective reps = floor((6.5/1 - 1) / 3) = 1 cycle + return,
    then idle phases (hold at the loop start) pad the remaining budget:
    int(6.5 - 4) = 2 idle phases."""
    out = list(iter_phases(
        static_electrodes=[],
        routes=[["a", "b", "c", "a"]],
        trail_length=1, trail_overlay=0,
        repeat_duration_s=6.5, step_duration_s=1.0,
        n_repeats=999,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"a"}, {"a"}]


def test_iter_phases_linear_repeats_replays_open_route():
    """Linear-repeats true on an open route: replay n_repeats times."""
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b"]],
        trail_length=1, trail_overlay=0,
        linear_repeats=True, n_repeats=3,
    ))
    assert out == [{"a"}, {"b"}, {"a"}, {"b"}, {"a"}, {"b"}]


# --- loop closes (return-to-start) in BOTH count and duration mode ---


def test_loop_closes_with_return_phase_in_both_modes():
    """A loop that starts at electrode 'a' must also end at 'a' in both
    count and duration mode. 4-window cycle: count mode runs the asked
    reps + return; duration mode caps reps by budget and idles at the
    start for the balance — either way the last phase is back at 'a'."""
    route = ["a", "b", "c", "d", "a"]   # loop, effective len 4, trail 1
    count_mode = list(iter_phases(
        [], [route], trail_length=1, trail_overlay=0,
        n_repeats=2, repeat_duration_s=0.0, step_duration_s=1.0))
    dur_mode = list(iter_phases(
        [], [route], trail_length=1, trail_overlay=0,
        n_repeats=2, repeat_duration_s=8.0, step_duration_s=1.0))
    # Count: 2 cycles * 4 windows + 1 return-to-start.
    assert len(count_mode) == 2 * 4 + 1
    # Duration: floor((8-1)/4) = 1 cycle + return = 5 active, + 3 idle.
    assert len(dur_mode) == 8
    # The loop closes: last phase == first phase (back at the start, 'a').
    assert count_mode[-1] == count_mode[0] == {"a"}
    assert dur_mode[-1] == dur_mode[0] == {"a"}


# --- effective_repetitions_for_duration / estimate_repeat_duration_s ---

def test_effective_repetitions_matches_central_formula():
    # cycle 3, dwell 1, budget 10 --> floor((10-1)/3) = 3 reps.
    reps = effective_repetitions_for_duration(
        routes=[["a", "b", "c", "a"]], trail_length=1, trail_overlay=0,
        step_duration_s=1.0, repeat_duration_s=10.0)
    assert reps == 3


def test_effective_repetitions_no_loops_or_budget_is_one():
    assert effective_repetitions_for_duration(
        routes=[["a", "b"]], repeat_duration_s=10.0) == 1
    assert effective_repetitions_for_duration(
        routes=[["a", "b", "a"]], repeat_duration_s=0.0) == 1


def test_estimate_repeat_duration_counts_phases():
    # Loop cycle 3 + return = 4 phases * 0.5 s.
    est = estimate_repeat_duration_s(
        routes=[["a", "b", "c", "a"]], trail_length=1, trail_overlay=0,
        n_repeats=1, step_duration_s=0.5)
    assert est == 4 * 0.5


def test_estimate_repeat_duration_no_routes_is_zero():
    assert estimate_repeat_duration_s(routes=[]) == 0.0


# --- duration_loop_parts ---

def test_duration_loop_parts_loop_route_basic():
    """One loop route, trail 1: unit cycle is the two windows; the return
    phase closes back to the first window; no soft-start ramp."""
    ramp, cycle, ret = duration_loop_parts(
        static_electrodes=[], routes=[["a", "b", "a"]],
        trail_length=1, trail_overlay=0, soft_start=False)
    assert cycle == [{"a"}, {"b"}]
    assert ret == {"a"}
    assert ramp == []


def test_duration_loop_parts_soft_start_statics_never_ramp():
    """Device-viewer soft-start semantics: static electrodes are always
    fully on (they never ramp), and a 1-electrode trail window needs no
    ramp at all."""
    ramp, cycle, ret = duration_loop_parts(
        static_electrodes=["s1", "s2"], routes=[["a", "b", "a"]],
        trail_length=1, trail_overlay=0, soft_start=True)
    assert cycle[0] == {"s1", "s2", "a"}         # static unioned into window
    assert ramp == []                            # nothing to ramp
    assert ret == cycle[0]


def test_duration_loop_parts_soft_start_ramps_in_path_order():
    """Device-viewer soft-start semantics: the ramp grows the first trail
    window in PATH order from the route start (with statics fully on),
    not in sorted-ID order."""
    ramp, cycle, _ret = duration_loop_parts(
        static_electrodes=["s"], routes=[["b", "a", "c", "b"]],
        trail_length=2, trail_overlay=1, soft_start=True)
    assert cycle[0] == {"s", "b", "a"}           # first window: b, a
    # Ramp starts from the ROUTE's first electrode ('b'), not sorted 'a'.
    assert ramp == [{"s", "b"}]


def test_duration_loop_parts_no_routes_static_only():
    """No routes: the unit cycle is the single static phase and there is
    no return phase (nothing to close)."""
    ramp, cycle, ret = duration_loop_parts(
        static_electrodes=["x"], routes=[], trail_length=1,
        trail_overlay=0, soft_start=True)
    assert cycle == [{"x"}]
    assert ret is None
    assert ramp == []


# --- unit_cycle_len ---

def test_unit_cycle_len_loop_route():
    # a genuine loop route (first == last) a-b-c-d-a: 4 unique nodes ->
    # 4 windows in the unit cycle (the return phase is not part of it).
    n = unit_cycle_len([], [["a", "b", "c", "d", "a"]], trail_length=1, trail_overlay=0)
    assert n == 4


def test_unit_cycle_len_static_only_is_one():
    assert unit_cycle_len(["a", "b"], []) == 1


# --- another_loop_fits ---

def test_another_loop_fits_boundary():
    # cycle_len 4 * dwell 2.0 = 8.0 worst loop; budget 20
    assert another_loop_fits(raw_elapsed=12.0, cycle_len=4, phase_dwell=2.0, budget=20.0) is True   # 12+8=20 exact fit
    assert another_loop_fits(raw_elapsed=12.001, cycle_len=4, phase_dwell=2.0, budget=20.0) is False
    assert another_loop_fits(raw_elapsed=0.0, cycle_len=0, phase_dwell=2.0, budget=20.0) is False    # no phases -> never


# --- loop_completion_fits ---

def test_loop_completion_fits_from_mid_cycle():
    # from phase k=1 of a 4-phase loop, 3 phases remain * 2.0 = 6.0
    assert loop_completion_fits(raw_elapsed=14.0, phase_in_cycle=1, cycle_len=4, phase_dwell=2.0, budget=20.0) is True  # 14+6=20
    assert loop_completion_fits(raw_elapsed=14.5, phase_in_cycle=1, cycle_len=4, phase_dwell=2.0, budget=20.0) is False


# --- idle_cell_index ---

def test_idle_cell_index_is_cycle_len():
    assert idle_cell_index(4) == 4
