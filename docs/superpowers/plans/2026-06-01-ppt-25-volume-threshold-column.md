# PPT-25 Volume Threshold Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the legacy `Volume Threshold` per-step column. Users enter a target droplet volume; the runner converts it to a target capacitance per phase (using calibration + actuated-electrode areas) and cuts the current phase short the moment measured capacitance reaches it.

**Architecture:** Two new `threading.Event`s on `StepContext` form the primitive: `phase_advance_event` (any handler sets it → `RoutesHandler._cooperative_sleep` wakes), `step_phases_done_event` (Routes sets it after its last phase → sibling handlers exit cleanly). A new sibling plugin `volume_threshold_protocol_controls` ships the column + a handler at priority 30 that subscribes to ELECTRODES_STATE_CHANGE / CAPACITANCE_UPDATED / CALIBRATION_DATA, computes target capacitance per phase, and sets the early-advance event when measured ≥ target. The dock pane seeds the live DV's per-electrode areas into a new `Executor.start(extra_scratch=...)` kwarg.

**Tech Stack:** Python 3, Traits/HasStrictTraits, Envisage plugins, pytest, `threading.Event`, dramatiq pub/sub.

**Spec:** `microdrop-py/src/docs/superpowers/specs/2026-06-01-ppt-25-volume-threshold-column-design.md`

**Working directory for all commands:** `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py` (where `pixi run pytest src/...` resolves correctly).

---

### Task 1: Add `phase_advance_event` + `step_phases_done_event` to `StepContext` + executor builder

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/step_context.py` (StepContext class)
- Modify: `src/pluggable_protocol_tree/execution/executor.py` (`_build_step_ctx`)
- Modify: `src/pluggable_protocol_tree/tests/test_step_context.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/pluggable_protocol_tree/tests/test_step_context.py`:

```python
def test_step_context_has_phase_advance_event_unset_by_default():
    """phase_advance_event is the early-phase-completion signal. New
    StepContexts must always start with it cleared so a stale set from
    a prior step can't leak in."""
    import threading
    from pluggable_protocol_tree.execution.step_context import (
        ProtocolContext, StepContext,
    )
    proto = ProtocolContext(stop_event=threading.Event())
    ctx = StepContext(protocol=proto, phase_advance_event=threading.Event(),
                      step_phases_done_event=threading.Event())
    assert ctx.phase_advance_event is not None
    assert ctx.phase_advance_event.is_set() is False
    assert ctx.step_phases_done_event is not None
    assert ctx.step_phases_done_event.is_set() is False


def test_executor_build_step_ctx_seeds_two_fresh_events():
    """Each call to _build_step_ctx must produce a fresh pair of
    threading.Events — a set leftover from the prior step must NOT
    appear on the next step."""
    import threading
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.execution.step_context import ProtocolContext
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    rm = RowManager(columns=[make_name_column()])
    rm.add_step()
    exe = ProtocolExecutor(row_manager=rm)
    proto = ProtocolContext(stop_event=threading.Event())
    row = rm.root.children[0]

    ctx_a = exe._build_step_ctx(row, list(rm.columns), proto)
    ctx_a.phase_advance_event.set()
    ctx_a.step_phases_done_event.set()

    ctx_b = exe._build_step_ctx(row, list(rm.columns), proto)
    assert ctx_b.phase_advance_event.is_set() is False
    assert ctx_b.step_phases_done_event.is_set() is False
    # And they must be distinct Event instances, not aliases.
    assert ctx_a.phase_advance_event is not ctx_b.phase_advance_event
    assert ctx_a.step_phases_done_event is not ctx_b.step_phases_done_event
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_step_context.py -v -k 'phase_advance_event or step_phases_done_event or build_step_ctx_seeds_two_fresh_events'
```

Expected: 2 failures — `TraitError` (unknown trait `phase_advance_event`) or AttributeError.

- [ ] **Step 3: Add the two traits to `StepContext`**

In `src/pluggable_protocol_tree/execution/step_context.py`, locate the `StepContext` class definition (around line 150). Add two new trait declarations alongside the existing `row`, `protocol`, `scratch`, `_mailboxes`:

```python
    phase_advance_event = Instance(threading.Event,
        desc="Set by any handler to cut the current phase short. "
             "Cleared on each phase boundary by RoutesHandler so a set "
             "carries through to the current phase only. "
             "RoutesHandler._cooperative_sleep wakes on it the same way "
             "it wakes on stop_event.")
    step_phases_done_event = Instance(threading.Event,
        desc="Set by RoutesHandler once after its per-phase loop returns. "
             "Lets sibling handlers in the same parallel bucket (notably "
             "VolumeThresholdHandler) exit their wait loops instead of "
             "blocking forever on a never-arriving next phase.")
```

`threading` is already imported at the top of the file.

- [ ] **Step 4: Initialise the events in `_build_step_ctx`**

In `src/pluggable_protocol_tree/execution/executor.py`, find `_build_step_ctx` (around line 302). Replace the `step_ctx = StepContext(row=row, protocol=proto_ctx)` line and the surrounding context construction to pass freshly-constructed events:

Current:
```python
        step_ctx = StepContext(row=row, protocol=proto_ctx)
```

Replace with:
```python
        # Fresh Events per step — never reused across steps so a stale
        # `set` from a prior step can't leak in.
        step_ctx = StepContext(
            row=row, protocol=proto_ctx,
            phase_advance_event=threading.Event(),
            step_phases_done_event=threading.Event(),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_step_context.py -v -k 'phase_advance_event or step_phases_done_event or build_step_ctx_seeds_two_fresh_events'
```

Expected: 2 passed.

- [ ] **Step 6: Full step_context + executor regression**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_step_context.py src/pluggable_protocol_tree/tests/test_executor.py -v
```

Expected: all previously-green stay green.

- [ ] **Step 7: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/pluggable_protocol_tree/execution/step_context.py src/pluggable_protocol_tree/execution/executor.py src/pluggable_protocol_tree/tests/test_step_context.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] StepContext: per-step phase_advance_event + step_phases_done_event"
```

---

### Task 2: `_cooperative_sleep` honours `phase_advance_event` + RoutesHandler clears/sets events

**Files:**
- Modify: `src/pluggable_protocol_tree/builtins/routes_column.py`
- Modify: `src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py`

- [ ] **Step 1: Write the failing tests**

Append to `src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py`:

```python
def test_cooperative_sleep_returns_early_on_phase_advance_event():
    """_cooperative_sleep wakes promptly when phase_advance_event is set,
    same shape as the existing stop_event wake — return cleanly (do NOT
    raise)."""
    import threading
    import time
    from pluggable_protocol_tree.builtins.routes_column import (
        _cooperative_sleep,
    )
    stop_event = threading.Event()
    pause_event = None
    advance_event = threading.Event()

    def _set_after(delay):
        time.sleep(delay)
        advance_event.set()

    threading.Thread(target=_set_after, args=(0.05,), daemon=True).start()
    t0 = time.monotonic()
    # 5 second dwell, but the advance_event fires at ~50 ms
    _cooperative_sleep(5.0, stop_event, pause_event,
                       phase_advance_event=advance_event)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"expected early return, elapsed={elapsed:.2f}s"


