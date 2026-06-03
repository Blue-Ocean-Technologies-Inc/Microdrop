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
                                        `route_repetitions` column).
    Loop route → ``cycles`` full cycles plus one return-to-start phase at
                 the very end (mirrors the legacy device-viewer route
                 executor: N cycles of a C-phase loop yields N*C + 1
                 phases, the final one being the window at position 0 so a
                 loop that starts at electrode X also ends at X). The
                 return phase is emitted in BOTH modes; only ``cycles``
                 differs: count mode uses ``max(1, n_repeats)``; duration
                 mode uses ``max(1, floor(repeat_duration_s /
                 (cycle_phases * step_duration_s)))``. The minimum of 1
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
        # Count vs duration mode differ ONLY in how many full cycles run;
        # both close the loop with a final return-to-start phase so a loop
        # that begins at electrode X also ends at X. Timing stays exact in
        # duration mode because the RoutesHandler's hold-pad is computed
        # from the actual emitted phase count (len(phases) * per_phase_dwell),
        # which already includes this return phase.
        if repeat_duration_s > 0 and step_duration_s > 0:
            cycle_phases = len(cycle)
            cycles = max(1, int(repeat_duration_s
                                / (cycle_phases * step_duration_s)))
        else:
            cycles = max(1, int(n_repeats))
        for _ in range(cycles):
            yield from cycle
        yield cycle[0]   # return-to-start so the loop visibly closes
    else:
        passes = max(1, int(n_repeats)) if linear_repeats else 1
        for _ in range(passes):
            yield from cycle


def duration_loop_parts(
    static_electrodes: List[str],
    routes: List[List[str]],
    *,
    trail_length: int = 1,
    trail_overlay: int = 0,
    soft_start: bool = False,
):
    """Decompose a step into the pieces the RoutesHandler needs to drive a
    *dynamic* duration-mode loop under volume threshold:

        (ramp_up_phases, unit_cycle, return_phase)

    ``unit_cycle`` is ONE pass of the zipped route windows + static set
    (the repeatable unit). ``ramp_up_phases`` is the soft-start ramp toward
    ``unit_cycle[0]`` (empty when soft_start is False or the first phase has
    <= 1 electrode). ``return_phase`` is ``unit_cycle[0]`` (to close the loop
    back to its origin) or None when there are no routes.

    There is deliberately NO soft-end ramp: volume threshold reaching its
    target guarantees the droplet's position, so the gentle-release ramp is
    dropped. See the design spec.
    """
    static = set(static_electrodes or [])
    if not routes:
        # Static-only step: the single static set is the repeatable unit;
        # nothing to "return to", so no closing phase.
        return [], [set(static)], None
    per_route = [_route_windows(r, trail_length, trail_overlay)
                 for r in routes]
    unit_cycle = list(_zip_with_static(per_route, static))
    if not unit_cycle:
        return [], [set(static)], None
    ramp_up: List[Set[str]] = []
    first = unit_cycle[0]
    if soft_start and len(first) > 1:
        ordered = sorted(first)
        ramp_up = [set(ordered[:size]) for size in range(1, len(first))]
    return ramp_up, unit_cycle, unit_cycle[0]


def _ramp_up(phases: Iterator[Set[str]]) -> Iterator[Set[str]]:
    """Prepend ramp phases that grow from 1 electrode to the size of
    the first phase. K=1 first phase → no-op. K=3 first phase {a,b,c}
    → yields {a}, {a,b} BEFORE the original {a,b,c}.

    Element ordering within a set is non-deterministic; the ramp picks
    elements in `sorted()` order so the choice is at least stable
    across runs."""
    try:
        first = next(phases)
    except StopIteration:
        return
    if len(first) > 1:
        ordered = sorted(first)
        for size in range(1, len(first)):
            yield set(ordered[:size])
    yield first
    yield from phases


def _ramp_down(phases: Iterator[Set[str]]) -> Iterator[Set[str]]:
    """Append ramp phases that shrink from the last phase's size down
    to 1. Mirror of _ramp_up — same sorted-element ordering for
    stability."""
    last = None
    for p in phases:
        if last is not None:
            yield last
        last = p
    if last is None:
        return
    yield last
    if len(last) > 1:
        ordered = sorted(last)
        for size in range(len(last) - 1, 0, -1):
            yield set(ordered[-size:])


