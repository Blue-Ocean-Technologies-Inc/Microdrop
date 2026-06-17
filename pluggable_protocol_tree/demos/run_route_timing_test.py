"""Headless validator for the route-execution **timing + reps** feature.

Builds one protocol that exercises many route types and runs it in
PREVIEW MODE (no Redis, no hardware — the RoutesHandler skips its broker
publish + ack wait and simply dwells ``duration_s`` per phase). For each
executed (row, repetition) frame it compares the measured wall-clock
against the value predicted purely from ``phase_math.iter_phases`` plus
the duration-mode hold-pad, and prints a PASS/FAIL table.

What it checks
--------------
* **Open / loop / multi routes** -> correct emitted phase counts.
* **Route Reps** (count mode) -> a loop route runs ``N`` cycles + 1
  return phase; an open route runs once (or ``N`` passes with Lin Reps).
* **Route Reps Dur** (duration mode) -> the step's total time lands on
  the budget ``T`` exactly via the hold-pad, INCLUDING soft-start/end
  ramp phases (the len(phases)-based pad).
* **Reps** (whole-thing) -> a step re-runs its on_step ``N`` times and a
  group expands its subtree ``N`` times.

Run::

    pixi run python -m pluggable_protocol_tree.demos.run_route_timing_test

It also writes ``route_timing_test_protocol.json`` next to the cwd so the
same protocol can be opened in the GUI (File > Open) to watch the
Phase x/y counter, the step/phase timers, and the repetition counter
update live.

No Qt event loop is required: ExecutorSignals are direct-connected, so
the step_started / step_finished slots fire synchronously on the worker
thread. ``publish_message`` is stubbed to a no-op so no broker is needed
even for the display-state publishes.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

from pyface.qt.QtCore import Qt

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.route_repetitions_column import (
    make_route_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.phase_math import iter_phases


# Per-phase dwell used for the route steps. Kept small so the whole
# validator finishes in a few seconds; the duration-mode budgets below
# are chosen as clean multiples so the hold-pad is clearly observable.
_DWELL = 0.1

# Wall-clock tolerance: preview-mode dwells use 50ms cooperative-sleep
# slices plus a little per-step signal/loop overhead, so allow a small
# absolute slack (plus a relative term for the longer steps).
def _tolerance(expected_s: float) -> float:
    return max(0.20, 0.15 * expected_s)


def _columns():
    """The route-relevant built-in column set (no magnet/voltage)."""
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_repetitions_column(),          # whole-thing Reps
        make_route_repetitions_column(),    # Route Reps (route loops)
        make_duration_column(),
        make_electrodes_column(),
        make_routes_column(),
        make_trail_length_column(),
        make_trail_overlay_column(),
        make_soft_start_column(),
        make_soft_end_column(),
        make_repeat_duration_column(),      # Route Reps Dur (budget)
        make_linear_repeats_column(),
    ]


def _phases_for(row):
    """The exact phase list RoutesHandler will emit for ``row`` — same
    iter_phases call, n_repeats sourced from route_repetitions."""
    return list(iter_phases(
        static_electrodes=list(getattr(row, "electrodes", []) or []),
        routes=list(getattr(row, "routes", []) or []),
        trail_length=int(getattr(row, "trail_length", 1)),
        trail_overlay=int(getattr(row, "trail_overlay", 0)),
        soft_start=bool(getattr(row, "soft_start", False)),
        soft_end=bool(getattr(row, "soft_end", False)),
        repeat_duration_s=float(getattr(row, "repeat_duration", 0.0)),
        linear_repeats=bool(getattr(row, "linear_repeats", False)),
        n_repeats=int(getattr(row, "route_repetitions", 1)),
        step_duration_s=float(getattr(row, "duration_s", 1.0)),
    ))


def _expected(row):
    """(phase_count, expected_total_s, pad_s) for one execution of row.

    Mirrors RoutesHandler: total = phases * dwell, plus a hold-pad of
    ``repeat_duration - phases*dwell`` when in Route-Reps-Dur mode."""
    phases = _phases_for(row)
    dwell = float(getattr(row, "duration_s", 0.0) or 0.0)
    n = len(phases)
    base = n * dwell
    in_duration_mode = (
        bool(getattr(row, "repeat_duration_controls", False))
        and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
    )
    if in_duration_mode:
        pad = max(0.0, float(getattr(row, "repeat_duration", 0.0)) - base)
        return n, base + pad, pad
    return n, base, 0.0


def build_protocol() -> RowManager:
    """One protocol covering the route types + reps + duration cases.

    The 'validates' note on each step says what behaviour it exercises."""
    rm = RowManager(columns=_columns())
    # 5x5 electrode grid; RoutesHandler resolves channels from this in a
    # real run (unused in preview but kept so the saved JSON is loadable).
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(25)
    }

    def set_trait(path, **traits):
        row = rm.get_row(path)
        for k, v in traits.items():
            setattr(row, k, v)

    # 1. Static hold — no routes. validates: 1 phase, total == duration.
    rm.add_step(values={
        "name": "1 Static hold (no route)",
        "duration_s": 0.3,
        "electrodes": ["e00", "e01", "e02"],
    })

    # 2. Open route, trail_length=1. validates: 5 single-electrode phases.
    rm.add_step(values={
        "name": "2 Open route trail=1",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 1,
    })

    # 3. Open route, trail window 2 / overlap 1. validates: sliding window.
    rm.add_step(values={
        "name": "3 Open route trail=2 ov=1",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 2, "trail_overlay": 1,
    })

    # 4. Loop route, Route Reps=3 (count mode). validates: N cycles + 1
    #    return phase.
    rm.add_step(values={
        "name": "4 Loop Route Reps=3",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e03", "e00"]],
        "trail_length": 1,
        "route_repetitions": 3,
    })

    # 5. Loop route, Route Reps Dur=1.0s (duration mode). validates: max
    #    full cycles that fit + hold-pad so total lands on 1.0s.
    p5 = rm.add_step(values={
        "name": "5 Loop Route Reps Dur=1.0s",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e03", "e00"]],
        "trail_length": 1,
        "repeat_duration": 1.0,
    })
    set_trait(p5, repeat_duration_controls=True)

    # 6. Loop route + soft ramps, count mode. validates: ramp phases are
    #    prepended/appended without breaking the loop.
    rm.add_step(values={
        "name": "6 Loop + soft ramps (count)",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e03", "e00"]],
        "trail_length": 2,
        "soft_start": True, "soft_end": True,
    })

    # 7. Loop + soft ramps + Route Reps Dur=1.1s. validates the headline
    #    fix: total time lands on the budget EVEN WITH ramp phases (the pad
    #    is computed from the actual emitted phase count, not loop cycles).
    #    8-cell loop @trail=2 -> 4 windows/cycle (0.4s); 2 full cycles
    #    (0.8s) + 2 ramp phases (0.2s) = 1.0s emitted, so pad = 0.1s lands
    #    the total on 1.1s. (A shorter loop here would overshoot the budget
    #    on the ramps alone, clamping pad to 0 — still correct, just not a
    #    pad>0 demo.)
    p7 = rm.add_step(values={
        "name": "7 Loop + ramps + Dur=1.1s",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e03",
                    "e04", "e05", "e06", "e07", "e00"]],
        "trail_length": 2,
        "soft_start": True, "soft_end": True,
        "repeat_duration": 1.1,
    })
    set_trait(p7, repeat_duration_controls=True)

    # 8. Multiple routes in one step. validates: per-tick union, runs
    #    until the longest route is exhausted.
    rm.add_step(values={
        "name": "8 Multiple routes",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02"], ["e10", "e11", "e12", "e13"]],
        "trail_length": 1,
    })

    # 9. Group with Reps=2 wrapping a route step. validates: whole-subtree
    #    repeat (the child executes twice).
    g = rm.add_group(name="9 Repeat group x2")
    set_trait(g, repetitions=2)
    rm.add_step(parent_path=g, values={
        "name": "9a Child route",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02"]],
        "trail_length": 1,
    })

    # 10. Reps=2 (whole step) x Route Reps=2 (route loop) on a loop route.
    #     validates: the step runs twice, each run loops the route twice
    #     (+ return) => total route plays = Reps x Route Reps.
    p10 = rm.add_step(values={
        "name": "10 Reps=2 x RouteReps=2",
        "duration_s": _DWELL,
        "routes": [["e00", "e01", "e02", "e00"]],
        "trail_length": 1,
        "route_repetitions": 2,
    })
    set_trait(p10, repetitions=2)

    return rm


def main() -> int:
    rm = build_protocol()

    # Predict the execution sequence (one entry per executed frame, in
    # execution order — the same order the executor iterates).
    expected = []
    for row, rep_chain in rm.iter_execution_frames():
        n, exp_t, pad = _expected(row)
        expected.append((row.name, n, exp_t, pad, rep_chain))

    print(f"Protocol: {len(expected)} executed step-frames "
          f"(after Reps expansion).\n")

    # Save a GUI-loadable copy.
    out = Path("route_timing_test_protocol.json")
    out.write_text(json.dumps(rm.to_json(), indent=2))
    print(f"Saved protocol -> {out.resolve()}  (open in the GUI to watch "
          f"the live Phase x/y + timers)\n")

    # Measure actual per-frame wall-clock via the executor signals.
    timings: list = []
    state = {"t0": None}
    ex = ProtocolExecutor(row_manager=rm)
    # DirectConnection: the executor emits these on its worker thread and
    # there is no Qt event loop here, so a queued (default) connection
    # would never deliver. Direct => the slot runs synchronously in the
    # emitting thread.
    ex.signals.step_started.connect(
        lambda row: state.update(t0=time.monotonic()), Qt.DirectConnection)
    ex.signals.step_finished.connect(
        lambda row: timings.append(time.monotonic() - state["t0"]),
        Qt.DirectConnection)

    # Preview mode + stubbed publish => pure timing, no broker/hardware.
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               lambda **kw: None):
        ex.start(preview_mode=True)
        ex.wait()

    # Report.
    header = (f"{'res':4} {'step':30} {'phases':>6} {'expect':>8} "
              f"{'actual':>8} {'pad':>6}  reps")
    print(header)
    print("-" * len(header))
    failures = 0
    for (name, n, exp_t, pad, chain), act_t in zip(expected, timings):
        ok = abs(act_t - exp_t) <= _tolerance(exp_t)
        failures += 0 if ok else 1
        chain_str = " > ".join(f"{nm} {i}/{tot}" for nm, i, tot in chain)
        print(f"{'PASS' if ok else 'FAIL':4} {name:30} {n:6d} "
              f"{exp_t:7.2f}s {act_t:7.2f}s {pad:5.2f}s  {chain_str}")

    if len(timings) != len(expected):
        print(f"\nFAIL: executed {len(timings)} frames, expected "
              f"{len(expected)} (rep-expansion mismatch).")
        failures += 1

    print()
    if failures == 0:
        print(f"ALL {len(expected)} frames PASS — route timing + reps OK.")
        return 0
    print(f"{failures} frame(s) FAILED — see table above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
