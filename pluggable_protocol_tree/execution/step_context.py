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

    ``timeout=float("inf")`` waits forever — the deadline arithmetic
    handles it naturally (``remaining`` never reaches zero), so one of
    ``events`` becomes the only exit path.

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

        ``timeout=float("inf")`` is the convention for "wait forever":
        no TimeoutError is ever raised and cancellation relies solely
        on ``stop_event``.
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


# --- contexts ---

from traits.api import Any, Bool, Dict, HasTraits, Instance, Str, List

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row import BaseRow


class ProtocolContext(HasTraits):
    """Spans one protocol run.

    Hooks reach this from a StepContext via ``ctx.protocol``. Use
    ``scratch`` for cross-step state (e.g. cumulative stats). The
    ``stop_event`` lets long-running CPU hooks check for Stop without
    going through ctx.wait_for; e.g.
    ``while not ctx.protocol.stop_event.is_set(): ...``.

    The ``pause_event`` lets a hook request a pause that takes effect
    at the next step boundary (executor checks it between steps and
    blocks until cleared). Setting it directly is equivalent to the
    user clicking Pause in the UI; the executor's main loop emits the
    protocol_paused / protocol_resumed signals from a single place so
    UI state stays consistent regardless of who set the event.
    """
    columns     = List(Instance(IColumn))
    scratch     = Dict(Str, Any,
                       desc="protocol-scoped scratch (cleared on each run)")
    stop_event  = Instance(threading.Event)
    pause_event = Instance(PauseEvent)

    # Hooks may emit UI signals (e.g. droplet check publishing
    # protocol_paused while it waits on a user dialog so the step
    # timer freezes). Qt signals are thread-safe to emit from worker
    # threads; the slot runs on the GUI thread via QueuedConnection.
    qsignals    = Any(desc="ExecutorSignals (QObject) — hooks may emit "
                           "protocol_paused / protocol_resumed for "
                           "in-hook waits the UI should reflect")

    # When True, hooks that drive hardware (e.g. publishing electrode
    # actuation requests) must skip their broker publishes and any
    # ack-waiting tied to them — the protocol runs through its step
    # iteration, dwells, signals, etc., but does not touch hardware.
    # Mirrors the legacy protocol_grid "Preview Mode" checkbox.
    preview_mode = Bool(False)

    def pause(self):
        """Pause the run and tell the UI.

        Sets ``pause_event`` (the executor blocks on it at the next step
        boundary) and emits ``protocol_paused`` so the UI freezes its
        step/phase timers. Safe to call from a worker thread — the signal
        is delivered to GUI slots via a queued connection. ``qsignals`` may
        be None in headless/test runs, in which case only the event is set.
        """
        self.pause_event.set()
        if self.qsignals is not None:
            self.qsignals.protocol_paused.emit()

    def resume(self):
        """Clear the pause and tell the UI.

        Inverse of :meth:`pause`: clears ``pause_event`` (waking the
        executor's ``wait_cleared``) and emits ``protocol_resumed``.
        ``qsignals`` may be None in headless/test runs.
        """
        self.pause_event.clear()
        if self.qsignals is not None:
            self.qsignals.protocol_resumed.emit()

    def wait(self, events: list[threading.Event], timeout: float = float("inf")):
        """Pause the run and block the worker thread until an event fires.

        Used by hooks that hand control to the UI mid-step (e.g. the
        message-prompt dialog): pauses the protocol so timers freeze, then
        polls ``events`` plus an "externally resumed" check until one of
        them trips. On a normal acknowledge it resumes the protocol before
        returning; on Stop it aborts.

        The default ``timeout`` of ``float("inf")`` waits forever — right
        for an operator-facing wait, where the real cancellation path is
        the protocol's ``stop_event`` (pass it in ``events``). Pass a
        finite timeout to bound the wait instead.

        Args:
            events: events to wake on. Include ``protocol.stop_event`` to
                make Stop abort the wait.
            timeout: seconds before raising ``TimeoutError``;
                ``float("inf")`` (the default) never times out.

        Returns ``None``. Raises:
          * ``TimeoutError`` after ``timeout`` seconds with nothing set.
          * ``AbortError`` if ``protocol.stop_event`` fires.

        Implementation note: like :func:`wait_first`, this polls on a
        short slice because the stdlib has no multi-event wait.
        """
        try:
            self.pause()

            deadline = time.monotonic() + timeout
            poll_interval = 0.01  # 10ms
            triggered = None

            while True:

                # External resume (e.g. toolbar Resume cleared pause_event)
                # — treat as "done waiting" and stop immediately.
                if not self.pause_event.is_set():
                    triggered = True
                    break

                # 1. Check if any of the caller's events has fired.
                for e in events:
                    if e.is_set():
                        triggered = e
                        break  # Break out of the inner 'for' loop

                # 2. If an event triggered, exit immediately (do NOT sleep).
                if triggered is not None:
                    break

                # 3. Calculate time left and check for timeout.
                remaining_time = deadline - time.monotonic()
                if remaining_time <= 0.0:
                    break

                # 4. Sleep briefly before checking again.
                time.sleep(min(poll_interval, remaining_time))

            if triggered is None:
                raise TimeoutError(
                    f"wait_for timed out after {timeout}s"
                )
            elif triggered is self.stop_event:
                raise AbortError("stop_event fired while waiting")

            else:
                # Acknowledged (event set) or externally resumed — clear the
                # pause and notify the UI before handing control back.
                self.resume()


        except TimeoutError:
            # Re-raise with a uniform message so the protocol-error dialog
            # states the wait timed out rather than surfacing the raw poll
            # internals.
            raise TimeoutError(
                f"Timed out after {timeout}s wait"
            ) from None

    def prompt_gui(self, gui_callable: Callable, *,
                   timeout: float = float("inf")):
        """Run ``gui_callable`` on the GUI thread, paused, and return its result.

        The dialog counterpart to :meth:`wait`. Where ``wait`` only parks the
        worker on a bare event (fine for a yes/no prompt whose answer is "the
        event fired"), this marshals an arbitrary callable onto the GUI thread,
        pauses the run while it's up, blocks the worker until it returns, and
        hands its return value back — so a dialog can answer with structured
        data, not just acknowledge.

        ``gui_callable`` takes no arguments and runs on the GUI thread, so it
        is safe to build and ``exec()`` a Qt dialog inside it. Whatever it
        returns becomes this method's return value.

        Headless/test runs have no GUI thread (``qsignals`` is None), so the
        callable runs inline on the calling thread.

        Args:
            gui_callable: zero-arg callable invoked on the GUI thread.
            timeout: seconds before the underlying wait raises TimeoutError;
                ``float("inf")`` (the default) never times out — Stop is
                the cancellation path.

        Returns the callable's result, or ``None`` if the wait ended without
        it finishing (external Resume before the user answered). Raises:
          * ``AbortError`` if ``protocol.stop_event`` fires.
          * ``TimeoutError`` after ``timeout`` seconds.
          * whatever ``gui_callable`` raised (re-raised on the worker thread).
        """
        done = threading.Event()
        box = {}

        def _runner():
            try:
                box["result"] = gui_callable()
            except Exception as exc:           # surfaced on the worker below
                box["error"] = exc
            finally:
                done.set()

        qsignals = self.qsignals
        if qsignals is None:
            _runner()
        else:
            # Marshal onto the GUI thread: qsignals is a GUI-thread QObject, so
            # singleShot with it as context runs _runner there (Qt builds the
            # dialog on the right thread). Imported lazily to keep this module
            # Qt-free for headless executor tests.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, qsignals, _runner)

        self.wait(events=[done, self.stop_event], timeout=timeout)

        if "error" in box:
            raise box["error"]
        return box.get("result")


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

    def traits_init(self):
        # Plain (non-trait) coordination state for phase-time buffering,
        # guarded by a lock so a handler on another worker thread can
        # extend the current phase safely. See
        # add_time_buffer_to_current_phase below.
        self._phase_buffer_lock = threading.Lock()
        self._phase_buffer_s = 0.0
        # Cumulative operator-requested extension applied this step. The
        # duration-mode loop credits this back to its budget so an
        # extension ADDS to the step's total time instead of displacing
        # later cycles.
        self._phase_extension_total_s = 0.0

    def add_time_buffer_to_current_phase(self, seconds: float) -> None:
        """Ask the phase driver (RoutesHandler) to hold the current phase
        ``seconds`` longer.

        The general extension hook for columns: a handler that decides
        mid-phase it needs more time (e.g. VolumeThresholdHandler waiting
        for the droplet to finish wetting) calls this; RoutesHandler folds
        the buffer into the current phase's dwell. If the step has no routes
        the "phase" is the whole step, so this just extends the step's single
        dwell. Thread-safe; callable from any handler's worker thread.
        Non-positive values are a no-op.
        """
        if not seconds or seconds <= 0:
            return
        with self._phase_buffer_lock:
            self._phase_buffer_s += float(seconds)

    def take_phase_time_buffer(self) -> float:
        """Atomically read and clear the accumulated phase buffer.

        The phase driver calls this to fold any pending buffer into its
        dwell. Returns the buffered seconds (0.0 if none)."""
        with self._phase_buffer_lock:
            buffered, self._phase_buffer_s = self._phase_buffer_s, 0.0
        return buffered

    def reset_phase_time_buffer(self) -> None:
        """Drop any unconsumed buffer. Called at each phase boundary so a
        leftover from a cut-short phase doesn't bleed into the next one."""
        with self._phase_buffer_lock:
            self._phase_buffer_s = 0.0

    def note_phase_extension(self, seconds: float) -> None:
        """Record that ``seconds`` of operator-requested buffer was actually
        applied to a phase. The duration-mode loop reads the running total
        (``phase_extension_total``) to credit these extensions back to its
        budget — so a 1000s budget plus a 30s stuck-phase extension yields a
        ~1030s total run, with the full 1000s of cycling preserved."""
        if not seconds or seconds <= 0:
            return
        with self._phase_buffer_lock:
            self._phase_extension_total_s += float(seconds)

    def phase_extension_total(self) -> float:
        """Cumulative operator-requested phase extension this step, seconds."""
        with self._phase_buffer_lock:
            return self._phase_extension_total_s

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

        ``timeout=float("inf")`` is the convention for "wait forever"
        (e.g. a user-decision dialog): no TimeoutError is ever raised
        and the protocol's stop_event becomes the only cancellation
        path.

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
        try:
            return box.drain_one(
                predicate=predicate,
                timeout=timeout,
                stop_event=self.protocol.stop_event,
            )
        except TimeoutError:
            # Re-raise naming the topic + likely cause so the protocol-error
            # dialog says WHAT we were waiting for, not just "timed out".
            raise TimeoutError(
                f"Timed out after {timeout}s waiting for a reply on "
                f"{topic!r}. No matching message arrived — the hardware or "
                f"backend responder for this topic may be disconnected, not "
                f"running, or slower than the timeout."
            ) from None

    def wait(self, *args, **kwargs):
        self.protocol.wait(*args, **kwargs)

    def prompt_gui(self,*args, **kwargs):
        self.protocol.prompt_gui(*args, **kwargs)
