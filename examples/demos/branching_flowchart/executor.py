"""Demo executor — the real ProtocolExecutor's logic plus decision routing.

Mirrored 1:1 from ``pluggable_protocol_tree/execution/executor.py``:

  * plain ``threading.Thread`` worker, not QThread (executor.py:197)
  * pause_event honored at step boundaries only; stop_event short-circuits
    everywhere and clears a pause so Stop-while-paused can't deadlock
    (executor.py:234)
  * hooks fanned across priority buckets — sequential between buckets,
    ThreadPoolExecutor-parallel within one; first exception sets stop_event
    and re-raises (executor.py:548 ``_run_hooks``)
  * hook order per step: on_pre_step -> on_step -> on_post_step; protocol
    brackets on_pre_protocol_start / on_protocol_start ... on_protocol_end /
    on_post_protocol_end, with the repeats loop inside (executor.py:242)
  * terminal signal precedence error > aborted > finished in one place
    (executor.py:489 ``_emit_terminal_signal``)

The ONE structural change under test: ``_run_steps`` walks step indices
through a routing resolver instead of always ``i += 1``. After
``on_post_step``, decisions requested by handlers via
``ctx.request_decision`` are resolved — by prompting the user (a
PendingDecision handed to the GUI thread) or automatically (auto mode /
auto-after-N / provider default) — and the chosen outcome's route decides
the next step index. Steps with no decision fall through exactly as today.

Signals are Qt signals on a QObject instead of Traits Events: created on
the GUI thread and emitted from the worker, Qt auto-queues them onto the
GUI thread — same marshalling role dispatch="ui" plays in the real app.
"""

import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal

from .model import ABORT, END, NEXT, SELF


class ExecutorSignals(QObject):
    protocol_started = Signal()
    protocol_finished = Signal()
    protocol_aborted = Signal()
    protocol_error = Signal(str)
    protocol_paused = Signal()
    protocol_resumed = Signal()
    protocol_repetition_finished = Signal(int, int)     # rep, total
    step_started = Signal(str, int, int)                # step_id, n, total
    step_finished = Signal(str)                         # step_id
    decision_pending = Signal(object)                   # PendingDecision
    decision_resolved = Signal(str, str, str, bool)     # step_id, decision_id, outcome_id, was_auto
    log = Signal(str)


class PauseEvent:
    """Same surface as the real PauseEvent: set/clear/is_set/wait_cleared."""

    def __init__(self):
        self._resumed = threading.Event()
        self._resumed.set()

    def set(self):
        self._resumed.clear()

    def clear(self):
        self._resumed.set()

    def is_set(self):
        return not self._resumed.is_set()

    def wait_cleared(self, timeout=None):
        return self._resumed.wait(timeout)


class AbortError(Exception):
    """Stop surfaced from inside a hook (mirror of execution/exceptions.py)."""


class PendingDecision:
    """One decision awaiting a user answer. Emitted to the GUI thread via
    ``decision_pending``; the dialog calls :meth:`resolve` and the worker
    thread (blocked in ``_answer_for``) picks the answer up."""

    def __init__(self, step, spec, cfg, message, options):
        self.step = step
        self.spec = spec
        self.cfg = cfg
        self.message = message
        # list[(Outcome, target, target_description)] in button order
        self.options = options
        self.answered = threading.Event()
        self.answer = None           # outcome_id
        self.remember_auto = False   # "auto-pick this for the rest of the run"

    def resolve(self, outcome_id, remember_auto=False):
        self.answer = outcome_id
        self.remember_auto = remember_auto
        self.answered.set()


class ProtocolContext:
    def __init__(self, protocol, signals, stop_event, pause_event):
        self.protocol = protocol
        self.signals = signals
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.scratch = {}


class StepContext:
    """Per-step context handed to hooks (mirror of the real StepContext,
    minus the dramatiq mailboxes — plus decision collection)."""

    def __init__(self, step, proto_ctx):
        self.step = step
        self.protocol = proto_ctx
        self._lock = threading.Lock()
        self._decision_requests = []   # [(DecisionSpec, message)]

    def log(self, msg):
        self.protocol.signals.log.emit(f"[{self.step.name}] {msg}")

    def sleep(self, seconds):
        """Stop-aware, pause-aware dwell (the demo's ctx.sleep/wait_for)."""
        deadline = time.monotonic() + seconds
        while not self.protocol.stop_event.is_set():
            if self.protocol.pause_event.is_set():
                remaining = deadline - time.monotonic()
                self.protocol.pause_event.wait_cleared()
                deadline = time.monotonic() + max(0.0, remaining)
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))
        raise AbortError()

    def request_decision(self, spec, message=None):
        """Called by a handler hook: this step's outcome needs a decision.
        Thread-safe — hooks in one priority bucket run in parallel."""
        with self._lock:
            self._decision_requests.append((spec, message))

    def pending_decisions(self):
        with self._lock:
            reqs = list(self._decision_requests)
        # Deterministic resolution order regardless of in-bucket thread
        # timing: provider priority, then spec id.
        prio = {c.model.col_id: c.handler.priority
                for c in self.protocol.protocol.columns}
        reqs.sort(key=lambda r: (prio.get(r[0].provider_col_id, 999), r[0].id))
        return reqs


