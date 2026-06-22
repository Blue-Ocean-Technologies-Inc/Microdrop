"""Live execution position + pending seek for a run (issue #471).

A single Qt-free model owning where the executor is in the protocol — which
step, which phase — plus any pending mid-run seek the operator requested while
paused. The executor writes the step position as it walks frames; the routes
handler writes the phase position as it runs phases and consults the cursor at
its pause checkpoint. The pure decision rules live in ``execution.seek``; the
cursor holds the state and delegates to them, so it stays unit-testable with no
threads or Qt.
"""

from traits.api import Any, HasTraits, Int

from pluggable_protocol_tree.execution.seek import resolve_seek, seek_decision


class ExecutionCursor(HasTraits):
    #: Current step's path (tuple) — set by the executor as it enters each frame.
    step_path = Any(None)
    #: 0-based current phase within the step; also the re-entry start phase when
    #: the executor redirects to a step after a seek.
    phase_index = Int(0)
    #: Total phases in the current step (set by the routes handler; 0 if unknown).
    phase_total = Int(0)
    #: Index of the current frame in execution order — set by the executor as it
    #: walks frames. Distinguishes repetitions of the same step (same path).
    frame_index = Int(0)
    #: Pending seek target (step_path, phase_index) or None. Set by the executor's
    #: seek() (GUI thread, while paused); read + cleared on resume.
    resume_target = Any(None)
    #: Optional exact target frame for a step-rep seek; None for a path seek.
    resume_frame = Any(None)

    def request_seek(self, step_path, phase_index, frame_index=None):
        """Record a pending seek to ``(step_path, phase_index)`` (0-based phase).
        Pass ``frame_index`` to target a specific repetition (execution frame)
        of the step rather than its first occurrence."""
        self.resume_target = (tuple(step_path), int(phase_index))
        self.resume_frame = None if frame_index is None else int(frame_index)

    def clear_seek(self):
        self.resume_target = None
        self.resume_frame = None

    def enter_step(self, step_path, phase_index=0, frame_index=None):
        """Executor: mark the live step position when entering a frame."""
        self.step_path = tuple(step_path)
        self.phase_index = int(phase_index)
        self.phase_total = 0
        if frame_index is not None:
            self.frame_index = int(frame_index)

    def decision_at_phase(self, current_phase_index):
        """Routes handler, at a phase pause checkpoint on resume: returns
        ``("continue", phase)`` / ``("jump", phase)`` (same step) /
        ``("abort", phase)`` (different step or repetition frame)."""
        return seek_decision(self.resume_target, self.step_path, current_phase_index,
                             target_frame=self.resume_frame,
                             current_frame_index=self.frame_index)

    def frame_for_seek(self, frame_paths):
        """Executor: resolve a pending seek to ``(frame_index, phase)`` or None."""
        return resolve_seek(frame_paths, self.resume_target,
                            target_frame=self.resume_frame)
