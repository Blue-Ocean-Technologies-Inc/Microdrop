"""HasTraits model for the protocol status bar (issue #467).

Holds the observable counters / names and three ScopeStopwatch clocks
(protocol / step / phase), and encapsulates the timing *rules* (a new step
resets the phase clock; pause freezes active but not elapsed; ...). Pure:
no Qt, no threads, no direct clock calls -- every timing method takes
``now`` so the model is unit-testable with a fake clock.

The view binds to the observable traits (discrete updates) and polls the
clocks for the continuously-changing time readouts. See
ProtocolStatusController for the executor-signal -> model wiring.
"""

from traits.api import Bool, Float, HasTraits, Instance, Int, Str

from pluggable_protocol_tree.models.stopwatch import ScopeStopwatch


class ProtocolStatusModel(HasTraits):
    # --- counters ---
    step_index = Int(0)
    step_total = Int(0)
    phase_index = Int(0)
    phase_total = Int(0)
    repeats_completed = Int(0)
    repeats_total = Int(1)

    # --- names / labels ---
    recent_step_name = Str("-")
    next_step_name = Str("-")
    rep_chain_label = Str("")

    # --- phase target (for the "elapsed / target" readout) ---
    phase_target_s = Float(0.0)

    # --- run state ---
    running = Bool(False)
    paused = Bool(False)

    # --- clocks (plain helpers; default-constructed per model) ---
    protocol_clock = Instance(ScopeStopwatch, ())
    step_clock = Instance(ScopeStopwatch, ())
    phase_clock = Instance(ScopeStopwatch, ())

    # --- rule methods ---

    def reset(self):
        """Return to idle: zero counters/names and all three clocks.

        Used both at the start of a run (on_protocol_start) and as the
        post-protocol teardown (the controller calls this on the terminal
        signals that fire right after the executor's on_post_protocol_end).
        Clocks are zeroed BEFORE flipping ``running`` so the view's
        running->False refresh paints 0.0, not the final frozen time."""
        self.protocol_clock = ScopeStopwatch()
        self.step_clock = ScopeStopwatch()
        self.phase_clock = ScopeStopwatch()
        self.trait_set(
            step_index=0, step_total=0, phase_index=0, phase_total=0,
            repeats_completed=0, repeats_total=1,
            recent_step_name="-", next_step_name="-", rep_chain_label="",
            phase_target_s=0.0, running=False, paused=False,
        )

    def on_protocol_start(self, now, step_total):
        self.reset()
        self.step_total = int(step_total)
        self.running = True
        self.protocol_clock.start(now)

    def on_step_start(self, now, recent_name, next_name):
        self.step_index += 1
        self.recent_step_name = recent_name
        self.next_step_name = next_name
        self.phase_index = 0
        self.phase_total = 0
        self.phase_target_s = 0.0
        self.step_clock.start(now)
        self.phase_clock = ScopeStopwatch()      # fresh, unstarted
        if self.paused:                          # started mid-pause: keep frozen
            self.step_clock.pause(now)

    def on_phase_start(self, now, phase_index, phase_total, phase_target_s):
        self.phase_index = int(phase_index)
        self.phase_total = int(phase_total)
        try:
            self.phase_target_s = float(phase_target_s)
        except (TypeError, ValueError):
            self.phase_target_s = 0.0
        self.phase_clock.start(now)
        if self.paused:
            self.phase_clock.pause(now)

    def seek_step(self, now, step_index, recent_name, next_name):
        """Navigate to an arbitrary step while paused: SET the counter (not
        increment), reset the phase scope, and reset the step timer. Seek only
        happens while paused, so the fresh step clock is started then immediately
        stopped so both elapsed and active read 0 until resume (which re-starts
        the clock from that moment)."""
        self.step_index = int(step_index)
        self.recent_step_name = recent_name
        self.next_step_name = next_name
        self.phase_index = 0
        self.phase_total = 0
        self.phase_target_s = 0.0
        self.step_clock = ScopeStopwatch()
        self.step_clock.start(now)
        self.step_clock.stop(now)                # freeze elapsed at 0 while paused
        self.phase_clock = ScopeStopwatch()      # fresh, unstarted

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
        self.paused = True
        self.protocol_clock.pause(now)
        self.step_clock.pause(now)
        self.phase_clock.pause(now)

    def resume(self, now):
        self.paused = False
        self.protocol_clock.resume(now)
        # Clocks that were stopped by seek (elapsed_anchor is None) need a
        # fresh start rather than a resume so they begin ticking from now.
        for clock_attr in ("step_clock", "phase_clock"):
            clock = getattr(self, clock_attr)
            if clock._elapsed_anchor is None and clock._elapsed_accum == 0.0:
                clock.start(now)
            else:
                clock.resume(now)

    def on_repetition(self, completed, total):
        self.repeats_completed = int(completed)
        self.repeats_total = int(total)

    def set_rep_chain(self, label):
        self.rep_chain_label = label
