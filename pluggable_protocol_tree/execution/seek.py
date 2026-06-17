"""Pure (Qt-free, thread-free) seek resolution for mid-run navigation (#471).

A seek target is ``(step_path, phase_index)``. ``resolve_seek`` maps it to a
frame index in execution order; ``seek_decision`` tells a phase loop what to do
on resume given the current position. Both are pure so they unit-test without
the executor, threads, or Qt.
"""

from typing import List, Optional, Tuple

Path = Tuple[int, ...]


def resolve_seek(frame_paths: List[Path], target) -> Optional[Tuple[int, int]]:
    """Return ``(frame_index, phase_index)`` for ``target`` ((path, phase)), or
    None if target is None or its path is not among ``frame_paths``. The phase
    index is clamped to >= 0 (upper clamping is the phase loop's job — it knows
    the materialized phase count)."""
    if target is None:
        return None
    target_path, target_phase = target
    target_path = tuple(target_path)
    for i, path in enumerate(frame_paths):
        if tuple(path) == target_path:
            return i, max(0, int(target_phase))
    return None


def seek_decision(resume_target, current_path: Path, current_phase_index: int):
    """Decide what a phase loop should do at its pause checkpoint on resume.

    Returns one of:
      ``("continue", current_phase_index)`` — no seek pending,
      ``("jump", target_phase)``           — same step, jump the phase loop,
      ``("abort", target_phase)``          — different step, unwind to the
                                             frame walk and re-enter the target.
    """
    if resume_target is None:
        return ("continue", current_phase_index)
    target_path, target_phase = resume_target
    if tuple(target_path) == tuple(current_path):
        return ("jump", int(target_phase))
    return ("abort", int(target_phase))
