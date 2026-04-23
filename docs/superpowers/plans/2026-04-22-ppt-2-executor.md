# PPT-2: Executor + StepContext.wait_for + pause/stop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the protocol-execution layer for the new pluggable protocol tree: a `ProtocolExecutor` that runs a `RowManager`'s rows, fires the five `IColumnHandler` hooks per step in priority-bucket order, and lets handlers block on `ctx.wait_for(topic)` for asynchronous Dramatiq replies — with pause/stop/error semantics doing the right thing in every case.

**Architecture:** Three-layer split inside a new `execution/` subpackage.
1. **Plumbing** — small types: `AbortError`, `PauseEvent`, `ExecutorSignals` (QObject), `Mailbox`, `wait_first` helper. Each one-job, one-file.
2. **Context** — `ProtocolContext` and `StepContext`. Per-step mailboxes are *pre-registered* before any hook publishes, so the publish-then-ack race never bites. A single Dramatiq listener actor holds an "active-step" pointer and routes incoming messages into the active step's mailboxes.
3. **Executor** — `ProtocolExecutor` (HasTraits, hosted on its own `QThread`). Walks `iter_execution_steps`, fans hooks across priority buckets (sequential between buckets, parallel within), distinguishes `protocol_finished` / `protocol_aborted` / `protocol_error` by checking `_error` then `stop_event` in one place.

**Tech Stack:** PySide6 / Qt6, Pyface, Traits/HasTraits, Dramatiq + Redis (the existing message router), `concurrent.futures.ThreadPoolExecutor` for in-bucket parallelism, `queue.SimpleQueue` + `threading.Event` for mailboxes, pytest (+ pytest gates for the Redis integration test).

**Spec:** `src/docs/superpowers/specs/2026-04-22-ppt-2-executor-design.md`

**Issue:** Closes #364 (sub-issue) — part of umbrella #361.

**Branch:** `feat/ppt-2-executor` (already created when the spec was committed).

---

## File structure

New files in this PR:

```
src/pluggable_protocol_tree/
├── execution/
│   ├── __init__.py
│   ├── exceptions.py         # AbortError
│   ├── events.py             # PauseEvent
│   ├── signals.py            # ExecutorSignals(QObject)
│   ├── step_context.py       # wait_first + Mailbox + ProtocolContext + StepContext
│   ├── listener.py           # active-step pointer + Dramatiq executor_listener actor
│   └── executor.py           # ProtocolExecutor
├── builtins/
│   └── repetitions_column.py     # 5th always-on built-in
├── demos/
│   └── message_column.py     # toy column for the demo
└── tests/
    ├── test_step_context.py
    ├── test_executor.py
    └── tests_with_redis_server_need/
        ├── __init__.py
        └── test_executor_redis_integration.py
```

Modified files:

```
src/pluggable_protocol_tree/
├── plugin.py                 # _assemble_columns adds repetitions; start() registers subscriptions
├── demos/run_widget.py       # adds Run/Pause/Stop toolbar + signal wiring
└── tests/test_builtins.py    # adds repetitions tests
```

Each `execution/` file has one clear responsibility. The `step_context.py` file groups `Mailbox`, `wait_first`, `ProtocolContext`, and `StepContext` together because they form one cohesive unit (mailbox lifetime is bound to step context lifetime, and `wait_for` is the public method that ties them together) — splitting them across files would scatter their tight coupling for no payoff.

---

## Working directory and conventions

All commands run from the **outer repo** at `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py` (this is where `pixi.toml` lives). Pixi is required — never invoke `python` or `pytest` directly. The standard form is:

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest <args>"
```

All `git` operations run from the **submodule** at `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src` on branch `feat/ppt-2-executor`. The pre-existing modification to `protocol_grid/preferences.py` must remain unstaged throughout — do not stage or modify it.

Commit messages all start with `[PPT-2]` and end with the standard `Co-Authored-By:` trailer.

---

## Task 0: Verify branch + issue state

**Files:** none (git/gh only)

- [ ] **Step 1: Verify the working branch and clean tree (other than preferences.py)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git rev-parse --abbrev-ref HEAD && git status --short
```

Expected: `feat/ppt-2-executor` and only ` M protocol_grid/preferences.py` (or possibly nothing if the file is untouched in your local clone). Anything else means there's stray work — investigate before continuing.

- [ ] **Step 2: Verify issue #364 is open and the spec commit is on the branch**

```bash
gh issue view 364 --repo Blue-Ocean-Technologies-Inc/Microdrop --json state,title
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git log --oneline -3
```

Expected: issue state `OPEN`, title `[PPT-2] Executor + StepContext.wait_for + pause/stop`. Most recent commit on the branch is `[Spec] PPT-2 executor — design doc`.

---

## Task 1: Package scaffolding for `execution/`

**Files:**
- Create: `src/pluggable_protocol_tree/execution/__init__.py`

- [ ] **Step 1: Create the directory and empty package init**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  mkdir -p pluggable_protocol_tree/execution
```

Then create `src/pluggable_protocol_tree/execution/__init__.py` as an **empty file** (no content).

- [ ] **Step 2: Smoke-test the package is importable**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'import pluggable_protocol_tree.execution; print(pluggable_protocol_tree.execution.__name__)'"
```

Expected: `pluggable_protocol_tree.execution`

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/__init__.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Package scaffolding for execution subpackage

Empty __init__.py so subsequent tasks can land focused modules
(exceptions, events, signals, step_context, listener, executor)
without touching package import shape.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `AbortError` exception

**Files:**
- Create: `src/pluggable_protocol_tree/execution/exceptions.py`
- Create: `src/pluggable_protocol_tree/tests/test_step_context.py` (just the imports + first test for now)

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_step_context.py`:

```python
"""Tests for execution.exceptions, .events, .step_context.

Pure-Python unit tests — no Qt application, no Dramatiq broker.
Behavioral tests for Mailbox / ProtocolContext / StepContext / wait_for
get appended in later tasks; this file starts with the smallest
foundational types."""

from pluggable_protocol_tree.execution.exceptions import AbortError


def test_abort_error_is_exception():
    assert issubclass(AbortError, Exception)


def test_abort_error_carries_message():
    e = AbortError("stop pressed")
    assert str(e) == "stop pressed"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.execution.exceptions`.

- [ ] **Step 3: Implement `AbortError`**

Create `src/pluggable_protocol_tree/execution/exceptions.py`:

```python
"""Execution-layer exceptions."""


class AbortError(Exception):
    """Raised inside ctx.wait_for() when the executor's stop_event fires.

    Hooks should let it propagate; the executor catches it at the bucket
    boundary, sets stop_event (idempotent), drains other in-flight hooks,
    and routes to the protocol_aborted or protocol_error terminal signal
    via _emit_terminal_signal().
    """
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/exceptions.py pluggable_protocol_tree/tests/test_step_context.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] AbortError exception

Marker exception raised by ctx.wait_for() when the executor's stop_event
fires mid-wait. Lets handlers stay agnostic about cooperative shutdown
while the executor handles the routing decision (aborted vs error) at
the bucket boundary.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `PauseEvent`

**Files:**
- Create: `src/pluggable_protocol_tree/execution/events.py`
- Modify: `src/pluggable_protocol_tree/tests/test_step_context.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_step_context.py`:

```python
# --- PauseEvent ---

import threading
import time

from pluggable_protocol_tree.execution.events import PauseEvent


def test_pause_event_starts_unset_and_cleared():
    p = PauseEvent()
    assert p.is_set() is False


def test_pause_event_set_and_clear_round_trip():
    p = PauseEvent()
    p.set()
    assert p.is_set() is True
    p.clear()
    assert p.is_set() is False


def test_pause_event_wait_cleared_returns_immediately_when_unset():
    p = PauseEvent()
    # Already cleared; should not block.
    start = time.monotonic()
    p.wait_cleared(timeout=0.5)
    assert time.monotonic() - start < 0.1


def test_pause_event_wait_cleared_blocks_until_clear():
    p = PauseEvent()
    p.set()
    woken = threading.Event()

    def waiter():
        p.wait_cleared(timeout=2.0)
        woken.set()

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    # waiter should still be blocked
    assert woken.wait(timeout=0.1) is False
    p.clear()
    assert woken.wait(timeout=1.0) is True
    t.join(timeout=1.0)
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.execution.events`.

- [ ] **Step 3: Implement `PauseEvent`**

Create `src/pluggable_protocol_tree/execution/events.py`:

```python
"""Synchronization primitives used by the executor."""

import threading


class PauseEvent:
    """A pause/resume primitive built on two ``threading.Event``s.

    ``threading.Event`` itself doesn't have a ``wait_cleared()`` method,
    but the executor's main loop needs to block at a step boundary until
    the user resumes — a single Event would only let it block until
    *something* is set, not until the existing 'set' state goes away.
    Implementing it as two events (one fires on set, the other on clear)
    keeps each side a simple Event.wait() under the hood.
    """

    def __init__(self):
        self._set = threading.Event()
        self._cleared = threading.Event()
        self._cleared.set()       # initial state: not paused

    def set(self):
        """Mark paused. wait_cleared() will block until clear() is called."""
        self._set.set()
        self._cleared.clear()

    def clear(self):
        """Mark unpaused. Wakes any thread blocked in wait_cleared()."""
        self._set.clear()
        self._cleared.set()

    def is_set(self) -> bool:
        return self._set.is_set()

    def wait_cleared(self, timeout: float = None) -> bool:
        """Block until the event is cleared (i.e., not paused).

        Returns True if the event was cleared, False on timeout.
        Returns immediately if already clear.
        """
        return self._cleared.wait(timeout)
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: 6 passed (2 from Task 2 + 4 here).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/events.py pluggable_protocol_tree/tests/test_step_context.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] PauseEvent: pause/resume primitive

Two-Event composition (set / cleared) so the executor's main loop can
block at a step boundary via wait_cleared() until the user resumes.
threading.Event alone has wait() (block-until-set) but no symmetric
"block until cleared", which is what pause/resume actually needs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `ExecutorSignals` (QObject)

**Files:**
- Create: `src/pluggable_protocol_tree/execution/signals.py`
- Create: `src/pluggable_protocol_tree/tests/test_executor.py` (just imports + signals tests for now)

- [ ] **Step 1: Write the failing tests**

Create `src/pluggable_protocol_tree/tests/test_executor.py`:

```python
"""Tests for execution.executor and .signals.

Most tests do NOT require a QApplication — Qt direct-connect signals work
without an event loop when sender and receiver share a thread. Tests that
need cross-thread signal delivery construct a QApplication via fixture.
"""