def test_cooperative_sleep_phase_advance_event_kwarg_is_optional():
    """Callers that don't care about phase early-advance can omit the
    kwarg and get the original behaviour."""
    import threading
    import time
    from pluggable_protocol_tree.builtins.routes_column import (
        _cooperative_sleep,
    )
    stop_event = threading.Event()
    t0 = time.monotonic()
    _cooperative_sleep(0.1, stop_event, None)
    elapsed = time.monotonic() - t0
    assert 0.05 <= elapsed < 0.5      # roughly the requested dwell


def test_routes_handler_clears_phase_advance_event_each_iteration(qapp):
    """RoutesHandler must clear the event at the TOP of each phase loop
    iteration so a set from phase N doesn't leak into phase N+1."""
    from unittest.mock import MagicMock, patch
    import threading
    from pluggable_protocol_tree.builtins.routes_column import (
        RoutesColumnHandler,
    )

    handler = RoutesColumnHandler()
    advance_event = threading.Event()
    advance_event.set()                # simulate stale set from prior phase

    row = MagicMock()
    row.routes = []                    # no routes -> single static phase
    row.electrodes = ["e1"]
    row.duration_s = 0.001
    row.route_repetitions = 1
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.repeat_duration_controls = False
    row.linear_repeats = False
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True          # skip hardware publish + ack wait
    proto.scratch = {"electrode_to_channel": {"e1": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = advance_event
    ctx.step_phases_done_event = threading.Event()
    ctx.wait_for = MagicMock()

    handler.on_step(row, ctx)
    # Even though the test pre-set the event, RoutesHandler must clear
    # it before entering the dwell (otherwise the single-phase wouldn't
    # actually sleep). Confirm by asserting the event ended up CLEARED
    # after on_step returns (Routes also has nothing left to set after
    # the loop exits).
    assert advance_event.is_set() is False


def test_routes_handler_sets_step_phases_done_event_when_loop_finishes(qapp):
    """After Routes finishes its per-phase loop (and any in-duration-mode
    hold), step_phases_done_event must be set so sibling handlers can
    exit their wait loops."""
    from unittest.mock import MagicMock
    import threading
    from pluggable_protocol_tree.builtins.routes_column import (
        RoutesColumnHandler,
    )

    handler = RoutesColumnHandler()
    row = MagicMock()
    row.routes = []
    row.electrodes = ["e1"]
    row.duration_s = 0.001
    row.route_repetitions = 1
    row.trail_length = 1
    row.trail_overlay = 0
    row.soft_start = False
    row.soft_end = False
    row.repeat_duration = 0.0
    row.repeat_duration_controls = False
    row.linear_repeats = False
    row.uuid = "u"
    row.path = (0,)

    proto = MagicMock()
    proto.stop_event = threading.Event()
    proto.pause_event = MagicMock(is_set=lambda: False)
    proto.preview_mode = True
    proto.scratch = {"electrode_to_channel": {"e1": 1}}
    proto.qsignals = MagicMock()

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()
    ctx.wait_for = MagicMock()

    assert ctx.step_phases_done_event.is_set() is False
    handler.on_step(row, ctx)
    assert ctx.step_phases_done_event.is_set() is True
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v -k 'cooperative_sleep_returns_early_on_phase_advance or cooperative_sleep_phase_advance_event_kwarg_is_optional or clears_phase_advance_event_each or sets_step_phases_done_event'
```

Expected: 4 failures — `TypeError: unexpected keyword argument 'phase_advance_event'` on `_cooperative_sleep`, AttributeError on `ctx.step_phases_done_event`.

- [ ] **Step 3: Extend `_cooperative_sleep`**

In `src/pluggable_protocol_tree/builtins/routes_column.py`, find `_cooperative_sleep` (around line 219). Replace it with:

```python
def _cooperative_sleep(seconds: float, stop_event, pause_event=None,
                       phase_advance_event=None) -> None:
    """Sleep for ``seconds``, waking every _SLICE_S to check stop_event
    (and pause_event if provided). Used so a Stop or Pause press lands
    within ~50ms even mid-dwell. On pause: block in
    ``pause_event.wait_cleared()`` until the user resumes, then
    continue with the remaining dwell. Returns early on stop, on
    phase_advance_event (any handler can set it to cut the phase short),
    or when seconds reaches 0."""
    remaining = seconds
    while remaining > 0:
        if stop_event.is_set():
            return
        if phase_advance_event is not None and phase_advance_event.is_set():
            return
        if pause_event is not None and pause_event.is_set():
            pause_event.wait_cleared()
            if stop_event.is_set():
                return
        slice_dur = min(_SLICE_S, remaining)
        time.sleep(slice_dur)
        remaining -= slice_dur
```

- [ ] **Step 4: Clear `phase_advance_event` at the top of each phase iteration + set `step_phases_done_event` after the loop + pass the event into `_cooperative_sleep`**

Still in `routes_column.py`, find `RoutesColumnHandler.on_step` (around line 100). Make three targeted edits:

**4a — At the top of the `for phase_idx, phase in enumerate(phases, start=1):` loop body**, add as the first executable line of the body:

```python
            # Fresh slate: a handler set in phase N-1 must NOT carry
            # over into phase N. Cleared before the stop/pause checks
            # below so a stale set doesn't accidentally fire here.
            ctx.phase_advance_event.clear()
```

**4b — In the same loop body**, find the existing `_cooperative_sleep(per_phase_dwell, stop_event, pause_event)` call and add the `phase_advance_event` kwarg:

```python
            _cooperative_sleep(per_phase_dwell, stop_event, pause_event,
                               phase_advance_event=ctx.phase_advance_event)
```

**4c — After the entire phase loop and after the in-duration-mode hold block**, just before `on_step` returns, add:

```python
        # Signal sibling parallel-bucket handlers (e.g.
        # VolumeThresholdHandler) that the per-phase loop is done so
        # they can exit their wait loops cleanly. Without this,
        # handlers blocked in wait_for(ELECTRODES_STATE_CHANGE) for a
        # next phase that will never come would block the bucket's
        # ThreadPoolExecutor indefinitely.
        ctx.step_phases_done_event.set()
```

Place this as the LAST statement in `on_step`, after any in-duration-mode hold (the existing `if in_duration_mode and not stop_event.is_set(): ...` block). Inside the existing `on_step`'s scope.

- [ ] **Step 5: Run tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v -k 'cooperative_sleep_returns_early_on_phase_advance or cooperative_sleep_phase_advance_event_kwarg_is_optional or clears_phase_advance_event_each or sets_step_phases_done_event'
```

Expected: 4 passed.

- [ ] **Step 6: Full routes/electrodes regression**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -v
```

Expected: all previously-green stay green.

- [ ] **Step 7: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/pluggable_protocol_tree/builtins/routes_column.py src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] RoutesHandler: honour phase_advance_event + signal step_phases_done_event"
```

---

### Task 3: `Executor.start(extra_scratch=...)` kwarg merges runtime-only scratch

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/executor.py`
- Modify: `src/pluggable_protocol_tree/tests/test_executor.py`

- [ ] **Step 1: Write the failing test**

Append to `src/pluggable_protocol_tree/tests/test_executor.py`:

```python
def test_executor_start_extra_scratch_merges_after_protocol_metadata():
    """`extra_scratch` is for runtime-only data (electrode areas etc.)
    that must NOT be serialised into the protocol file. It merges into
    proto_ctx.scratch AFTER protocol_metadata, so a key in extra_scratch
    overrides one with the same name in protocol_metadata."""
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    rm = RowManager(columns=[make_name_column()])
    rm.add_step()
    rm.protocol_metadata = {
        "electrode_to_channel": {"e1": 1},
        "override_me": "from_metadata",
    }

    from pluggable_protocol_tree.models.column import BaseColumnHandler

    seen = {}
    class _PeekHandler(BaseColumnHandler):
        priority = 50
        def on_protocol_start(self, ctx):
            seen.update(dict(ctx.scratch))

    # Inject a snooping column.
    rm.columns[0].handler = _PeekHandler()

    exe = ProtocolExecutor(row_manager=rm)
    exe.start(extra_scratch={
        "electrode_areas": {"e1": 1.5, "e2": 2.0},
        "override_me": "from_extra",
    })
    exe.wait(timeout=5.0)

    # Both metadata + extra are present; extra wins on the conflict.
    assert seen["electrode_to_channel"] == {"e1": 1}
    assert seen["electrode_areas"] == {"e1": 1.5, "e2": 2.0}
    assert seen["override_me"] == "from_extra"


def test_executor_start_extra_scratch_optional_defaults_to_none():
    """Callers that don't pass extra_scratch get the prior behaviour
    (only protocol_metadata in scratch)."""
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.models.column import BaseColumnHandler
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    rm = RowManager(columns=[make_name_column()])
    rm.add_step()
    rm.protocol_metadata = {"electrode_to_channel": {"e1": 1}}

    seen = {}
    class _PeekHandler(BaseColumnHandler):
        priority = 50
        def on_protocol_start(self, ctx):
            seen.update(dict(ctx.scratch))

    rm.columns[0].handler = _PeekHandler()

    exe = ProtocolExecutor(row_manager=rm)
    exe.start()
    exe.wait(timeout=5.0)

    assert seen == {"electrode_to_channel": {"e1": 1}}
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_executor.py -v -k 'extra_scratch'
```

Expected: 1 failure — `TypeError: start() got an unexpected keyword argument 'extra_scratch'`. (The second test will pass already because the kwarg-less call already works.)

- [ ] **Step 3: Add the `_extra_scratch` Trait attr + `start()` kwarg + merge in `run()`**

In `src/pluggable_protocol_tree/execution/executor.py`:

**3a — Add a private trait** alongside the existing `_start_step_path` / `_preview_mode` declarations (around line 66-70):

```python
    # Runtime-only scratch merged into ProtocolContext.scratch by run()
    # AFTER protocol_metadata. Use this for data that comes from the
    # live app at start time (e.g. electrode areas from the DV model)
    # and must NOT be persisted into the protocol JSON file.
    _extra_scratch = Any
```

**3b — Add the kwarg to `start()`**. Find the existing signature:

```python
    def start(
        self,
        start_step_path: Optional[tuple] = None,
        preview_mode: bool = False,
    ) -> None:
```

Replace with:

```python
    def start(
        self,
        start_step_path: Optional[tuple] = None,
        preview_mode: bool = False,
        extra_scratch: Optional[dict] = None,
    ) -> None:
```

In the body of `start()`, after `self._preview_mode = bool(preview_mode)`, add:

```python
        self._extra_scratch = dict(extra_scratch) if extra_scratch else None
```

**3c — Merge into `proto_ctx.scratch` in `run()`**. Find the existing line (around line 192):

```python
        proto_ctx.scratch.update(self.row_manager.protocol_metadata)
```

Add immediately after it:

```python
        # Runtime-only scratch (electrode areas, etc.) — merged AFTER
        # protocol_metadata so it wins on key collision.
        if self._extra_scratch:
            proto_ctx.scratch.update(self._extra_scratch)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_executor.py -v -k 'extra_scratch'
```

Expected: 2 passed.

- [ ] **Step 5: Full executor regression**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_executor.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/pluggable_protocol_tree/execution/executor.py src/pluggable_protocol_tree/tests/test_executor.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] Executor.start(extra_scratch=...): runtime-only scratch merge"
```

---

### Task 4: Scaffold the new `volume_threshold_protocol_controls` plugin

**Files (all NEW):**
- Create: `src/volume_threshold_protocol_controls/__init__.py`
- Create: `src/volume_threshold_protocol_controls/consts.py`
- Create: `src/volume_threshold_protocol_controls/plugin.py`
- Create: `src/volume_threshold_protocol_controls/protocol_columns/__init__.py`
- Create: `src/volume_threshold_protocol_controls/tests/__init__.py`
- Create: `src/volume_threshold_protocol_controls/tests/conftest.py`
- Create: `src/volume_threshold_protocol_controls/tests/test_plugin_shell.py`

- [ ] **Step 1: Write the failing test**

Create `src/volume_threshold_protocol_controls/tests/test_plugin_shell.py`:

```python
"""Plugin scaffold smoke tests."""

import volume_threshold_protocol_controls
from volume_threshold_protocol_controls.consts import PKG, PKG_name
from volume_threshold_protocol_controls.plugin import (
    VolumeThresholdProtocolControlsPlugin,
)


def test_package_importable():
    assert volume_threshold_protocol_controls is not None


def test_consts_derived_from_package_name():
    assert PKG == "volume_threshold_protocol_controls"
    assert PKG_name == "Volume Threshold Protocol Controls"


def test_plugin_id_and_name():
    p = VolumeThresholdProtocolControlsPlugin()
    assert p.id == "volume_threshold_protocol_controls.plugin"
    assert p.name == "Volume Threshold Protocol Controls Plugin"


def test_plugin_default_contributions_is_empty_until_task_6():
    """Column factory ships in Task 6. Scaffold must boot cleanly
    with no contributions so the rest of the plan can land in any
    order without breaking Envisage load."""
    p = VolumeThresholdProtocolControlsPlugin()
    assert isinstance(p.contributed_protocol_columns, list)
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: `ModuleNotFoundError: No module named 'volume_threshold_protocol_controls'`.

- [ ] **Step 3: Create the scaffold files**

`src/volume_threshold_protocol_controls/__init__.py`:
```python
"""Volume-threshold per-step column contribution (#437).

Architecture lives in pluggable_protocol_tree (StepContext events +
RoutesHandler hooks). This plugin ships the column + handler that
subscribes to ELECTRODES_STATE_CHANGE / CAPACITANCE_UPDATED /
CALIBRATION_DATA and sets ctx.phase_advance_event when measured
capacitance reaches the per-phase target.
"""
```

`src/volume_threshold_protocol_controls/consts.py`:
```python
"""Package-level constants.

PKG / PKG_name derived from __name__ (MicroDrop convention)."""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

VOLUME_THRESHOLD_COL_ID = "volume_threshold"
VOLUME_THRESHOLD_COL_NAME = "Volume Threshold"
VOLUME_THRESHOLD_DEFAULT = 0.0           # disabled

# Handler polling interval while waiting for the next phase boundary
# (ELECTRODES_STATE_CHANGE). Short so the handler exits within ~2s of
# Routes finishing — see step_phases_done_event in the spec.
PHASE_POLL_TIMEOUT_S = 2.0

# Polling interval while monitoring CAPACITANCE_UPDATED during a phase.
# Lets the handler re-check stop_event between samples.
CAP_POLL_TIMEOUT_S = 1.0
```

`src/volume_threshold_protocol_controls/plugin.py`:
```python
"""VolumeThresholdProtocolControlsPlugin — contributes the
volume-threshold per-step column to the pluggable protocol tree.

Pattern mirrors peripheral_protocol_controls /
dropbot_protocol_controls. The column factory lands in Task 6; the
scaffold lands first so plugin-load smoke tests pass.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name

logger = get_logger(__name__)


class VolumeThresholdProtocolControlsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        # Populated by Task 6 (column factory).
        return []
```

`src/volume_threshold_protocol_controls/protocol_columns/__init__.py`:
```python
"""IColumn implementations for the volume-threshold column."""
```

`src/volume_threshold_protocol_controls/tests/__init__.py` — empty file (touch).

`src/volume_threshold_protocol_controls/tests/conftest.py`:
```python
"""Session-scoped qapp fixture. Matches the per-plugin pattern used
in peripheral_protocol_controls / dropbot_protocol_controls /
protocol_quick_action_tools."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
```

- [ ] **Step 4: Run scaffold tests to verify they pass**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/volume_threshold_protocol_controls/
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] Scaffold volume_threshold_protocol_controls plugin"
```

---

### Task 5: `VolumeThresholdColumnModel` + view

**Files:**
- Create: `src/volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py`
- Create: `src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py`

- [ ] **Step 1: Write the failing test**

Create `src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py`:

```python
"""Volume-threshold column smoke tests.

This file grows over Tasks 5 and 6 — Task 5 adds model + view + factory
metadata tests, Task 6 adds handler behaviour tests."""

from volume_threshold_protocol_controls.consts import (
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)
from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
    make_volume_threshold_column,
)


def test_column_id_name_default():
    col = make_volume_threshold_column()
    assert col.model.col_id == VOLUME_THRESHOLD_COL_ID
    assert col.model.col_name == VOLUME_THRESHOLD_COL_NAME
    assert col.model.default_value == VOLUME_THRESHOLD_DEFAULT


def test_column_view_hidden_by_default_and_step_only():
    """Step-only column (no value on a group row); hidden by default
    in the column header — same posture as droplet_check and the trail
    /loop knobs. Surfaces via header right-click."""
    col = make_volume_threshold_column()
    assert col.view.hidden_by_default is True
    assert col.view.renders_on_group is False


def test_column_trait_is_float_with_default_zero():
    """trait_for_row must return a Float trait — the legacy column was
    a numeric volume; a string trait would silently accept garbage."""
    from traits.api import Float
    col = make_volume_threshold_column()
    trait = col.model.trait_for_row()
    assert isinstance(trait.handler, Float().handler.__class__)


def test_plugin_default_lists_the_column():
    """Task 6 wires the factory into the plugin's contribution list.
    Tested here so the scaffold-task placeholder gets a real value."""
    from volume_threshold_protocol_controls.plugin import (
        VolumeThresholdProtocolControlsPlugin,
    )
    p = VolumeThresholdProtocolControlsPlugin()
    contribs = p._contributed_protocol_columns_default()
    assert len(contribs) == 1
    assert contribs[0].model.col_id == VOLUME_THRESHOLD_COL_ID
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py -v
```

Expected: `ImportError: cannot import name 'make_volume_threshold_column'`.

- [ ] **Step 3: Create the column file (model + view + factory; handler stub for Task 6)**

Create `src/volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py`:

```python
"""Volume-threshold per-step column: model + view + handler + factory.

Single-file layout mirrors peripheral_protocol_controls's magnet_column
and dropbot_protocol_controls's voltage / frequency / droplet columns.

The handler is a stub in Task 5; the real on_step body lands in Task 6.
"""

from traits.api import Float

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)

from ..consts import (
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)


class VolumeThresholdColumnModel(BaseColumnModel):
    """Per-step volume threshold (user units, typically µL). 0 disables.

    Stored as a Float trait. The unit is unit-agnostic from the
    column's perspective — the handler multiplies it into the
    target-capacitance formula and the user picks the unit by
    convention with their calibration data.
    """

    def trait_for_row(self):
        return Float(float(self.default_value or 0.0),
                     desc="Volume threshold for this step. Reaches "
                          "target capacitance early-ends the phase. "
                          "0 disables.")


class VolumeThresholdColumnView(DoubleSpinBoxColumnView):
    """Numeric edit; hidden by default like droplet_check / trail knobs.
    User opts the column in via the header right-click menu when they
    want volume-threshold behaviour on a step."""

    renders_on_group = False
    hidden_by_default = True


class VolumeThresholdHandler(BaseColumnHandler):
    """Stub. Task 6 fills in the on_step body that subscribes to
    ELECTRODES_STATE_CHANGE / CAPACITANCE_UPDATED / CALIBRATION_DATA,
    computes per-phase target capacitance, and sets
    ctx.phase_advance_event when the threshold is met.

    Priority 30 puts it in the SAME parallel bucket as RoutesHandler —
    they run concurrently within the bucket so the handler can monitor
    while Routes drives the phases.
    """

    priority = 30
    wait_for_topics = []                # populated in Task 6


def make_volume_threshold_column() -> Column:
    return Column(
        model=VolumeThresholdColumnModel(
            col_id=VOLUME_THRESHOLD_COL_ID,
            col_name=VOLUME_THRESHOLD_COL_NAME,
            default_value=VOLUME_THRESHOLD_DEFAULT,
        ),
        view=VolumeThresholdColumnView(
            low=0.0, high=1_000_000.0, decimals=4, single_step=0.01,
        ),
        handler=VolumeThresholdHandler(),
    )
```

- [ ] **Step 4: Wire the factory into the plugin's contribution list**

Modify `src/volume_threshold_protocol_controls/plugin.py`. Replace `_contributed_protocol_columns_default`'s body:

```python
    def _contributed_protocol_columns_default(self):
        from .protocol_columns.volume_threshold_column import (
            make_volume_threshold_column,
        )
        return [make_volume_threshold_column()]
```

- [ ] **Step 5: Run tests to verify they pass**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py src/volume_threshold_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: 8 passed (4 from Task 4 scaffold + 4 new).

- [ ] **Step 6: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py src/volume_threshold_protocol_controls/plugin.py src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] VolumeThresholdColumn: model + view + factory (handler stub)"
```

---

### Task 6: `VolumeThresholdHandler.on_step` — the real per-phase monitor loop

**Files:**
- Modify: `src/volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py` (handler body)
- Modify: `src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py` (handler tests)

- [ ] **Step 1: Write the failing tests**

Append to `src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py`:

```python
def _make_handler_ctx(*, threshold=0.0, preview=False, electrode_areas=None,
                      cpa_initial=None, stop_event=None):
    """Build a minimal handler + ctx pair for unit tests. The ctx's
    wait_for is a queue-backed stub — feed it items via _enqueue."""
    import threading
    from unittest.mock import MagicMock

    from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
        VolumeThresholdHandler,
    )

    handler = VolumeThresholdHandler()
    row = MagicMock()
    row.volume_threshold = threshold

    proto = MagicMock()
    proto.stop_event = stop_event or threading.Event()
    proto.preview_mode = preview
    proto.scratch = {}
    if electrode_areas is not None:
        proto.scratch["electrode_areas"] = electrode_areas

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()

    # Queue-backed wait_for: each topic gets a list of payloads to
    # dispense in order; raises TimeoutError when empty.
    queues = {}
    def _wait_for(topic, timeout=5.0, predicate=None):
        q = queues.setdefault(topic, [])
        while q:
            item = q.pop(0)
            if predicate is None or predicate(item):
                return item
        raise TimeoutError(topic)
    ctx.wait_for = _wait_for

    def _enqueue(topic, payload):
        queues.setdefault(topic, []).append(payload)

    return handler, row, ctx, _enqueue


