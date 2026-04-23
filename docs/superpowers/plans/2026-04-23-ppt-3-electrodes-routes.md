# PPT-3: Electrodes + Routes columns + simplified phase math + simple device viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the electrodes/routes per-step columns + simplified phase math + a small demo device viewer, against the existing PPT-1+PPT-2 plugin. Leaves the legacy `protocol_grid`'s `path_execution_service.py` and the production `device_viewer/` plugin untouched.

**Architecture:** Three layers.
1. **Phase math** — pure functions in `services/phase_math.py`. Composed of small one-job helpers (`_route_windows`, `_route_with_repeats`, `_zip_with_static`, `_ramp_up`, `_ramp_down`). Pure data-in / data-out; no Traits, no Qt, no broker. ~150 lines vs the legacy ~600.
2. **Columns + persistence** — `electrodes` (List[Str]) and `routes` (List[List[Str]]) with read-only summary cells, 6 hidden config columns (trail/loop/ramp), `RoutesHandler` at priority 30 that walks `iter_phases()`, publishes each phase, waits for ack. New `protocol_metadata` Dict trait on `RowManager` carries `electrode_to_channel` in the JSON header.
3. **Demo** — `SimpleDeviceViewer` (5×5 grid) lets the user click-toggle static electrodes and click-then-Finish to draw routes; live green overlay paints currently-actuated cells subscribed off the actuation topic. Embedded alongside the tree via `QSplitter`. In-process `electrode_responder` Dramatiq actor closes the loop.

**Tech Stack:** PySide6/Qt6 (`QWidget`, `QSplitter`, `QPainter`), Pyface, Traits/HasTraits, Dramatiq + Redis, pytest.

**Spec:** `src/docs/superpowers/specs/2026-04-23-ppt-3-electrodes-routes-design.md`

**Issue:** Closes #365 (sub-issue) — part of umbrella #361.

**Branch:** `feat/ppt-3-electrodes-routes` (already created when the spec was committed).

---

## File structure

New files:

```
src/pluggable_protocol_tree/
├── services/phase_math.py
├── builtins/
│   ├── electrodes_column.py
│   ├── routes_column.py
│   ├── trail_length_column.py
│   ├── trail_overlay_column.py
│   ├── soft_start_column.py
│   ├── soft_end_column.py
│   ├── repeat_duration_column.py
│   └── linear_repeats_column.py
├── views/columns/_hidden_view_mixins.py
├── demos/
│   ├── simple_device_viewer.py
│   └── electrode_responder.py
└── tests/
    ├── test_phase_math.py
    ├── test_electrodes_routes_columns.py
    ├── test_hidden_columns.py
    └── tests_with_redis_server_need/
        └── test_routes_handler_redis.py
```

Modified files:

```
src/pluggable_protocol_tree/
├── consts.py                       # +ELECTRODES_STATE_CHANGE/_APPLIED topics
├── models/row_manager.py           # +protocol_metadata trait + to/from_json plumbing
├── services/persistence.py         # +metadata round-trip
├── execution/executor.py           # +scratch.update(metadata) at run start
├── plugin.py                       # +new builtins; +seed-from-prefs
├── views/tree_widget.py            # +hide hidden_by_default columns; +header menu
├── demos/run_widget.py             # +SimpleDeviceViewer in QSplitter; +metadata seed
└── tests/test_persistence.py       # +metadata round-trip + backward-compat
```

---

## Working directory and conventions

All commands run from the **outer repo** at `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py`. Pixi required — never invoke `python` / `pytest` directly. Standard form:

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest <args>"
```

`git` operations run from the **submodule** at `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` on branch `feat/ppt-3-electrodes-routes`.

Commit messages all start with `[PPT-3]` and end with the standard `Co-Authored-By:` trailer.

---

## Task 0: Verify branch + issue state

**Files:** none (git/gh only)

- [ ] **Step 1: Verify the working branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git rev-parse --abbrev-ref HEAD && git status --short
```

Expected: `feat/ppt-3-electrodes-routes` and a clean tree (or only pre-existing modifications you've been intentionally preserving).

- [ ] **Step 2: Verify issue #365 is open + spec is committed**

```bash
gh issue view 365 --repo Blue-Ocean-Technologies-Inc/Microdrop --json state,title
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git log --oneline -3
```

Expected: state `OPEN`, title contains `PPT-3`. Most recent commit on the branch is `[Spec] PPT-3 electrodes + routes — design doc`.

---

## Task 1: Topic constants + `protocol_metadata` trait + executor scratch hydration

**Files:**
- Modify: `src/pluggable_protocol_tree/consts.py` — add 2 topic constants
- Modify: `src/pluggable_protocol_tree/models/row_manager.py` — add `protocol_metadata = Dict(...)` trait
- Modify: `src/pluggable_protocol_tree/execution/executor.py` — `proto_ctx.scratch.update(self.row_manager.protocol_metadata)` in `run()`
- Modify: `src/pluggable_protocol_tree/tests/test_row_manager.py` — append a small test for the trait default

- [ ] **Step 1: Add topic constants**

Open `src/pluggable_protocol_tree/consts.py`. Append after the existing `PROTOCOL_TOPIC_PREFIX` line:

```python
# PPT-3: per-phase electrode actuation
ELECTRODES_STATE_CHANGE  = f"{PROTOCOL_TOPIC_PREFIX}/electrodes_state_change"
ELECTRODES_STATE_APPLIED = f"{PROTOCOL_TOPIC_PREFIX}/electrodes_state_applied"
```

- [ ] **Step 2: Add `protocol_metadata` trait to RowManager**

In `src/pluggable_protocol_tree/models/row_manager.py`, find the imports block at the top. The existing imports include `Dict`? Verify — if not, add `Dict` and `Any` to the `from traits.api import (...)` line (`Dict` and `Any` may already be imported from PPT-2's clipboard work).

After the existing `clipboard_mime = Str(...)` declaration in the `RowManager` class, add:

```python
    protocol_metadata = Dict(Str, Any,
        desc="Per-protocol scratch persisted in the JSON header. Keys "
             "are namespaced by feature ('electrode_to_channel', etc.). "
             "Hydrated into ProtocolContext.scratch by the executor at "
             "run start.")
```

- [ ] **Step 3: Append a unit test for the new trait**

Append to `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- PPT-3: protocol_metadata ---

def test_protocol_metadata_defaults_empty(manager):
    assert manager.protocol_metadata == {}


def test_protocol_metadata_holds_arbitrary_payload(manager):
    manager.protocol_metadata["electrode_to_channel"] = {"e00": 0, "e01": 1}
    manager.protocol_metadata["someone_elses_key"] = [1, 2, 3]
    assert manager.protocol_metadata["electrode_to_channel"] == {"e00": 0, "e01": 1}
    assert manager.protocol_metadata["someone_elses_key"] == [1, 2, 3]
```

- [ ] **Step 4: Run the new tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v -k 'protocol_metadata'"
```

Expected: 2 passed.

- [ ] **Step 5: Hydrate metadata into the protocol context**

In `src/pluggable_protocol_tree/execution/executor.py`, find the `run()` method's opening block:

```python
        cols = list(self.row_manager.columns)
        proto_ctx = ProtocolContext(
            columns=cols, stop_event=self.stop_event,
        )
```

Replace with:

```python
        cols = list(self.row_manager.columns)
        proto_ctx = ProtocolContext(
            columns=cols, stop_event=self.stop_event,
        )
        # PPT-3: hydrate per-protocol metadata (e.g. electrode_to_channel)
        # into the context's scratch so handlers can reach it without
        # holding a reference to the RowManager.
        proto_ctx.scratch.update(self.row_manager.protocol_metadata)
```

- [ ] **Step 6: Re-run the executor tests to confirm no regressions**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: all existing executor tests still pass.

- [ ] **Step 7: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/consts.py \
          pluggable_protocol_tree/models/row_manager.py \
          pluggable_protocol_tree/execution/executor.py \
          pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Topic constants + RowManager.protocol_metadata + executor scratch hydration

Three small additions wired together so PPT-3 builtins can land
without per-column boilerplate:

- consts.py: ELECTRODES_STATE_CHANGE / _APPLIED topic constants
  under the existing PROTOCOL_TOPIC_PREFIX namespace.
- RowManager.protocol_metadata = Dict(Str, Any) — per-protocol
  scratch persisted in the JSON header. Generic bag; PPT-3's only
  user is electrode_to_channel.
- Executor.run() hydrates protocol_metadata into ProtocolContext.scratch
  at run start, so handlers reach config via ctx.protocol.scratch
  without holding a RowManager reference.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `phase_math.py` — `_is_loop_route` + `_route_windows`

**Files:**
- Create: `src/pluggable_protocol_tree/services/phase_math.py`
- Create: `src/pluggable_protocol_tree/tests/test_phase_math.py`

- [ ] **Step 1: Write the failing test file**

Create `src/pluggable_protocol_tree/tests/test_phase_math.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.services.phase_math`.

- [ ] **Step 3: Create `phase_math.py` with the two helpers**

Create `src/pluggable_protocol_tree/services/phase_math.py`:

```python
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
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/services/phase_math.py \
          pluggable_protocol_tree/tests/test_phase_math.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] phase_math: _is_loop_route + _route_windows

Two foundational helpers for the simplified phase math. Loop routes
detected by first==last; the duplicate is dropped from the effective
path so windows wrap correctly. step_size clamped to max(1, length -
overlay) so a misconfigured overlay >= length still makes progress.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `phase_math.py` — `_route_with_repeats`

**Files:**
- Modify: `src/pluggable_protocol_tree/services/phase_math.py` — append `_route_with_repeats`
- Modify: `src/pluggable_protocol_tree/tests/test_phase_math.py` — append tests

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_phase_math.py`:

```python
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
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: ImportError on `_route_with_repeats`.

- [ ] **Step 3: Append `_route_with_repeats` to `phase_math.py`**

Append to `src/pluggable_protocol_tree/services/phase_math.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: 18 passed (11 + 7).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/services/phase_math.py \
          pluggable_protocol_tree/tests/test_phase_math.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] phase_math: _route_with_repeats

Wraps _route_windows with three orthogonal repeat semantics:
- Open route + linear_repeats=True  → replay N times (N from row's
  repetitions column).
- Loop route → N cycles by default; when repeat_duration_s > 0,
  derived from the budget instead. Always at least 1 cycle so a
  too-small budget doesn't suppress the route entirely.
- Empty route yields nothing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `phase_math.py` — `_zip_with_static`

**Files:**
- Modify: `src/pluggable_protocol_tree/services/phase_math.py` — append `_zip_with_static`
- Modify: `src/pluggable_protocol_tree/tests/test_phase_math.py` — append tests

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_phase_math.py`:

```python
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
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: ImportError on `_zip_with_static`.

- [ ] **Step 3: Append `_zip_with_static` to `phase_math.py`**

Append to `src/pluggable_protocol_tree/services/phase_math.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: 24 passed (18 + 6).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/services/phase_math.py \
          pluggable_protocol_tree/tests/test_phase_math.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] phase_math: _zip_with_static

