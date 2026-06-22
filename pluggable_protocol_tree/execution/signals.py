"""Traits event carrier for the executor's UI-facing signals.

A plain ``HasTraits`` whose ``Event`` traits stand in for the old Qt
signals: emitting becomes *setting* the trait, and consumers *observe* it.
The set value is the payload, read by observers as ``event.new``.

The executor runs on a worker thread, so it sets these events off the GUI
thread. Consumers that touch widgets observe with ``dispatch="ui"`` so
Traits marshals their handler onto the GUI thread (the dock pane does
this); consumers that only touch Qt-free models / do I/O observe with the
default dispatch and run on the setting thread.

UI consumers observe directly:
    executor.signals.observe(handler, "step_started", dispatch="ui")
    # handler(event): row, idx, total = event.new
"""

from traits.api import Event, HasTraits


class ExecutorSignals(HasTraits):
    # Lifecycle
    protocol_started   = Event()
    protocol_paused    = Event()
    protocol_resumed   = Event()
    protocol_finished  = Event()            # ran to completion
    protocol_aborted   = Event()            # user pressed Stop
    protocol_error     = Event()            # payload: str message
    # Pre-protocol settle/wait phase: set with the total wait in ms once
    # the on_pre_protocol_start hooks' contributions are summed, then again
    # when the wait ends. Drives the loading screen.
    protocol_wait_started  = Event()        # payload: int ms
    protocol_wait_finished = Event()

    # Per-step. step_started carries the executor's AUTHORITATIVE 1-based
    # position so the status model can SET (never increment) its step index —
    # robust across a mid-run seek (issue #471).
    step_started       = Event()            # payload: (row, step_index, step_total)
    step_finished      = Event()            # payload: row
    # Tuple of (group_name, rep_idx_1based, rep_total) entries describing
    # the active rep context for the current step (outermost-first).
    # Empty tuple means "no repeating ancestor". Set just before each
    # step_started so UI labels can update in lockstep.
    step_repetition    = Event()            # payload: rep_chain tuple
    # Whole-protocol repetition progress. Set by the executor after each
    # repetition finishes so the UI can update its "rep x/y" label — the
    # executor owns the repeat loop, the view only reflects it.
    protocol_repetition_finished = Event()  # payload: (completed, total)
    # Per-phase. RoutesHandler sets this before publishing each phase so the
    # UI can update Phase x/y and reset its elapsed-time clock without
    # waiting for the hardware ack.
    phase_started      = Event()            # payload: (phase_index, phase_total, phase_duration_s)
    # Extra dwell (seconds) granted to the CURRENT phase via
    # StepContext.add_time_buffer_to_current_phase — e.g. volume threshold
    # holding the phase open for more wetting time. The status bar grows
    # the phase's target time by this amount so "elapsed / target" stays
    # honest while the phase is held.
    phase_extended     = Event()            # payload: extra_s
    # Dynamic duration loop (#477).
    #: (cycle_pos 1-based, cycle_len, phase_dwell_s) — a unique phase is active.
    dyn_phase_started  = Event()
    #: cycle_len — the loop has entered its idle (electrodes-off) phase.
    dyn_idle_entered   = Event()
