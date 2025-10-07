
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
    return f'{ureg.Quantity(text):.{n_digits}g~H}'