def test_handler_returns_immediately_when_threshold_is_zero():
    """0 disables the column — handler must NOT touch wait_for or
    phase_advance_event."""
    handler, row, ctx, _ = _make_handler_ctx(threshold=0.0)
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_immediately_when_preview_mode():
    """No hardware in preview, nothing to monitor."""
    handler, row, ctx, _ = _make_handler_ctx(threshold=1.0, preview=True,
                                              electrode_areas={"e1": 1.0})
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_immediately_when_electrode_areas_missing():
    """No electrode_areas in scratch (demo / headless) — log and exit
    without crashing."""
    handler, row, ctx, _ = _make_handler_ctx(threshold=1.0,
                                              electrode_areas=None)
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_sets_phase_advance_event_when_capacitance_crosses_target():
    """Phase boundary publishes electrodes ["e1"] -> area = 1.0;
    calibration is liquid=5, filler=3 -> cpa=2; threshold=0.5 -> target=1.0pF.
    A capacitance reading of 1.5pF must trigger early-advance."""
    import json
    handler, row, ctx, enq = _make_handler_ctx(
        threshold=0.5, electrode_areas={"e1": 1.0},
    )
    enq("dropbot/signals/calibration_data",
        json.dumps({"liquid_capacitance_over_area": 5.0,
                    "filler_capacitance_over_area": 3.0}))
    enq("microdrop/electrode_controller/electrodes_state_change",
        json.dumps({"electrodes": ["e1"], "channels": [1]}))
    enq("dropbot/signals/capacitance_updated",
        json.dumps({"capacitance": "1.5pF", "voltage": "100V"}))
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is True