class DemoExecutor:
    """One executor per Protocol. Reused across runs (same as the real one:
    start() is a no-op while the previous worker thread is alive)."""

    _PROTOCOL_HOOKS = (
        "on_pre_protocol_start", "on_protocol_start",
        "on_protocol_end", "on_post_protocol_end",
    )
    _TEARDOWN_HOOKS = ("on_protocol_end", "on_post_protocol_end")

    def __init__(self, protocol, signals=None):
        self.protocol = protocol
        self.signals = signals or ExecutorSignals()
        self.pause_event = PauseEvent()
        self.stop_event = threading.Event()
        self._thread = None
        self._error = None
        self._repeats = 1

    # ------- public control API (called from the GUI thread) -------

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, repeats=1):
        if self.is_running():
            return
        self.pause_event.clear()
        self.stop_event.clear()
        self._error = None
        self._repeats = max(1, int(repeats))
        self._thread = threading.Thread(
            target=self.run, name="flowchart_demo_executor", daemon=True)
        self._thread.start()

    def wait(self, timeout=None):
        if self._thread is None:
            return True
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def pause(self):
        self.pause_event.set()
        self.signals.protocol_paused.emit()

    def resume(self):
        self.pause_event.clear()
        self.signals.protocol_resumed.emit()

    def stop(self):
        # Clear pause too so Stop-while-paused doesn't deadlock wait_cleared.
        self.stop_event.set()
        self.pause_event.clear()

    # ------- main loop (mirror of ProtocolExecutor.run) -------

    def run(self):
        handlers = [c.handler for c in self.protocol.columns]
        proto_ctx = ProtocolContext(self.protocol, self.signals,
                                    self.stop_event, self.pause_event)
        started_at = time.monotonic()
        try:
            self._run_hooks("on_pre_protocol_start", handlers, proto_ctx, None)
            if not self.stop_event.is_set():
                self.signals.protocol_started.emit()
                self.signals.log.emit("Protocol started")
            for rep in range(self._repeats):
                if self.stop_event.is_set():
                    break
                if self._repeats > 1:
                    self.signals.log.emit(
                        f"Protocol repetition {rep + 1}/{self._repeats}")
                self._run_hooks("on_protocol_start", handlers, proto_ctx, None)
                self._run_steps(handlers, proto_ctx)
                self._run_hooks("on_protocol_end", handlers, proto_ctx, None)
                self.signals.protocol_repetition_finished.emit(
                    rep + 1, self._repeats)
            self._run_hooks("on_post_protocol_end", handlers, proto_ctx, None)
        except AbortError:
            # Clean cancellation (Stop while a hook was blocked), not a failure.
            self.stop_event.set()
            try:
                self._run_hooks("on_protocol_end", handlers, proto_ctx, None)
                self._run_hooks("on_post_protocol_end", handlers, proto_ctx, None)
            except Exception:
                pass
        except Exception as e:
            self._error = e
            try:
                self._run_hooks("on_protocol_end", handlers, proto_ctx, None)
                self._run_hooks("on_post_protocol_end", handlers, proto_ctx, None)
            except Exception:
                pass
        finally:
            self._emit_terminal_signal()
            outcome = ("errored" if self._error is not None
                       else "aborted" if self.stop_event.is_set()
                       else "finished")
            self.signals.log.emit(
                f"Protocol {outcome} in {time.monotonic() - started_at:.2f}s")

    # ------- step walk: sequential fall-through + decision routing -------

    def _run_steps(self, handlers, proto_ctx):
        steps = self.protocol.steps
        # times each (step_id, decision_id) has fired this run — drives
        # the "stop prompting after N retries" behaviour.
        occurrences = defaultdict(int)

        i = 0
        step_no = 0
        while 0 <= i < len(steps):
            if self.stop_event.is_set():
                break
            if self.pause_event.is_set():
                self.signals.protocol_paused.emit()
                self.pause_event.wait_cleared()
                if self.stop_event.is_set():
                    break
                self.signals.protocol_resumed.emit()

            step = steps[i]
            step_no += 1
            step_ctx = StepContext(step, proto_ctx)
            self.signals.step_started.emit(step.id, step_no, len(steps))
            self._run_hooks("on_pre_step", handlers, step_ctx, step)
            self._run_hooks("on_step", handlers, step_ctx, step)
            self._run_hooks("on_post_step", handlers, step_ctx, step)
            self.signals.step_finished.emit(step.id)

            verdict = self._resolve_routing(step, step_ctx, i, occurrences)
            if verdict[0] == "jump":
                i = verdict[1]
            elif verdict[0] == "end":
                break
            else:  # "abort"
                self.stop_event.set()
                break

    def _resolve_routing(self, step, step_ctx, i, occurrences):
        """Turn the step's pending decisions + completion route into the
        next frame index. Returns ("jump", idx) | ("end",) | ("abort",).

        Decisions resolve in provider-priority order; the first one whose
        outcome routes anywhere other than NEXT wins and later requests
        from the same step are skipped (logged)."""
        requests = step_ctx.pending_decisions()
        for n, (spec, message) in enumerate(requests):
            if self.stop_event.is_set():
                return ("abort",)
            cfg = step.cfg_for(spec.id)
            occurrences[(step.id, spec.id)] += 1
            seen = occurrences[(step.id, spec.id)]

            auto = (cfg.mode == "auto"
                    or (cfg.auto_after is not None and seen > cfg.auto_after))
            if auto:
                outcome_id = cfg.auto_outcome or spec.default_outcome
                why = ("auto mode" if cfg.mode == "auto"
                       else f"auto after {cfg.auto_after} prompts")
                step_ctx.log(
                    f"Decision {spec.title!r} -> "
                    f"{spec.outcome_by_id(outcome_id).label} ({why})")
            else:
                outcome_id = self._answer_for(step, spec, cfg, message)
                if outcome_id is None:      # stopped while waiting
                    return ("abort",)
                step_ctx.log(
                    f"Decision {spec.title!r} -> "
                    f"{spec.outcome_by_id(outcome_id).label} (user)")
            self.signals.decision_resolved.emit(step.id, spec.id,
                                                outcome_id, auto)

            target = cfg.routes.get(outcome_id,
                                    spec.default_routes.get(outcome_id, NEXT))
            if target == NEXT:
                continue  # no redirect — let remaining decisions weigh in
            if requests[n + 1:]:
                step_ctx.log(
                    f"{len(requests) - n - 1} later decision(s) skipped — "
                    f"{spec.title!r} already redirected the flow")
            return self._verdict_for(step, target, i)

        # No decision redirected: follow the step's completion route.
        return self._verdict_for(step, step.next_target, i,
                                 completion=True)

    def _verdict_for(self, step, target, i, completion=False):
        proto = self.protocol
        if target == SELF:
            return ("jump", i)
        if target == END:
            return ("end",)
        if target == ABORT:
            return ("abort",)
        if target == NEXT:
            return ("jump", i + 1) if i + 1 < len(proto.steps) else ("end",)
        idx = proto.index_of(target)
        if idx is None:
            self.signals.log.emit(
                f"[{step.name}] Route target missing — falling through "
                f"to next step")
            return ("jump", i + 1) if i + 1 < len(proto.steps) else ("end",)
        return ("jump", idx)

    def _answer_for(self, step, spec, cfg, message):
        """Hand a PendingDecision to the GUI thread and block (stop-aware)
        until it's answered. Returns the outcome_id, or None on stop."""
        options = []
        for outcome in spec.outcomes:
            target = cfg.routes.get(outcome.id,
                                    spec.default_routes.get(outcome.id, NEXT))
            options.append((outcome, target,
                            self.protocol.describe_target(target)))
        pending = PendingDecision(step, spec, cfg, message, options)
        self.signals.decision_pending.emit(pending)
        while not pending.answered.wait(0.1):
            if self.stop_event.is_set():
                return None
        if pending.remember_auto:
            cfg.mode = "auto"
            cfg.auto_outcome = pending.answer
        return pending.answer

    # ------- hook fan-out (mirror of ProtocolExecutor._run_hooks) -------

    def _run_hooks(self, hook_name, handlers, ctx, step):
        """Priority-bucket fan-out: lower priority first, equal priorities
        parallel in one ThreadPoolExecutor, first exception sets stop_event
        and re-raises. Teardown hooks always run every bucket."""
        buckets = defaultdict(list)
        for handler in handlers:
            buckets[handler.priority].append(handler)

        teardown = hook_name in self._TEARDOWN_HOOKS
        for priority in sorted(buckets):
            if not teardown and self.stop_event.is_set():
                break
            bucket = buckets[priority]
            with ThreadPoolExecutor(max_workers=max(1, len(bucket))) as pool:
                futures = {
                    pool.submit(self._invoke_hook, h, hook_name, ctx, step): h
                    for h in bucket
                }
                first_exc = None
                for f in as_completed(futures):
                    exc = f.exception()
                    if exc is not None and first_exc is None:
                        first_exc = exc
                        self.stop_event.set()
                if first_exc is not None:
                    raise first_exc

    def _invoke_hook(self, handler, hook_name, ctx, step):
        fn = getattr(handler, hook_name)
        try:
            if hook_name in self._PROTOCOL_HOOKS:
                fn(ctx)
            else:
                fn(step, ctx)
        except AbortError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"{type(handler).__name__}.{hook_name} failed on step "
                f"{getattr(step, 'name', '<protocol>')!r}: {e}") from e

    def _emit_terminal_signal(self):
        """Error > aborted > finished — same precedence as the real one."""
        if self._error is not None:
            self.signals.protocol_error.emit(str(self._error))
        elif self.stop_event.is_set():
            self.signals.protocol_aborted.emit()
        else:
            self.signals.protocol_finished.emit()
