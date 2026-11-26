# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The run log's force column agrees with the DropBot status pane (#1033)."""

# Standard library imports.
import json

# Third-party imports.
import pytest

# Microdrop package imports.
from pluggable_protocol_tree.services.logging.consts import FORCE_COLUMN
from pluggable_protocol_tree.services.logging.ingestion import LoggingIngestion

# Microdrop utils imports.
from microdrop_utils.force_math_helpers import force_for_step


def _ingestion_with_calibration(c_per_a):
    ing = LoggingIngestion()
    ing.update_capacitance_per_unit_area(c_per_a)
    ing.set_step(step_id="s", step_idx=1)
    ing.set_actuation(actuated_channels=[1], actuated_area=1.0)

    return ing


def _capacitance_message(volt):
    return json.dumps(
        {
            "capacitance": "10pF",
            "voltage": f"{volt}V",
            "instrument_time_us": 1,
            "reception_time": 2,
        }
    )


@pytest.mark.parametrize("volt, c_per_a", [(100.0, 2.0), (120.0, 5.9), (35.5, 0.4)])
def test_logged_force_matches_force_for_step(volt, c_per_a):
    ing = _ingestion_with_calibration(c_per_a)

    assert ing.log_capacitance(_capacitance_message(volt)) is True
    assert ing.entries[-1][FORCE_COLUMN] == pytest.approx(force_for_step(volt, c_per_a))


def test_logged_force_is_in_mn_per_m():
    """5.9 pF/mm^2 at 120 V is about 42 mN/m, not the raw 4.2e4 product."""
    ing = _ingestion_with_calibration(5.9)

    ing.log_capacitance(_capacitance_message(120.0))

    assert ing.entries[-1][FORCE_COLUMN] == pytest.approx(42.48, abs=0.01)


def test_logged_force_none_for_nonpositive_voltage():
    ing = _ingestion_with_calibration(2.0)

    ing.log_capacitance(_capacitance_message(0.0))

    assert ing.entries[-1][FORCE_COLUMN] is None