Per-tick fan-in: union the static set with each route's current
window. Routes that exhaust early hold at their last value so the
output isn't ragged. Stops when all routes are exhausted.

Edge cases: no routes → static yielded exactly once; no static + no
routes → one empty phase (preserves the executor's "every step has
at least one phase" invariant).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `phase_math.py` — ramps + `iter_phases` composition

**Files:**
- Modify: `src/pluggable_protocol_tree/services/phase_math.py` — append `_ramp_up`, `_ramp_down`, `iter_phases`
- Modify: `src/pluggable_protocol_tree/tests/test_phase_math.py` — append tests

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_phase_math.py`:

```python
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
    # Order within a set isn't deterministic, so compare lengths only;
    # set the static element to a single deterministic seed for the
    # ramp by ordering on the natural set sort.
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
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b", "c", "a"]],
        trail_length=1, trail_overlay=0,
    ))
    assert out == [{"a"}, {"b"}, {"c"}]


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
    """Loop with cycle=3, step_duration=1, budget=6.5 → 2 cycles."""
    out = list(iter_phases(
        static_electrodes=[],
        routes=[["a", "b", "c", "a"]],
        trail_length=1, trail_overlay=0,
        repeat_duration_s=6.5, step_duration_s=1.0,
        n_repeats=999,
    ))
    assert out == [{"a"}, {"b"}, {"c"}, {"a"}, {"b"}, {"c"}]


def test_iter_phases_linear_repeats_replays_open_route():
    """Linear-repeats true on an open route: replay n_repeats times."""
    out = list(iter_phases(
        static_electrodes=[], routes=[["a", "b"]],
        trail_length=1, trail_overlay=0,
        linear_repeats=True, n_repeats=3,
    ))
    assert out == [{"a"}, {"b"}, {"a"}, {"b"}, {"a"}, {"b"}]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: ImportError on `_ramp_up` / `_ramp_down` / `iter_phases`.

- [ ] **Step 3: Append the helpers + iter_phases to `phase_math.py`**

Append to `src/pluggable_protocol_tree/services/phase_math.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_phase_math.py -v"
```

Expected: 36 passed (24 + 12).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/services/phase_math.py \
          pluggable_protocol_tree/tests/test_phase_math.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] phase_math: ramps + iter_phases composition

Two transformer helpers (_ramp_up, _ramp_down) and the public
iter_phases() that composes the whole pipeline:

  routes → per-route windows → repeat-wrapped → zip-with-static
         → optional ramp-up → optional ramp-down → yield

Soft-start ramp grows from 1 electrode up to the first phase's size,
picking elements in sorted order for stable test output. Soft-end is
the mirror — same sorted-order picking.

iter_phases is the only public surface of this module; everything
else is _-prefixed and tested in isolation in earlier tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 6 hidden config columns + view subclasses

**Files:**
- Create: `src/pluggable_protocol_tree/views/columns/_hidden_view_mixins.py`
- Create: `src/pluggable_protocol_tree/builtins/trail_length_column.py`
- Create: `src/pluggable_protocol_tree/builtins/trail_overlay_column.py`
- Create: `src/pluggable_protocol_tree/builtins/soft_start_column.py`
- Create: `src/pluggable_protocol_tree/builtins/soft_end_column.py`
- Create: `src/pluggable_protocol_tree/builtins/repeat_duration_column.py`
- Create: `src/pluggable_protocol_tree/builtins/linear_repeats_column.py`
- Create: `src/pluggable_protocol_tree/tests/test_hidden_columns.py`

- [ ] **Step 1: Write failing tests**

Create `src/pluggable_protocol_tree/tests/test_hidden_columns.py`:

```python
"""Tests for the 6 hidden-by-default trail/loop/ramp config columns
shipped by the core plugin in PPT-3."""

from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.soft_end_column import (
    make_soft_end_column,
)
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)


def test_trail_length_column_metadata_and_hidden():
    col = make_trail_length_column()
    assert col.model.col_id == "trail_length"
    assert col.model.col_name == "Trail Len"
    assert col.model.default_value == 1
    assert col.view.hidden_by_default is True
    assert col.view.low == 1 and col.view.high == 64


def test_trail_overlay_column_metadata_and_hidden():
    col = make_trail_overlay_column()
    assert col.model.col_id == "trail_overlay"
    assert col.model.default_value == 0
    assert col.view.hidden_by_default is True
    assert col.view.low == 0 and col.view.high == 63


def test_soft_start_column_metadata_and_hidden():
    col = make_soft_start_column()
    assert col.model.col_id == "soft_start"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True


def test_soft_end_column_metadata_and_hidden():
    col = make_soft_end_column()
    assert col.model.col_id == "soft_end"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True


def test_repeat_duration_column_metadata_and_hidden():
    col = make_repeat_duration_column()
    assert col.model.col_id == "repeat_duration"
    assert col.model.default_value == 0.0
    assert col.view.hidden_by_default is True
    assert col.view.low == 0.0 and col.view.high == 3600.0


def test_linear_repeats_column_metadata_and_hidden():
    col = make_linear_repeats_column()
    assert col.model.col_id == "linear_repeats"
    assert col.model.default_value is False
    assert col.view.hidden_by_default is True
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_hidden_columns.py -v"
```

Expected: ImportError on the new column modules.

- [ ] **Step 3: Create the hidden-view mixins file**

Create `src/pluggable_protocol_tree/views/columns/_hidden_view_mixins.py`:

```python
"""Tiny ``hidden_by_default = True`` overrides of the PPT-1 base views.

Used by the 6 trail/loop/ramp config columns shipped in PPT-3 — those
columns are sometimes-needed knobs, not always-visible columns. The
ProtocolTreeWidget reads ``view.hidden_by_default`` after model
attach and calls ``tree.setColumnHidden(idx, True)`` for any column
where it's True.
"""

from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView, IntSpinBoxColumnView,
)


class HiddenIntSpinBoxColumnView(IntSpinBoxColumnView):
    hidden_by_default = True


class HiddenDoubleSpinBoxColumnView(DoubleSpinBoxColumnView):
    hidden_by_default = True


class HiddenCheckboxColumnView(CheckboxColumnView):
    hidden_by_default = True
```

- [ ] **Step 4: Create the 6 column files**

Create `src/pluggable_protocol_tree/builtins/trail_length_column.py`:

