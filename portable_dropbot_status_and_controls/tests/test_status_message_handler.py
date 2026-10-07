# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The status pane's Chip Status text: the chip_on_pad contact mask
(bit0 presence verdict, bit1 left pogo, bit2 right pogo) decoded into
which pogo pads touch the chip, raw mask appended."""

# Third-party imports.
import pytest

# Microdrop package imports.
from portable_dropbot_status_and_controls.message_handlers.message_handler import (
    summarize_chip_pad_contacts,
)


@pytest.mark.parametrize(
    "contacts, expected",
    [
        (0, "No pogos on chip (0)"),
        (1, "No pogos on chip (1)"),
        (3, "Left pogos on chip (3)"),
        (5, "Right pogos on chip (5)"),
        (7, "All pogos on chip (7)"),
    ],
)
def test_chip_pad_contacts_summary(contacts, expected):
    assert summarize_chip_pad_contacts(contacts) == expected
