# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""How a dock pane is brought forward, from whether it is closed and can
float."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.dock_pane_presenting import (
    POP_OUT,
    RAISE,
    SHOW_DOCKED,
    presentation_for,
)


@pytest.mark.parametrize("floatable", [True, False])
def test_a_pane_on_screen_is_raised_where_it_is(floatable):
    assert presentation_for(closed=False, floatable=floatable) == RAISE


def test_a_closed_pane_pops_out():
    assert presentation_for(closed=True, floatable=True) == POP_OUT


def test_a_closed_pane_that_cannot_float_shows_docked():
    assert presentation_for(closed=True, floatable=False) == SHOW_DOCKED