```python
"""Hidden trail-length column. How many electrodes are simultaneously
active in a route's sliding window."""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenIntSpinBoxColumnView,
)


class TrailLengthColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(int(self.default_value or 1),
                   desc="Number of electrodes simultaneously active in "
                        "a route's sliding window.")


def make_trail_length_column():
    return Column(
        model=TrailLengthColumnModel(
            col_id="trail_length", col_name="Trail Len", default_value=1,
        ),
        view=HiddenIntSpinBoxColumnView(low=1, high=64),
    )
```

Create `src/pluggable_protocol_tree/builtins/trail_overlay_column.py`:

```python
"""Hidden trail-overlay column. How many electrodes the current and
next windows share — controls the effective step size."""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenIntSpinBoxColumnView,
)


class TrailOverlayColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(int(self.default_value or 0),
                   desc="Electrodes shared between the current and "
                        "next windows. step_size = max(1, length - overlay).")


def make_trail_overlay_column():
    return Column(
        model=TrailOverlayColumnModel(
            col_id="trail_overlay", col_name="Trail Overlay", default_value=0,
        ),
        view=HiddenIntSpinBoxColumnView(low=0, high=63),
    )
```

Create `src/pluggable_protocol_tree/builtins/soft_start_column.py`:

```python
"""Hidden soft-start column. When True, prepend ramp-up phases that
grow from 1 electrode to trail_length."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class SoftStartColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Prepend ramp-up phases (1 electrode → trail_length).")


def make_soft_start_column():
    return Column(
        model=SoftStartColumnModel(
            col_id="soft_start", col_name="Soft Start", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
```

Create `src/pluggable_protocol_tree/builtins/soft_end_column.py`:

```python
"""Hidden soft-end column. When True, append ramp-down phases that
shrink from trail_length back to 1 electrode."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class SoftEndColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Append ramp-down phases (trail_length → 1).")


def make_soft_end_column():
    return Column(
        model=SoftEndColumnModel(
            col_id="soft_end", col_name="Soft End", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
```

Create `src/pluggable_protocol_tree/builtins/repeat_duration_column.py`:

```python
"""Hidden repeat-duration column. When > 0, caps loop cycles to fit
within this many seconds of step time."""

from traits.api import Float

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenDoubleSpinBoxColumnView,
)


class RepeatDurationColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Float(float(self.default_value or 0.0),
                     desc="Loop cycles capped to fit within this many "
                          "seconds. 0 disables (use linear n_repeats).")


def make_repeat_duration_column():
    return Column(
        model=RepeatDurationColumnModel(
            col_id="repeat_duration", col_name="Repeat (s)", default_value=0.0,
        ),
        view=HiddenDoubleSpinBoxColumnView(low=0.0, high=3600.0,
                                           decimals=2, single_step=0.1),
    )
```

Create `src/pluggable_protocol_tree/builtins/linear_repeats_column.py`:

```python
"""Hidden linear-repeats column. When True, replay open routes
n_repeats times (n_repeats comes from the row's repetitions column)."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class LinearRepeatsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Replay open routes n_repeats times.")


def make_linear_repeats_column():
    return Column(
        model=LinearRepeatsColumnModel(
            col_id="linear_repeats", col_name="Lin Reps", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
```

- [ ] **Step 5: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_hidden_columns.py -v"
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/views/columns/_hidden_view_mixins.py \
          pluggable_protocol_tree/builtins/trail_length_column.py \
          pluggable_protocol_tree/builtins/trail_overlay_column.py \
          pluggable_protocol_tree/builtins/soft_start_column.py \
          pluggable_protocol_tree/builtins/soft_end_column.py \
          pluggable_protocol_tree/builtins/repeat_duration_column.py \
          pluggable_protocol_tree/builtins/linear_repeats_column.py \
          pluggable_protocol_tree/tests/test_hidden_columns.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Six hidden trail / loop / ramp config columns

The phase math reads these from the row at runtime; the user only
sees them when they explicitly opt-in via the header right-click
menu (lands later in this PR). Following the PPT-1 one-file-per-
column convention so each column's metadata stays trivially
discoverable.

Three small "hidden" view subclasses (HiddenIntSpinBoxColumnView,
HiddenDoubleSpinBoxColumnView, HiddenCheckboxColumnView) override
the existing PPT-1 views' hidden_by_default class attribute. The
tree widget reads it post-attach (Task 11) to call setColumnHidden.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `electrodes_column.py`

**Files:**
- Create: `src/pluggable_protocol_tree/builtins/electrodes_column.py`
- Create: `src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py` (one section now, second section in Task 8)

- [ ] **Step 1: Write failing tests**

Create `src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py`:

```python
"""Tests for the electrodes and routes columns + RoutesHandler.
electrodes/routes are read-only summary cells; the actual edit path is
the demo's SimpleDeviceViewer (and tests / programmatic mutation)."""

from pyface.qt.QtCore import Qt

from pluggable_protocol_tree.models.row import BaseRow, build_row_type
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)


# --- electrodes column ---

def test_electrodes_column_metadata():
    col = make_electrodes_column()
    assert col.model.col_id == "electrodes"
    assert col.model.col_name == "Electrodes"
    assert col.model.default_value == []


def test_electrodes_column_trait_defaults_to_empty_list():
    col = make_electrodes_column()
    RowType = build_row_type([col], base=BaseRow)
    r = RowType()
    assert r.electrodes == []


def test_electrodes_summary_shows_pluralized_count():
    col = make_electrodes_column()
    assert col.view.format_display([], BaseRow()) == "0 electrodes"
    assert col.view.format_display(["e0"], BaseRow()) == "1 electrode"
    assert col.view.format_display(["e0", "e1", "e2"], BaseRow()) == "3 electrodes"


def test_electrodes_summary_handles_none_value():
    """Defensive: if the underlying value is somehow None, render as 0."""
    col = make_electrodes_column()
    assert col.view.format_display(None, BaseRow()) == "0 electrodes"


def test_electrodes_cell_is_not_editable():
    col = make_electrodes_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_electrodes_cell_create_editor_returns_none():
    col = make_electrodes_column()
    assert col.view.create_editor(None, None) is None
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v"
```

Expected: ImportError on `electrodes_column`.

- [ ] **Step 3: Implement the column**

Create `src/pluggable_protocol_tree/builtins/electrodes_column.py`:

```python
"""Electrodes column — list of electrode IDs held active for the step.

Read-only summary cell ('3 electrodes'). Mutated only via the demo's
SimpleDeviceViewer or programmatic / JSON-load path. Production
device-viewer integration is deferred to a later sub-issue.
"""

from pyface.qt.QtCore import Qt
from traits.api import List, Str

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.base import BaseColumnView


class ElectrodesColumnModel(BaseColumnModel):
    """List[str] trait. Default = empty list."""
    def trait_for_row(self):
        return List(Str, value=list(self.default_value or []),
                    desc="Electrode IDs held active for the entire step.")


class ElectrodesSummaryView(BaseColumnView):
    """Read-only cell. Shows '0 electrodes' / '1 electrode' / 'N electrodes'."""

    def format_display(self, value, row):
        n = len(value or [])
        return f"{n} electrode" + ("" if n == 1 else "s")

    def get_flags(self, row):
        # NOT editable — no ItemIsEditable flag.
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def create_editor(self, parent, context):
        return None


def make_electrodes_column():
    return Column(
        model=ElectrodesColumnModel(
            col_id="electrodes", col_name="Electrodes", default_value=[],
        ),
        view=ElectrodesSummaryView(),
    )
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v"
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/builtins/electrodes_column.py \
          pluggable_protocol_tree/tests/test_electrodes_routes_columns.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Electrodes column: List[str] + read-only summary view

Per-step list of electrode IDs held active for the entire step
duration. Cell shows a pluralized summary ("0 electrodes" /
"1 electrode" / "N electrodes"); not editable in the cell. Edited
via the demo's SimpleDeviceViewer or programmatic / JSON-load path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `routes_column.py` with `RoutesHandler`

**Files:**
- Create: `src/pluggable_protocol_tree/builtins/routes_column.py`
- Modify: `src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py` — append routes section

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py`:

