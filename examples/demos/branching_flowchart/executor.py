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
    protocol_repetition_finished = Signal(int, int)  # rep, total
    step_started = Signal(str, int, int)  # step_id, n, total
    step_finished = Signal(str)  # step_id
    decision_pending = Signal(object)  # PendingDecision
    decision_resolved = Signal(
        str, str, str, bool
    )  # step_id, decision_id, outcome_id, was_auto
    # Edge-identifying tuple for the route the executor just followed —
    # ("op", op_id) | ("outcome", dn_id, outcome_id) | ("flow", step_id)
    # | ("next", step_id). The canvas flashes the matching edge.
    route_taken = Signal(object)
    # (row_or_shape_id, text): a short note the canvas shows as a toast
    # next to the item (silent auto answers, group repeat passes, ...).
    canvas_note = Signal(str, str)
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

    def __init__(self, step, spec, decision_node, message, options):
        self.step = step
        self.spec = spec
        self.decision_node = decision_node  # placed shape, or None
        self.message = message
        # list[(Outcome, target, target_description)] in button order
        self.options = options
        self.answered = threading.Event()
        self.answer = None  # outcome_id
        self.remember_auto = False  # "auto-pick this for the rest of the run"

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

    def log(self, msg):
        self.signals.log.emit(msg)


class StepContext:
    """Per-step context handed to hooks (mirror of the real StepContext,
    minus the dramatiq mailboxes — plus decision collection)."""

    def __init__(self, step, proto_ctx):
        self.step = step
        self.protocol = proto_ctx
        self._lock = threading.Lock()
        self._decision_requests = []  # [(DecisionSpec, message)]

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
        prio = {
            c.model.col_id: c.handler.priority for c in self.protocol.protocol.columns
        }
        reqs.sort(key=lambda r: (prio.get(r[0].provider_col_id, 999), r[0].id))
        return reqs


