# Protocol Status Trackers — Design (issue #467 / PPT-23)

## Problem

The protocol status bar must show, while a protocol runs:

- **Elapsed times** (wall-clock; do **not** freeze on pause) for protocol, step, phase.
- **Active times** (do freeze on pause) for protocol, step, phase.
- **Counters**: `Step n/N` and `Phase n/N`.

Today all of this logic is embedded directly in `ProtocolTreePane`
(`views/protocol_tree_pane.py`): per-run counters (`_step_index`,
`_step_total`, `_phase_index`, `_phase_total`), raw `time.monotonic()`
start stamps (`_step_started_at`, `_phase_started_at`), a 10 Hz
`_tick_timer`, and a `_refresh_status()` that pokes `QLabel` text
directly. The pane is simultaneously the model, the controller, and the
view. That tangle is hard to test (needs Qt + a live executor) and hard
to extend (the six new readouts and counters pile more state onto the
widget).

`StatusBar` (`views/navigation_bar.py`) is already a dumb strip of
`QLabel`s, so the view layer mostly exists; what's missing is a real
model and a clean updater.

## Scope

**In scope:** the model/controller/view separation, all six time
readouts (elapsed + active for protocol/step/phase), and `Step n/N` +
`Phase n/N` counters that reflect **executor** state.

