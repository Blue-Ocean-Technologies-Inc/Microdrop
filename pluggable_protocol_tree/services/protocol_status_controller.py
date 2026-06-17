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

import json
import time

from traits.api import Any, Callable, HasTraits, Instance

from logger.logger_service import get_logger
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODE_TO_CHANNEL_KEY, ELECTRODES_STATE_CHANGE,
    PROTOCOL_TREE_DISPLAY_STATE,
)
from pluggable_protocol_tree.models.display_state import ProtocolTreeDisplayMessage
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel
from pluggable_protocol_tree.services.phase_math import iter_phases

logger = get_logger(__name__)


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
    def _phases_for(row):
        """Materialized phase sequence for a row, mirroring the executor's
        iter_phases call (count/fixed steps). [] on failure. Duration-mode
        precise phases are deferred (#477)."""
        try:
            in_duration_mode = (
                bool(getattr(row, "repeat_duration_controls", False))
                and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
            )
            return list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=(float(getattr(row, "repeat_duration", 0.0))
                                   if in_duration_mode else 0.0),
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "route_repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
        except Exception:
            return []

    def _phase_total_for(self, row):
        return max(1, len(self._phases_for(row)))

    def preview_phase(self, step_path, phase_index, preview):
        """Publish the selected phase's electrodes to the DV overlay (always)
        and to hardware (unless ``preview``) while paused. ``phase_index`` is
        0-based. Best-effort -- publish failures are logged, never raised."""
        row = self._row_at(step_path)
        if row is None:
            return
        phases = self._phases_for(row)
        if not phases:
            return
        idx = max(0, min(int(phase_index), len(phases) - 1))
        try:
            mapping = self.manager.protocol_metadata.get(
                ELECTRODE_TO_CHANNEL_KEY, {})
        except Exception:
            mapping = {}
        electrodes = sorted(phases[idx])
        channels = sorted(mapping[e] for e in electrodes if e in mapping)
        display_msg = ProtocolTreeDisplayMessage(
            electrodes=electrodes,
            routes=list(getattr(row, "routes", []) or []),
            step_id=getattr(row, "uuid", "") or "",
            step_label=f"Step {row.dotted_path()}",
            free_mode=False,
            editable=False,
        )
        try:
            publish_message(topic=PROTOCOL_TREE_DISPLAY_STATE,
                            message=display_msg.serialize())
        except Exception as e:
            logger.warning(f"seek display publish failed: {e}")
        if not preview:
            try:
                publish_message(
                    topic=ELECTRODES_STATE_CHANGE,
                    message=json.dumps(
                        {"electrodes": electrodes, "channels": channels}))
            except Exception as e:
                logger.warning(f"seek hardware publish failed: {e}")

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
