"""Protocol executor — runs a RowManager's rows on a worker thread.

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

The worker thread is a plain ``threading.Thread``, not ``QThread``. The
executor itself is a HasTraits, not a QObject — moveToThread only works
on QObjects. Qt signal marshalling to GUI-thread slots still works
because ExecutorSignals is its own QObject; emissions from any thread
queue correctly to slots living on the GUI thread.
"""

import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from traits.api import Any, Callable as CallableTrait, HasTraits, Instance

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.listener import (
    set_active_step, clear_active_step, warm_broker_connection,
)
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.execution.step_context import (
    ProtocolContext, StepContext,
)
from pluggable_protocol_tree.models.row_manager import RowManager


logger = logging.getLogger(__name__)


def _dotted_path(path: tuple) -> str:
    """1-indexed dotted display ('1.2.3') for a 0-indexed path tuple."""
    return ".".join(str(i + 1) for i in path) if path else ""


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

    # ------- defaults so headless callers can ProtocolExecutor(row_manager=rm) -------

    def _qsignals_default(self):
        return ExecutorSignals()

    def _pause_event_default(self):
        return PauseEvent()

    def _stop_event_default(self):
        return threading.Event()

    def _bucket_pool_factory_default(self):
        return ThreadPoolExecutor

    # ------- one-shot convenience for headless / scripting callers -------

    @classmethod
    def execute(cls, row_manager, blocking: bool = True,
                timeout: float = None) -> "ProtocolExecutor":
        """Construct an executor with sensible defaults, start it, and
        optionally block until done. Returns the executor so the caller
        can pause/resume/stop or inspect signals afterwards.

        Headless usage:
            ex = ProtocolExecutor.execute(rm, blocking=False)
            ex.pause()
            time.sleep(2)
            ex.resume()
            ex.wait()
        """
        ex = cls(row_manager=row_manager)
        ex.start()
        if blocking:
            ex.wait(timeout=timeout)
        return ex

    # ------- public control API (called from the GUI thread) -------

    def start(self) -> None:
        """Spawn a worker thread and call run() on it. Idempotent —
        a second call while already running is ignored."""
        if self._thread is not None and self._thread.is_alive():
            return
        self.pause_event.clear()
        self.stop_event.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self.run,
            name="pluggable_protocol_tree_executor",
            daemon=True,
        )
        self._thread.start()

    def wait(self, timeout: float = None) -> bool:
        """Block until the executor's worker thread finishes (or the
        timeout elapses). Returns True if the thread is no longer
        running, False if it's still going (timeout case). Returns True
        immediately if start() was never called."""
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

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

    # ------- main loop -------

    def run(self) -> None:
        """Main loop. Runs synchronously when called directly (tests),
        or on its worker thread when entered via start()."""
        import time as _time
        cols = list(self.row_manager.columns)
        proto_ctx = ProtocolContext(
            columns=cols, stop_event=self.stop_event,
        )
        # PPT-3: hydrate per-protocol metadata (e.g. electrode_to_channel)
        # into the context's scratch so handlers can reach it without
        # holding a reference to the RowManager.
        proto_ctx.scratch.update(self.row_manager.protocol_metadata)
        proto_started_at = _time.monotonic()
        try:
            # Hide first-publish latency (Redis connect ~2s) from step 1's
            # observed duration by warming the broker connection upfront.
            warm_broker_connection()
            self._run_hooks("on_protocol_start", cols, proto_ctx, row=None)
            self.qsignals.protocol_started.emit()
            logger.info("Protocol started")

            step_index = 0
            for row, rep_chain in self.row_manager.iter_execution_frames():
                if self.stop_event.is_set():
                    break
                if self.pause_event.is_set():
                    logger.info("Protocol paused at step %d", step_index + 1)
                    self.pause_event.wait_cleared()
                    if self.stop_event.is_set():
                        break
                    logger.info("Protocol resumed")

                step_index += 1
                step_started_at = _time.monotonic()
                rep_str = (
                    " | " + ", ".join(f"rep {i}/{n} of {name!r}"
                                      for name, i, n in rep_chain)
                    if rep_chain else ""
                )
                logger.info(
                    "Step %d started: %r (path %s, duration_s=%s)%s",
                    step_index, row.name,
                    _dotted_path(row.path),
                    getattr(row, "duration_s", None),
                    rep_str,
                )

                step_ctx = self._build_step_ctx(row, cols, proto_ctx)
                set_active_step(step_ctx)
                try:
                    # Rep info first so UI labels are populated before the
                    # row-highlight fires from step_started.
                    self.qsignals.step_repetition.emit(rep_chain)
                    self.qsignals.step_started.emit(row)
                    self._run_hooks("on_pre_step",  cols, step_ctx, row)
                    self._run_hooks("on_step",      cols, step_ctx, row)
                    self._run_hooks("on_post_step", cols, step_ctx, row)
                    self.qsignals.step_finished.emit(row)
                finally:
                    clear_active_step()

                logger.info(
                    "Step %d finished: %r in %.2fs",
                    step_index, row.name, _time.monotonic() - step_started_at,
                )

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
            outcome = (
                "errored" if self._error is not None
                else "aborted" if self.stop_event.is_set()
                else "finished"
            )
            logger.info(
                "Protocol %s in %.2fs",
                outcome, _time.monotonic() - proto_started_at,
            )
            # threading.Thread terminates naturally when run() returns;
            # nothing to quit() here. start() checks is_alive() to make
            # sure a previous run has completed before starting a new one.

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