def estimate_repeat_duration_s(
    *,
    routes: List[List[str]],
    trail_length: int = 1,
    trail_overlay: int = 0,
    n_repeats: int = 1,
    step_duration_s: float = 1.0,
    linear_repeats: bool = False,
    soft_start: bool = False,
    soft_end: bool = False,
) -> float:
    """Total wall-clock seconds the step would take in Route Reps-
    controlled mode (i.e. with ``repeat_duration_s = 0`` so the loop
    runs exactly ``n_repeats`` cycles + 1 return phase). Equivalent to
    ``len(iter_phases(...)) * step_duration_s`` — handy for the
    "auto-estimate" the Route Reps Dur column shows when the user hasn't
    taken manual control of the knob yet.

    Returns 0.0 when there are no routes (nothing to time-budget).
    """
    if not routes:
        return 0.0
    phases = list(iter_phases(
        static_electrodes=[],
        routes=routes,
        trail_length=trail_length,
        trail_overlay=trail_overlay,
        soft_start=soft_start,
        soft_end=soft_end,
        repeat_duration_s=0.0,
        linear_repeats=linear_repeats,
        n_repeats=n_repeats,
        step_duration_s=step_duration_s,
    ))
    return len(phases) * float(step_duration_s)


def effective_repetitions_for_duration(
    *,
    routes: List[List[str]],
    trail_length: int = 1,
    trail_overlay: int = 0,
    step_duration_s: float = 1.0,
    repeat_duration_s: float = 0.0,
) -> int:
    """How many full loop cycles fit inside ``repeat_duration_s``,
    given each cycle takes ``cycle_phases * step_duration_s`` seconds.
    Mirrors the legacy
    PathExecutionService.calculate_effective_repetitions_for_path
    formula: N <= (repeat_duration / step_duration - 1) / cycle_length.

    Returns 1 if no loop routes or budget is too small for one cycle.
    """
    loop_lengths = []
    for r in routes or []:
        if not _is_loop_route(r):
            continue
        cycle = list(_route_windows(r, trail_length, trail_overlay))
        if cycle:
            loop_lengths.append(len(cycle))
    if not loop_lengths or step_duration_s <= 0 or repeat_duration_s <= 0:
        return 1
    cycle_length = max(loop_lengths)
    n = int(((repeat_duration_s / step_duration_s) - 1) / cycle_length)
    return max(1, n)


def iter_phases(
    static_electrodes: List[str],
    routes: List[List[str]],
    *,
    trail_length: int = 1,
    trail_overlay: int = 0,
    soft_start: bool = False,
    soft_end: bool = False,
    repeat_duration_s: float = 0.0,
    linear_repeats: bool = False,
    n_repeats: int = 1,
    step_duration_s: float = 1.0,
) -> Iterator[Set[str]]:
    """Yield each phase as the set of electrode IDs to actuate.

    Each yield is one snapshot in time: static electrodes always
    included; per-route trail windows unioned in. The caller (a
    RoutesHandler) publishes the set, waits for the device's apply
    confirmation, then asks for the next phase.

    Composes the small helpers in this module — see the module
    docstring for the full pipeline.
    """
    static = set(static_electrodes or [])
    if not routes:
        # No paths to traverse; the static set is the only phase.
        yield static
        return
    per_route = [_route_with_repeats(r, trail_length, trail_overlay,
                                     linear_repeats=linear_repeats,
                                     n_repeats=n_repeats,
                                     repeat_duration_s=repeat_duration_s,
                                     step_duration_s=step_duration_s)
                 for r in routes]
    base = _zip_with_static(per_route, static)
    if soft_start:
        base = _ramp_up(base)
    if soft_end:
        base = _ramp_down(base)
    yield from base


def _zip_with_static(per_route_iters: list,
                     static: Set[str]) -> Iterator[Set[str]]:
    """At each tick, union the static set with each route's current
    window. Routes that exhaust early hold at their last yielded
    window; the iteration stops only when ALL routes are exhausted.

    No routes at all → yield the static set exactly once (the step
    still gets one phase). No static + no routes → yield one empty
    phase (preserves the 'every step has at least one phase'
    invariant the executor relies on).
    """
    if not per_route_iters:
        yield set(static)
        return

    # Drive each iterator forward by one step; remember the last value
    # so an exhausted route can keep contributing.
    last_windows: list = [None] * len(per_route_iters)

    while True:
        any_advanced = False
        for i, it in enumerate(per_route_iters):
            try:
                last_windows[i] = next(it)
                any_advanced = True
            except StopIteration:
                pass   # keep last_windows[i] as the held value
        # If on the very first tick none of the iterators yielded, fall
        # back to one phase of just the static set.
        if not any_advanced and all(w is None for w in last_windows):
            yield set(static)
            return
        if not any_advanced:
            return
        merged = set(static)
        for w in last_windows:
            if w is not None:
                merged |= w
        yield merged
