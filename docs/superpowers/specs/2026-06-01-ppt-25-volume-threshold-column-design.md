# PPT-25: Volume Threshold Column — Design

**Date:** 2026-06-01
**Branch:** `feat/ppt-25_volume_threshold`
**Issue:** [#437](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/437)

## Goal

Port the `Volume Threshold %` per-step column from legacy `protocol_grid`
into the pluggable protocol tree. The column stores a 0-100 **percent**
(Int; 0 disables). Each phase ends early once the measured capacitance of
the actuated electrodes reaches this percent of their calibrated FULL
(liquid-covered) capacitance:

    target = (percent / 100) × liquid_capacitance_over_area × actuated_area

The filler/baseline value is NOT used. Preview-mode runs skip the check
entirely.

## Background

### Legacy reference

`protocol_grid/services/volume_threshold_service.py` is a `QObject`
that runs a 50 ms `QTimer` to poll capacitance updates. The legacy
runner (`protocol_runner_controller.py:1500-1611`):

1. Reads `step.parameters["Volume Threshold"]` (float, `0.0` disables).
2. At each phase start, computes
   `target = threshold × actuated_area × (liquid_cap − filler_cap)`
   (legacy formula using `ForceCalculationService.calculate_capacitance_per_unit_area`;
   the new column uses `(percent / 100) × liquid_cap × actuated_area` — filler not used)
   and the calibration's per-electrode areas.
3. Starts the service, which polls; on `current_cap >= target` emits
   `threshold_reached` → the runner stops the phase timer and jumps to
   the next phase early.
4. On phase timeout (target not reached), service simply stops and the
   phase advances normally.

### Why this isn't a clean drop-in

The pluggable tree's `RoutesColumnHandler.on_step` (`builtins/
routes_column.py:100`) owns the per-phase loop. Its
`_cooperative_sleep(per_phase_dwell, stop_event, pause_event)` is the
dwell — woken today only by `stop_event` (whole-protocol abort) or
`pause_event`. There is no public way for another column handler to
cut the current phase short.

This design adds exactly one new affordance — a per-phase
`threading.Event` on `StepContext` that `RoutesHandler` honours — and
nothing else in the core contract changes.

### Existing building blocks reused

- `StepContext.wait_for(topic, timeout, predicate)` + the mailbox
  machinery (`step_context.py`) for receiving CAPACITANCE_UPDATED and
  ELECTRODES_STATE_CHANGE payloads in-handler.
- `ELECTRODES_STATE_CHANGE` is already published by `RoutesHandler`
  per phase with `{"electrodes": [...], "channels": [...]}`.
- `CALIBRATION_DATA` topic carries `{liquid_capacitance_over_area,
  filler_capacitance_over_area}` (used today by
  `pluggable_protocol_tree.services.logging.controller.on_calibration`).
- `proto_ctx.scratch` already hydrates from
  `RowManager.protocol_metadata` at protocol start
  (`executor.py:192`).

## Architecture

Three units change, one new plugin lands.

### 1. `pluggable_protocol_tree` — two new per-step events

**`execution/step_context.py`** — `StepContext` gains two new fields:

```python
phase_advance_event = Instance(threading.Event)
step_phases_done_event = Instance(threading.Event)
```

Constructed fresh in the executor's `_build_step_ctx` (alongside
mailbox setup).

- **`phase_advance_event`** — any handler sets it to mean "this phase
  is done, move on now". Cleared on each phase boundary by
  `RoutesHandler` (the owner of the phase loop) so a set carries
  through to the *current* phase only.
- **`step_phases_done_event`** — `RoutesHandler` sets it once after
  finishing its per-phase loop. Lets sibling handlers in the same
  parallel bucket (notably `VolumeThresholdHandler`) exit instead of
  blocking forever waiting for the next phase that will never come.
  Without this, the bucket's `ThreadPoolExecutor` would hang on
  whichever handler is still inside a `wait_for`.

**`builtins/routes_column.py`** — three small edits to
`RoutesColumnHandler`:

1. At the top of each phase-loop iteration:
   `ctx.phase_advance_event.clear()`.
2. The `_cooperative_sleep(per_phase_dwell, stop_event, pause_event)`
   call grows an optional `phase_advance_event` kwarg; the function
   wakes on it the same way it wakes on `stop_event` (return early,
   not raise).
3. Immediately before `on_step` returns (after any in-duration-mode
   hold), set `ctx.step_phases_done_event`.

**`execution/executor.py`** — `_build_step_ctx` initialises both
events as fresh `threading.Event()` instances. Other handlers get
them for free via `ctx.phase_advance_event` / `ctx.step_phases_done_event`.

**`execution/executor.py`** — `Executor.start()` and `__init__` grow
an optional `extra_scratch: dict | None = None` argument that
merges into `proto_ctx.scratch` AFTER the `protocol_metadata` update.
Mirrors how `electrode_to_channel` flows in today, but is for runtime
(not file-persisted) data such as electrode areas. Demo callers don't
pass it; the dock pane does.

### 2. New plugin `volume_threshold_protocol_controls`

A sibling plugin mirroring `peripheral_protocol_controls`:

```
volume_threshold_protocol_controls/
  __init__.py
  consts.py                                    # PKG, defaults
  plugin.py                                    # contributes the column
  protocol_columns/
    __init__.py
    volume_threshold_column.py                 # model + view + handler + factory
  tests/
    __init__.py
    test_volume_threshold_column.py
```

**`VolumeThresholdColumnModel`** —
`col_id="volume_threshold"`, `col_name="Volume Threshold %"`,
`default_value=0`. Int trait (0-100 percent). Step-level
(`renders_on_group=False`). Hidden by default (`hidden_by_default=True`)
— surfaces via header right-click, same posture as `droplet_check` and
the trail-loop knobs. 0 disables; reaching the percent of the full
(liquid-covered) capacitance cuts the phase short.

**`VolumeThresholdColumnView`** — `IntSpinBoxColumnView` with
`low=0, high=100`.

**`VolumeThresholdHandler`** — `priority=30` (same bucket as
`RoutesHandler` so they run in the same parallel pool; the handler
must NOT touch hardware so the bucket-collision rule doesn't apply).
`wait_for_topics = [CAPACITANCE_UPDATED, ELECTRODES_STATE_CHANGE,
CALIBRATION_DATA]`. Formula: `target = (percent / 100) × liquid_capacitance_over_area × actuated_area`.

**`on_step(self, row, ctx)`** body:

```
percent = float(getattr(row, "volume_threshold", 0) or 0)
if percent <= 0:                    # disabled
    return
if ctx.protocol.preview_mode:       # no hardware, nothing to monitor
    return

electrode_areas = dict(ctx.protocol.scratch.get("electrode_areas") or {})
if not electrode_areas:
    logger.info(
        "volume_threshold: no electrode_areas in scratch — skipping "
        "(headless / demo run)"
    )
    return

full_cap_over_area = self._latest_full_cap_over_area(ctx, default=None)
stop_event = ctx.protocol.stop_event

# Outer loop: one iteration per phase. ELECTRODES_STATE_CHANGE marks
# each phase boundary (Routes publishes it). Loop exits when stop fires,
# when Routes signals step_phases_done_event, or when the wait_for
# times out and the phases-done event is set in the meantime.
while (not stop_event.is_set()
       and not ctx.step_phases_done_event.is_set()):
    try:
        payload = ctx.wait_for(
            ELECTRODES_STATE_CHANGE,
            timeout=_PHASE_POLL_TIMEOUT_S,        # short; recheck exit flags
        )
    except TimeoutError:
        continue                       # recheck loop conditions

    # Drain any pending CALIBRATION_DATA messages so full_cap_over_area stays current.
    full_cap_over_area = self._latest_full_cap_over_area(ctx, default=full_cap_over_area)

    electrodes = json.loads(payload).get("electrodes") or []
    actuated_area = sum(
        float(electrode_areas.get(e, 0.0)) for e in electrodes
    )
    if full_cap_over_area is None or actuated_area <= 0.0:
        continue                     # cannot compute target — wait next phase

    full_cap = full_cap_over_area * actuated_area
    target = (percent / 100.0) * full_cap
    self._monitor_until_threshold(ctx, target)


def _monitor_until_threshold(self, ctx, target):
    """Loop wait_for(CAPACITANCE_UPDATED) until current_cap >= target
    or the per-phase dwell elapses. Sets ctx.phase_advance_event on hit;
    returns silently on timeout (phase will advance normally)."""
    while True:
        try:
            cap_payload = ctx.wait_for(
                CAPACITANCE_UPDATED,
                timeout=_CAP_POLL_TIMEOUT_S,
                predicate=lambda raw: _parse_capacitance_pf(raw) is not None,
            )
        except TimeoutError:
            return
        if ctx.protocol.stop_event.is_set():
            return
        current = _parse_capacitance_pf(cap_payload)
        if current is None:
            continue
        if current >= target:
            ctx.phase_advance_event.set()
            return


@staticmethod
def _latest_full_cap_over_area(ctx, default=None):
    """Drain any pending CALIBRATION_DATA messages from the mailbox and
    return the most recent FULL (liquid-covered) capacitance-per-unit-area,
    or `default` if nothing has arrived. 'Full' is the liquid reference
    from calibration; the percentage target is a fraction of it.
    Reads `liquid_capacitance_over_area` only — filler is not used."""
    ...
```

**Tunables (module-level constants):**

- `_PHASE_POLL_TIMEOUT_S = 2.0` — short; the handler wakes every
  2 s to re-check `stop_event` and `step_phases_done_event`. Worst-
  case 2 s lag between Routes finishing its phases and
  VolumeThresholdHandler returning — acceptable for an end-of-step
  pause, far better than blocking forever.
- `_CAP_POLL_TIMEOUT_S = 1.0` — one second between capacitance polls
  while monitoring a phase; lets us re-check stop_event and not block
  indefinitely on a dead listener.

### 3. Live-app wiring (dock pane)

`PluggableProtocolDockPane.create_contents` (`views/dock_pane.py`)
constructs the pane; the pane's protocol-start path
(`_start_protocol_run`) is where `electrode_areas` enters the system.

**`views/protocol_tree_pane.py`** — `_start_protocol_run` receives an
optional `electrode_areas_provider: Callable[[], dict] | None`
(injected via constructor, same shape as `logging_device_context_provider`
already there). When provided, the pane resolves it once and passes
the dict as `extra_scratch={"electrode_areas": ...}` into
`self.executor.start(...)`.

**`views/dock_pane.py`** — alongside the existing
`_logging_device_context` provider, add a sibling
`_electrode_areas` provider that reads from `dv_pane.model.electrodes`
(unit conversion to mm² already lives in the DV model). Pass it into
`ProtocolTreePane(..., electrode_areas_provider=_electrode_areas)`.

**Plugin registration:** add
`VolumeThresholdProtocolControlsPlugin()` to
`examples/plugin_consts.py` next to the other contribution plugins
(`PeripheralProtocolControlsPlugin`, `DropbotProtocolControlsPlugin`,
etc.).

## Data flow

```
user sets Volume Threshold % cell (e.g. 50)
  -> persisted in row.volume_threshold (Int, 0-100 percent)

dock pane / start_protocol_run
  -> electrode_areas_provider() -> {electrode_id: area_mm2, ...}
  -> executor.start(extra_scratch={"electrode_areas": ...})

executor.run
  -> proto_ctx.scratch hydrated:
       {"electrode_to_channel": ..., "electrode_areas": ...}
  -> per step: _build_step_ctx() creates fresh phase_advance_event,
       opens mailboxes for CAPACITANCE_UPDATED / ELECTRODES_STATE_CHANGE /
       CALIBRATION_DATA (plus everything else handlers declare).
  -> _run_hooks("on_step", ...) fires Routes + VolumeThreshold in parallel.

[Routes per phase]
  ctx.phase_advance_event.clear()
  publish ELECTRODES_STATE_CHANGE  -- VolumeThreshold's mailbox sees it
  wait for ELECTRODES_STATE_APPLIED ack
  _cooperative_sleep(dwell, stop_event, pause_event,
                     phase_advance_event=ctx.phase_advance_event)
[Routes after final phase]
  ctx.step_phases_done_event.set()         -- signals VolumeThreshold to exit
  return from on_step

[VolumeThreshold loop]
  while not stop_event AND not step_phases_done_event:
    try: wait_for(ELECTRODES_STATE_CHANGE, timeout=2s) -> electrodes
    except TimeoutError: continue          -- re-check exit flags
    drain CALIBRATION_DATA -> latest full_cap_over_area (liquid reference)
    compute target = (percent / 100) * full_cap_over_area * actuated_area
    while monitoring:
      payload = wait_for(CAPACITANCE_UPDATED, timeout=1s)
      if parse(payload) >= target:
        ctx.phase_advance_event.set()
        break
  return from on_step

If volume threshold hits mid-dwell:
  -> phase_advance_event is set
  -> _cooperative_sleep returns immediately
  -> Routes advances to its next phase iteration
  -> next iteration clears phase_advance_event and the cycle repeats
```

## Error handling

- **Threshold = 0 / preview / no electrode_areas / no calibration:**
  the handler logs and returns; no-op for the rest of the step.
  Routes runs uninterrupted.
- **Unparseable capacitance / electrodes payload:** the predicate
  discards; the loop polls the next message. A truly broken
  publisher manifests as the phase running its normal dwell — same
  as threshold-not-reached.
- **Stop event:** every wait honours `stop_event` (raises `AbortError`
  out of `wait_for`); the handler exits cleanly.
- **Demo / headless runs without a DV:** the dock pane is the only
  injector of `electrode_areas`; demos pass nothing → scratch is
  missing the key → handler logs once and returns. No crash, no
  hardware coupling.

## Testing

**`pluggable_protocol_tree/tests/`**

- `test_step_context.py` (extend): both `phase_advance_event` and
  `step_phases_done_event` exist on a fresh `StepContext` and are
  not set.
- `test_routes_handler_cooperative_sleep.py` (new or extend):
  - `_cooperative_sleep` returns early when `phase_advance_event` is
    set before the dwell elapses.
  - Per-phase loop clears `phase_advance_event` at the start of each
    iteration (set during phase N → cleared at the top of phase N+1).
  - `step_phases_done_event` is set exactly once, after the final
    phase (and after any in-duration-mode hold).
- `test_executor.py` (extend): `executor.start(extra_scratch=...)`
  merges into `proto_ctx.scratch` after `protocol_metadata` (and
  takes precedence on key collision).

**`volume_threshold_protocol_controls/tests/`**

- `test_volume_threshold_column.py`:
  - Column metadata (id, name, default, priority, wait_for_topics).
  - Handler short-circuits when `threshold <= 0`, `preview_mode`, or
    `electrode_areas` empty.
  - `_latest_full_cap_over_area` reads `liquid_capacitance_over_area`
    (full liquid reference; filler not used) and returns `default` when
    no CALIBRATION_DATA pending.
  - Driven via a stubbed `StepContext` whose mailboxes are pre-
    populated with synthetic ELECTRODES_STATE_CHANGE +
    CAPACITANCE_UPDATED payloads:
    - Capacitance crosses target → `ctx.phase_advance_event` is set.
    - Capacitance stays below target through the dwell → event NOT
      set; handler simply waits for the next ELECTRODES_STATE_CHANGE.

No live Redis or Qt event loop needed for these tests; the existing
`Mailbox` is thread-safe and accepts `deposit()` calls directly.

## Out of scope

- **Persisting calibration data per-protocol.** Calibration stays a
  live runtime input (CALIBRATION_DATA + DV model). The column value
  itself is per-step and persisted in the protocol JSON via the
  existing column-serialize plumbing.
- **A new "Volume Threshold reached" report metric.** The logging
  controller already records every capacitance sample with its step
  context; analysis tooling can derive whether/when a phase was cut
  short from the existing data.
- **UI feedback for an in-progress threshold meter** (e.g. a progress
  bar). The phase ending early is the user-visible signal.
- **Tuning the `_CAP_POLL_TIMEOUT_S` interval.** 1s is a reasonable
  default; expose as a user setting only if real-world runs show it
  matters.
- **Per-phase-precise target re-sync for sub-1s dwells.** The handler
  re-syncs to the current phase's actuated electrodes whenever
  `_monitor_until_threshold` returns (on a `CAP_POLL_TIMEOUT_S`
  timeout or a crossing), then recomputes the target from the next
  buffered `ELECTRODES_STATE_CHANGE`. On real hardware capacitance
  reports arrive sub-second, so re-sync effectively happens at every
  phase boundary. For protocols whose per-phase dwell is shorter than
  ~`CAP_POLL_TIMEOUT_S`, several phases can buffer during one monitor
  poll, so a phase may be evaluated against a slightly-stale (earlier)
  phase's target — ending it marginally early. Association is always
  correct (the mailbox is FIFO; the handler never reads a phase it has
  already consumed), only freshness lags. The legacy bounded
  monitoring explicitly to the phase duration; a future enhancement
  could stamp a monotonic phase index into the `ELECTRODES_STATE_CHANGE`
  payload and have the monitor abandon as soon as a newer index
  appears. Out of scope for the initial port.
