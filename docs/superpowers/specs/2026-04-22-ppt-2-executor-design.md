# PPT-2 Design — Executor + StepContext.wait_for + pause/stop

Companion to `2026-04-21-pluggable-protocol-tree-design.md` (sections 9–10).
Refines and locks down the choices that the parent spec deferred to PPT-2.

## 0. Scope

Ship the protocol-execution layer for the new pluggable protocol tree:

1. `ProtocolExecutor` — long-lived, one-per-`RowManager`, runs on its own `QThread`.
2. `StepContext` and `ProtocolContext` — passed to each hook, carry per-scope scratch and `wait_for(topic, timeout, predicate)`.
3. Per-step pre-registered mailboxes + a single Dramatiq listener actor that fans incoming messages into the active step's mailboxes.
4. Pause / Resume / Stop with the boundary semantics established in the parent spec.
5. A `repetitions` built-in column (always-on, default 1) so `iter_execution_steps`'s rep-expansion has a real column to drive it.
6. Demo `MessageColumn` (toy) and an enhanced `demos/run_widget.py` that adds Run / Pause / Stop toolbar buttons and wires `MvcTreeModel.set_active_node` to the executor's `step_started` / `step_finished` signals.

Out of scope: hardware columns, route phase math, voltage/frequency, production dock-pane toolbar (deferred to PPT-3+).

## 1. Decisions locked in during brainstorming

| # | Question | Decision |
|---|---|---|
| 1 | Threading model | **QThread** — `executor.start()` constructs a `QThread`, `moveToThread`s the executor, connects `started → run`. Headless tests can call `executor.run()` directly without ever calling `start()`. |
| 2 | UI scope | **Programmatic API + active-row highlighting + demo toolbar.** Production dock pane stays passive until PPT-3. |
| 3 | Repetitions column | **Always-on built-in** (5th default column). `IntSpinBoxColumnView` default 1, range 1–1000. Visible by default. |
| 4 | Test strategy | **Stub-listener unit tests + one real-Redis integration test** in `tests_with_redis_server_need/`. |
| 5 | `wait_for` buffering | **Per-step pre-registered mailboxes.** At step start the executor opens one empty mailbox per topic in any contributed handler's `wait_for_topics`. Listener routes incoming messages into mailboxes. `wait_for` drains. Predicate-rejected messages are discarded. |

## 2. Package layout

```
pluggable_protocol_tree/
├── execution/
│   ├── __init__.py
│   ├── exceptions.py        # AbortError
│   ├── events.py            # PauseEvent (threading.Event + wait_cleared())
│   ├── signals.py           # ExecutorSignals (QObject)
│   ├── step_context.py      # ProtocolContext, StepContext, Mailbox, wait_first
│   ├── listener.py          # Dramatiq actor + active-step pointer
│   └── executor.py          # ProtocolExecutor (HasTraits, QThread-hosted)
├── builtins/
│   └── repetitions_column.py    # NEW 5th built-in
├── demos/
│   ├── run_widget.py            # extended: Run/Pause/Stop toolbar + signal wiring
│   └── message_column.py        # NEW toy column for the demo
├── tests/
│   ├── test_step_context.py             # mailbox semantics, predicate, timeout, abort
│   ├── test_executor.py                 # bucket fan-out, pause/stop, error propagation
│   ├── test_repetitions_column.py       # 5th built-in
│   └── tests_with_redis_server_need/
│       └── test_executor_redis_integration.py    # one end-to-end test
```

`execution/` is a single cohesive subpackage. Every file in it serves the same responsibility (running protocols). Keeping it separate from `services/` (which only holds `persistence.py` today) makes the boundary obvious.

## 3. Core types