from pluggable_protocol_tree.execution.signals import ExecutorSignals


def test_executor_signals_constructible_without_qapplication():
    s = ExecutorSignals()
    # All seven expected signals are present as attributes.
    for name in (
        "protocol_started", "step_started", "step_finished",
        "protocol_paused", "protocol_resumed",
        "protocol_finished", "protocol_aborted", "protocol_error",
    ):
        assert hasattr(s, name), f"missing signal: {name}"


def test_executor_signals_direct_connect_invokes_slot():
    s = ExecutorSignals()
    received = []
    s.protocol_finished.connect(lambda: received.append("finished"))
    s.protocol_finished.emit()
    assert received == ["finished"]


def test_executor_signals_step_started_carries_row():
    s = ExecutorSignals()
    received = []
    s.step_started.connect(lambda row: received.append(row))
    sentinel = object()
    s.step_started.emit(sentinel)
    assert received == [sentinel]


def test_executor_signals_protocol_error_carries_message():
    s = ExecutorSignals()
    received = []
    s.protocol_error.connect(lambda msg: received.append(msg))
    s.protocol_error.emit("oops")
    assert received == ["oops"]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.execution.signals`.

- [ ] **Step 3: Implement `ExecutorSignals`**

Create `src/pluggable_protocol_tree/execution/signals.py`:

```python
"""QObject carrying the executor's UI-facing signals.

Lives on a QObject (not the Traits-based ProtocolExecutor) so Qt's
queued-connection machinery can marshal emissions from the executor's
worker thread to slots living on the GUI thread automatically.

UI consumers connect directly:
    executor.qsignals.step_started.connect(tree_model.set_active_node)
"""

from pyface.qt.QtCore import QObject, Signal


class ExecutorSignals(QObject):
    # Lifecycle
    protocol_started   = Signal()
    protocol_paused    = Signal()
    protocol_resumed   = Signal()
    protocol_finished  = Signal()           # ran to completion
    protocol_aborted   = Signal()           # user pressed Stop
    protocol_error     = Signal(str)        # exception raised in a hook

    # Per-step
    step_started       = Signal(object)     # row
    step_finished      = Signal(object)     # row
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/signals.py pluggable_protocol_tree/tests/test_executor.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] ExecutorSignals — UI-facing Qt signal bundle

Eight signals split across protocol-lifecycle and per-step. Lives on a
QObject (not the Traits ProtocolExecutor) so Qt can marshal emissions
from the executor's worker thread to GUI-thread slots via queued
connections automatically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `Mailbox` + `wait_first`

**Files:**
- Create: `src/pluggable_protocol_tree/execution/step_context.py` (with just the helpers for now)
- Modify: `src/pluggable_protocol_tree/tests/test_step_context.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_step_context.py`:

```python
# --- wait_first ---

from pluggable_protocol_tree.execution.step_context import wait_first


def test_wait_first_returns_event_that_fires_first():
    a = threading.Event()
    b = threading.Event()
    threading.Timer(0.05, b.set).start()
    fired = wait_first([a, b], timeout=1.0)
    assert fired is b


def test_wait_first_returns_none_on_timeout():
    a = threading.Event()
    b = threading.Event()
    fired = wait_first([a, b], timeout=0.05)
    assert fired is None


def test_wait_first_returns_immediately_when_event_already_set():
    a = threading.Event()
    a.set()
    start = time.monotonic()
    fired = wait_first([a], timeout=1.0)
    assert fired is a
    assert time.monotonic() - start < 0.1


# --- Mailbox ---

from pluggable_protocol_tree.execution.step_context import Mailbox
from pluggable_protocol_tree.execution.exceptions import AbortError


def test_mailbox_drain_one_returns_pre_deposited_immediately():
    mb = Mailbox()
    mb.deposit({"v": 1})
    stop = threading.Event()
    start = time.monotonic()
    item = mb.drain_one(predicate=None, timeout=1.0, stop_event=stop)
    assert item == {"v": 1}
    assert time.monotonic() - start < 0.1


def test_mailbox_drain_one_blocks_then_wakes_on_deposit():
    mb = Mailbox()
    stop = threading.Event()
    threading.Timer(0.05, lambda: mb.deposit("hello")).start()
    item = mb.drain_one(predicate=None, timeout=1.0, stop_event=stop)
    assert item == "hello"


def test_mailbox_drain_one_raises_timeout_when_nothing_arrives():
    mb = Mailbox()
    stop = threading.Event()
    with __import__("pytest").raises(TimeoutError):
        mb.drain_one(predicate=None, timeout=0.05, stop_event=stop)


def test_mailbox_drain_one_raises_abort_when_stop_pre_set():
    mb = Mailbox()
    stop = threading.Event()
    stop.set()
    with __import__("pytest").raises(AbortError):
        mb.drain_one(predicate=None, timeout=1.0, stop_event=stop)


def test_mailbox_drain_one_raises_abort_when_stop_fires_mid_wait():
    mb = Mailbox()
    stop = threading.Event()
    threading.Timer(0.05, stop.set).start()
    start = time.monotonic()
    with __import__("pytest").raises(AbortError):
        mb.drain_one(predicate=None, timeout=2.0, stop_event=stop)
    # Must abort promptly, not wait out the 2s timeout.
    assert time.monotonic() - start < 0.5


def test_mailbox_predicate_rejects_then_accepts():
    mb = Mailbox()
    stop = threading.Event()
    mb.deposit({"ready": False})
    mb.deposit({"ready": True})
    item = mb.drain_one(
        predicate=lambda p: p.get("ready"),
        timeout=1.0,
        stop_event=stop,
    )
    assert item == {"ready": True}


def test_mailbox_predicate_rejects_all_pre_deposited_then_blocks():
    mb = Mailbox()
    stop = threading.Event()
    mb.deposit({"ready": False})
    mb.deposit({"ready": False})
    threading.Timer(0.05, lambda: mb.deposit({"ready": True})).start()
    item = mb.drain_one(
        predicate=lambda p: p.get("ready"),
        timeout=1.0,
        stop_event=stop,
    )
    assert item == {"ready": True}
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.execution.step_context`.

- [ ] **Step 3: Implement `wait_first` and `Mailbox`**

Create `src/pluggable_protocol_tree/execution/step_context.py`:

```python
"""Per-protocol and per-step contexts plus the mailbox machinery that
backs ctx.wait_for().

This file groups Mailbox, wait_first, ProtocolContext, and StepContext
together because they form one cohesive unit — a Mailbox's lifetime is
bound to a StepContext's lifetime, and wait_for is the public method
that ties them together. Splitting them across files would scatter
their tight coupling for no payoff.

ProtocolContext / StepContext land in Task 6 — this task ships only the
two primitives Mailbox depends on.
"""

import queue
import threading
import time
from typing import Callable, Optional

from pluggable_protocol_tree.execution.exceptions import AbortError


def wait_first(events: list, timeout: float) -> Optional[threading.Event]:
    """Block until any of `events` fires, or the timeout elapses.

    Returns the Event that fired, or None on timeout. Implemented by
    polling each event with a short slice — Python's stdlib does not
    expose a kqueue/epoll-style multi-event wait, and rolling a
    waker-channel implementation is more code than the executor needs.

    The poll interval is small enough that responsiveness is dominated
    by the OS scheduler, not by the polling cadence.
    """
    deadline = time.monotonic() + timeout
    poll_interval = 0.01      # 10ms
    while True:
        for e in events:
            if e.is_set():
                return e
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_interval, remaining))


class Mailbox:
    """A SimpleQueue-backed buffer with a wake event.

    One Mailbox per (active step, topic) pair. The dramatiq listener
    deposits payloads; ``drain_one`` blocks until a satisfying item is
    available, the stop_event fires, or the timeout expires.
    """

    def __init__(self):
        self._queue = queue.SimpleQueue()
        self._wake = threading.Event()

    def deposit(self, payload):
        """Push a payload onto the queue and wake any blocked waiter."""
        self._queue.put(payload)
        self._wake.set()

    def drain_one(self, predicate: Optional[Callable], timeout: float,
                  stop_event: threading.Event):
        """Return the first queued item satisfying ``predicate``.

        Discards predicate-rejected items (they are not requeued).
        Raises ``TimeoutError`` if the deadline elapses with no match.
        Raises ``AbortError`` if ``stop_event`` is set, either before
        the call or while the call is blocked.
        """
        if stop_event.is_set():
            raise AbortError("stop_event set before wait_for")
        deadline = time.monotonic() + timeout
        while True:
            # 1) Drain any currently-queued items.
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if predicate is None or predicate(item):
                    return item
                # else discard and continue
            # 2) Block for more.
            self._wake.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"wait_for timed out after {timeout}s"
                )
            triggered = wait_first(
                [self._wake, stop_event], timeout=remaining
            )
            if triggered is None:
                raise TimeoutError(
                    f"wait_for timed out after {timeout}s"
                )
            if triggered is stop_event:
                raise AbortError("stop_event fired while waiting")
            # else self._wake fired; loop back and try to drain.
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: 16 passed (2 + 4 + 3 + 7).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/step_context.py pluggable_protocol_tree/tests/test_step_context.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Mailbox + wait_first helper

Mailbox buffers payloads from the dramatiq listener until the active
hook's ctx.wait_for() drains them. Predicate-rejected items are
discarded; TimeoutError on deadline; AbortError when stop_event fires
(immediately if pre-set, promptly if mid-wait — without waiting out
the timeout).

wait_first polls a list of Events for the first to fire (10ms slice),
since stdlib doesn't expose a cross-event multi-wait. Used by Mailbox
to break out of a long-timeout wait the moment Stop is pressed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `ProtocolContext` + `StepContext` + `wait_for`

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/step_context.py` (append)
- Modify: `src/pluggable_protocol_tree/tests/test_step_context.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_step_context.py`:

