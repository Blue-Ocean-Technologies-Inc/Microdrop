# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Small color-representation converters shared across the app —
notably between the '#rrggbb' hex strings we persist in preferences
and the (r, g, b) float tuples TraitsUI's RGBColor trait uses."""


def hex_to_rgb(hex_color: str) -> tuple:
    """'#rrggbb' -> (r, g, b) floats in 0..1."""
    value = hex_color.lstrip("#")

    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    """(r, g, b) floats in 0..1 -> '#rrggbb'."""
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
