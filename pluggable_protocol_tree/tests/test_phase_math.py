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
