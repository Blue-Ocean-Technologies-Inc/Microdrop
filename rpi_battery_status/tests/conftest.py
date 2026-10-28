# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json

# Third-party imports.
import pytest

#: status.json exactly as the daemon wrote it on the portable Pi while
#: charging (current is negative: + means discharge).
PI_CHARGING_STATUS_JSON = (
    '{"timestamp": 1793205197.6192737, "present": true, '
    '"soc": 34.484282657375246, "voltage": 23.625, "voltage_per_cell": 3.9375, '
    '"current": -5.9, "power": -139.38750000000002, "state": "Charging", '
    '"charging": true, "alert": false, "cells": 6, "chemistry": "li-ion", '
    '"dark_theme": false, "soc_source": "coulomb", "time_to_empty_s": null, '
    '"time_to_full_s": 39768, "remaining_ah": 34.484282657375246, '
    '"battery_absent": false, "schema": 1}'
)


@pytest.fixture
def pi_charging_snapshot():
    """The real Pi snapshot, parsed."""
    return json.loads(PI_CHARGING_STATUS_JSON)


@pytest.fixture
def pi_charging_status_file(tmp_path):
    """The real Pi snapshot written to a status file."""
    path = tmp_path / "status.json"
    path.write_text(PI_CHARGING_STATUS_JSON)

    return path
