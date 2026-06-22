"""Pure (Qt-free, thread-free) seek resolution for mid-run navigation (#471).

A seek target is ``(step_path, phase_index)``. ``resolve_seek`` maps it to a
frame index in execution order; ``seek_decision`` tells a phase loop what to do
on resume given the current position. Both are pure so they unit-test without
the executor, threads, or Qt.
"""

from typing import List, Optional, Tuple

Path = Tuple[int, ...]


def resolve_seek(frame_paths: List[Path], target,
                 target_frame: Optional[int] = None) -> Optional[Tuple[int, int]]:
    """Return ``(frame_index, phase_index)`` for ``target`` ((path, phase)), or
    None if target is None or its path is not among ``frame_paths``. The phase
    index is clamped to >= 0 (upper clamping is the phase loop's job — it knows
    the materialized phase count).

    ``target_frame`` (set for a step-rep seek) names an exact execution frame:
    when given and in range it is used directly, so a specific repetition of a
    step (same path, different frame) can be targeted. Without it, the first
    frame matching the path is returned (the path-based behaviour)."""
    if target is None:
        return None
    target_path, target_phase = target
    if target_frame is not None:
        if 0 <= target_frame < len(frame_paths):
            return int(target_frame), max(0, int(target_phase))
        return None
    target_path = tuple(target_path)
    for i, path in enumerate(frame_paths):
        if tuple(path) == target_path:
            return i, max(0, int(target_phase))
    return None


def seek_decision(resume_target, current_path: Path, current_phase_index: int,
                  target_frame: Optional[int] = None,
                  current_frame_index: Optional[int] = None):
    """Decide what a phase loop should do at its pause checkpoint on resume.

    Returns one of:
      ``("continue", current_phase_index)`` — no seek pending,
      ``("jump", target_phase)``           — same step, jump the phase loop,
      ``("abort", target_phase)``          — different step (or a different
                                             repetition frame), unwind to the
                                             frame walk and re-enter the target.
    """
    if resume_target is None:
        return ("continue", current_phase_index)
    target_path, target_phase = resume_target
    # An exact-frame (step-rep) seek to a different frame must abort even within
    # the same path, so the frame walk re-enters the chosen repetition.
    if (target_frame is not None and current_frame_index is not None
            and target_frame != current_frame_index):
        return ("abort", int(target_phase))
    if tuple(target_path) == tuple(current_path):
        return ("jump", int(target_phase))
    return ("abort", int(target_phase))
