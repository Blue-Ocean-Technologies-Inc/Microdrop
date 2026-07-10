"""Phase-generation helpers for the RoutesHandler, delegating ALL phase
geometry to the centralized ``PathExecutionService``
(``microdrop_utils.route_execution``) so protocol-run route execution
exactly mirrors the device viewer's route playback — same trail windows,
same loop cycles and return phase, same soft ramps, same idle padding and
repetition math.

A "phase" is one snapshot in time of which electrodes are actuated. Each
step of a protocol expands to a sequence of phases, each yielded by
iter_phases() and consumed (publish + wait_for ack) by the RoutesHandler.

Only the dynamic duration-mode loop helpers stay local (budget gates and
unit cycles for volume-threshold steps — a runtime mode the device viewer
doesn't have); their phase windows also come from the central geometry.

No Traits, no Qt, no broker — testable as plain Python.
"""

from typing import Iterator, List, Optional, Set, Tuple

from microdrop_utils.route_execution import PathExecutionService


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

    Each yield is one snapshot in time: static electrodes always included;
    per-route trail windows unioned in. The caller (a RoutesHandler)
    publishes the set, waits for the device's apply confirmation, then
    asks for the next phase.

    The sequence is exactly the centralized execution plan's — including
    loop cycles capped by ``repeat_duration_s`` with idle hold-at-start
    padding (when > 0), the closing return-to-start phase for loops, and
    soft start/end ramps.
    """
    plan = PathExecutionService.calculate_execution_plan_from_params(
        duration=float(step_duration_s),
        repetitions=int(n_repeats),
        repeat_duration=float(repeat_duration_s),
        trail_length=int(trail_length),
        trail_overlay=int(trail_overlay),
        paths=[list(route) for route in (routes or [])],
        activated_electrodes=list(static_electrodes or []),
        repeat_duration_mode=repeat_duration_s > 0,
        soft_start=soft_start,
        soft_terminate=soft_end,
        linear_repeats=linear_repeats,
    )
    for plan_item in plan:
        yield set(plan_item["activated_electrodes"])


def effective_repetitions_for_duration(
    *,
    routes: List[List[str]],
    trail_length: int = 1,
    trail_overlay: int = 0,
    step_duration_s: float = 1.0,
    repeat_duration_s: float = 0.0,
) -> int:
    """How many full loop cycles fit inside ``repeat_duration_s`` — the
    centralized breakdown's rep count (one rep = one cycle of the longest
    loop route, like the device viewer's status display).

    Returns 1 if no loop routes or the budget is too small for one cycle.
    """
    _phases_per_rep, total_reps = (
        PathExecutionService.calculate_phase_rep_breakdown(
            routes or [], 1,
            duration=step_duration_s,
            repetitions=1,
            repeat_duration=repeat_duration_s,
            trail_length=trail_length,
            trail_overlay=trail_overlay,
        ))
    return total_reps


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


# --------------------------------------------------------------------- #
# Dynamic duration-mode loop helpers (volume-threshold steps)             #
# --------------------------------------------------------------------- #

def duration_loop_parts(
    static_electrodes: List[str],
    routes: List[List[str]],
    *,
    trail_length: int = 1,
    trail_overlay: int = 0,
    soft_start: bool = False,
) -> Tuple[List[Set[str]], List[Set[str]], Optional[Set[str]]]:
    """Decompose a step into the pieces the RoutesHandler needs to drive a
    *dynamic* duration-mode loop under volume threshold:

        (ramp_up_phases, unit_cycle, return_phase)

    ``unit_cycle`` is ONE pass of the centralized plan's phases (the
    repeatable unit — a single-rep plan minus the closing return phase for
    loop routes, since the dynamic loop closes cycles itself).
    ``ramp_up_phases`` are the centralized plan's own soft-start phases
    (device-viewer semantics: route electrodes grow in PATH order from the
    route start; static electrodes are always fully on and never ramp).
    Empty when soft_start is False or the first trail window has <= 1
    electrode. ``return_phase`` is ``unit_cycle[0]`` (to close the loop
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

    def build_plan(with_soft_start):
        return PathExecutionService.calculate_execution_plan_from_params(
            duration=1.0,
            repetitions=1,
            repeat_duration=0.0,
            trail_length=int(trail_length),
            trail_overlay=int(trail_overlay),
            paths=[list(route) for route in routes],
            activated_electrodes=list(static),
            repeat_duration_mode=False,
            soft_start=with_soft_start,
            soft_terminate=False,
            linear_repeats=False,
        )

    plan = build_plan(False)
    unit_cycle = [set(plan_item["activated_electrodes"])
                  for plan_item in plan]
    # A single-rep plan for loop routes ends with the return-to-start
    # phase; the dynamic loop closes cycles itself (the next loop's phase
    # 0 IS the return), so drop it from the repeatable unit.
    if (len(unit_cycle) > 1
            and any(PathExecutionService.is_loop_path(list(route))
                    for route in routes)):
        unit_cycle = unit_cycle[:-1]
    if not unit_cycle:
        return [], [set(static)], None
    ramp_up: List[Set[str]] = []
    if soft_start:
        # The soft plan prepends the ramp phases before the same cycle, so
        # the length difference IS the ramp — taken from the plan itself
        # to match the device viewer's ramp exactly.
        soft_plan = build_plan(True)
        ramp_up = [set(plan_item["activated_electrodes"])
                   for plan_item in soft_plan[:len(soft_plan) - len(plan)]]
    return ramp_up, unit_cycle, unit_cycle[0]


def unit_cycle_len(static_electrodes, routes, *, trail_length=1,
                   trail_overlay=0, soft_start=False) -> int:
    """Number of phases in one unit loop (the unique, navigable phases)."""
    _ramp, unit_cycle, _ret = duration_loop_parts(
        static_electrodes, routes, trail_length=trail_length,
        trail_overlay=trail_overlay, soft_start=soft_start)
    return len(unit_cycle)


def another_loop_fits(raw_elapsed: float, cycle_len: int,
                      phase_dwell: float, budget: float) -> bool:
    """True if a FULL fresh loop is guaranteed to finish within budget.

    Worst case assumes every phase runs its full ``phase_dwell`` (the
    volume-threshold timeout equals the duration-column value). Uses raw
    wall-clock elapsed (pauses/holds already spent count against budget)."""
    if cycle_len <= 0:
        return False
    return raw_elapsed + cycle_len * phase_dwell <= budget


def loop_completion_fits(raw_elapsed: float, phase_in_cycle: int,
                         cycle_len: int, phase_dwell: float,
                         budget: float) -> bool:
    """True if finishing the CURRENT loop from ``phase_in_cycle`` (0-based)
    back to the start still fits the budget. Used for the mid-loop-expiry
    check on resume after a seek."""
    remaining = max(0, cycle_len - phase_in_cycle)
    return raw_elapsed + remaining * phase_dwell <= budget


def idle_cell_index(cycle_len: int) -> int:
    """0-based index of the trailing idle cell on the phase bar
    (the bar shows ``cycle_len`` unique phases + this idle cell)."""
    return cycle_len
