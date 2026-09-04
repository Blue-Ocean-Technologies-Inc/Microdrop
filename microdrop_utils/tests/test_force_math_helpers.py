# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for force_math_helpers.force_for_step (guards + behaviour).

Moved here from dropbot_protocol_controls/tests/test_force_math.py (#610):
force_for_step is pure math shared by more than one plugin, so it now lives
in microdrop_utils, owned by neither. The app-globals-backed calibration
lookup stays under dropbot_protocol_controls, along with its own tests."""

from microdrop_utils.force_math_helpers import force_for_step


def test_force_for_step_zero_voltage_returns_none():
    assert force_for_step(0, 1.5) is None


def test_force_for_step_negative_voltage_returns_none():
    assert force_for_step(-10, 1.5) is None


def test_force_for_step_zero_c_per_a_returns_none():
    assert force_for_step(100, 0) is None


def test_force_for_step_negative_c_per_a_returns_none():
    assert force_for_step(100, -1.0) is None


def test_force_for_step_returns_positive_float():
    result = force_for_step(100, 1.5)
    assert result is not None
    assert isinstance(result, float)
    assert result > 0