**Deferred to a follow-up issue:** the navigate-while-paused clause
("changing the selected step/phase while paused updates the counters and
makes the run resume from there with a reset timer"). That requires new
executor *resume-from-arbitrary-step/phase* semantics plus tree-selection
wiring — a change to execution semantics, not status tracking. The model
is designed so adding it later is a localized change (a `reset`/`seek`
method + a selection→controller hook), not a rewrite.

## Naming note

A `PluggableProtocolStateTracker` already exists in
`services/protocol_state_tracker.py`, but it tracks **file** state
(loaded name, dirty/modified, `is_active`), not run timing. To avoid
confusion the new pieces use **"status"**: `ProtocolStatusModel`,
`ProtocolStatusController`. `PluggableProtocolStateTracker` is also the
precedent for this design — it already drives the dock-pane title purely
through Traits observers (`@observe("protocol_name, is_modified, ...")`),
which is exactly the model→view-via-observers pattern used here.

## Architecture (MVC)

```
ExecutorSignals ──(Qt queued, GUI thread)──▶ ProtocolStatusController
                                                     │  (signal → model method)
                                                     ▼
                                           ProtocolStatusModel  (HasTraits, no Qt)
                                                     │  Traits observers (discrete)
                                                     │  + QTimer poll (continuous)
                                                     ▼
                                              StatusBar (QLabels)
```

Three units, each independently understandable and testable:

- **Model** — state + timing **rules**. Pure HasTraits, no Qt, no
  threads, no `time` calls (clock passed in). The brain.
- **Controller** ("handler") — subscribes to `ExecutorSignals`, maps
  each signal to one model method call. No formatting, no widgets.
- **View** — `StatusBar` binds to the model: Traits observers update the
  discrete labels; a `QTimer` polls the stopwatches for the smoothly
  changing time fields.

### Load-bearing invariant

**The model is only ever mutated on the GUI thread.** It holds because
`ExecutorSignals` is a `QObject` delivering via queued connections, so
the controller's slots run on the GUI thread; therefore the model's
Traits observers also fire on the GUI thread and may touch widgets
directly. This is why **no Qt-signal bridge is needed** (unlike
`DeviceViewerSyncController._Bridge`, which guards against off-thread
mutation). The controller asserts GUI-thread affinity on each slot in
debug builds.

## Component 1 — `ScopeStopwatch` (`models/stopwatch.py`)

A generic, Qt-free primitive tracking two clocks for one scope. Every
method takes `now` (a monotonic timestamp) so it never calls the clock
itself — fully deterministic under test.

State: `_elapsed_anchor`, `_elapsed_accum`, `_active_anchor`,
`_active_accum` (all float / `None`).

```
start(now)   reset accums to 0; both anchors = now           (begins ticking + running)
pause(now)   _active_accum += now - _active_anchor; _active_anchor = None   (elapsed keeps ticking)
resume(now)  _active_anchor = now                            (no-op if already running / not started)
stop(now)    fold BOTH anchors into accums; both = None      (freezes final elapsed + active)
elapsed(now) _elapsed_accum + (now - _elapsed_anchor if ticking else 0)   # ignores pause
active(now)  _active_accum  + (now - _active_anchor  if running else 0)    # freezes between pause/resume
```

- *Elapsed* clock pauses for nothing; only `start` (reset) and `stop`
  affect it beyond free-running.
- *Active* clock freezes during every pause→resume gap.
- Not started → both anchors `None`, accums 0 → both read 0.

Three instances per run cover all six readouts: `protocol`, `step`,
`phase`.

## Component 2 — `ProtocolStatusModel` (`models/protocol_status.py`)

`HasTraits`, zero Qt.

**Observable traits** (drive discrete view updates):
`step_index`, `step_total`, `phase_index`, `phase_total`,
`repeats_completed`, `repeats_total` (`Int`); `recent_step_name`,
`next_step_name`, `rep_chain_label` (`Str`); `phase_target_s` (`Float`);
`running`, `paused` (`Bool`).

**Composed** (plain `ScopeStopwatch`): `protocol_clock`, `step_clock`,
`phase_clock`.

**Rule methods** (each takes `now` where timing is involved):

| Method | Effect |
|---|---|
| `on_protocol_start(now, step_total)` | reset everything; `step_total=…`; `running=True`; `paused=False`; `protocol_clock.start(now)` |
| `on_step_start(now, recent, next_)` | `step_index += 1`; set names; clear phase counters + `phase_target_s`; `step_clock.start(now)`; fresh (unstarted) phase clock |
| `on_phase_start(now, idx, total, target)` | set `phase_index/total/target`; `phase_clock.start(now)` |
| `on_phase_extended(extra)` | `phase_target_s += extra` |
| `pause(now)` | `paused=True`; pause all three clocks |
| `resume(now)` | `paused=False`; resume all three clocks |
| `on_repetition(completed, total)` | set repeat counters |
| `set_rep_chain(label)` | set `rep_chain_label` |
| `stop(now)` | `running=False`; `paused=False`; stop (freeze) all three clocks |
| `reset()` | counters→0, names→"-", clocks fresh, flags False |

The rules ("increment step per step_start", "a new step resets the phase
clock", "pause freezes active but not elapsed") live **here** — testable
with a fake clock, no executor, no Qt.

## Component 3 — `ProtocolStatusController` (`services/protocol_status_controller.py`)

A small **`HasTraits`** adapter that **owns the model** and links the Qt
layer to it. Constructed with `qsignals` (`ExecutorSignals`), `manager`
(`RowManager`, for the step count + next-step name), and
`clock=time.monotonic`; it creates its own `model = ProtocolStatusModel()`
(exposed as `.model`). On construction it connects one slot per executor
signal; each slot reads `now = self.clock()` and calls a model method.

**Ownership / reuse.** The controller is *not* the dock pane itself, but
the dock pane (the app's `HasTraits` composition root) **instantiates and
owns it** — satisfying "the dock pane sets up the link between the Qt
layer and the model." The standalone `BasePluggableProtocolDemoWindow`
(used by demos and tests, with no dock pane) instantiates the **same**
controller, so there is one wiring implementation and no duplication.
This is why the controller is a standalone reusable class rather than
slots on the dock pane: the pane is reused without a dock pane, and the
wiring must come along.

Each slot is a near one-liner: `now = self.clock()` then a model call.

| `ExecutorSignals` | model call |
|---|---|
| `protocol_started` | `on_protocol_start(now, self._count_steps())` |
| `step_started(row)` | `on_step_start(now, row.name, self._next_name(row))` |
| `step_repetition(chain)` | `set_rep_chain(self._fmt_chain(chain))` |
| `phase_started(i, n, d)` | `on_phase_start(now, i, n, d)` |
| `phase_extended(x)` | `on_phase_extended(x)` |
| `protocol_paused` | `pause(now)` |
| `protocol_resumed` | `resume(now)` |
| `protocol_repetition_finished(c, t)` | `on_repetition(c, t)` |
| `protocol_finished` / `protocol_aborted` / `protocol_error` | `stop(now)` |

`_count_steps`, `_next_name`, `_fmt_chain` move here from the pane (they
need `manager`). The controller also exposes `disconnect()` for teardown.

The controller deliberately does **not** subscribe to the demo-only
`phase_acked` path or `protocol_wait_*`; those stay where they are (the
pane / demo window own the pre-protocol loading screen and the demo ack
plumbing). The controller is purely executor-lifecycle → status model.

## Component 4 — View binding (`StatusBar.bind(model)` in `navigation_bar.py`)

`StatusBar` gains `bind(model)` and the three combined time fields
(replacing the current `lbl_total_time` / `lbl_step_time` /
`lbl_phase_time`):

- `Protocol 12.3s (act 9.1s)`
- `Step 3.4s (act 2.1s)`
- `Phase 2/4  1.2s/2.0s (act 1.0s)`

plus the existing-style counters `Step n/N`, the rep-chain label, and the
recent/next step marquees.

`bind(model)`:

- **Discrete** → `model.observe(...)` handlers update counter / name /
  rep-chain labels and the `Phase n/N` portion.
- **Continuous** → a 100 ms `QTimer`, started/stopped by observing
  `running`, reads `model.<scope>_clock.elapsed(now)` / `.active(now)`
  and writes the three time labels. The timer runs only while a protocol
  is active, so an idle status bar costs nothing.

All number→string formatting lives in the view. Touching widgets inside
Traits observers is safe per the GUI-thread invariant above.

## Component 5 — `ProtocolTreePane` refactor (`views/protocol_tree_pane.py`)

Remove the embedded **status** logic: the state vars (`_step_index`,
`_step_total`, `_phase_index`, `_phase_total`, `_phase_target`,
`_step_started_at`, `_phase_started_at`, `_current_row`), the
`_tick_timer`, `_refresh_status`, the `_status_*` label aliases, and the
status-display bodies of `_on_protocol_started` / `_on_step_started` /
`_on_phase_started` / `_on_phase_extended` / `_on_step_repetition` /
`_on_step_finished`. `_next_step_name` moves to the controller.

The pane does **not** itself create the model/controller — the
composition root does (Component 6). The pane only needs to expose
`self.status_bar` (already public) so the root can call
`status_bar.bind(model)`.

The pane **keeps** its non-status responsibilities that happen to share
the same signals — `protocol_running_changed.emit(...)`, publishing
`PROTOCOL_RUNNING`, the error dialog flow (`_on_error`), the button
state machine, navigation, pause-phase handling, repeat-count label, and
the pre-protocol wait/loading screen. Several of these are currently
interleaved with status pokes in the same slot bodies, so the edit is
surgical (remove the status lines, keep the rest), not whole-slot
deletion. Multiple slots per signal is fine.

## Component 6 — Composition roots wire model + controller

Two roots construct and own the controller; neither duplicates logic.

**`PluggableProtocolDockPane`** (`views/dock_pane.py`) — gains
`status_controller = Instance(ProtocolStatusController)`. In
`create_contents`, after the pane exists:

```python
self.status_controller = ProtocolStatusController(
    qsignals=pane.executor.qsignals, manager=self.manager)
pane.status_bar.bind(self.status_controller.model)
```

**`BasePluggableProtocolDemoWindow`** (`demos/base_demo_window.py`) — does
the same after building `self.pane`, storing `self.status_controller`.
Its status-internal properties (`_step_index`, `_step_total`,
`_step_started_at`, `_phase_started_at`, `_current_row`, `_tick_timer`,
`_status_step_label`, `_status_step_time_label`, `_status_reps_label`,
`_status_phase_time_label`) are **removed**; demos/tests read
`window.status_controller.model` instead.

## Test migration

`tests/test_base_demo_window.py` currently asserts on the removed pane
internals (e.g. `_status_step_label.text()`, `_tick_timer.interval()`,
`_phase_started_at` set on ack, terminate resets `_step_started_at`,
`_status_reps_label`, elapsed text). These tests pin the *old*
implementation. They are migrated:

- Behaviors that are really **model/controller** logic (counters,
  elapsed/active, rep-chain formatting, reset-on-terminate) move to the
  new `test_protocol_status_model.py` / `test_protocol_status_controller.py`
  (pure, no Qt) — which is strictly better coverage.
- The few genuinely window-level assertions (the StatusBar shows the
  bound values; the poll timer ticks while running) are rewritten against
  `window.status_controller.model` and the new combined labels, or
  deleted if fully superseded.

## Testing

Pure-Python unit tests (no Qt, no executor):

- `tests/test_stopwatch.py` — fake clock: elapsed ignores pause, active
  freezes across pause→resume, `stop` freezes both, not-started reads 0.
- `tests/test_protocol_status_model.py` — drive a realistic method
  sequence (start → step → phase → pause → resume → repetition → stop)
  with a fake `now`, asserting counters, names, flags, and clock reads at
  each step.

Controller mapping can be exercised by calling its slot methods directly
with a stub `manager` and asserting model state; full Qt signal delivery
is out of unit scope.

## Separation directive (reusable convention)

This issue establishes the pattern for status/UI features going forward:

> Split into a **Qt-free `HasTraits` model** (state + rules) ← a
> **controller** (external signals → model method calls) → a **view**
> (Traits observers + a poll timer → widgets). Keep the model free of Qt
> and of direct clock/IO calls (pass `now`/inputs in) so it is
> unit-testable in isolation. Mutate the model only on the GUI thread so
> observers can drive widgets directly without a Qt-signal bridge; if
> off-thread mutation is unavoidable, add a `QObject` bridge
> (cf. `DeviceViewerSyncController._Bridge`).

The pane-as-model-controller-view tangle removed here is the
anti-pattern this convention prevents.

## Out of scope / non-goals

- Navigate-while-paused resume-from-step (deferred, see Scope).
- Persisting timing across app restarts.
- Changing executor pause/resume semantics.