```python
# --- routes column + RoutesHandler ---

import json
from unittest.mock import MagicMock, patch

from pluggable_protocol_tree.builtins.routes_column import (
    make_routes_column, RoutesHandler,
)
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)


def test_routes_column_metadata():
    col = make_routes_column()
    assert col.model.col_id == "routes"
    assert col.model.col_name == "Routes"
    assert col.model.default_value == []


def test_routes_column_trait_defaults_to_empty_list():
    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    r = RowType()
    assert r.routes == []


def test_routes_summary_shows_pluralized_count():
    col = make_routes_column()
    assert col.view.format_display([], BaseRow()) == "0 routes"
    assert col.view.format_display([["a", "b"]], BaseRow()) == "1 route"
    assert col.view.format_display(
        [["a", "b"], ["c", "d"], ["e", "f"]], BaseRow()
    ) == "3 routes"


def test_routes_cell_is_not_editable():
    col = make_routes_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_routes_handler_default_priority_and_wait_topics():
    """Priority 30 keeps it earlier than DurationColumnHandler (90)."""
    h = RoutesHandler()
    assert h.priority == 30
    assert ELECTRODES_STATE_APPLIED in h.wait_for_topics


def test_routes_handler_publishes_each_phase_then_waits():
    """Build a row with electrodes=['e0','e1'] + routes=[['e2','e3','e4']]
    + trail_length=1; the handler should publish 3 phases (one per
    route position, each unioned with the static electrodes), and
    ctx.wait_for between each."""
    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    row = RowType()
    row.electrodes = ["e0", "e1"]
    row.routes = [["e2", "e3", "e4"]]
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.linear_repeats = False
    row.duration_s = 1.0
    row.repetitions = 1

    ctx = MagicMock()
    ctx.protocol.scratch = {"electrode_to_channel": {
        "e0": 0, "e1": 1, "e2": 2, "e3": 3, "e4": 4,
    }}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    # 3 publishes, 3 wait_for calls (one between each)
    assert len(published) == 3
    assert ctx.wait_for.call_count == 3
    # Each publish targets ELECTRODES_STATE_CHANGE
    assert all(p["topic"] == ELECTRODES_STATE_CHANGE for p in published)
    # Payloads are JSON envelopes carrying electrodes + channels
    payloads = [json.loads(p["message"]) for p in published]
    assert payloads[0]["electrodes"] == ["e0", "e1", "e2"]
    assert payloads[0]["channels"] == [0, 1, 2]
    assert payloads[1]["electrodes"] == ["e0", "e1", "e3"]
    assert payloads[2]["electrodes"] == ["e0", "e1", "e4"]


def test_routes_handler_unmapped_electrode_logs_warning_and_skips_channel():
    """If an electrode in the phase isn't in electrode_to_channel, the
    payload's `channels` array doesn't include it (skipped silently
    aside from a logger.warning). The `electrodes` list still does."""
    col = make_routes_column()
    RowType = build_row_type([col], base=BaseRow)
    row = RowType()
    row.electrodes = []
    row.routes = [["unknown_electrode"]]
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.linear_repeats = False
    row.duration_s = 1.0
    row.repetitions = 1

    ctx = MagicMock()
    ctx.protocol.scratch = {"electrode_to_channel": {}}

    published = []
    with patch("pluggable_protocol_tree.builtins.routes_column.publish_message",
               side_effect=lambda **kw: published.append(kw)):
        col.handler.on_step(row, ctx)

    assert len(published) == 1
    payload = json.loads(published[0]["message"])
    assert payload["electrodes"] == ["unknown_electrode"]
    assert payload["channels"] == []
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v"
```

Expected: ImportError on `routes_column`.

- [ ] **Step 3: Implement `routes_column.py`**

Create `src/pluggable_protocol_tree/builtins/routes_column.py`:

```python
"""Routes column + RoutesHandler.

Per-step list of routes (each route = ordered list of electrode IDs).
Cell shows a read-only summary; the demo's SimpleDeviceViewer is the
primary edit path in PPT-3.

The RoutesHandler walks iter_phases() over the row's electrodes /
routes / trail config, publishes each phase to ELECTRODES_STATE_CHANGE
(JSON envelope with both electrode IDs and resolved channel numbers),
then blocks via ctx.wait_for() for the device's
ELECTRODES_STATE_APPLIED ack before requesting the next phase.

Priority 30 keeps this in a strictly earlier bucket than
DurationColumnHandler (90), so the duration sleep only starts after
ALL phases have completed and been ack'd.
"""

import json
import logging

from pyface.qt.QtCore import Qt
from traits.api import List, Str

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.services.phase_math import iter_phases
from pluggable_protocol_tree.views.columns.base import BaseColumnView


logger = logging.getLogger(__name__)


class RoutesColumnModel(BaseColumnModel):
    """List[List[str]] trait. Default = empty list."""
    def trait_for_row(self):
        return List(List(Str), value=list(self.default_value or []),
                    desc="Per-step list of routes; each route is an "
                         "ordered list of electrode IDs.")


class RoutesSummaryView(BaseColumnView):
    """Read-only cell. '0 routes' / '1 route' / 'N routes'."""

    def format_display(self, value, row):
        n = len(value or [])
        return f"{n} route" + ("" if n == 1 else "s")

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def create_editor(self, parent, context):
        return None


class RoutesHandler(BaseColumnHandler):
    """Drives electrode actuation for the step. See module docstring."""
    priority = 30
    wait_for_topics = [ELECTRODES_STATE_APPLIED]

    def on_step(self, row, ctx):
        mapping = ctx.protocol.scratch.get("electrode_to_channel", {})
        for phase in iter_phases(
            static_electrodes=list(getattr(row, "electrodes", []) or []),
            routes=list(getattr(row, "routes", []) or []),
            trail_length=int(getattr(row, "trail_length", 1)),
            trail_overlay=int(getattr(row, "trail_overlay", 0)),
            soft_start=bool(getattr(row, "soft_start", False)),
            soft_end=bool(getattr(row, "soft_end", False)),
            repeat_duration_s=float(getattr(row, "repeat_duration", 0.0)),
            linear_repeats=bool(getattr(row, "linear_repeats", False)),
            n_repeats=int(getattr(row, "repetitions", 1)),
            step_duration_s=float(getattr(row, "duration_s", 1.0)),
        ):
            electrodes = sorted(phase)
            channels = sorted(mapping[e] for e in electrodes if e in mapping)
            for e in electrodes:
                if e not in mapping:
                    logger.warning(
                        "electrode %r has no channel mapping; "
                        "actuation channel skipped", e,
                    )
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps({
                    "electrodes": electrodes,
                    "channels": channels,
                }),
            )
            ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=2.0)


def make_routes_column():
    return Column(
        model=RoutesColumnModel(
            col_id="routes", col_name="Routes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
    )
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v"
```

Expected: 13 passed (6 + 7).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/builtins/routes_column.py \
          pluggable_protocol_tree/tests/test_electrodes_routes_columns.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Routes column + RoutesHandler

List[List[str]] per-step routes with read-only "N routes" summary
view. Editing in PPT-3 is via the demo's SimpleDeviceViewer or
programmatic / JSON-load.

RoutesHandler at priority 30 (before DurationColumnHandler's 90)
walks iter_phases(), publishes each phase as a JSON envelope on
ELECTRODES_STATE_CHANGE (carrying both electrode IDs and resolved
channel numbers from the protocol's electrode_to_channel mapping),
and blocks on ctx.wait_for(ELECTRODES_STATE_APPLIED) before the
next phase. Duration timer only starts after the last phase ack.

Electrodes without a channel mapping are logged once at WARNING and
omitted from the channel array; the electrodes array still includes
them so subscribers can decide what to do.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Persistence — `protocol_metadata` round-trip

**Files:**
- Modify: `src/pluggable_protocol_tree/services/persistence.py`
- Modify: `src/pluggable_protocol_tree/models/row_manager.py` — `to_json` / `from_json` plumbing
- Modify: `src/pluggable_protocol_tree/tests/test_persistence.py` — append round-trip test + backward-compat

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_persistence.py`:

```python
# --- PPT-3: protocol_metadata in the JSON header ---

def test_protocol_metadata_round_trips():
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {"e00": 0, "e01": 1}
    rm.add_step(values={"name": "A"})

    payload = rm.to_json()
    assert payload["protocol_metadata"] == {"electrode_to_channel": {"e00": 0, "e01": 1}}

    rm2 = RowManager.from_json(payload, columns=list(cols))
    assert rm2.protocol_metadata == {"electrode_to_channel": {"e00": 0, "e01": 1}}


def test_protocol_metadata_missing_in_legacy_payload_loads_as_empty():
    """Backward-compat: a PPT-1/PPT-2 era JSON without the
    protocol_metadata key loads with manager.protocol_metadata == {}."""
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "A"})
    payload = rm.to_json()
    payload.pop("protocol_metadata", None)   # simulate older format

    rm2 = RowManager.from_json(payload, columns=list(cols))
    assert rm2.protocol_metadata == {}
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_persistence.py -v -k 'protocol_metadata'"
```

Expected: failures (round-trip test fails because `to_json` doesn't include the key yet).

- [ ] **Step 3: Update `serialize_tree` to include `protocol_metadata`**

In `src/pluggable_protocol_tree/services/persistence.py`, modify `serialize_tree`:

```python
def serialize_tree(root, columns, protocol_metadata=None):
    """Serialize the protocol tree + per-protocol metadata header.

    `protocol_metadata` is a dict of namespaced settings (PPT-3:
    'electrode_to_channel'). Optional for backward compat with
    PPT-1/PPT-2 callers that don't pass it.
    """
    col_specs = [...]    # keep existing logic
    fields = [...]       # keep existing logic
    rows_out = list(_walk(root, columns))    # keep existing logic
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "protocol_metadata": dict(protocol_metadata or {}),
        "columns": col_specs,
        "fields": fields,
        "rows": rows_out,
    }
