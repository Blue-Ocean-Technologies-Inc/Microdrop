"""Tests for services.phase_math.

Pure-function unit tests — no Traits, no Qt, no broker. Each helper
gets its own section. Sections grow as later tasks land more helpers.
"""

from pluggable_protocol_tree.services.phase_math import (
    _is_loop_route, _route_windows,
)


# --- _is_loop_route ---

def test_is_loop_route_first_equals_last():
    assert _is_loop_route(["a", "b", "c", "a"]) is True


def test_is_loop_route_open_path():
    assert _is_loop_route(["a", "b", "c"]) is False


def test_is_loop_route_single_element_not_a_loop():
    assert _is_loop_route(["a"]) is False


def test_is_loop_route_empty_not_a_loop():
    assert _is_loop_route([]) is False


# --- _route_windows ---

def test_windows_open_route_trail_length_1_no_overlap():
    """trail_length=1, trail_overlay=0: window = single electrode at
    each position, advancing by 1 each step (step = max(1, 1-0))."""
    out = list(_route_windows(["a", "b", "c"], trail_length=1, trail_overlay=0))
    assert out == [{"a"}, {"b"}, {"c"}]


def test_windows_open_route_trail_length_2_overlap_1():
    """trail_length=2, trail_overlay=1: step = 1, window slides by 1."""
    out = list(_route_windows(["a", "b", "c", "d"], trail_length=2, trail_overlay=1))
    assert out == [{"a", "b"}, {"b", "c"}, {"c", "d"}]


def test_windows_trail_length_exceeds_route():
    """trail_length larger than route: one window of the whole route."""
    out = list(_route_windows(["a", "b"], trail_length=5, trail_overlay=0))
    assert out == [{"a", "b"}]


def test_windows_overlap_ge_length_clamps_step_to_1():
    """trail_overlay >= trail_length: step clamped to 1 (always advance)."""
    out = list(_route_windows(["a", "b", "c"], trail_length=2, trail_overlay=10))
    assert out == [{"a", "b"}, {"b", "c"}]


def test_windows_loop_route_one_cycle():
    """Loop route: drop the duplicated last electrode, walk one cycle
    of windows that wrap around."""
    out = list(_route_windows(["a", "b", "c", "a"], trail_length=1, trail_overlay=0))
    assert out == [{"a"}, {"b"}, {"c"}]


def test_windows_loop_route_trail_2_wraps():
    """Loop route with trail_length=2 wraps the window across the cycle."""
    out = list(_route_windows(["a", "b", "c", "a"], trail_length=2, trail_overlay=1))
    # Effective path is ['a', 'b', 'c'], step=1, windows wrap mod 3:
    # pos 0: {a, b}; pos 1: {b, c}; pos 2: {c, a}
    assert out == [{"a", "b"}, {"b", "c"}, {"c", "a"}]


def test_windows_empty_route_yields_nothing():
    out = list(_route_windows([], trail_length=1, trail_overlay=0))
    assert out == []


# --- _route_with_repeats ---

from pluggable_protocol_tree.services.phase_math import (
    _route_with_repeats, pad_seconds_for_duration,
)


def test_repeats_open_route_no_linear_repeats_one_pass():
    """Open route, linear_repeats=False: same as one _route_windows pass."""
    out = list(_route_with_repeats(
        ["a", "b", "c"], trail_length=1, trail_overlay=0,
        linear_repeats=False, repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}]


def test_repeats_open_route_linear_repeats_replays_n_times():
    """Open route, linear_repeats=True: replay the windows N=2 times."""
    out = list(_route_with_repeats(
        ["a", "b"], trail_length=1, trail_overlay=0,
        linear_repeats=True, n_repeats=2,
        repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"a"}, {"b"}]


def test_repeats_loop_route_default_one_cycle():
    """One cycle of a 3-electrode loop yields 4 phases — the three
    cycle windows plus a return-to-start phase (matches the legacy
    device-viewer route executor)."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}]


def test_repeats_loop_route_n_repeats():
    """Loop route + n_repeats=2 → 2 full cycles + 1 return phase."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, n_repeats=2,
        repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"b"}, {"c"}, {"a"}]