def test_handler_does_not_set_event_when_below_target():
    """Capacitance stays below target — handler waits the phase out
    (TimeoutError loops it back to the outer loop), then the
    step_phases_done_event eventually breaks the outer loop."""
    import json
    import threading
    handler, row, ctx, enq = _make_handler_ctx(
        threshold=0.5, electrode_areas={"e1": 1.0},
    )
    enq("dropbot/signals/calibration_data",
        json.dumps({"liquid_capacitance_over_area": 5.0,
                    "filler_capacitance_over_area": 3.0}))
    enq("microdrop/electrode_controller/electrodes_state_change",
        json.dumps({"electrodes": ["e1"], "channels": [1]}))
    enq("dropbot/signals/capacitance_updated",
        json.dumps({"capacitance": "0.5pF", "voltage": "100V"}))
    # Simulate Routes finishing — sets step_phases_done_event so the
    # outer loop exits on its next iteration after the inner CAPACITANCE
    # queue empties.
    def _set_done_soon():
        import time
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_set_done_soon, daemon=True).start()
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_skips_phase_when_actuated_area_is_zero():
    """Phase has electrodes the device doesn't know about -> area=0 ->
    cannot compute target. Loop continues to the next phase boundary
    without setting the event."""
    import json
    import threading
    handler, row, ctx, enq = _make_handler_ctx(
        threshold=1.0, electrode_areas={"e1": 1.0},
    )
    enq("dropbot/signals/calibration_data",
        json.dumps({"liquid_capacitance_over_area": 5.0,
                    "filler_capacitance_over_area": 3.0}))
    enq("microdrop/electrode_controller/electrodes_state_change",
        json.dumps({"electrodes": ["unknown"], "channels": [99]}))
    def _set_done_soon():
        import time; time.sleep(0.05); ctx.step_phases_done_event.set()
    threading.Thread(target=_set_done_soon, daemon=True).start()
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_wait_for_topics_declared():
    """Executor opens mailboxes only for topics the handler declares —
    a missing topic would mean wait_for(topic) raises KeyError."""
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from device_viewer.consts import CALIBRATION_DATA
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
        VolumeThresholdHandler,
    )
    declared = set(VolumeThresholdHandler.wait_for_topics)
    assert CAPACITANCE_UPDATED in declared
    assert ELECTRODES_STATE_CHANGE in declared
    assert CALIBRATION_DATA in declared
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py -v -k 'handler_'
```

Expected: 7 failures (the topic-declaration test will fail on empty list; the rest will fail because on_step doesn't do anything yet).

- [ ] **Step 3: Implement the handler**

Replace the stub `VolumeThresholdHandler` in `src/volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py` with the full implementation. Replace the `class VolumeThresholdHandler(BaseColumnHandler):` block with:

```python
import json as _json