```python
# --- ProtocolContext + StepContext + wait_for ---

from pluggable_protocol_tree.execution.step_context import (
    ProtocolContext, StepContext,
)
from pluggable_protocol_tree.models.row import BaseRow


def _make_step_ctx(topics: list[str]) -> StepContext:
    """Helper: build a StepContext with mailboxes pre-opened for `topics`."""
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    for t in topics:
        step.open_mailbox(t)
    return step


def test_wait_for_returns_payload_after_deposit():
    step = _make_step_ctx(["t/foo"])
    threading.Timer(
        0.05, lambda: step.deposit("t/foo", {"v": 1})
    ).start()
    payload = step.wait_for("t/foo", timeout=1.0)
    assert payload == {"v": 1}


def test_wait_for_returns_pre_deposited_immediately():
    """The race-fix that justifies the per-step pre-registration model."""
    step = _make_step_ctx(["t/ack"])
    step.deposit("t/ack", {"ok": True})
    start = time.monotonic()
    payload = step.wait_for("t/ack", timeout=1.0)
    assert payload == {"ok": True}
    assert time.monotonic() - start < 0.1


def test_wait_for_unknown_topic_raises_keyerror():
    """Unopened topics indicate a missing wait_for_topics declaration."""
    step = _make_step_ctx(["t/known"])
    import pytest
    with pytest.raises(KeyError):
        step.wait_for("t/unknown", timeout=0.1)


def test_wait_for_timeout():
    step = _make_step_ctx(["t/never"])
    import pytest
    with pytest.raises(TimeoutError):
        step.wait_for("t/never", timeout=0.05)


def test_wait_for_abort_when_stop_event_fires():
    step = _make_step_ctx(["t/never"])
    threading.Timer(0.05, step.protocol.stop_event.set).start()
    import pytest
    with pytest.raises(AbortError):
        step.wait_for("t/never", timeout=2.0)


def test_wait_for_predicate_filters_payloads():
    step = _make_step_ctx(["t/status"])
    step.deposit("t/status", {"ready": False})
    step.deposit("t/status", {"ready": True})
    payload = step.wait_for(
        "t/status", timeout=1.0,
        predicate=lambda p: p.get("ready") is True,
    )
    assert payload == {"ready": True}


def test_protocol_context_scratch_is_per_protocol():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    proto.scratch["k"] = "v"
    assert proto.scratch["k"] == "v"


def test_step_context_scratch_is_per_step_and_independent():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    a = StepContext(row=BaseRow(name="a"), protocol=proto)
    b = StepContext(row=BaseRow(name="b"), protocol=proto)
    a.scratch["k"] = "av"
    b.scratch["k"] = "bv"
    assert a.scratch["k"] == "av"
    assert b.scratch["k"] == "bv"
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: ImportError on `ProtocolContext` / `StepContext`.

- [ ] **Step 3: Append `ProtocolContext` + `StepContext` to `step_context.py`**

Append to `src/pluggable_protocol_tree/execution/step_context.py`:

```python
# --- contexts ---

from traits.api import Any, Dict, HasTraits, Instance, Str, List

from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row import BaseRow


class ProtocolContext(HasTraits):
    """Spans one protocol run.

    Hooks reach this from a StepContext via ``ctx.protocol``. Use
    ``scratch`` for cross-step state (e.g. cumulative stats). The
    ``stop_event`` lets long-running CPU hooks check for Stop without
    going through ctx.wait_for; e.g.
    ``while not ctx.protocol.stop_event.is_set(): ...``.
    """
    columns    = List(Instance(IColumn))
    scratch    = Dict(Str, Any,
                      desc="protocol-scoped scratch (cleared on each run)")
    stop_event = Instance(threading.Event)


class StepContext(HasTraits):
    """Spans one row's execution.

    Hooks call ``wait_for(topic, ...)`` on this. Mailboxes are opened by
    the executor before any hook runs (so a hook can publish a request
    and immediately wait for the ack without losing fast replies).
    """
    row       = Instance(BaseRow)
    protocol  = Instance(ProtocolContext)
    scratch   = Dict(Str, Any,
                     desc="step-scoped scratch (cleared per step)")
    _mailboxes = Dict(Str, Instance(Mailbox))

    def open_mailbox(self, topic: str) -> None:
        """Pre-register a mailbox for ``topic``. Called by the executor
        at step start for every topic in the union of all handlers'
        wait_for_topics. Idempotent."""
        if topic not in self._mailboxes:
            self._mailboxes[topic] = Mailbox()

    def deposit(self, topic: str, payload) -> None:
        """Called by the dramatiq listener for any message on a topic
        the active step has a mailbox for. Drops messages for topics
        without an open mailbox (handler didn't declare wait_for)."""
        box = self._mailboxes.get(topic)
        if box is not None:
            box.deposit(payload)

    def wait_for(self, topic: str, timeout: float = 5.0,
                 predicate: Optional[Callable] = None):
        """Block until a message on ``topic`` satisfying ``predicate``
        arrives, or the timeout/stop fires.

        Returns the payload. Raises:
          * ``KeyError`` if ``topic`` was not declared in any handler's
            ``wait_for_topics`` (the executor would not have opened a
            mailbox; waiting would block forever).
          * ``TimeoutError`` after ``timeout`` seconds.
          * ``AbortError`` if the protocol's stop_event fires.
        """
        try:
            box = self._mailboxes[topic]
        except KeyError:
            raise KeyError(
                f"wait_for({topic!r}) called but topic not in any handler's "
                f"wait_for_topics; declare it on the IColumnHandler."
            )
        return box.drain_one(
            predicate=predicate,
            timeout=timeout,
            stop_event=self.protocol.stop_event,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: 24 passed (16 + 8).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/step_context.py pluggable_protocol_tree/tests/test_step_context.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] ProtocolContext + StepContext + ctx.wait_for

