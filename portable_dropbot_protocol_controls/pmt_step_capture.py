# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The PMT step-capture value contract: a step's PMT capture setup, stored
on the row as a plain JSON-native dict (or None for "no PMT capture") and
parsed back into a typed `PmtStepCapture` model.

Parsing is deliberately tolerant, like the fluorescence capture-chain's
`parse_chain` (`fluorescence_protocol_controls/capture_chain.py`): a stale
or hand-edited protocol file must never crash a load — an invalid cell logs
a warning and reads as no capture.
"""

# Microdrop package imports.
from portable_dropbot_controller.consts import PmtStepCapture

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The two phases a step's ticked entries fire in, matching the executor's
#: on_pre_step / on_post_step hooks.
PHASE_START = "start"
PHASE_END = "end"


def parse_step_capture(value):
    """A stored column value (dict, or None) parsed into a
    `PmtStepCapture`, or None for "no PMT capture". An invalid value is
    logged and read as None rather than failing the protocol load."""
    if not value:
        return None

    try:
        return PmtStepCapture.model_validate(value)
    except Exception as e:
        logger.warning(f"Skipping invalid PMT step capture {value!r}: {e}")
        return None


def normalize_step_capture(value):
    """The value to store: a JSON-native dict, or None.

    Entries with neither `at_start` nor `at_end` ticked are dropped; a
    capture left with no entries collapses to None.
    """
    step = parse_step_capture(value)

    if step is None:
        return None

    entries = [e for e in step.entries if e.at_start or e.at_end]

    if not entries:
        return None

    return step.model_copy(update={"entries": entries}).model_dump(mode="json")


def entries_for_phase(step, phase):
    """The step's entries ticked for `phase` (PHASE_START/PHASE_END), in
    capture order."""

    if phase == PHASE_START:
        return [e for e in step.entries if e.at_start]

    if phase == PHASE_END:
        return [e for e in step.entries if e.at_end]

    raise ValueError(f"Unknown PMT capture phase: {phase!r}")


def summary_text(value):
    """Display-only summary, e.g. '3 spots · 1 start / 3 end'; blank for
    no capture."""
    step = parse_step_capture(value)

    if step is None or not step.entries:
        return ""

    n = len(step.entries)
    n_start = len(entries_for_phase(step, PHASE_START))
    n_end = len(entries_for_phase(step, PHASE_END))
    spot_word = "spot" if n == 1 else "spots"

    return f"{n} {spot_word} · {n_start} start / {n_end} end"