from logger.logger_service import get_logger

from dropbot_controller.consts import CAPACITANCE_UPDATED
from device_viewer.consts import CALIBRATION_DATA
from electrode_controller.consts import ELECTRODES_STATE_CHANGE

from ..consts import PHASE_POLL_TIMEOUT_S, CAP_POLL_TIMEOUT_S


logger = get_logger(__name__)


def _parse_capacitance_pf(raw):
    """Pull the numeric pF value out of a CAPACITANCE_UPDATED payload.
    Returns None on any parse failure (handler skips and waits for the
    next reading rather than crashing)."""
    try:
        data = _json.loads(raw)
    except (TypeError, ValueError):
        return None
    cap_str = data.get("capacitance")
    if not isinstance(cap_str, str):
        return None
    try:
        return float(cap_str.split("pF")[0])
    except (ValueError, AttributeError):
        return None


def _capacitance_per_unit_area(liquid, filler):
    """liquid - filler when both are present, non-negative, and
    liquid > filler. Returns None otherwise. Mirrors the legacy
    ForceCalculationService.calculate_capacitance_per_unit_area and the
    logging controller's _capacitance_per_unit_area helper."""
    if liquid is None or filler is None:
        return None
    try:
        liquid = float(liquid); filler = float(filler)
    except (TypeError, ValueError):
        return None
    if liquid < 0 or filler < 0 or liquid <= filler:
        return None
    return liquid - filler