```

(Substitute the existing helpers / variable names from the current implementation. Only the addition of the `protocol_metadata` argument and the new dict key matters.)

- [ ] **Step 4: Update `deserialize_tree` to extract `protocol_metadata`**

In the same file, change `deserialize_tree`'s signature/return so the metadata flows out:

```python
def deserialize_tree(data, columns, step_type, group_type):
    """... existing docstring ...

    Returns (root, protocol_metadata) tuple; protocol_metadata is an
    empty dict if the JSON predates PPT-3.
    """
    # ... existing logic that builds `root` ...
    metadata = dict(data.get("protocol_metadata") or {})
    return root, metadata
```

- [ ] **Step 5: Update `RowManager.to_json` / `from_json`**

In `src/pluggable_protocol_tree/models/row_manager.py`, find the existing `to_json` and `from_json` methods and update them.

Replace the `to_json` body (it's a one-liner today) with:

```python
    def to_json(self):
        """Serialize the tree + per-protocol metadata to a JSON-ready dict."""
        from pluggable_protocol_tree.services.persistence import serialize_tree
        return serialize_tree(
            self.root, list(self.columns),
            protocol_metadata=dict(self.protocol_metadata),
        )
```

Replace the `from_json` classmethod body with:

```python
    @classmethod
    def from_json(cls, data, columns):
        """Reconstruct a RowManager from a serialized payload."""
        from pluggable_protocol_tree.services.persistence import deserialize_tree
        manager = cls(columns=list(columns))
        root, metadata = deserialize_tree(
            data, columns,
            step_type=manager.step_type, group_type=manager.group_type,
        )
        manager.root = root
        manager.protocol_metadata = metadata
        return manager
```

- [ ] **Step 6: Run all persistence tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_persistence.py -v"
```

Expected: all existing tests pass + 2 new tests pass.

- [ ] **Step 7: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/services/persistence.py \
          pluggable_protocol_tree/models/row_manager.py \
          pluggable_protocol_tree/tests/test_persistence.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Persistence: protocol_metadata round-trip

JSON header gains a protocol_metadata block carrying per-protocol
namespaced settings (PPT-3 user: electrode_to_channel). Optional —
older PPT-1/PPT-2 era files without the key load with
manager.protocol_metadata == {}.

deserialize_tree now returns (root, metadata); RowManager.from_json
unpacks both. RowManager.to_json passes self.protocol_metadata
through serialize_tree.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Plugin updates — assemble new builtins + start() includes new wait_for_topics

**Files:**
- Modify: `src/pluggable_protocol_tree/plugin.py` — extend `_assemble_columns` with the 8 new column factories
- Modify: `src/pluggable_protocol_tree/tests/test_plugin.py` — append assertions

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_plugin.py`:

```python
# --- PPT-3 additions ---

def test_assemble_columns_includes_electrodes_and_routes():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()]
    assert "electrodes" in ids
    assert "routes" in ids


def test_assemble_columns_includes_six_hidden_config_columns():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()]
    for hid in ("trail_length", "trail_overlay", "soft_start",
                "soft_end", "repeat_duration", "linear_repeats"):
        assert hid in ids


def test_assemble_columns_canonical_order_after_ppt3():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()
           if c.model.col_id in (
               "type", "id", "name", "repetitions", "duration_s",
               "electrodes", "routes",
               "trail_length", "trail_overlay", "soft_start", "soft_end",
               "repeat_duration", "linear_repeats",
           )]
    assert ids == [
        "type", "id", "name", "repetitions", "duration_s",
        "electrodes", "routes",
        "trail_length", "trail_overlay", "soft_start", "soft_end",
        "repeat_duration", "linear_repeats",
    ]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_plugin.py -v -k 'electrodes or six_hidden or canonical_order_after'"
```

Expected: failures (the new columns aren't in `_assemble_columns` yet).

- [ ] **Step 3: Add the 8 new factories to `_assemble_columns`**

In `src/pluggable_protocol_tree/plugin.py`, add the imports near the top (alphabetical with the existing builtin imports):

```python
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.linear_repeats_column import make_linear_repeats_column
from pluggable_protocol_tree.builtins.repeat_duration_column import make_repeat_duration_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import make_soft_start_column
from pluggable_protocol_tree.builtins.trail_length_column import make_trail_length_column
from pluggable_protocol_tree.builtins.trail_overlay_column import make_trail_overlay_column
```

Replace the existing `_assemble_columns` body:

```python
    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_repetitions_column(),
            make_duration_column(),
            make_electrodes_column(),
            make_routes_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
            make_soft_start_column(),
            make_soft_end_column(),
            make_repeat_duration_column(),
            make_linear_repeats_column(),
        ]
        try:
            contributed = list(self.contributed_columns)
        except Exception:
            contributed = []     # no extension registry attached (e.g. headless)
        return builtins + contributed
```

- [ ] **Step 4: Run all plugin tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_plugin.py -v"
```

Expected: all pass. The plugin's `start()` already aggregates `wait_for_topics` from every contributed handler (PPT-2 work), so `RoutesHandler.wait_for_topics = [ELECTRODES_STATE_APPLIED]` gets registered automatically — no further changes needed in `start()`.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/plugin.py \
          pluggable_protocol_tree/tests/test_plugin.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Plugin: ship 8 new builtins (electrodes/routes + 6 hidden config)

_assemble_columns now ships, in canonical order:
  type, id, name, repetitions, duration_s,
  electrodes, routes,
  trail_length, trail_overlay, soft_start, soft_end,
  repeat_duration, linear_repeats,
  + contributed.

The plugin's start() already aggregates wait_for_topics from every
contributed handler (PPT-2 work); RoutesHandler's
wait_for_topics=[ELECTRODES_STATE_APPLIED] gets registered
automatically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Tree widget — hide hidden_by_default + header context menu

**Files:**
- Modify: `src/pluggable_protocol_tree/views/tree_widget.py`

This task has no unit tests — it's a UI behaviour change, exercised via the demo at Task 16. Smoke import + behavioural check below.

- [ ] **Step 1: Add the hide-on-attach + header menu wiring**

Open `src/pluggable_protocol_tree/views/tree_widget.py`. After the line that calls `self.tree.setModel(self.model)`, insert:

```python
        # PPT-3: hide columns marked hidden_by_default at construction
        for i, col in enumerate(self._manager.columns):
            if getattr(col.view, "hidden_by_default", False):
                self.tree.setColumnHidden(i, True)

        # PPT-3: header right-click menu to toggle column visibility
        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)
```

Then add a method (place it near the existing `_on_context_menu` method):

```python
    def _on_header_context_menu(self, pos):
        """Header right-click → menu listing every column with a
        toggleable 'Show' checkmark. Affects only the QTreeView's
        column visibility — does not touch the underlying row data."""
        menu = QMenu()
        for i, col in enumerate(self._manager.columns):
            action = menu.addAction(col.model.col_name)
            action.setCheckable(True)
            action.setChecked(not self.tree.isColumnHidden(i))

            def _toggle(checked, idx=i):
                self.tree.setColumnHidden(idx, not checked)

            action.toggled.connect(_toggle)
        menu.exec(self.tree.header().viewport().mapToGlobal(pos))
```

- [ ] **Step 2: Smoke-test that the widget still imports and constructs**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget; print(ProtocolTreeWidget)'"
```

Expected: prints the class.

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ --ignore=pluggable_protocol_tree/tests/tests_with_redis_server_need 2>&1 | tail -3"
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/views/tree_widget.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Tree widget: honor hidden_by_default + header right-click menu

Two small additions to ProtocolTreeWidget:

- After model attach, iterate columns and call
  tree.setColumnHidden(i, True) for any column whose
  view.hidden_by_default is True. PPT-1's BaseColumnView already
  declared the trait; this is its first consumer.
- Header right-click brings up a menu listing every column with a
  toggleable Show checkmark. Lets the user opt-in to the trail/loop/
  ramp config columns when they want to tweak them. Affects only Qt
  column visibility — the underlying row data is unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `SimpleDeviceViewer` widget

**Files:**
- Create: `src/pluggable_protocol_tree/demos/simple_device_viewer.py`

This widget is exercised manually via the demo at Task 14 + smoke-imported here. UI tests are minimal — Qt rendering is hard to assert programmatically.

- [ ] **Step 1: Implement the widget**

Create `src/pluggable_protocol_tree/demos/simple_device_viewer.py`:

```python
"""5x5 grid widget for the demo. NOT the production device viewer.

Two modes:
  Static: clicks toggle electrode IDs into row.electrodes
  Route:  clicks append electrode IDs to an in-progress route;
          Finish Route commits to row.routes; Clear discards.

Live actuation overlay: set_actuated() is called by an external
listener (the demo's actuation subscription) and paints those cells
bright green. Wired in run_widget.py.
"""