```python
# execution/exceptions.py
class AbortError(Exception):
    """Raised inside ctx.wait_for() when the executor's stop_event fires.
    Hooks should let it propagate; the executor catches it at the bucket boundary."""


# execution/events.py
class PauseEvent:
    """threading.Event with a wait_cleared() helper so the executor's main loop
    can block at a step boundary until the user resumes."""
    def __init__(self):
        self._set = threading.Event()
        self._cleared = threading.Event()
        self._cleared.set()
    def set(self):       self._set.set();    self._cleared.clear()
    def clear(self):     self._set.clear();  self._cleared.set()
    def is_set(self):    return self._set.is_set()
    def wait_cleared(self, timeout=None):
        self._cleared.wait(timeout)


# execution/signals.py
class ExecutorSignals(QObject):
    protocol_started   = Signal()
    step_started       = Signal(object)        # row
    step_finished      = Signal(object)
    protocol_paused    = Signal()
    protocol_resumed   = Signal()
    protocol_finished  = Signal()              # ran to completion
    protocol_aborted   = Signal()              # user pressed Stop
    protocol_error     = Signal(str)           # exception raised in a hook


# execution/step_context.py
class ProtocolContext(HasTraits):
    """Spans the whole protocol run."""
    columns    = List(Instance(IColumn))
    scratch    = Dict(Str, Any, desc="protocol-scoped scratch (cleared on each run)")
    stop_event = Instance(threading.Event)


class StepContext(HasTraits):
    """Spans one step. Hooks call wait_for() on this."""
    row        = Instance(BaseRow)
    protocol   = Instance(ProtocolContext)
    scratch    = Dict(Str, Any, desc="step-scoped scratch (cleared per step)")
    _mailboxes = Dict(Str, Instance(Mailbox))   # topic → Mailbox; pre-opened at step start

    def wait_for(self, topic: str, timeout: float = 5.0,
                 predicate: Optional[Callable[[Any], bool]] = None) -> Any:
        """Block until a buffered or arriving message on `topic` satisfies
        `predicate`. Returns the payload. Raises TimeoutError on timeout.
        Raises AbortError if the protocol's stop_event fires."""
```