class VolumeThresholdHandler(BaseColumnHandler):
    """Per-step volume threshold monitor (priority 30 — runs in
    parallel with RoutesHandler).

    Per phase:
      * Read the actuated electrodes from the ELECTRODES_STATE_CHANGE
        payload that RoutesHandler publishes.
      * Drain any pending CALIBRATION_DATA messages and recompute
        capacitance-per-unit-area.
      * target = threshold * actuated_area * cpa
      * Poll CAPACITANCE_UPDATED until current ≥ target → set
        ctx.phase_advance_event (RoutesHandler's _cooperative_sleep
        wakes on it) → loop back for the next phase boundary.
    """

    priority = 30
    wait_for_topics = [
        ELECTRODES_STATE_CHANGE, CAPACITANCE_UPDATED, CALIBRATION_DATA,
    ]

    def on_step(self, row, ctx):
        threshold = float(getattr(row, "volume_threshold", 0.0) or 0.0)
        if threshold <= 0:
            return
        if getattr(ctx.protocol, "preview_mode", False):
            return
        electrode_areas = dict(
            ctx.protocol.scratch.get("electrode_areas") or {}
        )
        if not electrode_areas:
            logger.info(
                "volume_threshold: no electrode_areas in scratch; "
                "skipping (likely a demo / headless run)"
            )
            return

        stop_event = ctx.protocol.stop_event
        cpa = self._latest_cpa(ctx, default=None)

        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            try:
                payload = ctx.wait_for(
                    ELECTRODES_STATE_CHANGE,
                    timeout=PHASE_POLL_TIMEOUT_S,
                )
            except TimeoutError:
                # Wake up periodically to recheck stop / phases-done.
                continue

            # Phase boundary observed — refresh calibration if a new
            # CALIBRATION_DATA arrived since last time.
            cpa = self._latest_cpa(ctx, default=cpa)
            try:
                electrodes = _json.loads(payload).get("electrodes") or []
            except (TypeError, ValueError):
                continue

            actuated_area = sum(
                float(electrode_areas.get(e, 0.0)) for e in electrodes
            )
            if cpa is None or actuated_area <= 0.0:
                # Cannot compute target — wait for the next phase.
                continue

            target = threshold * actuated_area * cpa
            self._monitor_until_threshold(ctx, target)

    @staticmethod
    def _monitor_until_threshold(ctx, target):
        """Loop wait_for(CAPACITANCE_UPDATED) until current_cap ≥
        target, the step's phases finish, or stop fires. Sets
        ctx.phase_advance_event on hit; returns silently otherwise so
        the outer loop can pick up the next phase boundary."""
        stop_event = ctx.protocol.stop_event
        while (not stop_event.is_set()
               and not ctx.step_phases_done_event.is_set()):
            try:
                cap_payload = ctx.wait_for(
                    CAPACITANCE_UPDATED, timeout=CAP_POLL_TIMEOUT_S,
                )
            except TimeoutError:
                # Either monitoring lost the publisher or the phase
                # ended without crossing — outer loop will pick up
                # the next ELECTRODES_STATE_CHANGE.
                return
            current = _parse_capacitance_pf(cap_payload)
            if current is None:
                continue
            if current >= target:
                ctx.phase_advance_event.set()
                return

    @staticmethod
    def _latest_cpa(ctx, default):
        """Drain any pending CALIBRATION_DATA messages and return the
        most recent capacitance-per-unit-area, or `default` if no
        valid calibration arrived. Returns immediately when the
        mailbox is empty (zero timeout)."""
        latest = default
        while True:
            try:
                raw = ctx.wait_for(CALIBRATION_DATA, timeout=0.0)
            except TimeoutError:
                return latest
            try:
                payload = _json.loads(raw)
            except (TypeError, ValueError):
                continue
            value = _capacitance_per_unit_area(
                payload.get("liquid_capacitance_over_area"),
                payload.get("filler_capacitance_over_area"),
            )
            if value is not None:
                latest = value
