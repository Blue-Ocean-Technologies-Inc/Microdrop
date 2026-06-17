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

import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from traits.api import (
    Any, Bool, Callable as CallableTrait, HasTraits, Instance, Int, List,
    Tuple, Union,
)

from pluggable_protocol_tree.interfaces.i_column import IColumnHandler
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.exceptions import (
    AbortError, StepExecutionError,
)
from pluggable_protocol_tree.execution.listener import (
    set_active_step, clear_active_step, warm_broker_connection,
)
from pluggable_protocol_tree.execution.seek import resolve_seek
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.execution.step_context import (
    ProtocolContext, StepContext,
)
from pluggable_protocol_tree.models.row_manager import RowManager

from logger.logger_service import get_logger
logger = get_logger(__name__)

# Brief pause between whole-protocol repetitions so the UI repaint/clear
# between reps lands before the next one starts (was the view's
# NEXT_REP_RESTART_DELAY_MS before repeats moved into the executor).
INTER_REP_DELAY_S = 0.05


class ProtocolExecutor(HasTraits):
    """One executor per RowManager. Reused across runs."""

    row_manager = Instance(RowManager)
    qsignals    = Instance(ExecutorSignals)

    # Execution-only handlers (no column/view) whose hooks run alongside the
    # column handlers, ordered by the same priority buckets. Used for
    # once-per-run lifecycle policy (realtime-mode prep, logging start/stop)
    # via the on_pre_protocol_start / on_post_protocol_end hooks. The
    # composition root assigns these; the executor stays generic.
    lifecycle_handlers = List(Instance(IColumnHandler))

    pause_event = Instance(PauseEvent)
    stop_event  = Instance(threading.Event)

    # Internal — reset by start(); _thread liveness gates re-entry
    # (is_alive()), _error routes _emit_terminal_signal. _error stays Any
    # on purpose: it holds an arbitrary exception instance.
    _thread = Instance(threading.Thread)
    _error  = Any
    # Optional row.path tuple — when set, run() skips frames until it
    # encounters this path, then proceeds normally. Cleared on every
    # start() so a previous "play from selected" doesn't carry over.
    _start_step_path = Union(None, Tuple)
    # Live ProtocolContext for the current run; seek() writes resume_target on
    # it. None between runs.
    _active_proto_ctx = Any
    # Position the frame walk last reported (path tuple) -- used to decide
    # same-step vs different-step on resume.
    _current_step_path = Union(None, Tuple)
    # When True, the next run() builds the ProtocolContext with
    # preview_mode=True so hardware-publishing hooks skip their
    # broker writes (legacy protocol_grid "Preview Mode" semantics).
    _preview_mode = Bool(False)
    # Whole-protocol repetitions for the next run. The executor owns the
    # repeat loop: on_pre_protocol_start / on_post_protocol_end bracket all
    # repetitions, while on_protocol_start / on_protocol_end fire per rep.
    _repeats = Int(1)
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

    def start(
        self,
        start_step_path: Optional[tuple] = None,
        preview_mode: bool = False,
        repeats: int = 1,
    ) -> None:
        """Spawn a worker thread and call run() on it. Idempotent —
        a second call while already running is ignored.

        If ``start_step_path`` is given, run() skips frames in execution
        order until it encounters a row whose ``path`` equals it, then
        proceeds normally. Useful for "play from currently-selected step".

        If ``preview_mode`` is True, the ProtocolContext built by run()
        carries ``preview_mode=True``; hardware-publishing hooks (e.g.
        the routes column's electrode-state publishes) check this flag
        and skip their broker writes. Step iteration, dwells, signals
        and column logic all run normally — only the hardware-touching
        side effects are gated. Mirrors the legacy protocol_grid
        "Preview Mode" checkbox semantics.

        ``repeats`` is the number of whole-protocol repetitions; the run
        loops the step sequence that many times inside a single run(),
        firing on_pre_protocol_start / on_post_protocol_end once around
        the whole thing.
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self.pause_event.clear()
        self.stop_event.clear()
        self._error = None
        self._start_step_path = (
            tuple(start_step_path) if start_step_path is not None else None
        )
        self._preview_mode = bool(preview_mode)
        self._repeats = max(1, int(repeats))
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

    def seek(self, step_path, phase_index) -> None:
        """Record a mid-run resume target (issue #471). Only meaningful while
        paused; ignored otherwise. The frame walk / phase loop consult it on
        resume. Qt-free: writes a plain tuple onto the live ProtocolContext."""
        if not self.pause_event.is_set():
            return
        if self._active_proto_ctx is not None:
            self._active_proto_ctx.resume_target = (tuple(step_path),
                                                    int(phase_index))

    def stop(self) -> None:
        """Set stop_event AND clear pause_event so a Stop-while-paused
        doesn't deadlock the main loop in pause_event.wait_cleared()."""
        self.stop_event.set()
        self.pause_event.clear()

    # ------- main loop -------

    def run(self) -> None:
        """Main loop. Runs synchronously when called directly (tests),
        or on its worker thread when entered via start()."""
        cols = list(self.row_manager.columns)
        # Column handlers + execution-only lifecycle handlers, ordered
        # together by priority in _run_hooks. _build_step_ctx stays
        # column-only (lifecycle handlers declare no wait_for_topics).
        handlers = [c.handler for c in cols] + list(self.lifecycle_handlers)
        proto_ctx = ProtocolContext(
            columns=cols,
            stop_event=self.stop_event,
            pause_event=self.pause_event,
            qsignals=self.qsignals,
            preview_mode=self._preview_mode,
        )
        self._active_proto_ctx = proto_ctx
        # PPT-3: hydrate per-protocol metadata (e.g. electrode_to_channel)
        # into the context's scratch so handlers can reach it without
        # holding a reference to the RowManager.
        proto_ctx.scratch.update(self.row_manager.protocol_metadata)
        proto_started_at = time.monotonic()
        try:
            # Hide first-publish latency (Redis connect ~2s) from step 1's
            # observed duration by warming the broker connection upfront.
            warm_broker_connection()
            # Once per run, before any repetition (realtime-mode prep,
            # logging start, ...) — fires before the per-rep on_protocol_start.
            self._run_hooks("on_pre_protocol_start", handlers, proto_ctx, row=None)

            # Pre-protocol wait: hooks contributed settle seconds via
            # ctx.add_pre_protocol_wait(); wait the total once here (shown as a
            # loading screen), pausable and stop-aware, before the first step.
            total_wait = proto_ctx.pre_protocol_wait_s
            if total_wait > 0 and not self.stop_event.is_set():
                self.qsignals.protocol_wait_started.emit(int(total_wait * 1000))
                self._wait_pre_protocol(total_wait)
                self.qsignals.protocol_wait_finished.emit()

            # Don't announce "started" if the run was already stopped during
            # the pre-protocol phase (e.g. Stop pressed on the loading screen):
            # that would publish PROTOCOL_RUNNING True for a run that never ran
            # and race the terminal's False. The terminal signal still fires.
            if not self.stop_event.is_set():
                self.qsignals.protocol_started.emit()
                logger.info("Protocol started")

            for rep in range(self._repeats):
                if self.stop_event.is_set():
                    break
                if self._repeats > 1:
                    logger.info(f"Protocol repetition {rep + 1}/{self._repeats}")
                # Per repetition. on_protocol_start / on_protocol_end keep
                # their per-rep semantics; on_protocol_end runs even on stop
                # as best-effort cleanup.
                self._run_hooks("on_protocol_start", handlers, proto_ctx, row=None)
                # "Play from selected step" applies to the first repetition
                # only; later reps run the full sequence.
                skip_until = self._start_step_path if rep == 0 else None
                self._run_steps(handlers, cols, proto_ctx, skip_until)
                self._run_hooks("on_protocol_end", handlers, proto_ctx, row=None)
                self.qsignals.protocol_repetition_finished.emit(
                    rep + 1, self._repeats)
                if rep + 1 < self._repeats and not self.stop_event.is_set():
                    self._interruptible_delay(INTER_REP_DELAY_S)

            # Once per run, after the last repetition (realtime-mode restore,
            # logging stop, ...).
            self._run_hooks("on_post_protocol_end", handlers, proto_ctx, row=None)

        except AbortError:
            # A Stop that surfaced as AbortError — e.g. the operator pressed
            # Stop while a worker-thread hook was blocked in ctx.wait_for /
            # ctx.prompt_gui (the pre-protocol recording / keep-realtime
            # dialogs). This is a clean cancellation, NOT a failure: leave
            # _error unset so _emit_terminal_signal routes to protocol_aborted
            # rather than protocol_error.
            logger.info("Protocol aborted (stop during a hook)")
            self.stop_event.set()
            try:
                self._run_hooks("on_protocol_end", handlers, proto_ctx, row=None)
                self._run_hooks("on_post_protocol_end", handlers, proto_ctx, row=None)
            except Exception:
                logger.exception("protocol-end hooks raised during abort cleanup")
        except Exception as e:
            self._error = e
            logger.exception("Protocol error")
            try:
                # Best-effort teardown for the current repetition and the run.
                self._run_hooks("on_protocol_end", handlers, proto_ctx, row=None)
                self._run_hooks("on_post_protocol_end", handlers, proto_ctx, row=None)
            except Exception:
                logger.exception("protocol-end hooks raised during error cleanup")

        finally:
            self._emit_terminal_signal()
            outcome = (
                "errored" if self._error is not None
                else "aborted" if self.stop_event.is_set()
                else "finished"
            )
            logger.info(
                f"Protocol {outcome} in "
                f"{time.monotonic() - proto_started_at:.2f}s"
            )
            self._active_proto_ctx = None
            # threading.Thread terminates naturally when run() returns;
            # nothing to quit() here. start() checks is_alive() to make
            # sure a previous run has completed before starting a new one.

    # ------- helpers -------

    def _run_steps(self, handlers, cols, proto_ctx, skip_until) -> None:
        """Run one repetition. Honors stop_event, pause_event (step + phase
        checkpoints), skip_until (start-of-run), and resume_target (#471
        mid-run seek)."""
        frames = list(self.row_manager.iter_execution_frames())
        frame_paths = [tuple(row.path) for row, _ in frames]

        i = 0
        step_index = 0
        start_phase_index = 0
        if skip_until is not None:
            # Generalised skip: jump to the first frame matching skip_until.
            for j, p in enumerate(frame_paths):
                if p == skip_until:
                    i = j
                    break
            else:
                return  # skip target absent -> nothing to run

        while i < len(frames):
            if self.stop_event.is_set():
                break
            row, rep_chain = frames[i]
            self._current_step_path = tuple(row.path)

            if self.pause_event.is_set():
                logger.info(f"Protocol paused at step {step_index + 1}")
                # Emitted here so a hook setting pause_event still surfaces
                # to the UI. The toolbar's executor.pause() also emits —
                # slots that toggle UI state on each signal must be
                # idempotent.
                self.qsignals.protocol_paused.emit()
                self.pause_event.wait_cleared()
                if self.stop_event.is_set():
                    break
                self.qsignals.protocol_resumed.emit()
                logger.info("Protocol resumed")
                # On resume, honor a mid-run seek to a DIFFERENT step here at
                # the step boundary (same-step seeks are handled inside the
                # phase loop). resolve_seek clamps + locates the target frame.
                target = proto_ctx.resume_target
                resolved = resolve_seek(frame_paths, target)
                if resolved is not None and tuple(target[0]) != tuple(row.path):
                    i, start_phase_index = resolved
                    proto_ctx.resume_target = None
                    step_index = i  # keep the counter roughly aligned
                    continue

            step_index += 1
            self._run_one_frame(handlers, cols, proto_ctx, row, rep_chain,
                                step_index, start_phase_index)
            start_phase_index = 0

            # A seek raised DURING the step (different step) aborts the phase
            # loop; redirect from here.
            target = proto_ctx.resume_target
            resolved = resolve_seek(frame_paths, target)
            if resolved is not None:
                i, start_phase_index = resolved
                proto_ctx.resume_target = None
                step_index = i
                continue
            i += 1

    def _run_one_frame(self, handlers, cols, proto_ctx, row, rep_chain,
                       step_index, start_phase_index) -> None:
        step_started_at = time.monotonic()
        rep_str = (
            " | " + ", ".join(f"rep {i}/{n} of {name!r}"
                              for name, i, n in rep_chain)
            if rep_chain else ""
        )
        logger.info(
            f"Step {step_index} started: {row.name!r} "
            f"(path {row.dotted_path()}, "
            f"duration_s={getattr(row, 'duration_s', None)}){rep_str}"
        )
        step_ctx = self._build_step_ctx(row, cols, proto_ctx)
        step_ctx.start_phase_index = int(start_phase_index)
        set_active_step(step_ctx)
        try:
            # Rep info first so UI labels are populated before the
            # row-highlight fires from step_started.
            self.qsignals.step_repetition.emit(rep_chain)
            self.qsignals.step_started.emit(row)
            self._run_hooks("on_pre_step",  handlers, step_ctx, row)
            self._run_hooks("on_step",      handlers, step_ctx, row)
            self._run_hooks("on_post_step", handlers, step_ctx, row)
            self.qsignals.step_finished.emit(row)
        finally:
            clear_active_step()
        logger.info(
            f"Step {step_index} finished: {row.name!r} in "
            f"{time.monotonic() - step_started_at:.2f}s"
        )

    def _interruptible_delay(self, seconds: float) -> None:
        """Sleep up to ``seconds``, returning early if stop_event fires."""
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self.stop_event.is_set():
                return
            time.sleep(min(0.02, remaining))

    def _wait_pre_protocol(self, seconds: float) -> None:
        """Block for ``seconds`` before the first step — pause- and stop-aware.

        While ``pause_event`` is set, the remaining time is frozen (the
        deadline is rebased on resume so paused time doesn't count), keeping
        the wait in lockstep with the paused loading screen. Returns early on
        ``stop_event`` (no raise — the rep loop then aborts cleanly via its
        own stop check)."""
        deadline = time.monotonic() + seconds
        while not self.stop_event.is_set():
            if self.pause_event.is_set():
                remaining = deadline - time.monotonic()
                self.pause_event.wait_cleared()
                if self.stop_event.is_set():
                    return
                deadline = time.monotonic() + max(0.0, remaining)
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))

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
        # Fresh Events per step — never reused across steps so a stale
        # `set` from a prior step can't leak in.
        step_ctx = StepContext(
            row=row, protocol=proto_ctx,
            phase_advance_event=threading.Event(),
            step_phases_done_event=threading.Event(),
        )
        # Detect within-bucket topic collisions before opening any boxes.
        per_priority_topics: dict[int, dict[str, str]] = {}  # priority --> topic --> col_id
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

    # Protocol-level hooks take (ctx); per-step hooks take (row, ctx).
    _PROTOCOL_HOOKS = (
        "on_pre_protocol_start", "on_protocol_start",
        "on_protocol_end", "on_post_protocol_end",
    )
    # Teardown hooks always run every bucket (best-effort cleanup), even once
    # stop_event is set. Forward hooks instead stop launching lower-priority
    # buckets the moment a hook sets stop_event — so a high-priority hook (e.g.
    # the recording-active dialog) can cancel the run before realtime-mode /
    # logging in lower buckets fire.
    _TEARDOWN_HOOKS = ("on_protocol_end", "on_post_protocol_end")

    def _run_hooks(self, hook_name, handlers, ctx, row) -> None:
        """Priority-bucket fan-out.

        Lower priority runs first. Equal priorities run in parallel
        (one ThreadPoolExecutor per bucket; the executor returns
        only when every future in the bucket has resolved).

        Operates on handlers directly (column handlers + lifecycle
        handlers) so execution-only lifecycle handlers participate in
        the same priority ordering as columns.

        The first exception in any bucket wins: stop_event is set so
        sibling hooks waiting on ctx.wait_for() return promptly via
        AbortError, the pool drains, and the original exception is
        re-raised out of this method.
        """
        buckets = defaultdict(list)
        for handler in handlers:
            buckets[handler.priority].append(handler)

        teardown = hook_name in self._TEARDOWN_HOOKS
        for priority in sorted(buckets):
            # A forward hook that set stop_event in an earlier bucket cancels
            # the rest of this phase; teardown hooks always run every bucket.
            if not teardown and self.stop_event.is_set():
                break
            bucket = buckets[priority]
            with self.bucket_pool_factory(
                max_workers=max(1, len(bucket)),
            ) as pool:
                futures = {
                    pool.submit(self._invoke_hook, h, hook_name, ctx, row): h
                    for h in bucket
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

    def _invoke_hook(self, handler, hook_name, ctx, row) -> None:
        """Dispatch to the handler's named hook with the right signature.

        Per-step hooks take (row, ctx); protocol-level take (ctx).
        Default handlers from BaseColumnHandler are no-ops, so calling
        them on every handler is safe (and cheaper than introspecting
        which handlers override).
        """
        fn = getattr(handler, hook_name)
        try:
            if hook_name in self._PROTOCOL_HOOKS:
                fn(ctx)
            else:
                fn(row, ctx)
        except AbortError:
            # Expected on Stop (a sibling/this hook's wait_for saw the
            # stop_event). Propagate unannotated so it routes to the
            # aborted/terminal path, not an error dialog.
            raise
        except Exception as e:
            # Annotate real failures with the step + handler so the
            # protocol-error dialog can report where and why, not just the
            # bare exception text. Chain so the full traceback survives.
            raise StepExecutionError(handler, hook_name, row, e) from e
