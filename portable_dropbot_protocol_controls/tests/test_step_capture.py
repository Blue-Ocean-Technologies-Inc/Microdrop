# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The step-capture rules shared by the PMT and fluorescence step captures:
the start/end phases (the codec itself is covered through each kind's
test_*_step_capture.py)."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import FluorescenceStepCapture, PmtStepCapture
from portable_dropbot_protocol_controls.step_capture import (
    PHASE_END,
    PHASE_START,
    entries_for_phase,
)


def _step(*ticks):
    """A step with one entry per (at_start, at_end) pair, numbered from 1."""
    return SimpleNamespace(
        entries=[
            SimpleNamespace(key=i, at_start=start, at_end=end)
            for i, (start, end) in enumerate(ticks, start=1)
        ]
    )


def test_entries_for_phase_filters_by_tick_in_capture_order():
    step = _step((True, False), (False, True), (True, True))

    assert [e.key for e in entries_for_phase(step, PHASE_START)] == [1, 3]
    assert [e.key for e in entries_for_phase(step, PHASE_END)] == [2, 3]


def test_entries_for_phase_unknown_phase_raises():
    with pytest.raises(ValueError, match="Unknown capture phase"):
        entries_for_phase(_step((True, True)), "middle")


@pytest.mark.parametrize(
    "step",
    [
        PmtStepCapture.model_validate(
            {
                "entries": [
                    {"slot": 1, "gain": 128, "exposure_s": 10.0, "at_start": True},
                    {"slot": 2, "gain": 128, "exposure_s": 10.0, "at_end": True},
                ]
            }
        ),
        FluorescenceStepCapture.model_validate(
            {
                "entries": [
                    {
                        "filter_position": 1,
                        "led_percent": 50,
                        "exposure_ms": 5.0,
                        "at_start": True,
                    },
                    {
                        "filter_position": 2,
                        "led_percent": 50,
                        "exposure_ms": 5.0,
                        "at_end": True,
                    },
                ]
            }
        ),
    ],
    ids=["pmt", "fluorescence"],
)
def test_entries_for_phase_works_on_both_step_captures(step):
    assert len(entries_for_phase(step, PHASE_START)) == 1
    assert len(entries_for_phase(step, PHASE_END)) == 1
