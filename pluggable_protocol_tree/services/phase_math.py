"""Pure-function phase-generation helpers for the RoutesHandler.

A "phase" is one snapshot in time of which electrodes are actuated.
Each step of a protocol expands to a sequence of phases, each yielded
by iter_phases() and consumed (publish + wait_for ack) by the
RoutesHandler.

Composed of small one-job helpers so each can be tested in isolation:

  _is_loop_route       — first == last, len >= 2
  _route_windows       — sliding windows over one route (open or loop)
  _route_with_repeats  — wrap windows in linear-repeats / loop-cycles /
                         repeat_duration_s budget logic   (Task 3)
  _zip_with_static     — at each tick, union static + each route's
                         current window                          (Task 4)
  _ramp_up / _ramp_down — soft-start / soft-end ramp transformers  (Task 5)
  iter_phases          — public composition                        (Task 5)

No Traits, no Qt, no broker — testable as plain Python.
"""

from typing import Iterator, List, Set


def _is_loop_route(route: List[str]) -> bool:
    """A loop route is one where first == last (and there are at least
    two electrodes — a single-element route can't be a loop)."""
    return len(route) >= 2 and route[0] == route[-1]


def _route_windows(route: List[str], trail_length: int,
                   trail_overlay: int) -> Iterator[Set[str]]:
    """Sliding-window iterator over a single route.

    Open route: yields ceil((len - trail_length) / step + 1) windows,
    each a set of trail_length consecutive electrodes (or fewer at the
    tail). Trail_length > len(route) → one window of the whole route.

    Loop route (first == last): drops the duplicated last electrode,
    yields one full cycle of windows that wrap around the effective
    path. Subsequent cycles, if any, are the caller's job
    (_route_with_repeats handles loop reps).

    step_size = max(1, trail_length - trail_overlay) — clamped to 1
    so progress is guaranteed even with overlay >= length.
    """
    if not route:
        return
    if _is_loop_route(route):
        effective = route[:-1]
        n = len(effective)
        step = max(1, trail_length - trail_overlay)
        size = min(trail_length, n)
        pos = 0
        emitted = 0
        while emitted == 0 or pos % n != 0:
            yield {effective[(pos + i) % n] for i in range(size)}
            pos += step
            emitted += 1
            # Safety: never loop forever.
            if emitted > n:
                return
    else:
        n = len(route)
        if trail_length >= n:
            yield set(route)
            return
        step = max(1, trail_length - trail_overlay)
        pos = 0
        while pos < n:
            window = {route[pos + i] for i in range(trail_length)
                      if pos + i < n}
            yield window
            if pos + trail_length >= n:
                return
            pos += step


def _route_with_repeats(
    route: List[str],
    trail_length: int,
    trail_overlay: int,
    *,
    linear_repeats: bool = False,
    n_repeats: int = 1,
    repeat_duration_s: float = 0.0,
    step_duration_s: float = 1.0,
) -> Iterator[Set[str]]:
    """Wraps _route_windows with repeat-count + duration-budget logic.

    Open route + linear_repeats=False → one pass of _route_windows.
    Open route + linear_repeats=True  → n_repeats passes (the row's
                                        `repetitions` column).
    Loop route → n_repeats cycles UNLESS repeat_duration_s > 0, in
                 which case cycles = max(1, floor(repeat_duration_s /
                 (cycle_phases * step_duration_s))). The minimum of 1
                 guarantees at least one cycle even on tiny budgets.

    Empty route yields nothing.
    """
    if not route:
        return
    cycle = list(_route_windows(route, trail_length, trail_overlay))
    if not cycle:
        return

    is_loop = _is_loop_route(route)
    if is_loop:
        if repeat_duration_s > 0 and step_duration_s > 0:
            cycle_phases = len(cycle)
            cycles = max(1, int(repeat_duration_s
                                / (cycle_phases * step_duration_s)))
        else:
            cycles = max(1, int(n_repeats))
        for _ in range(cycles):
            yield from cycle
    else:
        passes = max(1, int(n_repeats)) if linear_repeats else 1
        for _ in range(passes):
            yield from cycle
