# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Parse the preset quick-pick values the user types into Portable DropBot
Settings. The text is hand-edited, so parsing never fails: whatever is not
a usable number is skipped."""

# Standard library imports.
import math
import re

# Local imports.
from ..consts import PRESET_SLOTS_MAX


def parse_presets(text, low, high, decimals=None, nonzero=False):
    """Return the preset values in ``text``, in the order typed.

    Tokens split on commas and whitespace; ones that are not finite numbers
    are skipped. Each value is clamped into ``[low, high]`` and rounded,
    repeats are dropped (the first kept), and at most PRESET_SLOTS_MAX
    values are returned.

    Parameters
    ----------
    text : str
        Comma-separated numbers, e.g. ``"-1, -0.1, 0.1, 1"``.
    low, high : int or float
        Bounds each value is clamped into.
    decimals : int or None
        Digits kept after the point; None rounds to an int.
    nonzero : bool
        Drop values that round to zero, for offsets where zero does nothing.
    """
    values = []

    for token in re.split(r"[,\s]+", text):
        try:
            number = float(token)
        except ValueError:
            continue

        if not math.isfinite(number):
            continue

        number = min(max(number, low), high)

        if decimals is None:
            number = int(round(number))
        else:
            # Adding 0.0 turns -0.0 into 0.0, which would otherwise label "-0".
            number = round(number, decimals) + 0.0

        if (nonzero and number == 0) or number in values:
            continue

        values.append(number)

        if len(values) == PRESET_SLOTS_MAX:
            break

    return values
