"""Links executor lifecycle signals to a ProtocolStatusModel (issue #467).

A small HasTraits adapter owned by the composition root (the dock pane in
the full app; the demo window standalone). It owns the model, connects one
slot per ExecutorSignals signal, and translates each into a single model
method call stamped with ``now``. No formatting, no widgets -- the view
binds to ``self.model`` separately.

Invariant: ExecutorSignals is a QObject delivering via queued connections,
so these slots run on the GUI thread; the model is therefore mutated only
on the GUI thread and its observers may drive widgets directly.
"""

import time

from traits.api import Any, Callable, HasTraits, Instance

from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel
from pluggable_protocol_tree.services.phase_math import iter_phases


class ProtocolStatusController(HasTraits):
    #: The status model this controller drives. The view binds to it.
    model = Instance(ProtocolStatusModel, ())

    #: ExecutorSignals QObject (duck-typed; any object exposing the
    #: signals works -- keeps Qt types out of the signature and tests Qt-free).
    qsignals = Any()

    #: RowManager -- needed for the step count and next-step name.
    manager = Any()

    #: ProtocolExecutor -- needed to record the resume target for a seek.
    executor = Any()

    #: Monotonic clock source; overridable in tests.
    clock = Callable(time.monotonic)

    def traits_init(self):
        self._connect()

    # --- wiring ---

    def _pairs(self):
        s = self.qsignals
        return (
            (s.protocol_started, self._on_protocol_started),
            (s.step_started, self._on_step_started),
            (s.step_repetition, self._on_step_repetition),
            (s.phase_started, self._on_phase_started),
            (s.phase_extended, self._on_phase_extended),
            (s.protocol_paused, self._on_paused),
            (s.protocol_resumed, self._on_resumed),
            (s.protocol_repetition_finished, self._on_repetition_finished),
            (s.protocol_finished, self._on_stopped),
            (s.protocol_aborted, self._on_stopped),
            (s.protocol_error, self._on_error),
        )

    def _connect(self):
        if self.qsignals is None:
            return
        for sig, slot in self._pairs():
            sig.connect(slot)

    def disconnect(self):
        if self.qsignals is None:
            return
        for sig, slot in self._pairs():
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    # --- slots (executor signal -> model) ---

    def _on_protocol_started(self):
        self.model.on_protocol_start(self.clock(), self._count_steps())

    def _on_step_started(self, row):
        self.model.on_step_start(self.clock(), row.name, self._next_name(row))

    def _on_step_repetition(self, rep_chain):
        self.model.set_rep_chain(self._fmt_chain(rep_chain))

    def _on_phase_started(self, phase_index, phase_total, phase_duration_s):
        self.model.on_phase_start(
            self.clock(), phase_index, phase_total, phase_duration_s)

    def _on_phase_extended(self, extra_s):
        self.model.on_phase_extended(extra_s)

    def _on_paused(self):
        self.model.pause(self.clock())

    def _on_resumed(self):
        self.model.resume(self.clock())

    def _on_repetition_finished(self, completed, total):
        self.model.on_repetition(completed, total)

    def _on_stopped(self):
        # Terminal signals (finished / aborted) fire immediately after the
        # executor's on_post_protocol_end teardown, i.e. once the whole run
        # (all repeats) is done -- reset the trackers back to idle here.
        self.model.reset()

    def _on_error(self, _msg):
        self.model.reset()

    # --- helpers (need manager) ---

    def _count_steps(self):
        try:
            return sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            return 0

    def _next_name(self, current):
        steps = self.manager.iter_execution_steps()
        cur_path = tuple(current.path)
        for row in steps:
            if tuple(row.path) == cur_path:
                nxt = next(steps, None)
                return nxt.name if nxt is not None else "-"
        return "-"

    def _step_index_of(self, step_path):
        """1-based position of step_path in execution order, or 0 if absent."""
        target = tuple(step_path)
        for i, row in enumerate(self.manager.iter_execution_steps(), start=1):
            if tuple(row.path) == target:
                return i
        return 0

    def _row_at(self, step_path):
        target = tuple(step_path)
        for row in self.manager.iter_execution_steps():
            if tuple(row.path) == target:
                return row
        return None

    @staticmethod
    def _phase_total_for(row):
        """Materialized phase count for a row (count/fixed steps). Duration-mode
        precise phases are deferred (#477); fall back to 1 on any failure."""
        try:
            phases = list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=0.0,
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "route_repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
            return max(1, len(phases))
        except Exception:
            return 1

    def seek_to(self, step_path, phase_index):
        """Navigate (while paused) to ``(step_path, phase_index)`` -- 0-based
        phase. Records the resume target on the executor and updates the model
        so the counters/timers follow. No-op if the path is gone."""
        row = self._row_at(step_path)
        if row is None:
            return
        now = self.clock()
        step_idx = self._step_index_of(step_path)
        phase_total = self._phase_total_for(row)
        phase0 = max(0, min(int(phase_index), phase_total - 1))

        if self.executor is not None:
            self.executor.seek(tuple(step_path), phase0)

        if step_idx != self.model.step_index:
            self.model.seek_step(now, step_idx, row.name, self._next_name(row))
        self.model.seek_phase(
            now, phase0 + 1, phase_total, float(getattr(row, "duration_s", 0.0)))

    @staticmethod
    def _fmt_chain(rep_chain):
        if not rep_chain:
            return ""
        return " · ".join(
            f"rep {idx}/{total} of '{name}'" for name, idx, total in rep_chain
        )