def test_repeats_loop_with_repeat_duration_caps_cycles():
    """Loop route, repeat_duration_s=2.5, step_duration_s=1.0,
    cycle_phases=3 → 2.5/3 = 0.83, floor → 0 cycles. But minimum is 1
    cycle. Duration mode: 1 cycle, NO return phase (RoutesHandler holds
    the last phase for leftover time instead)."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, n_repeats=999,   # would otherwise loop 999×
        repeat_duration_s=2.5, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}]   # 1 cycle, no return


def test_repeats_loop_with_repeat_duration_fits_two_cycles():
    """Loop route, repeat_duration_s=6.5, step_duration_s=1.0,
    cycle_phases=3 → 6.5/3 = 2.17, floor → 2 cycles. Duration mode:
    no return phase (RoutesHandler holds the last phase for leftover)."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, n_repeats=999,
        repeat_duration_s=6.5, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"b"}, {"c"}]   # 2 cycles, no return


def test_repeats_empty_route_yields_nothing():
    out = list(_route_with_repeats(
        [], trail_length=1, trail_overlay=0,
        linear_repeats=False, repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == []


# --- _zip_with_static ---

from pluggable_protocol_tree.services.phase_math import _zip_with_static


def test_zip_no_routes_yields_static_once_then_stops():
    out = list(_zip_with_static([], static={"x", "y"}))
    assert out == [{"x", "y"}]


def test_zip_no_routes_no_static_yields_one_empty_phase():
    """Edge case: still emit one (empty) phase to keep the executor
    semantics that 'every step has at least one phase'."""
    out = list(_zip_with_static([], static=set()))
    assert out == [set()]


def test_zip_one_route_unions_static_each_phase():
    route_iter = iter([{"a"}, {"b"}, {"c"}])
    out = list(_zip_with_static([route_iter], static={"x"}))
    assert out == [{"a", "x"}, {"b", "x"}, {"c", "x"}]


def test_zip_two_routes_same_length_union_each_phase():
    r1 = iter([{"a"}, {"b"}])
    r2 = iter([{"p"}, {"q"}])
    out = list(_zip_with_static([r1, r2], static=set()))
    assert out == [{"a", "p"}, {"b", "q"}]


def test_zip_routes_of_different_length_shorter_holds_at_last():
    """The shorter route holds at its last window once exhausted, so
    the longer route's remaining windows still get emitted."""
    r1 = iter([{"a"}, {"b"}, {"c"}])
    r2 = iter([{"p"}])
    out = list(_zip_with_static([r1, r2], static=set()))
    assert out == [{"a", "p"}, {"b", "p"}, {"c", "p"}]


def test_zip_stops_when_all_routes_exhausted():
    """An empty-from-the-start route iterator contributes nothing; the
    other route's iterator drives the output."""
    r1 = iter([{"a"}, {"b"}])
    r2 = iter([])
    out = list(_zip_with_static([r1, r2], static={"x"}))
    assert out == [{"a", "x"}, {"b", "x"}]


# --- _ramp_up / _ramp_down ---

from pluggable_protocol_tree.services.phase_math import (
    _ramp_up, _ramp_down,
)


def test_ramp_up_single_electrode_first_phase_is_noop():
    """First phase has 1 electrode → nothing to ramp."""
    out = list(_ramp_up(iter([{"a"}, {"b"}])))
    assert out == [{"a"}, {"b"}]


def test_ramp_up_three_electrode_first_phase_prepends_two():
    """First phase {a,b,c} → prepend {a}, {a,b} so the trail grows."""
    out = list(_ramp_up(iter([{"a", "b", "c"}, {"d", "e", "f"}])))
    assert len(out) == 4
    assert len(out[0]) == 1 and out[0].issubset({"a", "b", "c"})
    assert len(out[1]) == 2 and out[1].issubset({"a", "b", "c"})
    assert out[2] == {"a", "b", "c"}
    assert out[3] == {"d", "e", "f"}


def test_ramp_up_empty_input_yields_empty():
    out = list(_ramp_up(iter([])))
    assert out == []


def test_ramp_down_single_electrode_last_phase_is_noop():
    out = list(_ramp_down(iter([{"a"}, {"b"}])))
    assert out == [{"a"}, {"b"}]


def test_ramp_down_three_electrode_last_phase_appends_two():
    """Last phase {x,y,z} → append two ramp-down phases shrinking by 1."""
    out = list(_ramp_down(iter([{"a"}, {"x", "y", "z"}])))
    assert len(out) == 4
    assert out[0] == {"a"}
    assert out[1] == {"x", "y", "z"}
    assert len(out[2]) == 2 and out[2].issubset({"x", "y", "z"})
    assert len(out[3]) == 1 and out[3].issubset({"x", "y", "z"})


# --- iter_phases (public composition) ---

from pluggable_protocol_tree.services.phase_math import iter_phases


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
    A→B→C→D→A. Five phases total (4 forward + 1 return). Mirrors the
    legacy device-viewer loop execution that the user expects."""
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


def test_iter_phases_repeat_duration_caps_loop_cycles():
    """Loop with cycle=3, step_duration=1, budget=6.5 → 2 cycles.
    Duration mode drops the trailing return phase; the RoutesHandler
    holds the last phase for the leftover seconds."""
    out = list(iter_phases(
        static_electrodes=[],
        routes=[["a", "b", "c", "a"]],
        trail_length=1, trail_overlay=0,
        repeat_duration_s=6.5, step_duration_s=1.0,
        n_repeats=999,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"b"}, {"c"}]   # 2 cycles, no return


def test_iter_phases_linear_repeats_replays_open_route():
    """Linear-repeats true on an open route: replay n_repeats times."""
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b"]],
        trail_length=1, trail_overlay=0,
        linear_repeats=True, n_repeats=3,
    ))
    assert out == [{"a"}, {"b"}, {"a"}, {"b"}, {"a"}, {"b"}]


# --- duration-mode return-phase drop + pad_seconds_for_duration ---


def test_duration_mode_omits_trailing_return_phase():
    """Loop route, 4-window cycle, T fits exactly 2 cycles at dwell=1.0.
    Count mode yields N*C + 1 (return) phases; duration mode yields N*C
    (no return) so emitted dwell == cycles*cycle_time exactly."""
    route = ["a", "b", "c", "d", "a"]   # loop, effective len 4, trail 1 => 4 windows
    count_mode = list(_route_with_repeats(
        route, trail_length=1, trail_overlay=0,
        n_repeats=2, repeat_duration_s=0.0, step_duration_s=1.0))
    dur_mode = list(_route_with_repeats(
        route, trail_length=1, trail_overlay=0,
        n_repeats=2, repeat_duration_s=8.0, step_duration_s=1.0))
    assert len(count_mode) == 2 * 4 + 1     # cycles + return phase
    assert len(dur_mode) == 2 * 4           # no return phase


def test_pad_seconds_exact_leftover():
    """T=10s, cycle=4 windows @1.0s => cycle_time=4. floor(10/4)=2 cycles
    => 8s used, pad = 2.0s held on the last phase."""
    routes = [["a", "b", "c", "d", "a"]]
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=1.0)
    assert pad == 2.0


def test_pad_seconds_zero_when_t_below_one_cycle():
    """T < cycle_time => max(1, floor)=1 cycle (overshoot), pad clamps to 0."""
    routes = [["a", "b", "c", "d", "a"]]
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=2.0, step_duration_s=1.0)
    assert pad == 0.0


def test_pad_seconds_zero_without_loop_routes():
    routes = [["a", "b", "c"]]   # open route, no loop
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=1.0)
    assert pad == 0.0


def test_pad_seconds_zero_when_step_duration_nonpositive():
    routes = [["a", "b", "c", "d", "a"]]
    assert pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=0.0) == 0.0


def test_pad_seconds_zero_on_exact_fit():
    """T=8, cycle=4 windows @1.0s => 2 full cycles fit exactly, pad 0
    (legitimate exact fit, distinct from the sub-cycle overshoot case)."""
    routes = [["a", "b", "c", "d", "a"]]
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=8.0, step_duration_s=1.0)
    assert pad == 0.0


def test_pad_seconds_multiple_loop_routes_uses_longest_running():
    """Two loop routes: cycle lengths 3 and 4, T=10, step=1.
    len-3 route runs floor(10/3)=3 cycles = 9 phases (9s);
    len-4 route runs floor(10/4)=2 cycles = 8 phases (8s).
    _zip runs until the longest-running (the len-3 route, 9s), so
    pad = 10 - 9 = 1.0 held on the last phase."""
    routes = [["a", "b", "c", "a"], ["e", "f", "g", "h", "e"]]
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=1.0)
    assert pad == 1.0
