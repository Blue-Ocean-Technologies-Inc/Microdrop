# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The self-test parameters the operator can set: the repeat counts of the
looping tests, the channels / calibration limits and the health tests'
switches."""

# Enthought library imports.
from traits.api import Bool, HasTraits, Range

# Local imports.
from .consts import (
    CALIBRATION_MAX_RAIL_PCT_BOUNDS,
    CALIBRATION_MIN_COUNTS_BOUNDS,
    CALIBRATION_REPLICATES_BOUNDS,
    CALIBRATION_TEST,
    CHANNELS_REPLICATES_BOUNDS,
    CHANNELS_TEST,
    CHANNELS_THRESHOLD_PF_BOUNDS,
    HEATERS_TEST,
    MOTORS_TEST,
    VOLTAGE_POINTS_BOUNDS,
    VOLTAGE_TEST,
)

# The vendor module (``dropbot_portable.self_test``) is imported inside the
# methods that need it: it loads its service module on import.


class SelfTestParameters(HasTraits):
    """Qt-free parameters, defaulting to the vendor's and kept for the
    session (the hub model outlives the panel)."""

    #: Points of the 40-200 V sweep of the voltage test.
    voltage_points = Range(*VOLTAGE_POINTS_BOUNDS)

    #: Replicates per point of the feedback calibration matrix.
    calibration_replicates = Range(*CALIBRATION_REPLICATES_BOUNDS)

    #: Calibration low limit: expected signal (IQR counts) below it is not judged.
    calibration_min_counts = Range(*CALIBRATION_MIN_COUNTS_BOUNDS)

    #: Calibration high limit: % of samples on an ADC rail above it = clipped.
    calibration_max_rail_pct = Range(*CALIBRATION_MAX_RAIL_PCT_BOUNDS)

    #: Replicates of the per-channel sweep.
    channels_replicates = Range(*CHANNELS_REPLICATES_BOUNDS)

    #: A channel is active above this capacitance (pF, baseline removed).
    channels_threshold_pf = Range(*CHANNELS_THRESHOLD_PF_BOUNDS)

    #: The heater test heats each OFF heater briefly (the vendor default).
    heaters_heat_step = Bool(True)

    #: The motor test moves PMT-Y and the filter out and back; off by
    #: default, as in the vendor tab, since the axes MOVE.
    motors_moves = Bool(False)

    def _voltage_points_default(self):
        return self._vendor_repeat_default(VOLTAGE_TEST)

    def _calibration_replicates_default(self):
        return self._vendor_repeat_default(CALIBRATION_TEST)

    def _channels_replicates_default(self):
        return self._vendor_repeat_default(CHANNELS_TEST)

    def _calibration_min_counts_default(self):
        from dropbot_portable import self_test

        return self_test.CAL_MATRIX_MIN_COUNTS

    def _calibration_max_rail_pct_default(self):
        from dropbot_portable import self_test

        return self_test.RAIL_FRAC_CLIPPED * 100.0

    def _channels_threshold_pf_default(self):
        from dropbot_portable import self_test

        return self_test.CHANNEL_CONNECTED_THRESHOLD_PF

    @staticmethod
    def _vendor_repeat_default(name):
        from dropbot_portable import self_test

        return self_test.REPEAT_PARAMS[name][1]

    def motor_moves(self, tests):
        """Whether a run of ``tests`` moves axes in the motor test."""
        return MOTORS_TEST in tests and self.motors_moves

    def test_kwargs(self, tests):
        """The parameters of ``tests`` as a run request's test_kwargs."""
        from dropbot_portable import self_test

        repeats = {
            VOLTAGE_TEST: self.voltage_points,
            CALIBRATION_TEST: self.calibration_replicates,
            CHANNELS_TEST: self.channels_replicates,
        }
        limits = {
            CALIBRATION_TEST: {
                "min_counts": float(self.calibration_min_counts),
                "max_rail_pct": float(self.calibration_max_rail_pct),
            },
            CHANNELS_TEST: {"threshold_pf": float(self.channels_threshold_pf)},
        }
        switches = {
            HEATERS_TEST: {"heat_step": bool(self.heaters_heat_step)},
            MOTORS_TEST: {"moves": bool(self.motors_moves)},
        }

        kwargs = {}

        for name in tests:
            if name in repeats:
                param = self_test.REPEAT_PARAMS[name][0]
                kwargs[name] = {param: int(repeats[name]), **limits.get(name, {})}

            elif name in switches:
                kwargs[name] = switches[name]

        return kwargs