Note: hook signature is `(self, row, ctx)` for per-step hooks (matches PPT-1's `IColumnHandler` interface as written), `(self, ctx)` for protocol-level (`on_protocol_start`, `on_protocol_end`). The executor passes arguments in this order.

## 4. Mailbox + listener

### Per-step mailbox lifecycle

```python
# execution/step_context.py
class Mailbox:
    """SimpleQueue-backed buffer with a wake event. One per (step, topic)."""
    def __init__(self):
        self.q    = queue.SimpleQueue()
        self.wake = threading.Event()
    def deposit(self, payload):
        self.q.put(payload)
        self.wake.set()
    def drain_one(self, predicate, timeout, stop_event):
        deadline = time.monotonic() + timeout
        while True:
            # 1. Pull a satisfying item out of the queue, if any.
            while not self.q.empty():
                item = self.q.get_nowait()
                if predicate is None or predicate(item):
                    return item
                # else discard and continue draining
            self.wake.clear()
            # 2. Block until the listener wakes us, stop fires, or timeout.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(...)
            triggered = wait_first([self.wake, stop_event], timeout=remaining)
            if triggered is stop_event:
                raise AbortError(...)


def wait_first(events: list[threading.Event], timeout: float) -> Optional[threading.Event]:
    """Block until any of `events` fires, or timeout. Returns the event that fired,
    or None on timeout. Implemented via a shared 'waker' event the executor + listener
    both signal when they want to interrupt a wait."""
```

### Listener — single Dramatiq actor, fans into the active step

```python
# execution/listener.py
_active_step_ctx: Optional[StepContext] = None
_active_lock    = threading.Lock()

def set_active_step(step_ctx):  # called by executor before each step
    global _active_step_ctx
    with _active_lock:
        _active_step_ctx = step_ctx

def clear_active_step():        # called by executor after each step
    global _active_step_ctx
    with _active_lock:
        _active_step_ctx = None


@dramatiq.actor(actor_name="pluggable_protocol_tree_executor_listener", queue_name="default")
def executor_listener(message: dict):
    """Receives every message on any topic in the aggregated wait_for_topics
    set. Routes payload into the active step's mailbox for that topic."""
    topic   = message["topic"]
    payload = message["payload"]
    with _active_lock:
        ctx = _active_step_ctx
    if ctx is None:
        return                  # no protocol running; drop silently
    box = ctx._mailboxes.get(topic)
    if box is not None:
        box.deposit(payload)
```

**Rationale.** The listener is module-level / singleton-ish; the active-step pointer is what gates message routing. Late messages from the previous step on a topic the next step also watches are *not* delivered — `clear_active_step` is called inside `finally`, so by the time the next step's `set_active_step` runs there's a deliberate gap. (If we wanted at-most-once cross-step buffering we'd carry a per-protocol mailbox; PPT-2 doesn't need it.)

### Subscription set — registered once at plugin start

The message router exposes `add_subscriber_to_topic(topic, actor_name)` (in `microdrop_utils/dramatiq_pub_sub_helpers.py`) for dynamic subscriptions. At plugin start the PPT plugin aggregates `wait_for_topics` from every contributed handler and registers each one for the executor's listener actor:

```python
# pluggable_protocol_tree/plugin.py — additions
class PluggableProtocolTreePlugin(Plugin):
    ...
    def start(self):
        super().start()
        all_columns = self._assemble_columns()
        topics = sorted({t for c in all_columns for t in c.handler.wait_for_topics})
        router_data = MessageRouterData()    # connects via shared Redis hash
        for topic in topics:
            router_data.add_subscriber_to_topic(
                topic=topic,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
```

(The static `ACTOR_TOPIC_DICT = {}` declared in `consts.py` stays empty — the executor's subscription is registered dynamically because the topic set depends on which columns are contributed, which is only knowable after extension-point resolution.)

The aggregated subscription list is computed once at plugin start. Adding a column with a new `wait_for_topic` after start would require a restart — acceptable for PPT-2; revisit if dynamic plugin loading becomes a thing.

### Executor's per-step setup

For each step in `iter_execution_steps`:
1. Build `step_ctx` with one empty `Mailbox` per topic in any contributed handler's `wait_for_topics`.
2. Call `set_active_step(step_ctx)`.
3. Run `on_pre_step`, `on_step`, `on_post_step` (each phase fans out across priority buckets).
4. Call `clear_active_step()` in a `finally`.

### Same-topic conflict guard

If two columns in the *same priority bucket* both declare the same topic in `wait_for_topics`, the executor raises a clear error at step start. Multiple concurrent waiters on the same topic is a fan-out pattern we don't have a use case for yet — supporting it changes `Mailbox` from a queue to a per-waiter copy-on-deposit broadcast. Two columns in *different* priority buckets is fine (sequential).

## 5. Executor mainloop

```python
# execution/executor.py
class ProtocolExecutor(HasTraits):
    """Long-lived; one per RowManager. Reused across runs."""

    row_manager = Instance(RowManager)
    qsignals    = Instance(ExecutorSignals)

    pause_event = Instance(PauseEvent)
    stop_event  = Instance(threading.Event)

    _thread = Instance(QThread)
    _error  = Instance(Exception)

    bucket_pool_factory = Callable    # injectable for tests; default ThreadPoolExecutor

    # --- public API (called from the GUI thread) ---

    def start(self):
        if self._thread and self._thread.isRunning():
            return                    # idempotent; ignore double-start
        self.pause_event.clear()
        self.stop_event.clear()
        self._error = None
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        self._thread.start()

    def pause(self):
        self.pause_event.set()
        self.qsignals.protocol_paused.emit()

    def resume(self):
        self.pause_event.clear()
        self.qsignals.protocol_resumed.emit()

    def stop(self):
        self.stop_event.set()
        self.pause_event.clear()      # unblock wait_cleared() so loop can notice

    # --- main loop (runs on _thread) ---

    def run(self):
        cols = list(self.row_manager.columns)
        proto_ctx = ProtocolContext(columns=cols, stop_event=self.stop_event)
        try:
            self._run_hooks("on_protocol_start", cols, proto_ctx, row=None)
            self.qsignals.protocol_started.emit()

            for row in self.row_manager.iter_execution_steps():
                if self.stop_event.is_set():
                    break
                if self.pause_event.is_set():
                    self.pause_event.wait_cleared()
                    if self.stop_event.is_set():
                        break

                step_ctx = self._build_step_ctx(row, cols, proto_ctx)
                set_active_step(step_ctx)
                try:
                    self.qsignals.step_started.emit(row)
                    self._run_hooks("on_pre_step",  cols, step_ctx, row)
                    self._run_hooks("on_step",      cols, step_ctx, row)
                    self._run_hooks("on_post_step", cols, step_ctx, row)
                    self.qsignals.step_finished.emit(row)
                finally:
                    clear_active_step()

            # on_protocol_end runs even on stop, as best-effort cleanup
            self._run_hooks("on_protocol_end", cols, proto_ctx, row=None)

        except Exception as e:
            self._error = e
            logger.exception("Protocol error")
            try:
                self._run_hooks("on_protocol_end", cols, proto_ctx, row=None)
            except Exception:
                logger.exception("on_protocol_end raised during error cleanup")

        finally:
            self._emit_terminal_signal()
            self._thread.quit()

    def _emit_terminal_signal(self):
        if self._error is not None:
            self.qsignals.protocol_error.emit(str(self._error))
        elif self.stop_event.is_set():
            self.qsignals.protocol_aborted.emit()
        else:
            self.qsignals.protocol_finished.emit()

    def _run_hooks(self, hook_name, cols, ctx, row):
        """Priority-bucket fan-out. Sequential buckets, parallel within."""
        buckets = group_by_priority(cols)
        for priority in sorted(buckets):
            bucket_cols = buckets[priority]
            self._assert_no_topic_conflicts(bucket_cols)
            with self.bucket_pool_factory(max_workers=max(1, len(bucket_cols))) as pool:
                futures = {
                    pool.submit(self._invoke_hook, col, hook_name, ctx, row): col
                    for col in bucket_cols
                }
                first_exc = None
                for f in as_completed(futures):
                    if f.exception() and first_exc is None:
                        first_exc = f.exception()
                        # Set stop so any sibling wait_for() returns promptly,
                        # then let the pool drain naturally.
                        self.stop_event.set()
                if first_exc is not None:
                    raise first_exc
```

### Three pinned-down behaviors

1. **Three terminal signal cases — single source of truth.** `_emit_terminal_signal` reads `self._error` and `self.stop_event` to decide which of `protocol_finished` / `protocol_aborted` / `protocol_error` fires. No path in `run()` emits these directly.

2. **`stop` unblocks `pause`.** A naive `pause_event.set(); wait_cleared()` would deadlock if Stop happens during pause — Stop only sets `stop_event`, not `pause_event`. So `stop()` also clears `pause_event`, and the main loop re-checks `stop_event` after `wait_cleared()` returns.

3. **Bucket parallel error → cooperative abort.** First exception in a bucket sets `stop_event`, lets siblings drain (their `wait_for` calls raise `AbortError` immediately), then raises the original exception out of `_run_hooks` to the outer try/except. We don't try to cancel futures — Python threads aren't cancellable.

### Acknowledged limitation

Hooks doing pure CPU work (no `wait_for`) **can't be aborted mid-call**. If a hook spins for 30 seconds doing math, Stop won't take effect until it returns. Doc'd best-practice: long-running hooks check `ctx.protocol.stop_event.is_set()` periodically. PPT-2's toy `MessageColumn` doesn't have this problem; PPT-3's `RoutesHandler` will need to mind it.

## 6. The repetitions built-in column

Always-on, fifth default column.

```python
# builtins/repetitions_column.py
class RepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this row executes (groups expand subtree N×)")


def make_repetitions_column():
    return Column(
        model=RepetitionsColumnModel(
            col_id="repetitions", col_name="Reps", default_value=1,
        ),
        view=IntSpinBoxColumnView(low=1, high=1000),
    )
```

Plugin's `_assemble_columns` becomes `[type, id, name, repetitions, duration_s] + contributed`. Default visible. PPT-1 ships `iter_execution_steps` already reading `getattr(row, "repetitions", 1)`; the column populates the trait so the `getattr` fallback becomes vestigial (kept as-is for safety against orphan persisted protocols).

## 7. Toy MessageColumn (demo only)

```python
# demos/message_column.py
class MessageColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Str("hello", desc="Message published when this step runs")


class MessageColumnHandler(BaseColumnHandler):
    priority        = 50
    wait_for_topics = []

    def on_step(self, row, ctx):
        msg = self.model.get_value(row)
        publish_message(topic="microdrop/protocol_tree/demo_message",
                        message={"row_uuid": row.uuid, "name": row.name, "msg": msg})


def make_message_column():
    return Column(
        model=MessageColumnModel(
            col_id="demo_message", col_name="Message", default_value="hello",
        ),
        view=StringEditColumnView(),
        handler=MessageColumnHandler(),
    )
```

Lives in `demos/`, not `builtins/`, because it's only useful in the demo. Tests instantiate it directly.

## 8. Demo enhancement

`demos/run_widget.py` gains a Run / Pause / Stop toolbar group; each button is wired to the executor. The demo wires:

```python
# in DemoWindow.__init__
self.executor = ProtocolExecutor(
    row_manager=self.manager,
    qsignals=ExecutorSignals(),
    pause_event=PauseEvent(),
    stop_event=threading.Event(),
)

# Active-row highlighting
self.executor.qsignals.step_started.connect(self.widget.model.set_active_node)
self.executor.qsignals.step_finished.connect(lambda row: self.widget.model.set_active_node(None))
self.executor.qsignals.protocol_finished.connect(lambda: self.widget.model.set_active_node(None))
self.executor.qsignals.protocol_aborted.connect(lambda: self.widget.model.set_active_node(None))
self.executor.qsignals.protocol_error.connect(lambda msg: QMessageBox.critical(self, "Protocol error", msg))

# Toolbar
tb.addAction("Run",   self.executor.start)
tb.addAction("Pause", self._toggle_pause)   # toggles between pause()/resume()
tb.addAction("Stop",  self.executor.stop)
```

The MessageColumn is added to the demo's column list so a fresh demo shows it as a column. Default reps=1 means a 3-step protocol runs 3 times through `on_step`; if the user changes a row's reps to 3, the active-row highlight visibly bounces back to that row 3 times.

## 9. Testing

### `tests/test_step_context.py` — pure unit, no Qt, no Dramatiq
- `Mailbox.deposit` + `drain_one` round-trip
- `drain_one` with predicate: matching message returns; non-matching is discarded; subsequent matching wakes
- `drain_one` timeout raises `TimeoutError`
- `drain_one` with `stop_event` pre-set raises `AbortError` immediately
- `drain_one` with `stop_event` fired mid-wait raises `AbortError` (not waiting out timeout)
- `wait_first` helper picks up the first event of N to fire
- Pre-deposited messages return without blocking (the race-fix that justifies the buffering model)

### `tests/test_executor.py` — executor logic, no Qt event loop, no Dramatiq
Uses an injected synchronous `bucket_pool_factory` for deterministic test order. Signals are spied via direct-connect lambdas appending to a list (no `QApplication` needed).
- All five hooks fire in the right order across one step (`on_protocol_start`, then per step `on_pre_step` / `on_step` / `on_post_step`, then `on_protocol_end`)
- Bucket fan-out ordering: priority 10 column runs entirely before priority 30 starts
- Same-priority bucket: two parallel columns both enter `on_step` before either returns (use a `threading.Barrier`)
- Same-topic conflict assertion: two columns in the same priority bucket both declaring `wait_for_topics=["foo"]` raises a clear error at step start
- `pause` between steps actually blocks: a column whose `on_step` calls `executor.pause()`; assert next step doesn't start until `executor.resume()`
- `stop` mid-protocol exits cleanly + emits `protocol_aborted` (not `_finished`)
- `stop` while paused unblocks (the deadlock-avoidance code in `executor.stop`)
- Hook raises → `protocol_error(str)` emitted, NOT `protocol_finished` or `protocol_aborted`; `on_protocol_end` still called as cleanup
- `on_protocol_end` raising during error cleanup is swallowed (logged, not re-raised) — original error wins
- Repetitions column with value 3 → `on_step` fires 3× for the row

### `tests/test_repetitions_column.py` — the new built-in
- Default value is 1
- IntSpinBox view low=1 high=1000
- `iter_execution_steps` expands a step with `repetitions=3` to 3 yields (regression-locks the existing PPT-1 contract through a real column rather than `setattr`)

### `tests_with_redis_server_need/test_executor_redis_integration.py` — one end-to-end test
- Spin up a real `executor_listener` Dramatiq actor with a fixture
- Build a column whose `on_step` does `publish_message("test/ack", {"ok": True})` then `ctx.wait_for("test/ack", timeout=2)`
- Run the executor with one step
- Assert the published message round-trips through Redis → listener → mailbox → `wait_for` → handler returns the payload
- Skip via the existing `tests_with_redis_server_need/` convention if Redis isn't reachable

### Acceptance bar for PPT-2 merge
- All `pluggable_protocol_tree/tests/` pass without Redis (the integration test is gated)
- The integration test passes with `redis-server` running
- `demos/run_widget.py` opens, you can click Run on a 3-step protocol with the MessageColumn enabled, the active row highlight walks down the tree, Pause/Resume work between steps, Stop exits cleanly

## 10. What's deferred

- **Multiple concurrent waiters on the same topic.** Out of scope. The conflict assertion documents the contract.
- **Dynamic column registration after plugin start.** The `wait_for_topics` aggregation runs once. New columns require a restart.
- **Long-running CPU hooks with cooperative abort.** Best-practice doc'd; no enforcement until PPT-3's `RoutesHandler` needs it.
- **Listener queue backpressure / persistence.** Default Dramatiq behavior; we don't tune it.
- **Production dock-pane Run/Pause/Stop buttons.** Wait for PPT-3 when there's hardware to gate.

## 11. Issue tracking

- Sub-issue: `#364 [PPT-2] Executor + StepContext.wait_for + pause/stop` (already exists)
- PR will close it via `Closes #364`
- Each bite-sized implementation task in the PPT-2 plan gets its own commit; the PR aggregates them.
