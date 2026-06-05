"""PhaseRecord — one entry in a step's per-phase timeline.

Emitted by RoutesHandler (via the ``phase_recorded`` signal) as each phase
starts, and collected by the UI into the current step's navigable timeline.
Small, immutable value object — carries exactly what the pane needs to
navigate to a phase (its position) and actuate it live (its electrodes).
"""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class PhaseRecord:
    """A single executed phase.

    ``step_path``: the row's 0-indexed path tuple (which step this phase
    belongs to). ``phase_index``: 0-based index of the phase within that
    step. ``electrodes`` / ``channels``: the phase's actuated sets (sorted),
    used to actuate the phase live when the operator navigates to it.
    ``duration_s``: the phase's target dwell (status target ``t``).
    """

    step_path: Tuple[int, ...]
    phase_index: int
    electrodes: List[str] = field(default_factory=list)
    channels: List[int] = field(default_factory=list)
    duration_s: float = 0.0
