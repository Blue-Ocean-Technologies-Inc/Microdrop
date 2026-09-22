# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A step sets only one of the PMT / fluorescence capture columns."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_protocol_controls.capture_exclusivity import (
    check_single_capture,
)

_PMT = {"entries": [{"slot": 1, "gain": 128, "exposure_s": 10.0, "at_start": True}]}
_FLUORESCENCE = {"entries": [{"filter_position": 1, "led_percent": 50}]}


def _row(pmt_capture=None, fluorescence_capture=None):
    return SimpleNamespace(
        pmt_capture=pmt_capture,
        fluorescence_capture=fluorescence_capture,
        dotted_path=lambda: "1.2",
    )


@pytest.mark.parametrize(
    "row",
    [
        _row(),
        _row(pmt_capture=_PMT),
        _row(fluorescence_capture=_FLUORESCENCE),
    ],
)
def test_a_step_with_at_most_one_capture_passes(row):
    check_single_capture(row)


def test_a_step_with_both_captures_is_refused():
    with pytest.raises(RuntimeError, match="Step 1.2 sets both"):
        check_single_capture(_row(pmt_capture=_PMT, fluorescence_capture=_FLUORESCENCE))
