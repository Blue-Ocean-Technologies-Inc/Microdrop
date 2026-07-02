"""HasTraits model for the protocol status bar (issue #467).

Holds the observable counters / names and three ScopeStopwatch clocks
(protocol / step / phase), and encapsulates the timing *rules* (a new step
resets the phase clock; pause freezes active but not elapsed; ...). Pure:
no Qt, no direct clock calls -- every timing method takes ``now`` so the
model is unit-testable with a fake clock. NOT thread-free: the executor's
worker threads drive the freeze transitions (pause/resume, ack-wait
bracketing) and the step/phase starts concurrently, so every mutation of
the clocks or the freeze state (``paused`` / ``_wait_depth``) happens under
``_freeze_lock``.

The view binds to the observable traits (discrete updates) and polls the
clocks for the continuously-changing time readouts. See
ProtocolStatusController for the executor-signal -> model wiring.
"""

import threading

from traits.api import Any, Bool, Float, HasTraits, Instance, Int, Str

from pluggable_protocol_tree.models.stopwatch import ScopeStopwatch


class ProtocolStatusModel(HasTraits):
    # --- counters ---
    step_index = Int(0)
    step_total = Int(0)
    phase_index = Int(0)
    phase_total = Int(0)
    repeats_completed = Int(0)
    repeats_total = Int(1)
    # Per-rep execution-frame position (reps expanded), distinct from the
    # collapsed step_index/step_total above. Drives the timeline's "show full"
    # step view, which lays out one cell per frame.
    frame_index = Int(0)
    frame_total = Int(0)
    # Current step's own repetition (1-based) and its total, from the innermost
    # entry of the executor's rep_chain. 0 when the step does not repeat.
    step_rep_index = Int(0)
    step_rep_total = Int(0)

    # --- current step identity (single source of truth) ---
    # Path tuple of the step the run is on, SET from the executor's
    # step_started and from a seek. The view observes this to drive the tree
    # highlight + the nav baseline; None when idle.
    current_step_path = Any(None)

    # --- names / labels ---
    recent_step_name = Str("-")
    next_step_name = Str("-")
    rep_chain_label = Str("")

    # --- phase target (for the "elapsed / target" readout) ---
    phase_target_s = Float(0.0)

    # --- run state ---
    running = Bool(False)
    paused = Bool(False)
    # True while a dynamic duration-mode step is parked in its idle phase
    # (the trailing dark-yellow cell). Drives the leaving-idle warning (#477).
    dyn_idle = Bool(False)
    # True while the current step is mid-dynamic-duration-loop (either an
    # active dynamic phase or the idle cell). Lets the GUI seek/preview/paint
    # paths tell they are operating on a dynamic step so they keep the live
    # cycle_len+1 phase bar, preview the unit cycle (idle -> electrodes off),
    # and gate the idle-tint correctly (#477).
    dyn_loop_active = Bool(False)

    # --- clocks (plain helpers; default-constructed per model) ---
    protocol_clock = Instance(ScopeStopwatch, ())
    step_clock = Instance(ScopeStopwatch, ())
    phase_clock = Instance(ScopeStopwatch, ())

    # Guards the freeze-state transitions (paused / _wait_depth) since the
    # executor's worker threads drive them concurrently. Mirrors the plain
    # lock StepContext keeps for its phase-buffer coordination state.
    _freeze_lock = Instance(threading.Lock)

    # Nesting depth of in-progress acknowledgement waits (ctx.wait_for). An
    # ack-wait is a pause in the protocol AS FAR AS TIMING GOES, so the active
    # clocks freeze while depth > 0 -- but WITHOUT entering the operator-Paused
    # state (``paused`` stays False, no pause_event, no "Paused" UI). Ref-counted
    # because parallel-bucket handlers (RoutesHandler + VolumeThresholdHandler)
    # can each be inside a wait_for at the same time, on different worker threads.
    _wait_depth = Int(0)

    def __freeze_lock_default(self):
        return threading.Lock()

    # --- freeze helpers (shared by operator-pause AND ack-wait) ---

    def _clocks_should_run(self):
        """The active clocks tick only when neither the operator has paused
        NOR an acknowledgement wait is in flight."""
        return not self.paused and self._wait_depth == 0

    def _freeze_clocks(self, now):
        self.protocol_clock.pause(now)
        self.step_clock.pause(now)
        self.phase_clock.pause(now)

    def _thaw_clocks(self, now, restart_seek_stopped=False):
        self.protocol_clock.resume(now)
        # Clocks that were stopped by seek need a fresh start rather than a
        # resume so they begin ticking from now -- but ONLY on an operator
        # resume. An exit_ack_wait thaw must NOT restart them: after a paused
        # seek the sought-to step has not begun executing, so its clocks stay
        # at 0 until step_started re-seats them.
        for clock_attr in ("step_clock", "phase_clock"):
            clock = getattr(self, clock_attr)
            if restart_seek_stopped and clock.is_stopped_at_zero():
                clock.start(now)
            else:
                clock.resume(now)

    def _apply_freeze(self, now, was_running, restart_seek_stopped=False):
        """Freeze or thaw the active clocks to match the current combined state,
        given whether they WERE running before the state change."""
        now_running = self._clocks_should_run()
        if was_running and not now_running:
            self._freeze_clocks(now)
        elif not was_running and now_running:
            self._thaw_clocks(now, restart_seek_stopped)

    # --- rule methods ---

    def reset(self):
        """Return to idle: zero counters/names and all three clocks.

        Used both at the start of a run (on_protocol_start) and as the
        post-protocol teardown (the controller calls this on the terminal
        signals that fire right after the executor's on_post_protocol_end).
        Clocks are zeroed BEFORE flipping ``running`` so the view's
        running->False refresh paints 0.0, not the final frozen time."""
        # The clock swap, wait-depth zeroing and paused clearing must be ONE
        # atomic freeze-state transition: an exit_ack_wait landing between
        # them on a worker thread would see stale depth/paused against the
        # fresh clocks and start them, leaving the idle view ticking.
        with self._freeze_lock:
            self.protocol_clock = ScopeStopwatch()
            self.step_clock = ScopeStopwatch()
            self.phase_clock = ScopeStopwatch()
            self._wait_depth = 0
            self.paused = False
        self.current_step_path = None
        self.trait_set(
            step_index=0, step_total=0, phase_index=0, phase_total=0,
            repeats_completed=0, repeats_total=1,
            frame_index=0, frame_total=0, step_rep_index=0, step_rep_total=0,
            recent_step_name="-", next_step_name="-", rep_chain_label="",
            phase_target_s=0.0, running=False, dyn_idle=False,
            dyn_loop_active=False,
        )

    def on_protocol_start(self, now, step_total):
        self.reset()
        self.step_total = int(step_total)
        self.running = True
        self.protocol_clock.start(now)

    def on_step_start(self, now, step_index, step_total, step_path,
                      recent_name, next_name, frame_index=0, frame_total=0):
        # SET the position from the executor's authoritative report (never
        # increment) so a mid-run seek can't drift the counter (issue #471).
        self.step_index = int(step_index)
        self.step_total = int(step_total)
        self.frame_index = int(frame_index)
        self.frame_total = int(frame_total)
        self.current_step_path = tuple(step_path) if step_path is not None else None
        self.recent_step_name = recent_name
        self.next_step_name = next_name
        self.phase_index = 0
        self.phase_total = 0
        self.phase_target_s = 0.0
        # The start + freeze-check must be one atomic freeze-state read: an
        # exit_ack_wait thawing on another worker thread in between would let
        # the stale "frozen" verdict pause the clock with no thaw ever coming.
        with self._freeze_lock:
            self.step_clock.start(now)
            self.phase_clock = ScopeStopwatch()  # fresh, unstarted
            if not self._clocks_should_run():    # started mid-freeze: keep frozen
                self.step_clock.pause(now)
        # Advancing to the next step clears any stale dynamic-loop state from
        # the previous step (fixes BUG #2 — stale dyn_idle/dyn_loop_active).
        self.dyn_idle = False
        self.dyn_loop_active = False

    def on_phase_start(self, now, phase_index, phase_total, phase_target_s):
        self.phase_index = int(phase_index)
        self.phase_total = int(phase_total)
        try:
            self.phase_target_s = float(phase_target_s)
        except (TypeError, ValueError):
            self.phase_target_s = 0.0
        # Atomic with the freeze state for the same reason as on_step_start.
        with self._freeze_lock:
            self.phase_clock.start(now)
            if not self._clocks_should_run():
                self.phase_clock.pause(now)
        # A NORMAL phase clears the dynamic-loop flags; the dyn_* methods below
        # call this first and re-set them afterward (#477).
        self.dyn_idle = False
        self.dyn_loop_active = False

    def on_dyn_phase(self, now, cycle_pos, cycle_len, phase_target_s):
        """Dynamic duration loop: park the bar on unique phase ``cycle_pos``
        (1-based) of a ``cycle_len``-phase loop. phase_total carries the extra
        trailing idle cell so the bar renders cycle_len + 1 cells (#477)."""
        self.on_phase_start(now, cycle_pos, cycle_len + 1, phase_target_s)
        # on_phase_start clears the flags; set the dynamic state afterward.
        self.dyn_idle = False
        self.dyn_loop_active = True

    def on_dyn_idle(self, now, cycle_len):
        """Dynamic duration loop: park on the trailing idle cell (electrodes
        off). The idle cell is the last of cycle_len + 1 cells (#477)."""
        self.on_phase_start(now, cycle_len + 1, cycle_len + 1, 0.0)
        # on_phase_start clears the flags; set the dynamic/idle state afterward.
        self.dyn_idle = True
        self.dyn_loop_active = True

    def seek_step(self, now, step_index, step_total, step_path,
                  recent_name, next_name):
        """Navigate to an arbitrary step while paused: SET the position, reset
        the phase scope, and reset the step timer. Same SET semantics as
        on_step_start so the executor's report on resume is idempotent. Seek
        only happens while paused, so the fresh step clock is started then
        immediately stopped (elapsed + active read 0 until resume re-starts
        it)."""
        self.step_index = int(step_index)
        self.step_total = int(step_total)
        self.current_step_path = tuple(step_path) if step_path is not None else None
        self.recent_step_name = recent_name
        self.next_step_name = next_name
        self.phase_index = 0
        self.phase_total = 0
        self.phase_target_s = 0.0
        self.step_clock = ScopeStopwatch()
        self.step_clock.start(now)
        self.step_clock.stop(now)                # freeze elapsed at 0 while paused
        self.phase_clock = ScopeStopwatch()      # fresh, unstarted
        # Navigating to a different step drops any stale dynamic-loop state.
        self.dyn_idle = False
        self.dyn_loop_active = False

    def seek_phase(self, now, phase_index, phase_total, phase_target_s):
        """Navigate to an arbitrary phase while paused: SET the counters and
        reset the phase timer (elapsed AND active), frozen while paused. On
        resume the clock starts fresh from that moment."""
        self.phase_index = int(phase_index)
        self.phase_total = int(phase_total)
        try:
            self.phase_target_s = float(phase_target_s)
        except (TypeError, ValueError):
            self.phase_target_s = 0.0
        self.phase_clock = ScopeStopwatch()
        self.phase_clock.start(now)
        self.phase_clock.stop(now)               # freeze elapsed at 0 while paused

    def on_phase_extended(self, extra_s):
        try:
            self.phase_target_s += float(extra_s)
        except (TypeError, ValueError):
            pass

    def pause(self, now):
        with self._freeze_lock:
            was_running = self._clocks_should_run()
            self.paused = True
            self._apply_freeze(now, was_running)

    def resume(self, now):
        with self._freeze_lock:
            was_running = self._clocks_should_run()
            self.paused = False
            self._apply_freeze(now, was_running, restart_seek_stopped=True)

    def enter_ack_wait(self, now):
        """A ctx.wait_for started blocking: freeze the active clocks (unless
        already frozen by pause or another in-flight wait). Balanced by
        :meth:`exit_ack_wait`."""
        with self._freeze_lock:
            was_running = self._clocks_should_run()
            self._wait_depth += 1
            self._apply_freeze(now, was_running)

    def exit_ack_wait(self, now):
        """A ctx.wait_for stopped blocking: thaw the active clocks once the last
        wait ends AND the operator has not paused."""
        with self._freeze_lock:
            was_running = self._clocks_should_run()
            if self._wait_depth > 0:
                self._wait_depth -= 1
            self._apply_freeze(now, was_running)

    def on_repetition(self, completed, total):
        self.repeats_completed = int(completed)
        self.repeats_total = int(total)

    def set_rep_chain(self, label):
        self.rep_chain_label = label

    def set_step_rep(self, index, total):
        self.step_rep_index = int(index)
        self.step_rep_total = int(total)
