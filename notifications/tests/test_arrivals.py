# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""An arrival rings (and chimes) whenever something visible happens, a
repeat included; it is silent only when nothing is seen."""

# Third-party imports.
import pytest

# Microdrop package imports.
from notifications.controllers.toast_controller import (
    ARRIVAL_IN_DRAWER,
    ARRIVAL_POP_UP,
    ARRIVAL_REFRESH,
    RINGING_ARRIVALS,
    SKIP_QUIET,
    SKIP_READ,
    SKIP_START_UP,
    arrival_outcome,
)


@pytest.mark.parametrize(
    "enabled, drawer_open, unread, toast_showing, held_quietly, expected",
    [
        (True, False, True, False, False, ARRIVAL_POP_UP),
        # The same notification again while its toast shows: it refreshes.
        (True, False, True, True, False, ARRIVAL_REFRESH),
        # A repeat while quiet refreshes a toast still showing.
        (True, False, True, True, True, ARRIVAL_REFRESH),
        (True, True, True, False, False, ARRIVAL_IN_DRAWER),
        (True, True, False, True, True, ARRIVAL_IN_DRAWER),
        (False, False, True, False, False, SKIP_START_UP),
        (True, False, False, False, False, SKIP_READ),
        (True, False, True, False, True, SKIP_QUIET),
    ],
)
def test_arrival_outcome(
    enabled, drawer_open, unread, toast_showing, held_quietly, expected
):
    outcome = arrival_outcome(enabled, drawer_open, unread, toast_showing, held_quietly)

    assert outcome == expected


def test_only_visible_outcomes_ring():
    assert set(RINGING_ARRIVALS) == {ARRIVAL_POP_UP, ARRIVAL_REFRESH, ARRIVAL_IN_DRAWER}
    assert not {SKIP_START_UP, SKIP_READ, SKIP_QUIET} & set(RINGING_ARRIVALS)