ProtocolContext spans the protocol run; StepContext spans one row.
Mailboxes are pre-opened by the executor at step start (covering the
union of all handlers' wait_for_topics), so a hook can publish a
request and immediately wait for the reply without the publish-then-
register race losing fast acks.

ctx.wait_for(topic) raises KeyError if the topic isn't pre-opened,
making the missing-wait_for_topics declaration a clear error rather
than a silent forever-block. TimeoutError on deadline, AbortError on
stop_event — both handled by Mailbox.drain_one already.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Listener — Dramatiq actor + active-step pointer

**Files:**
- Create: `src/pluggable_protocol_tree/execution/listener.py`
- Modify: `src/pluggable_protocol_tree/tests/test_step_context.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_step_context.py`:

```python
# --- listener active-step pointer ---

from pluggable_protocol_tree.execution import listener as _listener


def test_listener_active_step_initially_none():
    _listener.clear_active_step()
    assert _listener.get_active_step() is None


def test_listener_set_then_get_returns_step():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    _listener.set_active_step(step)
    try:
        assert _listener.get_active_step() is step
    finally:
        _listener.clear_active_step()


def test_listener_clear_resets_to_none():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    _listener.set_active_step(step)
    _listener.clear_active_step()
    assert _listener.get_active_step() is None


def test_listener_route_to_active_step_deposits_into_mailbox():
    """Direct route() helper bypasses Dramatiq for unit testing."""
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    step.open_mailbox("t/foo")
    _listener.set_active_step(step)
    try:
        _listener.route_to_active_step("t/foo", {"v": 42})
        item = step.wait_for("t/foo", timeout=0.1)
        assert item == {"v": 42}
    finally:
        _listener.clear_active_step()


def test_listener_route_with_no_active_step_drops_silently():
    _listener.clear_active_step()
    # No exception, no observable side effect.
    _listener.route_to_active_step("t/foo", {"v": 1})


def test_listener_route_for_unopened_topic_drops_silently():
    proto = ProtocolContext(columns=[], stop_event=threading.Event())
    step = StepContext(row=BaseRow(name="x"), protocol=proto)
    step.open_mailbox("t/known")
    _listener.set_active_step(step)
    try:
        # No exception — the listener simply has nowhere to put it.
        _listener.route_to_active_step("t/unknown", {"v": 1})
    finally:
        _listener.clear_active_step()
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.execution.listener`.

- [ ] **Step 3: Implement the listener**

Create `src/pluggable_protocol_tree/execution/listener.py`:

```python
"""Dramatiq listener actor + active-step pointer.

The actor itself receives every message published on any topic the
plugin's start() method aggregated from contributed handlers'
wait_for_topics. It routes payloads into the active step's mailbox via
``route_to_active_step`` — the same function tests can call directly to
bypass Dramatiq.

Only one protocol runs at a time, so a single module-level pointer is
enough. set/clear are guarded by a lock so the listener thread and the
executor's main loop don't see a torn read on the pointer transition
between steps.
"""

import threading
from typing import Optional

import dramatiq

from pluggable_protocol_tree.execution.step_context import StepContext


_active_step_ctx: Optional[StepContext] = None
_active_lock = threading.Lock()


def set_active_step(step_ctx: StepContext) -> None:
    """Called by the executor at the start of each step (before any
    hook runs)."""
    global _active_step_ctx
    with _active_lock:
        _active_step_ctx = step_ctx


def clear_active_step() -> None:
    """Called by the executor at the end of each step. Subsequent
    incoming messages on what *was* the step's topics are dropped
    silently until the next set_active_step()."""
    global _active_step_ctx
    with _active_lock:
        _active_step_ctx = None


def get_active_step() -> Optional[StepContext]:
    """For tests + the dramatiq actor."""
    with _active_lock:
        return _active_step_ctx


def route_to_active_step(topic: str, payload) -> None:
    """Deposit a payload into the active step's mailbox for ``topic``.
    Drops silently if no protocol is running, or if the active step
    didn't pre-open a mailbox for ``topic``.

    Direct entry point for both the dramatiq actor and unit tests.
    """
    ctx = get_active_step()
    if ctx is None:
        return
    ctx.deposit(topic, payload)


@dramatiq.actor(actor_name="pluggable_protocol_tree_executor_listener",
                queue_name="default")
def executor_listener(message: dict) -> None:
    """Receives every message on any topic in the aggregated
    wait_for_topics set. Conforms to the project's message-router
    payload shape: ``{"topic": ..., "message": ...}`` (the message
    router's publish_message wraps user payloads in this envelope)."""
    topic = message.get("topic")
    payload = message.get("message")
    if topic is None:
        return
    route_to_active_step(topic, payload)
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_step_context.py -v"
```

Expected: 30 passed (24 + 6).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/listener.py pluggable_protocol_tree/tests/test_step_context.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Dramatiq executor_listener + active-step pointer

Single Dramatiq actor "pluggable_protocol_tree_executor_listener"
receives every message published on any topic the plugin aggregated
from contributed handlers' wait_for_topics. The active-step pointer
(module-level, lock-guarded) gates routing — only one protocol runs at
a time, so a singleton is enough. set/clear bracketed by the
executor's per-step lifecycle, so cross-step messages on shared topics
get dropped during the gap (intentional; avoids cross-contamination).

route_to_active_step() is the same function the actor uses, so unit
tests can drive the routing logic without spinning up Dramatiq.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `ProtocolExecutor` scaffolding + public control API

**Files:**
- Create: `src/pluggable_protocol_tree/execution/executor.py` (skeleton + public API only)
- Modify: `src/pluggable_protocol_tree/tests/test_executor.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_executor.py`:

```python
# --- ProtocolExecutor public API ---

import threading

import pytest

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column


def _make_executor():
    """Bare-bones executor with the four PPT-1 built-in columns."""
    cols = [make_type_column(), make_id_column(),
            make_name_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    return ProtocolExecutor(
        row_manager=rm,
        qsignals=ExecutorSignals(),
        pause_event=PauseEvent(),
        stop_event=threading.Event(),
    )


def test_executor_constructible_with_required_traits():
    ex = _make_executor()
    assert ex.row_manager is not None
    assert ex.qsignals is not None
    assert ex.pause_event is not None
    assert ex.stop_event is not None


def test_executor_pause_emits_protocol_paused():
    ex = _make_executor()
    received = []
    ex.qsignals.protocol_paused.connect(lambda: received.append("paused"))
    ex.pause()
    assert ex.pause_event.is_set() is True
    assert received == ["paused"]


def test_executor_resume_emits_protocol_resumed():
    ex = _make_executor()
    received = []
    ex.qsignals.protocol_resumed.connect(lambda: received.append("resumed"))
    ex.pause()
    ex.resume()
    assert ex.pause_event.is_set() is False
    assert received == ["resumed"]


def test_executor_stop_sets_stop_event_and_clears_pause():
    """stop() must also clear pause_event so a Stop-while-paused doesn't
    deadlock the main loop in wait_cleared()."""
    ex = _make_executor()
    ex.pause()
    assert ex.pause_event.is_set() is True
    ex.stop()
    assert ex.stop_event.is_set() is True
    assert ex.pause_event.is_set() is False
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: ImportError on `pluggable_protocol_tree.execution.executor`.

- [ ] **Step 3: Implement the executor scaffolding**

Create `src/pluggable_protocol_tree/execution/executor.py`:

```python
"""Protocol executor — runs a RowManager's rows on a QThread.

Responsibilities:
  * Walk row_manager.iter_execution_steps() in order.
  * For each row, fan the five hooks across priority buckets (sequential
    between buckets, parallel within).
  * Distinguish protocol_finished / protocol_aborted / protocol_error in
    one place (_emit_terminal_signal).
  * Cooperate with stop/pause/error: stop_event short-circuits the loop
    and propagates into ctx.wait_for; pause_event blocks at step
    boundaries only; first hook exception aborts the step and routes to
    protocol_error.

This task ships only the scaffolding + public control API. The run loop,
hook fan-out, and conflict assertion land in subsequent tasks.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from pyface.qt.QtCore import QThread
from traits.api import Any, Callable as CallableTrait, HasTraits, Instance

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager


logger = logging.getLogger(__name__)


class ProtocolExecutor(HasTraits):
    """One executor per RowManager. Reused across runs."""

    row_manager = Instance(RowManager)
    qsignals    = Instance(ExecutorSignals)

    pause_event = Instance(PauseEvent)
    stop_event  = Instance(threading.Event)

    # Internal — set by start() / cleared by run()'s finally.
    _thread = Any
    _error  = Any

    # Injectable for tests (e.g. a synchronous executor for determinism).
    bucket_pool_factory = CallableTrait

    def _bucket_pool_factory_default(self):
        return ThreadPoolExecutor

    # ------- public control API (called from the GUI thread) -------

    def start(self) -> None:
        """Spawn a QThread and call run() on it. Idempotent — a second
        call while already running is ignored."""
        if self._thread is not None and self._thread.isRunning():
            return
        self.pause_event.clear()
        self.stop_event.clear()
        self._error = None
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        self._thread.start()

    def pause(self) -> None:
        """Set pause_event. Effective at the next step boundary."""
        self.pause_event.set()
        self.qsignals.protocol_paused.emit()

    def resume(self) -> None:
        """Clear pause_event so the main loop unblocks."""
        self.pause_event.clear()
        self.qsignals.protocol_resumed.emit()

    def stop(self) -> None:
        """Set stop_event AND clear pause_event so a Stop-while-paused
        doesn't deadlock the main loop in pause_event.wait_cleared()."""
        self.stop_event.set()
        self.pause_event.clear()

    # ------- main loop (overridden in Task 9) -------

    def run(self) -> None:
        """Stub — fully implemented in Task 9."""
        raise NotImplementedError("run() lands in Task 9")
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: 8 passed (4 from Task 4 + 4 here).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/executor.py pluggable_protocol_tree/tests/test_executor.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] ProtocolExecutor scaffolding + public control API

HasTraits class with row_manager / qsignals / pause_event / stop_event
traits, plus start/pause/resume/stop public methods. Run loop is a stub
that raises NotImplementedError; lands in Task 9.

The non-obvious bit: stop() also clears pause_event. Without this,
pressing Stop while paused leaves the main loop blocked in
pause_event.wait_cleared() forever — stop_event going True is invisible
to a thread that's only watching pause_event.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `ProtocolExecutor.run()` main loop + terminal signals

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/executor.py` (replace the `run` stub + add helpers)
- Modify: `src/pluggable_protocol_tree/tests/test_executor.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_executor.py`:

```python
# --- ProtocolExecutor.run() — main loop ---

import time

from pluggable_protocol_tree.execution.signals import ExecutorSignals


class _SignalSpy:
    """Collects signal emissions into a list for assertion."""
    def __init__(self, sigs: ExecutorSignals):
        self.events = []
        sigs.protocol_started.connect(lambda: self.events.append(("protocol_started",)))
        sigs.step_started.connect(lambda r: self.events.append(("step_started", r.name)))
        sigs.step_finished.connect(lambda r: self.events.append(("step_finished", r.name)))
        sigs.protocol_finished.connect(lambda: self.events.append(("protocol_finished",)))
        sigs.protocol_aborted.connect(lambda: self.events.append(("protocol_aborted",)))
        sigs.protocol_error.connect(lambda m: self.events.append(("protocol_error", m)))


def test_run_empty_protocol_emits_started_then_finished():
    ex = _make_executor()
    spy = _SignalSpy(ex.qsignals)
    ex.run()       # synchronous; bypasses start()/QThread
    assert spy.events[0] == ("protocol_started",)
    assert spy.events[-1] == ("protocol_finished",)


def test_run_three_steps_emits_step_signals_in_order():
    ex = _make_executor()
    a = ex.row_manager.add_step(values={"name": "A"})
    b = ex.row_manager.add_step(values={"name": "B"})
    c = ex.row_manager.add_step(values={"name": "C"})
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    step_events = [e for e in spy.events if e[0] in ("step_started", "step_finished")]
    assert step_events == [
        ("step_started", "A"), ("step_finished", "A"),
        ("step_started", "B"), ("step_finished", "B"),
        ("step_started", "C"), ("step_finished", "C"),
    ]