from typing import Iterable, Optional, Set

from pyface.qt.QtCore import QPoint, QRect, Qt, Signal
from pyface.qt.QtGui import QBrush, QColor, QPainter, QPen
from pyface.qt.QtWidgets import (
    QButtonGroup, QGridLayout, QHBoxLayout, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)


GRID_W = 5
GRID_H = 5
CELL_PX = 60
GRID_PADDING = 6


def _electrode_id(i: int) -> str:
    return f"e{i:02d}"


class SimpleDeviceViewer(QWidget):
    """Exposes set_active_row(row) and set_actuated(electrode_ids).
    Mutates row.electrodes / row.routes directly when the user clicks."""

    GRID_W = GRID_W
    GRID_H = GRID_H

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._active_row = None
        self._actuated: Set[str] = set()
        self._mode = "static"
        self._in_progress_route: list = []

        # Toolbar
        self._mode_static = QRadioButton("Static")
        self._mode_static.setChecked(True)
        self._mode_route = QRadioButton("Route")
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._mode_static)
        mode_group.addButton(self._mode_route)
        self._mode_static.toggled.connect(self._on_mode_changed)

        self._finish_btn = QPushButton("Finish Route")
        self._clear_btn = QPushButton("Clear")
        self._finish_btn.clicked.connect(self._finish_route)
        self._clear_btn.clicked.connect(self._clear_route)
        self._finish_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._mode_static)
        toolbar.addWidget(self._mode_route)
        toolbar.addWidget(self._finish_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addStretch()

        outer = QVBoxLayout(self)
        outer.addLayout(toolbar)
        outer.addStretch()

        self.setMinimumSize(
            GRID_W * CELL_PX + 2 * GRID_PADDING,
            GRID_H * CELL_PX + 2 * GRID_PADDING + 40,
        )

    # ---------- public API ----------

    def set_active_row(self, row):
        """Called when the tree's selection changes AND when the
        executor's step_started fires."""
        self._active_row = row
        self._in_progress_route = []
        self._update_route_button_state()
        self.update()

    def set_actuated(self, electrode_ids: Iterable[str]):
        """Called by the actuation subscription with the current phase's
        electrode set. Paints those cells green on top of the static /
        route layers."""
        self._actuated = set(electrode_ids or [])
        self.update()

    # ---------- mode ----------

    def _on_mode_changed(self, _checked):
        self._mode = "static" if self._mode_static.isChecked() else "route"
        self._update_route_button_state()

    def _update_route_button_state(self):
        in_route_mode = self._mode == "route"
        self._finish_btn.setEnabled(in_route_mode and bool(self._in_progress_route))
        self._clear_btn.setEnabled(in_route_mode and bool(self._in_progress_route))

    # ---------- grid geometry ----------

    def _grid_origin(self) -> QPoint:
        return QPoint(GRID_PADDING, 40 + GRID_PADDING)

    def _cell_rect(self, idx: int) -> QRect:
        col = idx % GRID_W
        row = idx // GRID_W
        origin = self._grid_origin()
        return QRect(origin.x() + col * CELL_PX,
                     origin.y() + row * CELL_PX,
                     CELL_PX - 2, CELL_PX - 2)

    def _cell_center(self, idx: int) -> QPoint:
        r = self._cell_rect(idx)
        return QPoint(r.x() + r.width() // 2, r.y() + r.height() // 2)

    def _hit_cell(self, pt: QPoint) -> Optional[int]:
        for i in range(GRID_W * GRID_H):
            if self._cell_rect(i).contains(pt):
                return i
        return None

    # ---------- click handling ----------

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._active_row is None:
            return
        idx = self._hit_cell(event.position().toPoint())
        if idx is None:
            return
        eid = _electrode_id(idx)
        if self._mode == "static":
            current = list(self._active_row.electrodes)
            if eid in current:
                current.remove(eid)
            else:
                current.append(eid)
            self._active_row.electrodes = current
        else:
            self._in_progress_route.append(eid)
            self._update_route_button_state()
        self.update()

    def _finish_route(self):
        if self._active_row is not None and self._in_progress_route:
            self._active_row.routes = list(self._active_row.routes) + [
                list(self._in_progress_route),
            ]
        self._in_progress_route = []
        self._update_route_button_state()
        self.update()

    def _clear_route(self):
        self._in_progress_route = []
        self._update_route_button_state()
        self.update()

    # ---------- painting ----------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        statics = set(getattr(self._active_row, "electrodes", []) or [])
        routes = list(getattr(self._active_row, "routes", []) or [])

        # 1. Cells
        for i in range(GRID_W * GRID_H):
            eid = _electrode_id(i)
            r = self._cell_rect(i)
            if eid in self._actuated:
                p.setBrush(QBrush(QColor(40, 220, 80)))    # bright green
            elif eid in statics:
                p.setBrush(QBrush(QColor(255, 230, 90)))   # yellow
            else:
                p.setBrush(QBrush(QColor(220, 220, 220)))  # light gray
            p.setPen(QPen(QColor(80, 80, 80), 1))
            p.drawRect(r)
            p.drawText(r, Qt.AlignCenter, eid)

        # 2. Route lines (solid)
        p.setPen(QPen(QColor(60, 60, 200), 3))
        for route in routes:
            for a, b in zip(route, route[1:]):
                ai = _id_to_idx(a)
                bi = _id_to_idx(b)
                if ai is None or bi is None:
                    continue
                p.drawLine(self._cell_center(ai), self._cell_center(bi))

        # 3. In-progress route (dashed)
        if self._in_progress_route:
            p.setPen(QPen(QColor(60, 60, 200), 2, Qt.DashLine))
            for a, b in zip(self._in_progress_route, self._in_progress_route[1:]):
                ai = _id_to_idx(a)
                bi = _id_to_idx(b)
                if ai is None or bi is None:
                    continue
                p.drawLine(self._cell_center(ai), self._cell_center(bi))
            # Outline the in-progress cells
            for eid in self._in_progress_route:
                idx = _id_to_idx(eid)
                if idx is not None:
                    p.setPen(QPen(QColor(60, 60, 200), 2, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(self._cell_rect(idx))

        p.end()


def _id_to_idx(eid: str) -> Optional[int]:
    """'e07' → 7. Returns None if the id isn't in this grid's namespace."""
    if not eid.startswith("e"):
        return None
    try:
        idx = int(eid[1:])
    except ValueError:
        return None
    if 0 <= idx < GRID_W * GRID_H:
        return idx
    return None
```

- [ ] **Step 2: Smoke-test that the widget imports**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.demos.simple_device_viewer import SimpleDeviceViewer, _electrode_id, _id_to_idx; assert _electrode_id(7) == \"e07\"; assert _id_to_idx(\"e07\") == 7; print(\"OK\")'"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/demos/simple_device_viewer.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] SimpleDeviceViewer demo widget

5x5 grid (electrodes e00..e24). Two modes selected via radio buttons:
- Static: click toggles the cell into row.electrodes.
- Route: click appends to an in-progress route; Finish Route commits
  to row.routes (a fresh list); Clear discards.

paintEvent draws cells (green if currently actuated, yellow if
static, gray otherwise) plus solid lines connecting consecutive
electrodes in each row.routes entry, plus a dashed line + outline
for the in-progress route.

set_actuated(electrode_ids) is called by the demo wiring
(subscribed to ELECTRODES_STATE_CHANGE) for the live overlay.
set_active_row(row) is called from both the tree's selection change
and the executor's step_started signal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: `electrode_responder.py`

**Files:**
- Create: `src/pluggable_protocol_tree/demos/electrode_responder.py`

- [ ] **Step 1: Implement the responder**

Create `src/pluggable_protocol_tree/demos/electrode_responder.py`:

```python
"""In-process Dramatiq actor that stands in for a hardware electrode
controller. Subscribes to ELECTRODES_STATE_CHANGE, sleeps a small
'apply' delay, then publishes ELECTRODES_STATE_APPLIED.

The demo's run_widget.py registers this actor's subscription with the
message router and starts a Dramatiq worker so it actually fires.
"""

import logging
import time

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED,
)


logger = logging.getLogger(__name__)

DEMO_RESPONDER_ACTOR_NAME = "ppt_demo_electrode_responder"
DEMO_APPLY_DELAY_S = 0.05


@dramatiq.actor(actor_name=DEMO_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_electrode_responder(message: str, topic: str,
                               timestamp: float = None):
    """Hardware-controller stand-in. ~50ms apply delay, acks."""
    logger.debug("[demo electrode responder] received %r on %s", message, topic)
    time.sleep(DEMO_APPLY_DELAY_S)
    publish_message(message="ok", topic=ELECTRODES_STATE_APPLIED)
```

- [ ] **Step 2: Smoke-test the import and actor registration**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c '
import dramatiq
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME, _demo_electrode_responder,
)
assert DEMO_RESPONDER_ACTOR_NAME in dramatiq.get_broker().actors
print(\"OK\")
'"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/demos/electrode_responder.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Demo electrode_responder Dramatiq actor

Stand-in for a hardware electrode controller. Subscribes to
ELECTRODES_STATE_CHANGE, sleeps 50ms (simulated apply), publishes
ELECTRODES_STATE_APPLIED. The demo's run_widget.py registers its
subscription with the message router and starts a worker so it fires.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Demo `run_widget.py` — embed SimpleDeviceViewer + actuation overlay

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/run_widget.py`

- [ ] **Step 1: Add new imports near the top of `run_widget.py`**

In `src/pluggable_protocol_tree/demos/run_widget.py`, add these imports alongside the existing demo imports (alphabetical):

```python
from pyface.qt.QtWidgets import QSplitter

from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
```

- [ ] **Step 2: Replace `setCentralWidget(self.widget)` with a QSplitter holding both**

Find the line `self.setCentralWidget(self.widget)` and replace the surrounding block (the construction of `self.widget` is fine; we're adding the device viewer alongside) with:

```python
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.device_view = SimpleDeviceViewer(self.manager, parent=self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        splitter.addWidget(self.device_view)
        splitter.setSizes([700, 400])
        self.setCentralWidget(splitter)
```

- [ ] **Step 3: Seed protocol_metadata electrode→channel mapping**

After the `splitter` block above, add:

```python
        # Seed the electrode→channel mapping. e00..e24 → channels 0..24.
        # The RoutesHandler reads this from ProtocolContext.scratch.
        self.manager.protocol_metadata["electrode_to_channel"] = {
            f"e{i:02d}": i for i in range(GRID_W * GRID_H)
        }
```

- [ ] **Step 4: Wire the device viewer to the active row**

Add (after the existing executor signal wiring in `_wire_signals`, or just below the seed block above):

```python
        # PPT-3: device viewer follows the tree's selection AND the
        # executor's currently-running step.
        sel_model = self.widget.tree.selectionModel()
        sel_model.currentRowChanged.connect(
            lambda cur, _prev: self.device_view.set_active_row(
                cur.data(Qt.UserRole) if cur.isValid() else None
            )
        )
        self.executor.qsignals.step_started.connect(
            self.device_view.set_active_row
        )
```

- [ ] **Step 5: Subscribe to ELECTRODES_STATE_CHANGE for the live overlay**

Update `_setup_dramatiq_routing` in `DemoWindow` (the existing PPT-2 method) to also register the electrode responder's subscriptions. After the existing `add_subscriber_to_topic` calls for the ack-roundtrip column, add:

```python
            # PPT-3: actuation chain
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
            )
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_APPLIED,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
            # And a tiny consumer that paints the live overlay in the demo.
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name="ppt_demo_actuation_overlay_listener",
            )
```

Then (still inside `DemoWindow`, near other actor declarations) add:

```python
import json   # at module top alongside the other imports if not already there


# Module-level Dramatiq actor for live overlay updates. Captures
# self.device_view via a global hook set by DemoWindow.__init__.
_overlay_target = {"viewer": None}


@dramatiq.actor(actor_name="ppt_demo_actuation_overlay_listener",
                queue_name="default")
def _overlay_listener(message: str, topic: str, timestamp: float = None):
    viewer = _overlay_target["viewer"]
    if viewer is None:
        return
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return
    electrodes = payload.get("electrodes", []) or []
    # Marshal into the GUI thread via a queued connection. Use
    # QMetaObject.invokeMethod with QueuedConnection.
    from pyface.qt.QtCore import QMetaObject, Q_ARG
    QMetaObject.invokeMethod(
        viewer, "set_actuated_qt_safe", Qt.QueuedConnection,
        Q_ARG(object, set(electrodes)),
    )
```

(The existing PPT-2 demo already imports `dramatiq`; reuse it. `Q_ARG` and `QMetaObject` come from `pyface.qt.QtCore`.)

In `DemoWindow.__init__` (after the device_view is constructed), set the hook:

```python
        _overlay_target["viewer"] = self.device_view
```

- [ ] **Step 6: Add a Qt slot on SimpleDeviceViewer that the overlay listener can invoke**

Open `src/pluggable_protocol_tree/demos/simple_device_viewer.py` and add at the top of the class:

```python
    from pyface.qt.QtCore import Slot, Qt

    # ... at the top of the SimpleDeviceViewer class body, near
    # set_actuated, add:

    @Slot(object)
    def set_actuated_qt_safe(self, electrode_ids):
        """Qt-decorated slot — the actuation listener calls this via
        QMetaObject.invokeMethod with QueuedConnection so the actual
        widget mutation runs on the GUI thread."""
        self.set_actuated(electrode_ids)
```

(Move the `from pyface.qt.QtCore import` line at the top of the file — currently `from pyface.qt.QtCore import QPoint, QRect, Qt, Signal` — to also include `Slot`. Don't double-import.)

- [ ] **Step 7: Smoke-test the demo imports**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.demos.run_widget import DemoWindow; print(\"OK\")'"
```

Expected: `OK`.

- [ ] **Step 8: Run the full unit suite**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ --ignore=pluggable_protocol_tree/tests/tests_with_redis_server_need 2>&1 | tail -3"
```

Expected: all green.

- [ ] **Step 9: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/demos/run_widget.py \
          pluggable_protocol_tree/demos/simple_device_viewer.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Demo: embed SimpleDeviceViewer + actuation overlay

DemoWindow now hosts a QSplitter with ProtocolTreeWidget on the
left and SimpleDeviceViewer on the right (sizes 700/400 by
default). manager.protocol_metadata seeded with a 25-electrode
identity mapping (e00→0 .. e24→24).

Tree selection + executor step_started both call
device_view.set_active_row so the viewer follows whatever is
currently being edited / executed.

Live actuation overlay: a small ppt_demo_actuation_overlay_listener
Dramatiq actor subscribes to ELECTRODES_STATE_CHANGE, parses the
JSON envelope, and forwards to SimpleDeviceViewer via
QMetaObject.invokeMethod(QueuedConnection) so the GUI mutation
happens on the GUI thread.

The existing PPT-2 routing-setup helper is extended to register the
electrode responder + executor_listener + overlay subscriptions for
the actuation topics.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Redis-backed integration test for RoutesHandler

**Files:**
- Create: `src/pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py`

- [ ] **Step 1: Write the integration test**

Create `src/pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py`:

```python
"""End-to-end test for the RoutesHandler chain against a real broker.

Flow exercised:
  RoutesHandler.on_step → publish_message(ELECTRODES_STATE_CHANGE)
                       → message_router → demo electrode_responder
                       → publish_message(ELECTRODES_STATE_APPLIED)
                       → message_router → executor_listener
                       → mailbox → ctx.wait_for() returns
                       → next phase
"""

import json
import threading
import time

import dramatiq
import pytest
from dramatiq import Worker
from pyface.qt.QtCore import Qt

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
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
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
# Importing the listener module registers its dramatiq actor.
from pluggable_protocol_tree.execution import listener as _listener  # noqa
from pluggable_protocol_tree.models.row_manager import RowManager


PHASE_SPY_ACTOR_NAME = "ppt_test_phase_spy"
_phase_spy_log: list = []


@dramatiq.actor(actor_name=PHASE_SPY_ACTOR_NAME, queue_name="default")
def _phase_spy(message: str, topic: str, timestamp: float = None):
    """Records every ELECTRODES_STATE_CHANGE for assertion."""
    _phase_spy_log.append(json.loads(message))


def _all_columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
    ]


def test_routes_handler_publishes_phases_and_unblocks_on_ack(router_actor):
    """One step with electrodes=['e00','e01'] + routes=[['e02','e03','e04']]
    + trail_length=1 → 3 phases, each unioned with the static set,
    each ack'd by the demo electrode_responder."""
    _phase_spy_log.clear()

    # Subscribe responder + listener + spy.
    subs = (
        (ELECTRODES_STATE_CHANGE, DEMO_RESPONDER_ACTOR_NAME),
        (ELECTRODES_STATE_APPLIED,
         "pluggable_protocol_tree_executor_listener"),
        (ELECTRODES_STATE_CHANGE, PHASE_SPY_ACTOR_NAME),
    )
    for topic, actor_name in subs:
        try:
            router_actor.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=actor_name,
            )
        except Exception:
            pass
        router_actor.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=actor_name,
        )

    broker = dramatiq.get_broker()
    broker.flush_all()
    try:
        cols = _all_columns()
        rm = RowManager(columns=cols)
        rm.protocol_metadata["electrode_to_channel"] = {
            f"e{i:02d}": i for i in range(25)
        }
        rm.add_step(values={
            "name": "S",
            "duration_s": 0.1,    # short dwell so total test stays fast
            "electrodes": ["e00", "e01"],
            "routes": [["e02", "e03", "e04"]],
            "trail_length": 1,
            "trail_overlay": 0,
        })

        ex = ProtocolExecutor(
            row_manager=rm,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )
        finished = threading.Event()
        ex.qsignals.protocol_finished.connect(
            finished.set, type=Qt.DirectConnection,
        )

        worker = Worker(broker, worker_timeout=100)
        worker.start()
        try:
            ex.start()
            assert finished.wait(timeout=15.0), \
                "protocol_finished did not fire within 15s"
            ex.wait(timeout=2.0)
        finally:
            worker.stop()

        # 3 phases — one per route position.
        assert len(_phase_spy_log) == 3, f"phases: {_phase_spy_log!r}"
        # Each phase = static ∪ {single route electrode}.
        assert _phase_spy_log[0]["electrodes"] == ["e00", "e01", "e02"]
        assert _phase_spy_log[1]["electrodes"] == ["e00", "e01", "e03"]
        assert _phase_spy_log[2]["electrodes"] == ["e00", "e01", "e04"]
        # Channel resolution from the seeded mapping.
        assert _phase_spy_log[0]["channels"] == [0, 1, 2]
        assert _phase_spy_log[1]["channels"] == [0, 1, 3]
        assert _phase_spy_log[2]["channels"] == [0, 1, 4]
    finally:
        for topic, actor_name in subs:
            try:
                router_actor.message_router_data.remove_subscriber_from_topic(
                    topic=topic, subscribing_actor_name=actor_name,
                )
            except Exception:
                pass
```

- [ ] **Step 2: Run the test (Redis must be up)**

Start Redis (e.g. `pixi run bash -c "cd src && python examples/start_redis_server.py"` in another shell), then:

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py -v"
```

Expected: 1 passed.

If Redis isn't up, the existing conftest will skip the test. Bring Redis up before reporting completion.

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py && \
  git commit -m "$(cat <<'EOF'
[PPT-3] Redis integration test: RoutesHandler full chain

End-to-end test exercising:
  publish(ELECTRODES_STATE_CHANGE)
    → message_router
    → demo electrode_responder (50ms simulated apply delay)
    → publish(ELECTRODES_STATE_APPLIED)
    → message_router
    → executor_listener
    → mailbox
    → ctx.wait_for returns
    → next phase

Asserts 3 phases for a 3-electrode route + 2-electrode static set,
each phase = static ∪ single route position, channels resolved
from the seeded electrode_to_channel mapping.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Final verification + push + PR

**Files:** none (git/gh + manual verification)

- [ ] **Step 1: Run the full PPT test suite (no Redis)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ -v --ignore=pluggable_protocol_tree/tests/tests_with_redis_server_need 2>&1 | tail -5"
```

Expected: all green. New tests added by PPT-3: ~36 in `test_phase_math.py`, ~13 in `test_electrodes_routes_columns.py`, 6 in `test_hidden_columns.py`, 3 in `test_plugin.py`, 2 in `test_persistence.py`, 2 in `test_row_manager.py` — on top of the PPT-1 + PPT-2 baseline.

- [ ] **Step 2: Run Redis integration tests (with Redis up)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/ -v 2>&1 | tail -5"
```

Expected: all green (PPT-2's 2 + PPT-3's 1 = 3 tests).

- [ ] **Step 3: Manual demo verification**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python -m pluggable_protocol_tree.demos.run_widget
```

Manual checks:
- Tree appears on the left, 5x5 grid on the right (resizable splitter).
- Right-click → Add Step. Select the new step in the tree.
- Click cells in the grid (Static mode default) — they turn yellow. Cell `electrodes` column updates to "N electrodes".
- Switch to Route mode. Click cells in sequence — dashed outline. Click "Finish Route" — solid blue line connecting them. Cell `routes` column updates to "N routes".
- Right-click the tree header → toggle one of the hidden columns visible (e.g. "Trail Len"). It appears.
- Click Run. The active-row highlight walks down the tree. The grid lights cells green per phase as the RoutesHandler publishes them.
- Pause / Resume / Stop work. Highlight clears on Stop.

- [ ] **Step 4: Verify clean tree + branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git status --short && git log --oneline feat/ppt-3-electrodes-routes --not main
```

Expected: clean status (or only pre-existing modifications you've kept). The `git log` shows the spec commit + ~16 PPT-3 commits.

- [ ] **Step 5: Push the branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git push -u origin feat/ppt-3-electrodes-routes
```

- [ ] **Step 6: Open the PR**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && gh pr create \
  --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "[PPT-3] Electrodes + Routes columns + simplified phase math + simple device viewer" \
  --body "$(cat <<'EOF'
Closes #365

## Summary

Ships the per-step electrode actuation layer for the new pluggable
protocol tree:

- **Two complex columns**: \`electrodes: List[Str]\` (held active for the
  step) + \`routes: List[List[Str]]\` (paths to traverse). Read-only
  summary cells; editing in PPT-3 happens via the demo's
  \`SimpleDeviceViewer\`.
- **Six hidden config columns**: \`trail_length\`, \`trail_overlay\`,
  \`soft_start\`, \`soft_end\`, \`repeat_duration\`, \`linear_repeats\`.
  Header right-click menu toggles them visible.
- **\`services/phase_math.py\`** — clean pure-function rewrite of the
  phase-generation logic. ~150 lines vs the legacy ~600. Composed of
  small one-job helpers (\`_route_windows\`, \`_route_with_repeats\`,
  \`_zip_with_static\`, \`_ramp_up\`, \`_ramp_down\`).
- **\`RoutesHandler\`** at priority 30. Walks \`iter_phases()\`, publishes
  each phase as a JSON envelope on \`ELECTRODES_STATE_CHANGE\` (carrying
  electrode IDs + resolved channel numbers), blocks on
  \`ctx.wait_for(ELECTRODES_STATE_APPLIED)\` before the next phase.
  Sequential vs DurationColumnHandler (priority 90) — the dwell timer
  only starts after the last phase ack.
- **\`RowManager.protocol_metadata\`** Dict trait persisted in the JSON
  header. PPT-3 uses it to carry \`electrode_to_channel: dict[str,int]\`,
  hydrated into \`ProtocolContext.scratch\` by the executor at run start.
  Forward-compat for any future per-protocol settings.
- **\`SimpleDeviceViewer\`** — 5x5 grid widget for the demo. NOT the
  production device viewer. Static / Route modes; live green overlay
  on currently-actuated cells subscribing to the actuation topic.
- **In-process \`electrode_responder\`** Dramatiq actor closes the loop
  with a 50ms simulated apply delay.

## Test plan

- [x] \`pytest pluggable_protocol_tree/tests/ -v --ignore=...tests_with_redis_server_need\` — all green
- [x] \`pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/\` — 3 tests pass with Redis up
- [ ] Manual demo: tree + grid side-by-side, Static/Route editing, header right-click toggles hidden columns, Run with the simple device viewer green overlay walking the route in lockstep with the active-row highlight.

## What's NOT in this PR (deferred per design)

- Touching \`device_viewer/\` plugin — left alone.
- Touching \`protocol_grid/services/path_execution_service.py\` — the legacy plugin keeps using its in-place phase math.
- Touching \`protocol_grid/state/device_state.py\` — \`DeviceState\` deletion is PPT-9.
- Replacing \`protocol_runner_controller.py\` — PPT-9.
- Production-device-viewer integration (\`STEP_PARAMS_COMMIT\` publishing on row select; subscribing to \`DEVICE_VIEWER_STATE_CHANGED\`) — small follow-up sub-issue or absorbed into PPT-9.

Design doc: \`src/docs/superpowers/specs/2026-04-23-ppt-3-electrodes-routes-design.md\`
Plan: \`src/docs/superpowers/plans/2026-04-23-ppt-3-electrodes-routes.md\`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: Confirm PR opens cleanly**

Copy the PR URL the command prints. Visit in browser; verify:
- Description renders.
- `Closes #365` link is detected.
- All commits show up in the timeline.

The umbrella issue's checklist should tick automatically on merge.

---

## Done

PPT-3 ships electrode actuation. PPT-4 picks up: voltage + frequency columns contributed by the dropbot_controller plugin, using the same publish/wait_for pattern PPT-2 / PPT-3 established. The phase math, persistence, hidden-column infrastructure, and demo conventions in this PR are reused as-is.
