# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""One row of the self-test hub's test table."""

# Enthought library imports.
from traits.api import Bool, HasTraits, Str

# Local imports.
from .consts import (
    INFO_TESTS,
    OUTCOME_ERROR,
    OUTCOME_FAIL,
    OUTCOME_INFO_DONE,
    OUTCOME_NO_VERDICT,
    OUTCOME_NONE,
    OUTCOME_PASS,
    OUTCOME_STOPPED,
)


class SelfTestRow(HasTraits):
    """A test of the vendor catalogue: whether to run it, and how it went
    last time."""

    #: The vendor test name, e.g. "test_voltage".
    name = Str()

    #: The vendor title, e.g. "Voltage".
    title = Str()

    #: Where the run puts the pogo pads for this test.
    pads = Str()

    #: Included in "Run selected".
    selected = Bool(True)

    #: The last outcome: a verdict word, or the run state while queued.
    outcome = Str(OUTCOME_NONE)

    #: The last outcome needs the operator's attention (FAIL / ERROR).
    outcome_is_bad = Bool(False)

    #: The last duration, e.g. "12.3 s"; empty until the test has run.
    duration = Str()

    def show_outcome(self, outcome):
        """Show a run-state word (queued, running..., not run)."""
        self.outcome = outcome
        self.outcome_is_bad = False

    def show_result(self, result):
        """Show a SelfTestResult: its verdict word and duration."""

        if result.cancelled:
            outcome = OUTCOME_STOPPED

        elif result.error:
            outcome = OUTCOME_ERROR

        elif result.verdict is True:
            outcome = OUTCOME_PASS

        elif result.verdict is False:
            outcome = OUTCOME_FAIL

        elif self.name in INFO_TESTS:
            outcome = OUTCOME_INFO_DONE

        else:
            outcome = OUTCOME_NO_VERDICT

        self.outcome = outcome
        self.outcome_is_bad = outcome in (OUTCOME_FAIL, OUTCOME_ERROR)
        self.duration = "" if result.duration is None else f"{result.duration:.1f} s"