```

- [ ] **Step 4: Run handler tests to verify they pass**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py -v -k 'handler_'
```

Expected: 7 passed.

- [ ] **Step 5: Full plugin regression**

```
pixi run pytest src/volume_threshold_protocol_controls/tests/ -v
```

Expected: 11 passed (4 scaffold + 4 model/factory + 7 handler).

- [ ] **Step 6: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/volume_threshold_protocol_controls/protocol_columns/volume_threshold_column.py src/volume_threshold_protocol_controls/tests/test_volume_threshold_column.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] VolumeThresholdHandler: per-phase target compute + early-advance"
```

---

### Task 7: Pane wiring — `electrode_areas_provider` kwarg + start_protocol_run

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing test**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_passes_electrode_areas_to_executor_start(qapp, monkeypatch):
    """When an electrode_areas_provider is injected, the pane resolves
    it once at start and threads the result into executor.start as
    extra_scratch['electrode_areas']."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    captured = {}
    from unittest.mock import MagicMock
    class _FakeExecutor:
        def __init__(self, **kw):
            # MagicMock for qsignals so the pane's _wire_executor_signals
            # can blindly .connect() on whatever it needs without us
            # enumerating every signal.
            self.qsignals = MagicMock()
        def start(self_inner, **kw):
            captured.update(kw)
    def _factory(**kw):
        return _FakeExecutor(**kw)

    areas = {"e1": 1.5, "e2": 2.0}
    pane = ptp.ProtocolTreePane(
        [make_name_column()],
        executor_factory=_factory,
        electrode_areas_provider=lambda: dict(areas),
    )
    # Drive the run-start path directly (no buttons).
    pane._start_protocol_run(preview_mode=False)

    assert captured.get("extra_scratch") == {"electrode_areas": areas}


def test_pane_omits_extra_scratch_when_no_provider(qapp):
    """Demos and pane constructions without an electrode_areas_provider
    must not pass extra_scratch — the executor's default behaviour
    (protocol_metadata only) applies."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    captured = {}
    from unittest.mock import MagicMock
    class _FakeExecutor:
        def __init__(self, **kw):
            # MagicMock for qsignals so the pane's _wire_executor_signals
            # can blindly .connect() on whatever it needs without us
            # enumerating every signal.
            self.qsignals = MagicMock()
        def start(self_inner, **kw):
            captured.update(kw)
    def _factory(**kw):
        return _FakeExecutor(**kw)

    pane = ptp.ProtocolTreePane(
        [make_name_column()], executor_factory=_factory,
    )
    pane._start_protocol_run(preview_mode=False)

    # extra_scratch either absent or None — never an empty dict (which
    # would still satisfy the executor's `if self._extra_scratch:`
    # gate but is sloppy).
    assert captured.get("extra_scratch") is None or "extra_scratch" not in captured
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'electrode_areas'
```

Expected: 1 failure (`TypeError: __init__() got an unexpected keyword argument 'electrode_areas_provider'`) and 1 might pass since extra_scratch was never passed at all.

- [ ] **Step 3: Add the `electrode_areas_provider` kwarg + wire it into `_start_protocol_run`**

In `src/pluggable_protocol_tree/views/protocol_tree_pane.py`:

**3a — Locate the `__init__` signature**. Add `electrode_areas_provider=None,` immediately before `quick_actions=None,` (or before whatever the last kwarg is just before `parent=None,`). Update the signature:

```python
    def __init__(
        self,
        columns_or_manager,
        *,
        application=None,
        experiment_manager=None,
        sticky_manager=None,
        device_viewer_sync=None,
        phase_ack_topic=ELECTRODES_STATE_APPLIED,
        executor_factory=None,
        logging_device_context_provider=None,
        electrode_areas_provider=None,
        quick_actions=None,
        parent=None,
    ):
```

**3b — Stash the provider on `self`** alongside the existing `self._logging_device_context_provider = logging_device_context_provider` line. Add:

```python
        self._electrode_areas_provider = electrode_areas_provider
```

**3c — Modify `_start_protocol_run`** to pass `extra_scratch` to `self.executor.start(...)`. Find the existing call to `self.executor.start(...)` in `_start_protocol_run`. Replace the call so it builds `extra_scratch` and forwards it:

Find the current existing call (looks like `self.executor.start(start_step_path=start_path, preview_mode=preview_mode)` or similar). Replace with:

```python
        extra_scratch = None
        if self._electrode_areas_provider is not None:
            try:
                areas = self._electrode_areas_provider()
                if areas:
                    extra_scratch = {"electrode_areas": dict(areas)}
            except Exception as e:
                logger.warning(
                    f"electrode_areas_provider raised: {e}; "
                    f"volume-threshold column will skip this run"
                )
        self.executor.start(
            start_step_path=start_path,
            preview_mode=preview_mode,
            extra_scratch=extra_scratch,
        )
```

If `_start_protocol_run`'s current code references variables named differently (e.g. `selected_path` instead of `start_path`), match the existing local names; don't rename things.

- [ ] **Step 4: Run tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'electrode_areas'
```

Expected: 2 passed.

- [ ] **Step 5: Full pane regression**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v
```

Expected: all previously-green stay green.