def test_run_stop_pre_set_aborts_immediately():
    ex = _make_executor()
    ex.row_manager.add_step(values={"name": "A"})
    ex.row_manager.add_step(values={"name": "B"})
    ex.stop_event.set()
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    # No step events; terminal is aborted, not finished.
    assert ("step_started", "A") not in spy.events
    assert spy.events[-1] == ("protocol_aborted",)


def test_run_pause_then_resume_blocks_then_continues():
    """Set pause_event before calling run() so iter_execution_steps's
    first iteration hits wait_cleared(). Then clear it from another
    thread to release."""
    ex = _make_executor()
    ex.row_manager.add_step(values={"name": "A"})
    ex.pause_event.set()
    spy = _SignalSpy(ex.qsignals)

    def resumer():
        time.sleep(0.05)
        ex.pause_event.clear()

    threading.Thread(target=resumer, daemon=True).start()
    start = time.monotonic()
    ex.run()
    elapsed = time.monotonic() - start
    # We waited ~50ms before resume; protocol then completed quickly.
    assert elapsed >= 0.05
    assert spy.events[-1] == ("protocol_finished",)


def test_run_stop_while_paused_breaks_out():
    """Regression for the deadlock-avoidance code in stop()."""
    ex = _make_executor()
    ex.row_manager.add_step(values={"name": "A"})
    ex.pause_event.set()
    spy = _SignalSpy(ex.qsignals)

    def stopper():
        time.sleep(0.05)
        ex.stop()

    threading.Thread(target=stopper, daemon=True).start()
    ex.run()
    assert spy.events[-1] == ("protocol_aborted",)
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: NotImplementedError from `run()` stub on each of the new tests.

- [ ] **Step 3: Replace `run` stub with the real loop**

Open `src/pluggable_protocol_tree/execution/executor.py` and replace the `run` method (the one that raises `NotImplementedError`) with this implementation. Also add the imports + helpers shown.

Add to the top of the file (after the existing imports):

```python
from pluggable_protocol_tree.execution.listener import (
    set_active_step, clear_active_step,
)
from pluggable_protocol_tree.execution.step_context import (
    ProtocolContext, StepContext,
)
```

Replace the `run()` stub with:

```python
    def run(self) -> None:
        """Main loop. Runs synchronously when called directly (tests),
        or on its QThread when entered via start()."""
        cols = list(self.row_manager.columns)
        proto_ctx = ProtocolContext(
            columns=cols, stop_event=self.stop_event,
        )
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

            # on_protocol_end runs even on stop, as best-effort cleanup.
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
            if self._thread is not None:
                self._thread.quit()

    # ------- helpers -------

    def _emit_terminal_signal(self) -> None:
        """Single source of truth for which lifecycle-end signal fires.

        Order matters: an in-loop exception (recorded as self._error)
        wins over user Stop, which wins over normal completion.
        """
        if self._error is not None:
            self.qsignals.protocol_error.emit(str(self._error))
        elif self.stop_event.is_set():
            self.qsignals.protocol_aborted.emit()
        else:
            self.qsignals.protocol_finished.emit()

    def _build_step_ctx(self, row, cols, proto_ctx) -> StepContext:
        """Construct a fresh StepContext and pre-open one mailbox per
        topic in the union of all handlers' wait_for_topics."""
        step_ctx = StepContext(row=row, protocol=proto_ctx)
        for col in cols:
            for topic in (col.handler.wait_for_topics or []):
                step_ctx.open_mailbox(topic)
        return step_ctx

    def _run_hooks(self, hook_name, cols, ctx, row) -> None:
        """Stub — full priority-bucket implementation lands in Task 10.
        Until then, run hooks sequentially in given order so the run-loop
        tests can pass without depending on the bucket fan-out yet."""
        for col in cols:
            self._invoke_hook(col, hook_name, ctx, row)

    def _invoke_hook(self, col, hook_name, ctx, row) -> None:
        """Dispatch to the handler's named hook with the right signature.

        Per-step hooks take (row, ctx); protocol-level take (ctx).
        Default handlers from BaseColumnHandler are no-ops, so calling
        them on every column is safe (and cheaper than introspecting
        which columns override).
        """
        fn = getattr(col.handler, hook_name)
        if hook_name in ("on_protocol_start", "on_protocol_end"):
            fn(ctx)
        else:
            fn(row, ctx)
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: 13 passed (8 + 5).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/executor.py pluggable_protocol_tree/tests/test_executor.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] ProtocolExecutor.run() main loop

Walks iter_execution_steps and fires the five hooks per step. Three
terminal-signal cases (finished / aborted / error) consolidated in
_emit_terminal_signal so call sites don't have to remember which one
to pick. Per-step StepContext opens mailboxes for the union of all
handlers' wait_for_topics before any hook runs (the publish-then-ack
race fix in concrete form).

_run_hooks is a sequential stub here; the priority-bucket fan-out
lands in Task 10.

stop_event is checked twice per iteration: once before the pause
boundary, once after wait_cleared returns. The post-pause check is
what makes Stop-while-paused work — see the regression test
test_run_stop_while_paused_breaks_out.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `_run_hooks` priority-bucket fan-out

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/executor.py` (replace `_run_hooks` stub)
- Modify: `src/pluggable_protocol_tree/tests/test_executor.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_executor.py`:

```python
# --- priority bucket fan-out ---

from traits.api import HasTraits, Int, List, provides, Str

from pluggable_protocol_tree.interfaces.i_column import IColumnHandler
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


def _recording_handler(name, priority, log: list, barrier=None):
    """Build a handler that appends (name, hook_name) to `log` on each
    fire. Optional `barrier` makes the handler block on a threading
    barrier inside on_step (used to prove parallel execution)."""
    class _H(BaseColumnHandler):
        def on_protocol_start(self, ctx):  log.append((name, "on_protocol_start"))
        def on_pre_step(self, row, ctx):   log.append((name, "on_pre_step"))
        def on_step(self, row, ctx):
            log.append((name, "on_step"))
            if barrier is not None:
                barrier.wait(timeout=2.0)
        def on_post_step(self, row, ctx):  log.append((name, "on_post_step"))
        def on_protocol_end(self, ctx):    log.append((name, "on_protocol_end"))
    h = _H()
    h.priority = priority
    return h


def _make_recording_column(col_id, priority, log, barrier=None):
    return Column(
        model=BaseColumnModel(col_id=col_id, col_name=col_id, default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_recording_handler(col_id, priority, log, barrier),
    )


def _executor_with(cols):
    """Build an executor on a fresh RowManager containing one step,
    with the given extra columns layered on top of the four PPT-1
    builtins (so iter_execution_steps yields one row)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    builtins = [make_type_column(), make_id_column(),
                make_name_column(), make_duration_column()]
    rm = RowManager(columns=builtins + list(cols))
    rm.add_step(values={"name": "A"})
    return ProtocolExecutor(
        row_manager=rm,
        qsignals=ExecutorSignals(),
        pause_event=PauseEvent(),
        stop_event=threading.Event(),
    )


def test_run_hooks_orders_buckets_by_priority():
    log = []
    low = _make_recording_column("low", priority=10, log=log)
    high = _make_recording_column("high", priority=30, log=log)
    ex = _executor_with([high, low])   # deliberately shuffled
    ex.run()
    on_step_calls = [name for (name, hook) in log if hook == "on_step"]
    # All low (priority 10) before any high (priority 30)
    assert on_step_calls.index("low") < on_step_calls.index("high")


def test_run_hooks_fans_same_priority_in_parallel():
    log = []
    barrier = threading.Barrier(2)
    a = _make_recording_column("a", priority=20, log=log, barrier=barrier)
    b = _make_recording_column("b", priority=20, log=log, barrier=barrier)
    ex = _executor_with([a, b])
    # If they don't run in parallel the barrier never trips and the
    # executor blocks until barrier timeout (2s) — test would take >2s.
    start = time.monotonic()
    ex.run()
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, "same-priority hooks did not fan out in parallel"
    on_step_names = [name for (name, hook) in log if hook == "on_step"]
    assert sorted(on_step_names) == ["a", "b"]


def test_run_hooks_uses_default_priority_50_for_unset():
    """BaseColumnHandler defaults priority to 50 — no explicit set
    needed for a column that doesn't care about ordering."""
    log = []
    no_pri = _make_recording_column("default", priority=50, log=log)
    early = _make_recording_column("early", priority=10, log=log)
    ex = _executor_with([no_pri, early])
    ex.run()
    on_step_calls = [name for (name, hook) in log if hook == "on_step"]
    assert on_step_calls.index("early") < on_step_calls.index("default")


def test_run_hooks_all_five_phases_fire_in_order_for_one_step():
    log = []
    col = _make_recording_column("c", priority=50, log=log)
    ex = _executor_with([col])
    ex.run()
    # Filter to the recording column only (built-ins also fire but with
    # no logging side effect — their handlers are BaseColumnHandler).
    c_calls = [hook for (name, hook) in log if name == "c"]
    assert c_calls == [
        "on_protocol_start",
        "on_pre_step", "on_step", "on_post_step",
        "on_protocol_end",
    ]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: parallel test fails (sequential stub serialises so the barrier never trips → test times out around 2s). Other tests may pass coincidentally because the sequential stub respects iteration order for matching priorities.

- [ ] **Step 3: Replace `_run_hooks` with priority-bucket fan-out**

In `src/pluggable_protocol_tree/execution/executor.py`, add this import alongside the others:

```python
from collections import defaultdict
from concurrent.futures import as_completed
```

Replace the `_run_hooks` method body (the sequential stub from Task 9) with:

```python
    def _run_hooks(self, hook_name, cols, ctx, row) -> None:
        """Priority-bucket fan-out.

        Lower priority runs first. Equal priorities run in parallel
        (one ThreadPoolExecutor per bucket; the executor returns
        only when every future in the bucket has resolved).

        The first exception in any bucket wins: stop_event is set so
        sibling hooks waiting on ctx.wait_for() return promptly via
        AbortError, the pool drains, and the original exception is
        re-raised out of this method.
        """
        buckets = defaultdict(list)
        for col in cols:
            buckets[col.handler.priority].append(col)

        for priority in sorted(buckets):
            bucket_cols = buckets[priority]
            with self.bucket_pool_factory(
                max_workers=max(1, len(bucket_cols)),
            ) as pool:
                futures = {
                    pool.submit(self._invoke_hook, col, hook_name, ctx, row): col
                    for col in bucket_cols
                }
                first_exc = None
                for f in as_completed(futures):
                    exc = f.exception()
                    if exc is not None and first_exc is None:
                        first_exc = exc
                        # Set stop so sibling wait_for() calls return
                        # promptly — pool.__exit__ will then wait for
                        # those threads to drain naturally.
                        self.stop_event.set()
                if first_exc is not None:
                    raise first_exc
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: 17 passed (13 + 4).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/executor.py pluggable_protocol_tree/tests/test_executor.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] _run_hooks priority-bucket fan-out