class DemoExecutor:
    """One executor per Protocol. Reused across runs (same as the real one:
    start() is a no-op while the previous worker thread is alive)."""

    _PROTOCOL_HOOKS = (
        "on_pre_protocol_start",
        "on_protocol_start",
        "on_protocol_end",
        "on_post_protocol_end",
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
            target=self.run, name="flowchart_demo_executor", daemon=True
        )
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
        proto_ctx = ProtocolContext(
            self.protocol, self.signals, self.stop_event, self.pause_event
        )
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
                        f"Protocol repetition {rep + 1}/{self._repeats}"
                    )
                self._run_hooks("on_protocol_start", handlers, proto_ctx, None)
                self._run_steps(handlers, proto_ctx)
                self._run_hooks("on_protocol_end", handlers, proto_ctx, None)
                self.signals.protocol_repetition_finished.emit(rep + 1, self._repeats)
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
            outcome = (
                "errored"
                if self._error is not None
                else "aborted" if self.stop_event.is_set() else "finished"
            )
            self.signals.log.emit(
                f"Protocol {outcome} in {time.monotonic() - started_at:.2f}s"
            )

    # ------- step walk: sequential fall-through + decision routing -------

    def _run_steps(self, handlers, proto_ctx):
        proto = self.protocol
        steps = proto.leaves()
        if not steps:
            return
        # Group chain (outermost first) per leaf, for entry/exit/repeat
        # bookkeeping.
        chains = [proto.group_chain_of(leaf.id) for leaf in steps]
        # times each (step_id, decision_id) has fired this run — drives
        # the "stop prompting after N retries" behaviour.
        occurrences = defaultdict(int)
        # group_id -> current pass number. Present only for groups that
        # were FORMALLY entered (fall-through or a route to the group
        # node); an informal jump into a group's step seeds the counter
        # exhausted, so no repeats get scheduled.
        passes = {}

        def transition(from_idx, to_idx, formal, reenter=frozenset()):
            """Fire group exits/entries for a move between leaves.
            ``reenter`` forces exit+entry for a group present on both
            sides (routing to the group node you're already inside =
            restart it)."""
            from_chain = chains[from_idx] if from_idx is not None else []
            to_chain = chains[to_idx] if to_idx is not None else []
            from_ids = {g.id for g in from_chain}
            to_ids = {g.id for g in to_chain}
            for g in reversed(from_chain):  # innermost first
                if g.id not in to_ids or g.id in reenter:
                    self.signals.log.emit(f"Leaving group {g.name!r}")
                    self._run_hooks("on_group_exit", handlers, proto_ctx, g)
                    passes.pop(g.id, None)
            for g in to_chain:  # outermost first
                if g.id not in from_ids or g.id in reenter:
                    if formal:
                        passes[g.id] = 1
                        reps = f" — pass 1/{g.repetitions}" if g.repetitions > 1 else ""
                        self.signals.log.emit(
                            f"Entering group {g.name!r}{reps} "
                            f"(group-entry hooks fire)"
                        )
                        self._run_hooks("on_group_enter", handlers, proto_ctx, g)
                    else:
                        passes[g.id] = g.repetitions
                        self.signals.log.emit(
                            f"Jumped into group {g.name!r} mid-sequence "
                            f"— no formal entry: group hooks and repeats "
                            f"are NOT restarted"
                        )
                        self.signals.canvas_note.emit(g.id, "no formal entry")

        i = 0
        step_no = 0
        transition(None, 0, formal=True)
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
            if verdict[0] == "abort":
                self.stop_event.set()
                break

            # Fall-through honors repetitions, innermost first: the step's
            # own repetitions replay it in place; then the innermost group
            # being left with passes remaining replays from its first
            # leaf. Explicit routes (drawn edges) override repeats.
            fallthrough = (verdict[0] == "jump" and verdict[2] == "next") or (
                verdict[0] == "end" and verdict[1]
            )
            if fallthrough:
                step_reps = max(1, int(step.repetitions or 1))
                k = passes.get(("leaf", step.id), 1)
                if k < step_reps:
                    passes[("leaf", step.id)] = k + 1
                    self.signals.log.emit(
                        f"Step {step.name!r} — repeat {k + 1}/{step_reps}"
                    )
                    self.signals.canvas_note.emit(
                        step.id, f"repeat {k + 1}/{step_reps}"
                    )
                    # Replay in place: no group transition, streak kept.
                    verdict = ("jump", i, "step", None)
                    fallthrough = False
            if fallthrough:
                to_ids = (
                    {g.id for g in chains[verdict[1]]}
                    if verdict[0] == "jump"
                    else set()
                )
                for g in reversed(chains[i]):
                    if g.id in to_ids:
                        continue
                    k = passes.get(g.id, 1)
                    if k < g.repetitions:
                        first_leaf = proto.leaf_index(g.id)
                        if first_leaf is not None:
                            passes[g.id] = k + 1
                            self.signals.log.emit(
                                f"Group {g.name!r} — repeat pass "
                                f"{k + 1}/{g.repetitions}"
                            )
                            self.signals.canvas_note.emit(
                                g.id, f"pass {k + 1}/{g.repetitions}"
                            )
                            verdict = ("jump", first_leaf, "next", None)
                            break

            if verdict[0] == "jump" and verdict[2] == "next":
                self.signals.route_taken.emit(("next", step.id))
            if verdict[0] == "end":
                transition(i, None, formal=True)
                break
            new_i, kind, gid = verdict[1], verdict[2], verdict[3]
            # Routing to the group node you're already inside restarts
            # it: exit + formal re-entry, fresh pass budget.
            reenter = (
                frozenset({gid})
                if kind == "group" and gid in {g.id for g in chains[i]}
                else frozenset()
            )
            if new_i != i or reenter:
                # Leaving the step (or restarting its group) ends the
                # retry streak: decision counters and the step's own
                # repeat counter reset so a later revisit starts fresh.
                for key in [k for k in occurrences if k[0] == step.id]:
                    del occurrences[key]
                passes.pop(("leaf", step.id), None)
                transition(i, new_i, formal=kind in ("next", "group"), reenter=reenter)
            i = new_i

    def _resolve_routing(self, step, step_ctx, i, occurrences):
        """Turn the step's pending decisions + completion route into the
        next frame index. Returns ("jump", idx) | ("end",) | ("abort",).

        Resolution order: decisions with no incoming chain edge resolve
        first, together, in provider-priority order. An outcome whose
        route targets another decision shape of the same step is a CHAIN:
        choosing it activates that decision, which resolves next — serial
        resolution. A chained decision whose activating outcome was not
        chosen (or that never fired) is skipped this round.

        Routing then evaluates: logic ops first (AND = every input
        outcome chosen this round, OR = any of them), in creation order;
        then the resolved decisions' own outcome routes in resolution
        order (chains excluded; first non-NEXT wins); then the step's
        completion route; then table order."""
        proto = self.protocol
        requests = step_ctx.pending_decisions()
        fired = {spec.id: (spec, message) for spec, message in requests}
        step_dns = {
            dn.decision_id: dn for dn in proto.decision_nodes if dn.step_id == step.id
        }
        dn_by_id = {dn.id: dn for dn in step_dns.values()}
        chained_dn_ids = {
            target
            for dn in step_dns.values()
            for target in dn.routes.values()
            if target in dn_by_id
        }

        # Roots: fired decisions not waiting on a chain activation.
        queue = [
            (spec, message)
            for spec, message in requests
            if not (spec.id in step_dns and step_dns[spec.id].id in chained_dn_ids)
        ]
        resolved = []  # [(spec, dn|None, outcome_id)] in order
        resolved_ids = set()
        activated = set()
        qi = 0
        while qi < len(queue):
            spec, message = queue[qi]
            qi += 1
            if spec.id in resolved_ids or self.stop_event.is_set():
                if self.stop_event.is_set():
                    return ("abort",)
                continue
            dn = step_dns.get(spec.id)
            outcome_id = self._resolve_one(
                step, step_ctx, spec, dn, message, occurrences
            )
            if outcome_id is None:  # stopped while waiting
                return ("abort",)
            resolved.append((spec, dn, outcome_id))
            resolved_ids.add(spec.id)
            # Chain: this outcome's route targets a sibling decision
            # shape -> activate it (once).
            if dn is not None:
                target = dn.routes.get(outcome_id)
                tdn = dn_by_id.get(target)
                if tdn is not None and target not in activated:
                    activated.add(target)
                    if tdn.decision_id in fired and tdn.decision_id not in resolved_ids:
                        queue.append(fired[tdn.decision_id])
                    else:
                        step_ctx.log(
                            f"Chained decision for {tdn.decision_id!r} "
                            f"didn't fire this round — skipped"
                        )

        # 1+2. Route arbitration by per-edge priority (lower wins; ties
        # keep the old order: matched ops in creation order, then the
        # chosen outcomes' routes in resolution order). Ops default to
        # priority 10 and outcome edges to 20, so ops win unless the
        # user raises an edge above them.
        chosen_endpoints = {
            (dn.id, oid) for _spec, dn, oid in resolved if dn is not None
        }
        candidates = []  # (priority, tiebreak, tag, target, describe)
        order = 0
        for op in proto.ops_for_step(step.id):
            if op.target is None or not op.inputs:
                continue
            hits = [pair in chosen_endpoints for pair in op.inputs]
            matched = all(hits) if op.kind == "and" else any(hits)
            if matched:
                candidates.append(
                    (
                        op.priority,
                        order,
                        ("op", op.id),
                        op.target,
                        f"{op.kind.upper()} op "
                        f"({sum(hits)}/{len(op.inputs)} outcomes)",
                    )
                )
                order += 1
        for spec, dn, outcome_id in resolved:
            routes = dn.routes if dn else {}
            target = routes.get(outcome_id, spec.default_routes.get(outcome_id, NEXT))
            if target in dn_by_id or target == NEXT:
                continue  # chains were consumed during resolution
            outcome = spec.outcome_by_id(outcome_id)
            label = dn.label_for(outcome) if dn else outcome.label
            prio = dn.priority_for(outcome_id) if dn else 20
            tag = ("outcome", dn.id, outcome_id) if dn is not None else None
            candidates.append((prio, order, tag, target, f"outcome {label!r}"))
            order += 1
        if candidates:
            candidates.sort(key=lambda c: (c[0], c[1]))
            prio, _t, tag, target, desc = candidates[0]
            if len(candidates) > 1:
                losers = ", ".join(f"{c[4]} (p{c[0]})" for c in candidates[1:])
                step_ctx.log(
                    f"Route arbitration: {desc} (p{prio}) -> "
                    f"{proto.describe_target(target)} — beat {losers}"
                )
            else:
                step_ctx.log(f"{desc} -> {proto.describe_target(target)}")
            if tag is not None:
                self.signals.route_taken.emit(tag)
            return self._verdict_for(step, target, i)

        # 3. No decision redirected: the step's completion route.
        if step.next_target != NEXT:
            self.signals.route_taken.emit(("flow", step.id))
        return self._verdict_for(step, step.next_target, i)

    def _resolve_one(self, step, step_ctx, spec, dn, message, occurrences):
        """Resolve one decision (prompt or auto). Returns the outcome_id,
        or None when the run was stopped mid-prompt."""
        occurrences[(step.id, spec.id)] += 1
        seen = occurrences[(step.id, spec.id)]
        mode = dn.mode if dn else "prompt"
        n = dn.auto_after if dn else None
        if mode == "auto":
            auto, why = True, "auto mode"
        elif mode == "auto_first":
            # Auto-resolve the first N occurrences (silent retries),
            # then escalate to the user.
            auto = n is not None and seen <= n
            why = f"auto {seen}/{n} before prompting"
        else:
            auto = n is not None and seen > n
            why = f"auto after {n} prompts"
        if auto:
            outcome_id = (dn.auto_outcome if dn else None) or spec.default_outcome
            label = spec.outcome_by_id(outcome_id).label
            step_ctx.log(f"Decision {spec.title!r} -> {label} ({why})")
            self.signals.canvas_note.emit(
                dn.id if dn else step.id,
                f"auto → {label}"
                + (f"  ({seen}/{n})" if mode == "auto_first" and n else ""),
            )
        else:
            if mode == "auto_first" and n:
                label = spec.outcome_by_id(
                    (dn.auto_outcome if dn else None) or spec.default_outcome
                ).label
                note = f"Auto-answered {label!r} {n}× already — " f"your call now."
                message = f"{message}\n{note}" if message else note
            outcome_id = self._answer_for(step, spec, dn, message)
            if outcome_id is None:
                return None
            step_ctx.log(
                f"Decision {spec.title!r} -> "
                f"{spec.outcome_by_id(outcome_id).label} (user)"
            )
        self.signals.decision_resolved.emit(step.id, spec.id, outcome_id, auto)
        return outcome_id

    def _verdict_for(self, step, target, i):
        """("jump", idx, kind, group_id) | ("end", was_fallthrough) |
        ("abort",). kind: "next" (fall-through), "self" (retry), "step"
        (explicit step route), "group" (explicit group route — formal
        entry with hooks + repeats)."""
        proto = self.protocol
        n_leaves = len(proto.leaves())
        if target == SELF:
            return ("jump", i, "self", None)
        if target == END:
            return ("end", False)
        if target == ABORT:
            return ("abort",)
        if target == NEXT:
            return ("jump", i + 1, "next", None) if i + 1 < n_leaves else ("end", True)
        row = proto.row_by_id(target)
        idx = proto.leaf_index(target)
        if idx is None:
            self.signals.log.emit(
                f"[{step.name}] Route target missing — falling through " f"to next step"
            )
            return ("jump", i + 1, "next", None) if i + 1 < n_leaves else ("end", True)
        if row is not None and row.is_group:
            return ("jump", idx, "group", row.id)
        return ("jump", idx, "step", None)

    def _answer_for(self, step, spec, dn, message):
        """Hand a PendingDecision to the GUI thread and block (stop-aware)
        until it's answered. Returns the outcome_id, or None on stop."""
        routes = dn.routes if dn else {}
        options = []
        for outcome in spec.outcomes:
            target = routes.get(outcome.id, spec.default_routes.get(outcome.id, NEXT))
            label = dn.label_for(outcome) if dn else outcome.label
            options.append(
                (outcome, target, self.protocol.describe_target(target), label)
            )
        pending = PendingDecision(step, spec, dn, message, options)
        self.signals.decision_pending.emit(pending)
        while not pending.answered.wait(0.1):
            if self.stop_event.is_set():
                return None
        if pending.remember_auto:
            # "Don't ask again this run": stored on the placed shape —
            # minted next to the step if the user never placed one.
            if dn is None:
                dn = self.protocol.add_decision_node(
                    step.id, spec.id, (step.pos[0] + 60, step.pos[1] + 90)
                )
            dn.mode = "auto"
            dn.auto_outcome = pending.answer
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
                f"{getattr(step, 'name', '<protocol>')!r}: {e}"
            ) from e

    def _emit_terminal_signal(self):
        """Error > aborted > finished — same precedence as the real one."""
        if self._error is not None:
            self.signals.protocol_error.emit(str(self._error))
        elif self.stop_event.is_set():
            self.signals.protocol_aborted.emit()
        else:
            self.signals.protocol_finished.emit()
