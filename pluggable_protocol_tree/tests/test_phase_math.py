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

from pluggable_protocol_tree.services.phase_math import _route_with_repeats


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
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}]


def test_repeats_loop_route_n_repeats():
    """Loop route + n_repeats=2 → 2 full cycles."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, n_repeats=2,
        repeat_duration_s=0.0, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"b"}, {"c"}]


def test_repeats_loop_with_repeat_duration_caps_cycles():
    """Loop route, repeat_duration_s=2.5, step_duration_s=1.0,
    cycle_phases=3 → 2.5/3 = 0.83, floor → 0 cycles. But minimum is 1
    cycle (always at least one pass). Test: 1 cycle yielded."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, n_repeats=999,   # would otherwise loop 999×
        repeat_duration_s=2.5, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}]   # 1 cycle


def test_repeats_loop_with_repeat_duration_fits_two_cycles():
    """Loop route, repeat_duration_s=6.5, step_duration_s=1.0,
    cycle_phases=3 → 6.5/3 = 2.17, floor → 2 cycles."""
    out = list(_route_with_repeats(
        ["a", "b", "c", "a"], trail_length=1, trail_overlay=0,
        linear_repeats=False, n_repeats=999,
        repeat_duration_s=6.5, step_duration_s=1.0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"b"}, {"c"}]   # 2 cycles


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
