# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Scale-bar maths: the units a calibration can be entered in, the
calibration a drawn line implies, and the round bar a map draws for a
given zoom. Qt-free, so the snapping ladder is testable on its own."""

# Standard library imports.
import math

#: Dropdown order (largest first) and each unit's size in metres.
UNITS = ("m", "cm", "mm", "µm", "nm")
UNIT_METRES = {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "µm": 1e-6, "nm": 1e-9}
DEFAULT_UNIT = "mm"

#: About how wide the drawn bar should be, in screen pixels, before its
#: length is snapped down to a round number.
SCALE_BAR_TARGET_PX = 120.0

#: Shorter calibration drags are a misclick, not a line.
MIN_SCALE_LINE_PX = 5.0

#: A scale bar reads 1, 2 or 5 times a power of ten — never 3.7.
_NICE_STEPS = (1.0, 2.0, 5.0)


def metres_per_pixel(line_px, value, unit):
    """The calibration a line of ``line_px`` called ``value`` ``unit``
    implies. None for a misclick or a non-positive value, so neither
    can poison an existing calibration."""
    if line_px < MIN_SCALE_LINE_PX or value <= 0:
        return None
    return value * UNIT_METRES[unit] / line_px


def format_length(length_m):
    """``length_m`` in the largest unit that still renders it at 1 or
    above: 0.0005 -> '500 µm'. Clamps at nm rather than reading
    '0 nm'."""
    for unit in UNITS:
        value = length_m / UNIT_METRES[unit]
        if value >= 1.0:
            return f"{value:g} {unit}"
    return f"{length_m / UNIT_METRES[UNITS[-1]]:g} {UNITS[-1]}"


def nice_scale(metres_per_screen_px, target_px=SCALE_BAR_TARGET_PX):
    """``(bar_px, label)`` for a bar of about ``target_px``, its length
    snapped DOWN to 1, 2 or 5 times a power of ten so the label always
    reads round. None when there is no usable calibration."""
    if not math.isfinite(metres_per_screen_px) or metres_per_screen_px <= 0:
        return None
    span = metres_per_screen_px * target_px
    decade = 10.0 ** math.floor(math.log10(span))
    length_m = decade
    for step in _NICE_STEPS:
        if step * decade <= span:
            length_m = step * decade
    return length_m / metres_per_screen_px, format_length(length_m)


def pixel_area(metres_per_pixel_value, unit):
    """One pixel's area in ``unit`` squared; 1.0 (that is, px²) when
    there is no calibration, so every size-aware stat still
    computes."""
    if metres_per_pixel_value <= 0:
        return 1.0
    return (metres_per_pixel_value / UNIT_METRES[unit]) ** 2


def area_unit(metres_per_pixel_value, unit):
    """'mm²' when calibrated, 'px²' when not."""
    return f"{unit}²" if metres_per_pixel_value > 0 else "px²"