- [ ] **Step 6: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] Pane: electrode_areas_provider -> executor.start(extra_scratch=...)"
```

---

### Task 8: Dock pane seeds `electrode_areas` from the DV model

**Files:**
- Modify: `src/pluggable_protocol_tree/views/dock_pane.py`

- [ ] **Step 1: Inspect the dock pane to find the existing provider pattern**

In `src/pluggable_protocol_tree/views/dock_pane.py`, the existing `_logging_device_context()` helper (added during PR #426) reads from `dv_pane.model.electrodes.channel_electrode_areas_scaled_map`. The volume-threshold column needs an **electrode_id → area** map (not channel-id-keyed), which lives at `dv_pane.model.electrodes.svg_model.electrode_areas_scaled` (keyed by electrode-id string).

- [ ] **Step 2: Add an `_electrode_areas` provider sibling to the existing `_logging_device_context`**

In `src/pluggable_protocol_tree/views/dock_pane.py`, find the existing `def _logging_device_context():` closure inside the dock-pane's `create_contents` (or equivalent) method. Add a sibling closure immediately after it:

```python
        def _electrode_areas():
            """Per-electrode area map keyed by electrode_id (string) →
            area in scaled mm² units. Read from the live DV model so
            the volume-threshold column can compute target capacitance
            for the actuated electrodes of each phase.

            Returns an empty dict when the DV isn't available — the
            volume-threshold handler logs and skips itself in that case
            (graceful degradation, same posture as the logging device
            context above)."""
            try:
                dv_pane = self.task.window.get_dock_pane(
                    "device_viewer.dock_pane")
                model = getattr(dv_pane, "model", None)
                if model is None:
                    return {}
                svg = getattr(model.electrodes, "svg_model", None)
                if svg is None:
                    return {}
                return dict(svg.electrode_areas_scaled)
            except Exception as e:
                logger.debug(f"electrode-areas probe failed: {e}")
                return {}
```

- [ ] **Step 3: Pass the provider into the pane constructor**

Still in the same method, find the existing `ProtocolTreePane(...)` instantiation and add `electrode_areas_provider=_electrode_areas` as a kwarg alongside `logging_device_context_provider=_logging_device_context`:

```python
        pane = ProtocolTreePane(
            ...,
            logging_device_context_provider=_logging_device_context,
            electrode_areas_provider=_electrode_areas,
            ...,
        )
```

Match the existing kwarg style / line wrapping. Don't rename or move other kwargs.

- [ ] **Step 4: Smoke check the import path**

```
pixi run python -c "from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane; print('ok')"
```

Expected: prints `ok` with no traceback.

- [ ] **Step 5: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/pluggable_protocol_tree/views/dock_pane.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] Dock pane: seed electrode_areas provider from DV svg_model"
```

---

### Task 9: Register `VolumeThresholdProtocolControlsPlugin` in the live app

**Files:**
- Modify: `src/examples/plugin_consts.py`

- [ ] **Step 1: Locate where `PeripheralProtocolControlsPlugin` is registered**

Run:

```
pixi run grep -n 'PeripheralProtocolControlsPlugin' src/examples/plugin_consts.py
```

Note the import line and the list it appears in (per PR #426 / `protocol_quick_action_tools` precedent, this is `EXPERIMENTAl_PLUGINS` — yes the variable name has a lowercase l; it's a pre-existing upstream typo, leave it as-is).

- [ ] **Step 2: Add the import + list entry**

In `src/examples/plugin_consts.py`:

**2a — Add the import alongside the existing peripheral / dropbot / quick-action imports** (find the block where they live; add a new line):

```python
from volume_threshold_protocol_controls.plugin import (
    VolumeThresholdProtocolControlsPlugin,
)
```

**2b — Append `VolumeThresholdProtocolControlsPlugin,`** to the same list `PeripheralProtocolControlsPlugin` appears in, immediately after it. All entries are bare class references (not instances) — match that convention. Final addition:

```python
EXPERIMENTAl_PLUGINS = [
    ...,
    PeripheralProtocolControlsPlugin,
    VolumeThresholdProtocolControlsPlugin,
    ...,
]
```

- [ ] **Step 3: Smoke check**

```
pixi run python -c "from volume_threshold_protocol_controls.plugin import VolumeThresholdProtocolControlsPlugin; print(VolumeThresholdProtocolControlsPlugin().id)"
```

Expected: prints `volume_threshold_protocol_controls.plugin`.

- [ ] **Step 4: Final regression across everything touched by this PR**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_step_context.py src/pluggable_protocol_tree/tests/test_executor.py src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py src/volume_threshold_protocol_controls/tests/ -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src add src/examples/plugin_consts.py
git -C C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src commit -m "[ppt-25] Load VolumeThresholdProtocolControlsPlugin in the live app"
```

---

## Spec coverage map

| Spec section | Implementing task(s) |
|---|---|
| §1 `phase_advance_event` + `step_phases_done_event` on StepContext | Task 1 |
| §1 `_cooperative_sleep` honours `phase_advance_event` | Task 2 |
| §1 RoutesHandler clears `phase_advance_event` per phase + sets `step_phases_done_event` after loop | Task 2 |
| §1 `Executor.start(extra_scratch=...)` merges into proto_ctx.scratch | Task 3 |
| §2 New plugin scaffold (consts, plugin shell) | Task 4 |
| §2 `VolumeThresholdColumnModel` (Float, default 0.0, hidden by default, step-level) | Task 5 |
| §2 `VolumeThresholdColumnView` (numeric edit, hidden, step-only) | Task 5 |
| §2 `VolumeThresholdHandler` (priority 30, wait_for_topics, per-phase monitor loop) | Task 6 |
| §2 Helper functions `_parse_capacitance_pf` / `_capacitance_per_unit_area` / `_latest_cpa` | Task 6 |
| §3 Pane: `electrode_areas_provider` kwarg + extra_scratch wiring | Task 7 |
| §3 Dock pane: seed `_electrode_areas` from DV svg_model | Task 8 |
| §3 Plugin registration in `examples/plugin_consts.py` | Task 9 |
| Tunables `PHASE_POLL_TIMEOUT_S` / `CAP_POLL_TIMEOUT_S` | Task 4 (consts) + Task 6 (used) |
| Error handling: threshold ≤ 0 / preview / no areas / unparseable payloads / stop_event | Task 6 (handler short-circuits, parse helpers return None, wait_for honours stop_event) |
| Demo / headless degradation | Task 6 (`if not electrode_areas: log + return`) |

All spec sections accounted for.
