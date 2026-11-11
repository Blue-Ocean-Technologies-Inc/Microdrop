# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""chip_seated turns a chip_on_pad contact mask (bit0 debounced presence,
bit1 left pogo, bit2 right pogo) into a chip-on-pad flag under the
chip-detect preference's rule. Hardware-free, no Redis."""

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    CHIP_DETECT_RULE_ANY_POGO,
    CHIP_DETECT_RULE_BOTH_POGOS,
)
from portable_dropbot_controller.portable_dropbot_controller_base import (
    chip_seated,
)


@pytest.mark.parametrize(
    ("contacts", "expected"),
    [
        (0, False),
        (1, False),
        (2, False),
        (3, False),
        (4, False),
        (5, False),
        (6, False),
        (7, True),
    ],
)
def test_both_pogos_rule_needs_every_contact_bit(contacts, expected):
    assert chip_seated(contacts, CHIP_DETECT_RULE_BOTH_POGOS) is expected


@pytest.mark.parametrize(
    ("contacts", "expected"),
    [
        (0, False),
        (1, False),
        (2, False),
        (3, True),
        (4, False),
        (5, True),
        (6, False),
        (7, True),
    ],
)
def test_any_pogo_rule_needs_presence_and_one_pogo(contacts, expected):
    assert chip_seated(contacts, CHIP_DETECT_RULE_ANY_POGO) is expected
