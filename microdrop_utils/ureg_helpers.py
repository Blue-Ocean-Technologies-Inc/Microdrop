# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# ureg = UnitRegistry()
from nadamq import ureg

def ureg_quant_percent_change(old, new):
    old = get_ureg_magnitude(old)
    new = get_ureg_magnitude(new)

    return 100 * abs(old - new) / old


def ureg_diff(old, new):
    old = get_ureg_magnitude(old)
    new = get_ureg_magnitude(new)

    return old - new


def get_ureg_magnitude(text):
    return ureg(text).magnitude


def trim_to_n_digits(text, n_digits):
    quantity = round(ureg.Quantity(text), n_digits)

    return f'{quantity:.{n_digits}g~H}'
