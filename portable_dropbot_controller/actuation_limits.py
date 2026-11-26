# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The HV actuation setpoints the portable's supply takes: voltage within
VOLTAGE_BOUNDS (its floor is 40 V, above the DropBot's 30 V) and frequency
within FREQUENCY_BOUNDS. Pure helpers, unit-testable without hardware."""

# Local imports.
from .consts import DEFAULT_FREQUENCY, DEFAULT_VOLTAGE, FREQUENCY_BOUNDS, VOLTAGE_BOUNDS

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _setpoint_refusal(name, value, bounds, unit):
    low, high = bounds

    if low <= value <= high:
        return ""

    return f"{name} {value} {unit} refused: the HV supply takes {low}-{high} {unit}"


def voltage_refusal(voltage):
    """Why the HV supply would refuse ``voltage`` (V), or "" when it takes it."""
    return _setpoint_refusal("voltage", voltage, VOLTAGE_BOUNDS, "V")


def frequency_refusal(frequency):
    """Why the HV supply would refuse ``frequency`` (Hz), or "" when it takes it."""
    return _setpoint_refusal("frequency", frequency, FREQUENCY_BOUNDS, "Hz")


def connect_actuation_setpoints(voltage, frequency):
    """Return the (voltage, frequency) to apply on connect.

    Each preferred setpoint the supply would refuse — a hand-edited
    preferences file — is replaced by the device default, with an error
    logged.
    """
    refusal = voltage_refusal(voltage)

    if refusal:
        logger.error(f"Default {refusal}; using {DEFAULT_VOLTAGE} V")
        voltage = DEFAULT_VOLTAGE

    refusal = frequency_refusal(frequency)

    if refusal:
        logger.error(f"Default {refusal}; using {DEFAULT_FREQUENCY} Hz")
        frequency = DEFAULT_FREQUENCY

    return voltage, frequency
