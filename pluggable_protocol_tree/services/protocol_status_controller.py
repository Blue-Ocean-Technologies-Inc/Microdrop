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


class ProtocolStatusController(HasTraits):
    #: The status model this controller drives. The view binds to it.
    model = Instance(ProtocolStatusModel, ())

    #: ExecutorSignals QObject (duck-typed; any object exposing the
    #: signals works -- keeps Qt types out of the signature and tests Qt-free).
    qsignals = Any()

    #: RowManager -- needed for the step count and next-step name.
    manager = Any()

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
        self.model.stop(self.clock())

    def _on_error(self, _msg):
        self.model.stop(self.clock())

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

    @staticmethod
    def _fmt_chain(rep_chain):
        if not rep_chain:
            return ""
        return " · ".join(
            f"rep {idx}/{total} of '{name}'" for name, idx, total in rep_chain
        )
