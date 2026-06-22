"""Links executor lifecycle signals to a ProtocolStatusModel (issue #467).

A small HasTraits adapter owned by the composition root (the dock pane in
the full app; the demo window standalone). It owns the model, observes one
handler per ExecutorSignals event, and translates each into a single model
method call stamped with ``now``. No formatting, no widgets -- the view
binds to ``self.model`` separately.

ExecutorSignals is now a HasTraits firing Traits ``Event`` traits. These
handlers observe with the DEFAULT dispatch, so during a run they execute on
the executor's worker thread (the thread that set the event) -- that is fine
because they touch only the Qt-free ProtocolStatusModel. Widget-touching
observers live elsewhere (the dock pane) and use ``dispatch="ui"``.
"""

import json
import time

from traits.api import Any, Callable, HasTraits, Instance

from logger.logger_service import get_logger
from microdrop_application.menus import is_advanced_mode
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import (
    ELECTRODE_TO_CHANNEL_KEY, ELECTRODES_STATE_CHANGE,
    PROTOCOL_TREE_DISPLAY_STATE,
)
from pluggable_protocol_tree.models.display_state import ProtocolTreeDisplayMessage
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel
from pluggable_protocol_tree.services.phase_math import (
    duration_loop_parts, iter_phases,
)

logger = get_logger(__name__)