Lower priority first; equal priority parallel via a per-bucket
ThreadPoolExecutor. First exception in a bucket sets stop_event so
sibling wait_for() calls return promptly via AbortError, the pool
drains naturally (Python threads aren't cancellable), and the original
exception re-raises out of _run_hooks.

The parallel test uses a threading.Barrier to prove same-priority
hooks actually run concurrently — the sequential stub from Task 9
would have hung on it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Same-topic conflict assertion + error-propagation tests

**Files:**
- Modify: `src/pluggable_protocol_tree/execution/executor.py` (extend `_build_step_ctx`)
- Modify: `src/pluggable_protocol_tree/tests/test_executor.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_executor.py`:

```python
# --- same-topic conflict + error propagation ---

def _handler_with_topic(name, priority, topic, log):
    class _H(BaseColumnHandler):
        wait_for_topics = [topic]
        def on_step(self, row, ctx):
            log.append((name, "on_step"))
    h = _H()
    h.priority = priority
    return h


def _column_with_topic_handler(col_id, priority, topic, log):
    return Column(
        model=BaseColumnModel(col_id=col_id, col_name=col_id, default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_handler_with_topic(col_id, priority, topic, log),
    )


def test_same_topic_in_same_priority_bucket_raises():
    """Two columns both declaring the same wait_for_topic at the same
    priority would race for the mailbox. Detected at step start."""
    log = []
    a = _column_with_topic_handler("a", 20, "shared/topic", log)
    b = _column_with_topic_handler("b", 20, "shared/topic", log)
    ex = _executor_with([a, b])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    # Surfaces as a protocol_error (the _build_step_ctx assertion raises).
    assert spy.events[-1][0] == "protocol_error"
    assert "shared/topic" in spy.events[-1][1]


def test_same_topic_different_priority_buckets_is_fine():
    """Sequential — no race. Should not raise."""
    log = []
    a = _column_with_topic_handler("a", 10, "shared/topic", log)
    b = _column_with_topic_handler("b", 30, "shared/topic", log)
    ex = _executor_with([a, b])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    assert spy.events[-1] == ("protocol_finished",)


def test_hook_exception_emits_protocol_error_not_finished():
    log = []

    class _Boom(BaseColumnHandler):
        def on_step(self, row, ctx):
            raise RuntimeError("kaboom")

    col = Column(
        model=BaseColumnModel(col_id="boom", col_name="boom", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_Boom(),
    )
    ex = _executor_with([col])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    err_events = [e for e in spy.events if e[0] == "protocol_error"]
    assert len(err_events) == 1
    assert "kaboom" in err_events[0][1]
    # Did NOT emit finished or aborted.
    assert ("protocol_finished",) not in spy.events
    assert ("protocol_aborted",) not in spy.events


def test_on_protocol_end_runs_even_on_error():
    """Best-effort cleanup: if on_step raises, on_protocol_end still
    fires (in the except branch's fallback)."""
    log = []

    class _Boom(BaseColumnHandler):
        def on_step(self, row, ctx):
            raise RuntimeError("kaboom")
        def on_protocol_end(self, ctx):
            log.append("end_ran")

    col = Column(
        model=BaseColumnModel(col_id="boom", col_name="boom", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_Boom(),
    )
    ex = _executor_with([col])
    ex.run()
    assert "end_ran" in log


def test_on_protocol_end_raising_during_error_cleanup_is_swallowed():
    """If both on_step AND on_protocol_end raise, the original error
    wins (it's what surfaces as protocol_error) and the on_protocol_end
    exception is logged but not re-raised."""
    log = []

    class _DoubleBoom(BaseColumnHandler):
        def on_step(self, row, ctx):
            raise RuntimeError("first")
        def on_protocol_end(self, ctx):
            raise RuntimeError("second")

    col = Column(
        model=BaseColumnModel(col_id="boom", col_name="boom", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_DoubleBoom(),
    )
    ex = _executor_with([col])
    spy = _SignalSpy(ex.qsignals)
    ex.run()
    err_events = [e for e in spy.events if e[0] == "protocol_error"]
    assert len(err_events) == 1
    assert "first" in err_events[0][1]
    assert "second" not in err_events[0][1]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: `test_same_topic_in_same_priority_bucket_raises` fails (no assertion in `_build_step_ctx` yet — the topic just gets opened twice silently). The error-propagation tests should already pass from Task 9's `try/except` structure.

- [ ] **Step 3: Add the conflict assertion**

In `src/pluggable_protocol_tree/execution/executor.py`, replace `_build_step_ctx` with:

```python
    def _build_step_ctx(self, row, cols, proto_ctx) -> StepContext:
        """Construct a fresh StepContext and pre-open one mailbox per
        topic in the union of all handlers' wait_for_topics.

        Raises ValueError if two columns *in the same priority bucket*
        declare the same topic — they'd race for the mailbox under
        parallel fan-out, and we don't yet have a use case for
        broadcast-to-multiple-waiters semantics. Same topic in
        different buckets is fine (sequential).
        """
        step_ctx = StepContext(row=row, protocol=proto_ctx)
        # Detect within-bucket topic collisions before opening any boxes.
        per_priority_topics: dict[int, dict[str, str]] = {}  # priority → topic → col_id
        for col in cols:
            topics = col.handler.wait_for_topics or []
            bucket = per_priority_topics.setdefault(col.handler.priority, {})
            for topic in topics:
                if topic in bucket:
                    raise ValueError(
                        f"Topic conflict: columns {bucket[topic]!r} and "
                        f"{col.model.col_id!r} both declare wait_for_topics={topic!r} "
                        f"at the same priority bucket ({col.handler.priority}); "
                        f"they would race for the mailbox."
                    )
                bucket[topic] = col.model.col_id
                step_ctx.open_mailbox(topic)
        return step_ctx
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_executor.py -v"
```

Expected: 22 passed (17 + 5).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/execution/executor.py pluggable_protocol_tree/tests/test_executor.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Same-topic conflict assertion + error-propagation tests

_build_step_ctx now scans wait_for_topics per priority bucket and
raises ValueError if two columns in the same bucket both declare the
same topic. Different buckets is fine (sequential — no race). The
error surfaces as protocol_error, not aborted.

Also locks in the error semantics from Task 9's run loop:
- Hook exception → protocol_error(message), NOT _finished or _aborted
- on_protocol_end runs as best-effort cleanup
- An on_protocol_end exception during cleanup is swallowed (logged) so
  the original error wins

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `repetitions` built-in column

**Files:**
- Create: `src/pluggable_protocol_tree/builtins/repetitions_column.py`
- Modify: `src/pluggable_protocol_tree/tests/test_builtins.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_builtins.py`:

```python
# --- repetitions column ---

from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)


def test_repetitions_column_default_one():
    col = make_repetitions_column()
    assert col.model.default_value == 1


def test_repetitions_column_trait_is_int_with_default_one():
    col = make_repetitions_column()
    RowType = build_row_type([col], base=BaseRow)
    r = RowType()
    assert r.repetitions == 1


def test_repetitions_column_view_uses_intspinbox_range():
    col = make_repetitions_column()
    assert col.view.low == 1
    assert col.view.high == 1000


def test_repetitions_column_drives_iter_execution_steps_expansion():
    """Locks in the PPT-1 contract through a real column (not setattr)."""
    from pluggable_protocol_tree.models.row_manager import RowManager
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "A", "repetitions": 3})
    names = [r.name for r in rm.iter_execution_steps()]
    assert names == ["A", "A", "A"]


def test_repetitions_column_metadata():
    col = make_repetitions_column()
    assert col.model.col_id == "repetitions"
    assert col.model.col_name == "Reps"
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: ImportError on `make_repetitions_column`.

- [ ] **Step 3: Implement the column**

Create `src/pluggable_protocol_tree/builtins/repetitions_column.py`:

