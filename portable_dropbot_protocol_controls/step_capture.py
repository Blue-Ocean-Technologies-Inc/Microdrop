# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The step-capture value contract shared by the PMT and fluorescence
protocol columns: a step's capture setup is stored on the row as a plain
JSON-native dict (or None for "no capture") and parsed back into the
capture kind's typed step model; its entries fire at the step's start
and/or end phase.

Parsing is deliberately tolerant: a stale or hand-edited protocol file must
never crash a load — an invalid cell logs a warning and reads as no capture.
`pmt_step_capture.py` and `fluorescence_step_capture.py` each bind one
StepCaptureCodec to their step model."""

# Enthought library imports.
from traits.api import Any, HasTraits, Str

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The two phases a step's ticked entries fire in, matching the executor's
#: on_pre_step / on_post_step hooks.
PHASE_START = "start"
PHASE_END = "end"


def entries_for_phase(step, phase):
    """The step's entries ticked for `phase` (PHASE_START/PHASE_END), in
    capture order. `step` is any step capture whose entries carry
    `at_start` / `at_end`."""

    if phase == PHASE_START:
        return [e for e in step.entries if e.at_start]

    if phase == PHASE_END:
        return [e for e in step.entries if e.at_end]

    raise ValueError(f"Unknown capture phase: {phase!r}")


class StepCaptureCodec(HasTraits):
    """Parse, normalize and summarize one capture kind's step cell."""

    #: The pydantic step model (e.g. PmtStepCapture); its `entries` carry
    #: `at_start` / `at_end`.
    model = Any
    #: The capture kind, for log messages ("PMT", "fluorescence").
    kind = Str
    #: What one entry captures, singular, for the summary ("spot").
    noun = Str

    def parse(self, value):
        """A stored column value (dict, or None) parsed into the step
        model, or None for "no capture". An invalid value is logged and
        read as None rather than failing the protocol load."""
        if not value:
            return None

        try:
            return self.model.model_validate(value)
        except Exception as e:
            logger.warning(f"Skipping invalid {self.kind} step capture {value!r}: {e}")
            return None

    def normalize(self, value):
        """The value to store: a JSON-native dict, or None.

        Entries with neither `at_start` nor `at_end` ticked are dropped; a
        capture left with no entries collapses to None.
        """
        step = self.parse(value)

        if step is None:
            return None

        entries = [e for e in step.entries if e.at_start or e.at_end]

        if not entries:
            return None

        return step.model_copy(update={"entries": entries}).model_dump(mode="json")

    def summary_text(self, value):
        """Display-only summary, e.g. '3 spots · 1 start / 3 end'; blank
        for no capture."""
        step = self.parse(value)

        if step is None or not step.entries:
            return ""

        n = len(step.entries)
        n_start = len(entries_for_phase(step, PHASE_START))
        n_end = len(entries_for_phase(step, PHASE_END))
        noun = self.noun if n == 1 else f"{self.noun}s"

        return f"{n} {noun} · {n_start} start / {n_end} end"