class ProtocolStatusController(HasTraits):
    #: The status model this controller drives. The view binds to it.
    model = Instance(ProtocolStatusModel, ())

    #: ExecutorSignals QObject (duck-typed; any object exposing the
    #: signals works -- keeps Qt types out of the signature and tests Qt-free).
    signals = Any()

    #: ProtocolExecutor -- needed to record the resume target for a seek.
    executor = Any()

    #: RowManager -- needed for the step count and next-step name.
    manager = Any()

    #: Monotonic clock source; overridable in tests.
    clock = Callable(time.monotonic)

    def traits_init(self):
        if self.executor is not None:
            self.signals = self.executor.signals
        self._connect()

    # --- wiring ---

    def _pairs(self):
        return (
            ("protocol_started", self._on_protocol_started),
            ("step_started", self._on_step_started),
            ("step_repetition", self._on_step_repetition),
            ("phase_started", self._on_phase_started),
            ("phase_extended", self._on_phase_extended),
            ("dyn_phase_started", self._on_dyn_phase_started),
            ("dyn_idle_entered", self._on_dyn_idle_entered),
            ("protocol_paused", self._on_paused),
            ("protocol_resumed", self._on_resumed),
            ("protocol_repetition_finished", self._on_repetition_finished),
            ("protocol_finished", self._on_stopped),
            ("protocol_aborted", self._on_stopped),
            ("protocol_error", self._on_error),
        )

    def _connect(self):
        if self.signals is None:
            return
        for name, handler in self._pairs():
            self.signals.observe(handler, name)

    def disconnect(self):
        if self.signals is None:
            return
        for name, handler in self._pairs():
            try:
                self.signals.observe(handler, name, remove=True)
            except (ValueError, TypeError):
                pass

    # --- handlers (executor event -> model) ---

    def _on_protocol_started(self, event):
        self.model.on_protocol_start(self.clock(), self._count_steps())

    def _on_step_started(self, event):
        # The executor reports one frame per repetition; collapse to distinct
        # steps so the status bar reads "Step 1/1" for a single 8x-repeated
        # step. The rep count is shown separately via step_repetition.
        row, frame_index, frame_total = event.new
        step_index = self._step_index_of(row.path)
        step_total = self._count_steps()
        self.model.on_step_start(
            self.clock(), step_index, step_total, tuple(row.path),
            row.name, self._next_name(row),
            frame_index=frame_index, frame_total=frame_total)
        logger.debug(
            f"status: step {step_index}/{step_total} @ {tuple(row.path)} "
            f"({row.name!r})")

    def _on_step_repetition(self, event):
        chain = event.new
        self.model.set_rep_chain(self._fmt_chain(chain))
        # Innermost rep entry is the step's own repetition (outermost-first).
        if chain:
            _name, idx, total = chain[-1]
            self.model.set_step_rep(idx, total)
        else:
            self.model.set_step_rep(0, 0)

    def _on_phase_started(self, event):
        phase_index, phase_total, phase_duration_s = event.new
        self.model.on_phase_start(
            self.clock(), phase_index, phase_total, phase_duration_s)

    def _on_phase_extended(self, event):
        self.model.on_phase_extended(event.new)

    def _on_dyn_phase_started(self, event):
        cycle_pos, cycle_len, phase_dwell = event.new
        self.model.on_dyn_phase(self.clock(), cycle_pos, cycle_len, phase_dwell)

    def _on_dyn_idle_entered(self, event):
        self.model.on_dyn_idle(self.clock(), int(event.new))

    def _on_paused(self, event):
        self.model.pause(self.clock())

    def _on_resumed(self, event):
        self.model.resume(self.clock())

    def _on_repetition_finished(self, event):
        completed, total = event.new
        self.model.on_repetition(completed, total)

    def _on_stopped(self, event):
        # Terminal events (finished / aborted) fire immediately after the
        # executor's on_post_protocol_end teardown, i.e. once the whole run
        # (all repeats) is done -- reset the trackers back to idle here.
        self.model.reset()

    def _on_error(self, event):
        self.model.reset()

    # --- helpers (need manager) ---

    def _distinct_steps(self):
        """Step rows in execution order with repetitions collapsed (one entry
        per row), so the status bar counts steps -- not per-rep frames."""
        seen = set()
        out = []
        for row in self.manager.iter_execution_steps():
            key = tuple(row.path)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    def _count_steps(self):
        try:
            return len(self._distinct_steps())
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
        """1-based position of step_path among the distinct steps, or 0 if
        absent. Distinct (not per-rep) so a repeated step keeps one index."""
        target = tuple(step_path)
        for i, row in enumerate(self._distinct_steps(), start=1):
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
    def _phases_for(row, n_repeats=None):
        """Materialized phase sequence for a row, mirroring the executor's
        iter_phases call (count/fixed steps). [] on failure. Duration-mode
        precise phases are deferred (#477). Pass ``n_repeats`` to override the
        row's route_repetitions (e.g. 1 for a single base loop)."""
        try:
            in_duration_mode = (
                bool(getattr(row, "repeat_duration_controls", False))
                and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
            )
            reps = (int(getattr(row, "route_repetitions", 1))
                    if n_repeats is None else int(n_repeats))
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
                n_repeats=reps,
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
        except Exception:
            return []

    def _phase_total_for(self, row):
        return max(1, len(self._phases_for(row)))

    def _base_phase_total_for(self, row):
        """Phase count for ONE route loop (n_repeats=1) -- the base loop a
        route-repeated step cycles through."""
        return max(1, len(self._phases_for(row, n_repeats=1)))

    def preview_phase(self, step_path, phase_index, preview):
        """Publish the selected phase's electrodes to the DV overlay (always)
        and to hardware (unless ``preview``) while paused. ``phase_index`` is
        0-based. Best-effort -- publish failures are logged, never raised."""
        row = self._row_at(step_path)
        if row is None:
            return
        try:
            mapping = self.manager.protocol_metadata.get(
                ELECTRODE_TO_CHANNEL_KEY, {})
        except Exception:
            mapping = {}
        if self.model.dyn_loop_active:
            # Dynamic duration step (#477): the unique navigable phases are the
            # UNIT CYCLE and the trailing cell is the idle phase (electrodes
            # off). Preview from the unit cycle, not the materialized phases.
            _ramp, unit_cycle, _ret = duration_loop_parts(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)))
            idle_idx = len(unit_cycle)
            electrodes = ([] if int(phase_index) >= idle_idx
                          else sorted(unit_cycle[int(phase_index)]))
            channels = sorted(mapping[e] for e in electrodes if e in mapping)
        else:
            phases = self._phases_for(row)
            if not phases:
                return
            idx = max(0, min(int(phase_index), len(phases) - 1))
            electrodes = sorted(phases[idx])
            channels = sorted(mapping[e] for e in electrodes if e in mapping)
        # Navigation happens while paused (mid-run), so the viewer must stay
        # editable only in Advanced Mode — same rule the run-time and
        # selection-driven publishes use (#434). Without this, stepping to the
        # next/prev phase relocked the viewer until the next cell edit.
        display_msg = ProtocolTreeDisplayMessage(
            electrodes=electrodes,
            routes=list(getattr(row, "routes", []) or []),
            step_id=getattr(row, "uuid", "") or "",
            step_label=f"Step {row.dotted_path()}",
            free_mode=False,
            editable=bool(is_advanced_mode()),
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
            logger.debug(f"seek_to: no row at {tuple(step_path)} -- ignored")
            return
        now = self.clock()
        step_idx = self._step_index_of(step_path)
        step_total = self._count_steps()
        phase_total = self._phase_total_for(row)
        if self.model.dyn_loop_active:
            # Mid-dynamic-loop: keep the live cycle_len+1 phase bar rather than
            # flipping to the materialized duration count (#477).
            phase_total = self.model.phase_total
        phase0 = max(0, min(int(phase_index), phase_total - 1))
        logger.debug(
            f"seek_to: step {step_idx}/{step_total} @ {tuple(step_path)} "
            f"phase={phase0}")

        if self.executor is not None:
            self.executor.seek(tuple(step_path), phase0)

        # Only re-seat the step (and reset its timer) when the step actually
        # changes; a phase-only nav within the same step keeps the step clock.
        if tuple(step_path) != self.model.current_step_path:
            self.model.seek_step(now, step_idx, step_total, tuple(step_path),
                                 row.name, self._next_name(row))
        self.model.seek_phase(
            now, phase0 + 1, phase_total, float(getattr(row, "duration_s", 0.0)))

    def _frame_index_for_rep(self, step_path, rep):
        """Execution-frame index of the ``rep``-th (1-based) occurrence of the
        step at ``step_path``, or None if absent."""
        target = tuple(step_path)
        seen = 0
        for i, (row, _chain) in enumerate(self.manager.iter_execution_frames()):
            if tuple(row.path) == target:
                seen += 1
                if seen == int(rep):
                    return i
        return None

    def seek_to_frame(self, step_path, frame_index):
        """Seek (while paused) to an exact execution frame -- used by the
        full-view step timeline, where each cell is one frame. The executor
        honours it on resume; the model's frame/step-rep are set optimistically
        so the view follows the drag immediately."""
        target = tuple(step_path)
        if self.executor is not None:
            self.executor.seek(target, 0, frame_index=int(frame_index))
        rep = 0
        total = 0
        for i, (row, _chain) in enumerate(self.manager.iter_execution_frames()):
            if tuple(row.path) == target:
                total += 1
                if i <= frame_index:
                    rep = total
        self.model.frame_index = int(frame_index) + 1
        self.model.set_step_rep(rep, total)
        self.model.set_rep_chain(
            self._fmt_chain([("", rep, total)]) if total > 1 else "")

    def seek_to_step_rep(self, step_path, rep, rep_total):
        """Seek (while paused) to repetition ``rep`` (1-based) of the step at
        ``step_path`` -- a specific execution frame. The executor honours it on
        resume; the model reflects the chosen rep optimistically. No-op if the
        rep frame is absent."""
        frame_index = self._frame_index_for_rep(step_path, rep)
        if frame_index is None:
            return
        if self.executor is not None:
            self.executor.seek(tuple(step_path), 0, frame_index=frame_index)
        self.model.set_step_rep(int(rep), int(rep_total))
        self.model.set_rep_chain(self._fmt_chain([("", int(rep), int(rep_total))]))

    @staticmethod
    def _fmt_chain(rep_chain):
        # Compact "Step Rep i/n" (per repeating level) -- the old
        # "rep i/n of 'name'" overflowed the fixed-width status label and
        # double-counted the step itself in the count beside it.
        if not rep_chain:
            return ""
        return " · ".join(
            f"Step Rep {idx}/{total}" for _name, idx, total in rep_chain
        )