```python
"""Repetitions column — number of times each row executes.

Steps repeat their on_step N times. Groups expand their child subtree
N times. Default 1.

iter_execution_steps in RowManager already reads ``getattr(row,
"repetitions", 1)`` (PPT-1 left the contract in place); this column
populates the trait so that getattr fallback becomes vestigial for
new protocols. The fallback is kept for safety against persisted
protocols that pre-date the column.
"""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this row executes (groups "
                            "expand subtree N×)")


def make_repetitions_column():
    return Column(
        model=RepetitionsColumnModel(
            col_id="repetitions", col_name="Reps", default_value=1,
        ),
        view=IntSpinBoxColumnView(low=1, high=1000),
    )
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: 18 passed (the existing 13 + 5 new).

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/builtins/repetitions_column.py pluggable_protocol_tree/tests/test_builtins.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Repetitions built-in column (5th always-on)

Int trait, default 1, IntSpinBox view (1–1000). Locks the PPT-1
iter_execution_steps "repetitions attribute" contract behind a real
column rather than the setattr cheat the original tests used.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Plugin updates — assemble repetitions + register subscriptions

**Files:**
- Modify: `src/pluggable_protocol_tree/plugin.py`
- Modify: `src/pluggable_protocol_tree/tests/test_plugin.py`

- [ ] **Step 1: Append failing tests**

Append to `src/pluggable_protocol_tree/tests/test_plugin.py`:

```python
# --- PPT-2 additions ---

def test_assemble_columns_includes_repetitions():
    p = PluggableProtocolTreePlugin()
    cols = p._assemble_columns()
    ids = [c.model.col_id for c in cols]
    assert "repetitions" in ids


def test_assemble_columns_canonical_order():
    """Built-ins land in: type, id, name, repetitions, duration_s order."""
    p = PluggableProtocolTreePlugin()
    cols = p._assemble_columns()
    builtin_ids = [c.model.col_id for c in cols
                   if c.model.col_id in ("type", "id", "name",
                                         "repetitions", "duration_s")]
    assert builtin_ids == ["type", "id", "name", "repetitions", "duration_s"]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_plugin.py -v"
```

Expected: 2 new tests fail because `repetitions` isn't in the assembled column list yet.

- [ ] **Step 3: Add repetitions to `_assemble_columns` + add the start() subscription registration**

Open `src/pluggable_protocol_tree/plugin.py`. Find the existing `_assemble_columns` and the imports above it. Make the following changes:

Add this import alongside the other `from pluggable_protocol_tree.builtins...` imports:

```python
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
```

Replace the existing `_assemble_columns` body so the order is `type, id, name, repetitions, duration_s + contributed`:

```python
    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_repetitions_column(),
            make_duration_column(),
        ]
        return builtins + list(self.contributed_columns)
```

Now add the `start()` method that registers the executor listener's subscriptions. Insert it inside the `PluggableProtocolTreePlugin` class (under `_assemble_columns` is fine):

```python
    def start(self):
        """Register the executor listener's subscriptions with the
        message router. Called by Envisage at plugin start, after
        extension points have resolved (so contributed_columns is
        populated)."""
        super().start()
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterData
        except ImportError:
            # Headless test environments may not have a broker. Plugin
            # construction must not require Redis; a missing broker is
            # only a problem at the moment a protocol actually runs.
            return
        topics = sorted({
            t for c in self._assemble_columns()
            for t in (c.handler.wait_for_topics or [])
        })
        if not topics:
            return
        router_data = MessageRouterData()
        for topic in topics:
            router_data.add_subscriber_to_topic(
                topic=topic,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
```

- [ ] **Step 4: Run plugin + builtins tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_plugin.py pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: existing 2 + new 2 + the 18 builtins all pass.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/plugin.py pluggable_protocol_tree/tests/test_plugin.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Plugin: assemble repetitions + register executor subscriptions

_assemble_columns now ships repetitions in canonical position
(between name and duration_s), so every default protocol has a Reps
column without needing PPT-3+ to land first.

start() aggregates wait_for_topics from all contributed handlers and
registers them with the message router under the executor listener's
actor name. Done dynamically (not via the static ACTOR_TOPIC_DICT)
because the topic set depends on which columns get contributed, which
is only knowable after extension-point resolution.

Wrapped in try/except for ImportError so headless test environments
without a broker can still construct the plugin — Redis is only
required at protocol-run time, not at plugin construction.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Demo MessageColumn

**Files:**
- Create: `src/pluggable_protocol_tree/demos/message_column.py`

This task has no unit tests — the column is exercised by the demo end-to-end and by the Redis integration test in Task 16.

- [ ] **Step 1: Implement the demo column**

Create `src/pluggable_protocol_tree/demos/message_column.py`:

```python
"""Toy demo column — publishes a log line on every on_step.

Lives in demos/, not builtins/, because it has no production purpose.
The Redis integration test in tests_with_redis_server_need/ uses this
column to prove the round-trip publish → listener → mailbox → wait_for
path works against a real broker.
"""

from traits.api import Str

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.string_edit import (
    StringEditColumnView,
)


DEMO_MESSAGE_TOPIC = "microdrop/protocol_tree/demo_message"


class MessageColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Str("hello", desc="Message published when this step runs")


class MessageColumnHandler(BaseColumnHandler):
    priority = 50
    wait_for_topics = []        # demo doesn't wait

    def on_step(self, row, ctx):
        msg = self.model.get_value(row)
        publish_message(
            topic=DEMO_MESSAGE_TOPIC,
            message={
                "row_uuid": row.uuid,
                "name": row.name,
                "msg": msg,
            },
        )


def make_message_column():
    return Column(
        model=MessageColumnModel(
            col_id="demo_message", col_name="Message", default_value="hello",
        ),
        view=StringEditColumnView(),
        handler=MessageColumnHandler(),
    )
```

- [ ] **Step 2: Smoke-test import**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.demos.message_column import make_message_column; c = make_message_column(); print(c.model.col_id, c.handler.priority)'"
```

Expected: `demo_message 50`

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/demos/message_column.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Demo MessageColumn

Toy column that publishes "microdrop/protocol_tree/demo_message" on
every on_step. Lives in demos/ because it has no production purpose;
exercised end-to-end by the demo widget and by the Redis integration
test (Task 16).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Demo run_widget — Run/Pause/Stop toolbar + signal wiring

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/run_widget.py`

This is purely UI wiring — no unit tests. Verified by the manual demo check at Task 17.

- [ ] **Step 1: Replace the existing run_widget.py with the enhanced version**

Open `src/pluggable_protocol_tree/demos/run_widget.py` and replace the entire file with:

```python
"""Standalone demo — open ProtocolTreeWidget in a QMainWindow with
Run / Pause / Stop toolbar buttons and active-row highlighting.

No envisage, no dramatiq broker required for the in-process demo (the
MessageColumn publishes to Dramatiq but the publish call no-ops if no
broker is configured — the demo still exercises the executor's full
control flow). For the round-trip with real subscribers, run the
integration test or the full app.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget
"""

import json
import sys
import threading

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QToolBar,
)

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.message_column import make_message_column
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


def _columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_repetitions_column(),
        make_duration_column(),
        make_message_column(),
    ]


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pluggable Protocol Tree — Demo (PPT-2)")
        self.resize(1000, 600)

        self.manager = RowManager(columns=_columns())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.setCentralWidget(self.widget)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        self._wire_signals()
        self._build_toolbar()

    def _wire_signals(self):
        # Active-row highlighting
        self.executor.qsignals.step_started.connect(
            self.widget.model.set_active_node
        )
        self.executor.qsignals.step_finished.connect(
            lambda _row: self.widget.model.set_active_node(None)
        )
        # Clean up highlight on terminal lifecycle signals
        for sig in (
            self.executor.qsignals.protocol_finished,
            self.executor.qsignals.protocol_aborted,
        ):
            sig.connect(lambda: self.widget.model.set_active_node(None))
        self.executor.qsignals.protocol_error.connect(self._on_error)

    def _build_toolbar(self):
        tb = QToolBar("Protocol")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())
        tb.addAction("Add Group", lambda: self.manager.add_group())
        tb.addSeparator()
        tb.addAction("Save…", self._save)
        tb.addAction("Load…", self._load)
        tb.addSeparator()
        tb.addAction("Run",   self.executor.start)
        self._pause_action = tb.addAction("Pause", self._toggle_pause)
        tb.addAction("Stop",  self.executor.stop)

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
            self._pause_action.setText("Pause")
        else:
            self.executor.pause()
            self._pause_action.setText("Resume")

    def _on_error(self, msg):
        self.widget.model.set_active_node(None)
        QMessageBox.critical(self, "Protocol error", msg)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.manager.to_json(), f, indent=2)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            self.manager = RowManager.from_json(data, columns=_columns())
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
            return
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.setCentralWidget(self.widget)
        # Re-wire executor against the new manager
        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )
        self._wire_signals()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test import**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.demos.run_widget import DemoWindow; print(DemoWindow)'"
```

Expected: prints the class.

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/demos/run_widget.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Demo widget — Run/Pause/Stop toolbar + active-row highlighting

DemoWindow constructs a ProtocolExecutor and wires:
- step_started/step_finished → MvcTreeModel.set_active_node (the green
  highlight already plumbed in PPT-1)
- protocol_finished / _aborted → clear highlight
- protocol_error → clear highlight + critical dialog

Toolbar gains Run / Pause / Stop. Pause toggles its own label between
"Pause" and "Resume" so the user can tell what clicking it will do.

The MessageColumn is preloaded so a Run on a 3-step protocol produces
visible activity (the highlight walks down the tree as Dramatiq
publishes go out). With Repetitions=3 on a step, the highlight bounces
back to that row 3× — visual confirmation iter_execution_steps still
works through PPT-2's executor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Redis-backed integration test

**Files:**
- Create: `src/pluggable_protocol_tree/tests/tests_with_redis_server_need/__init__.py`
- Create: `src/pluggable_protocol_tree/tests/tests_with_redis_server_need/test_executor_redis_integration.py`

- [ ] **Step 1: Create the directory + empty package init**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  mkdir -p pluggable_protocol_tree/tests/tests_with_redis_server_need
```

Create `src/pluggable_protocol_tree/tests/tests_with_redis_server_need/__init__.py` as **empty**.

- [ ] **Step 2: Write the integration test**

Create `src/pluggable_protocol_tree/tests/tests_with_redis_server_need/test_executor_redis_integration.py`:

```python
"""End-to-end test for the executor's Dramatiq round-trip.

Skips automatically if Redis isn't reachable. Run via:

    redis-server &              # in another shell
    cd microdrop-py && pixi run bash -c \\
      "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/ -v"
"""

import threading
import time

import pytest


def _redis_available() -> bool:
    try:
        import dramatiq
        broker = dramatiq.get_broker()
        broker.client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis broker not reachable",
)


def test_publish_then_wait_for_round_trips_via_real_dramatiq():
    """A handler publishes a request and then waits for an ack on the
    same topic the message router routes back to the executor's
    listener. Proves: publish → broker → executor_listener actor →
    route_to_active_step → mailbox → wait_for → handler returns the
    payload."""
    from microdrop_utils.dramatiq_pub_sub_helpers import (
        MessageRouterData, publish_message,
    )
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.execution.events import PauseEvent
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.execution.signals import ExecutorSignals
    from pluggable_protocol_tree.models.column import (
        BaseColumnHandler, BaseColumnModel, Column,
    )
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.views.columns.readonly_label import (
        ReadOnlyLabelColumnView,
    )

    ACK_TOPIC = "pluggable_protocol_tree/test/ack"
    received = []

    class _AckHandler(BaseColumnHandler):
        wait_for_topics = [ACK_TOPIC]

        def on_step(self, row, ctx):
            # Publish the ack ourselves (in a real handler this would
            # publish a request and a different actor would publish the
            # ack). The point is to prove the mailbox round-trips.
            publish_message(
                topic=ACK_TOPIC, message={"step_uuid": row.uuid, "ok": True},
            )
            payload = ctx.wait_for(ACK_TOPIC, timeout=5.0)
            received.append(payload)

    ack_col = Column(
        model=BaseColumnModel(col_id="ack", col_name="Ack", default_value=None),
        view=ReadOnlyLabelColumnView(),
        handler=_AckHandler(),
    )

    # Register the executor listener's subscription for ACK_TOPIC. (The
    # plugin's start() does this in production; we do it inline here.)
    router_data = MessageRouterData()
    router_data.add_subscriber_to_topic(
        topic=ACK_TOPIC,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )
    try:
        cols = [make_type_column(), make_id_column(), make_name_column(),
                make_repetitions_column(), make_duration_column(), ack_col]
        rm = RowManager(columns=cols)
        rm.add_step(values={"name": "S"})
        ex = ProtocolExecutor(
            row_manager=rm,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Run on a worker thread so dramatiq has time to deliver while
        # the main thread monitors. (Unit tests call ex.run() directly;
        # here we exercise the same code path but with the broker live.)
        runner = threading.Thread(target=ex.run, daemon=True)
        runner.start()
        runner.join(timeout=10.0)

        assert not runner.is_alive(), "executor.run did not return in 10s"
        assert len(received) == 1
        assert received[0]["ok"] is True
        assert received[0]["step_uuid"] == rm.root.children[0].uuid

    finally:
        router_data.remove_subscriber_from_topic(
            topic=ACK_TOPIC,
            subscribing_actor_name="pluggable_protocol_tree_executor_listener",
        )
```

- [ ] **Step 3: Run the test (assumes Redis is up)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/test_executor_redis_integration.py -v"
```

Expected with Redis up: 1 passed.
Expected without Redis: 1 skipped.

If the test fails because Redis isn't running, start it (`redis-server &` or `python examples/start_redis_server.py`) and rerun. If it fails for any other reason, debug — this test is the load-bearing assurance that the listener actually wires up to the broker.

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/tests/tests_with_redis_server_need/__init__.py pluggable_protocol_tree/tests/tests_with_redis_server_need/test_executor_redis_integration.py && \
  git commit -m "$(cat <<'EOF'
[PPT-2] Redis integration test for the executor round-trip

One end-to-end test that proves the publish → broker →
executor_listener actor → route_to_active_step → mailbox → wait_for →
handler return chain works against a real Dramatiq broker. Skips
automatically if Redis isn't reachable, matching the existing
tests_with_redis_server_need convention.

Catches the integration glue bugs (subscription registration, payload
envelope, MQTT-style topic match for the listener actor) that the
stub-listener unit tests can't see.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Final verification + push + PR

**Files:** none (git/gh + manual verification only)

- [ ] **Step 1: Run the full PPT test suite (no Redis)**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ -v --ignore=pluggable_protocol_tree/tests/tests_with_redis_server_need"
```

Expected: every test green. New tests added by PPT-2: ~30 in `test_step_context.py`, ~22 in `test_executor.py`, ~5 in `test_builtins.py` (repetitions), ~2 in `test_plugin.py` (assemble), all on top of the PPT-1 baseline (~111).

- [ ] **Step 2: Run the integration test (with Redis up)**

```bash
# In another shell:
redis-server &
# Then:
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/ -v"
```

Expected: 1 passed.

- [ ] **Step 3: Manual demo verification**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python -m pluggable_protocol_tree.demos.run_widget
```

Manual checks:
- Right-click → Add Step three times. Set the Reps column on the middle one to 3. Set the Message column to a custom string on each.
- Click Run. The active-row highlight should walk down: row 1 → row 2 (3×) → row 3.
- Click Pause during execution. Active row stays highlighted; nothing else moves. Click Resume — execution continues.
- Click Stop during execution. Highlight clears, no error dialog, demo stays open.
- Right-click → Add Group; expand; Add Step inside. Run again — the group's children execute in order.

- [ ] **Step 4: Verify clean tree + branch state**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git status --short && git log --oneline feat/ppt-2-executor --not main
```

Expected: only ` M protocol_grid/preferences.py` in status. The `git log` output is the full chain of `[Spec]` + `[PPT-2]` commits — should be ~17 lines.

- [ ] **Step 5: Push the branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git push -u origin feat/ppt-2-executor
```

- [ ] **Step 6: Open the PR**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && gh pr create \
  --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "[PPT-2] Executor + StepContext.wait_for + pause/stop" \
  --body "$(cat <<'EOF'
Closes #364

## Summary

Ships the protocol-execution layer for the new pluggable protocol tree:

- **`execution/`** subpackage: `AbortError`, `PauseEvent`, `ExecutorSignals` (QObject), `Mailbox` + `wait_first` helper, `ProtocolContext` + `StepContext` with `ctx.wait_for(topic, timeout, predicate)`, single Dramatiq listener actor + active-step pointer, and `ProtocolExecutor` (HasTraits, QThread-hosted).
- **Pre-registered mailboxes** at step start cover the union of every contributed handler's `wait_for_topics` — fixes the publish-then-register race so fast hardware acks don't get lost.
- **Priority-bucket fan-out**: lower priority first; equal priorities run in parallel via per-bucket `ThreadPoolExecutor`. First exception in a bucket sets `stop_event` so sibling waits abort promptly, the pool drains, and the original exception propagates.
- **Three terminal signals** (`finished` / `aborted` / `error`) decided in `_emit_terminal_signal` so call sites stay simple. `stop()` also clears `pause_event` so a Stop-while-paused doesn't deadlock.
- **Same-topic conflict assertion**: two columns in the same priority bucket both declaring the same `wait_for_topic` raises a clear error (multiple-waiter broadcast is out of scope until someone needs it).
- **Repetitions** built-in column shipped as the 5th always-on default.
- **Demo MessageColumn** + enhanced `demos/run_widget.py` with Run/Pause/Stop toolbar and active-row highlighting wired to the `MvcTreeModel.set_active_node` hook PPT-1 already plumbed.
- **Plugin** registers the executor listener's subscriptions dynamically via `MessageRouterData.add_subscriber_to_topic` (the static `ACTOR_TOPIC_DICT` pattern doesn't fit because the topic set depends on which columns get contributed, only known after extension-point resolution).

## Test plan

- [x] `pytest pluggable_protocol_tree/tests/ -v --ignore=...tests_with_redis_server_need` — all green
- [x] `pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/` — 1 passed with `redis-server` running
- [ ] Manual demo verification: Run on a 3-step protocol with Repetitions=3 on the middle step; active row highlight walks correctly. Pause/Resume work between steps. Stop exits cleanly.

## Not in scope (see follow-ups)

- Electrode + Routes columns + device-viewer binding → PPT-3
- Voltage/Frequency columns → PPT-4
- Production dock-pane Run/Pause/Stop buttons (deferred to PPT-3 when there's hardware to gate)
- Long-running CPU hooks with cooperative abort (best-practice doc'd; will be exercised by PPT-3's RoutesHandler)

Design doc: `src/docs/superpowers/specs/2026-04-22-ppt-2-executor-design.md`
Plan: `src/docs/superpowers/plans/2026-04-22-ppt-2-executor.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: Confirm PR opens cleanly**

Copy the PR URL the command prints. Visit in browser; verify:
- Description renders
- `Closes #364` link is detected by GitHub
- All commits show up in the timeline

The umbrella issue's checklist should tick automatically on merge.

---

## Done

PPT-2 ships the executor. PPT-3 picks up: electrode column, routes column, device-viewer binding, phase math lift from `path_execution_service.py`. The hooks contract this PR establishes is exactly what PPT-3's `RoutesHandler` will plug into — no further executor work needed.
