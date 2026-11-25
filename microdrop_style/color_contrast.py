# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Colour arithmetic on ``#RRGGBB`` strings, Qt-free: blending, WCAG
relative luminance and contrast, and making a colour readable on a surface.
"""

#: WCAG's least contrast for body text.
WCAG_TEXT_CONTRAST = 4.5

#: Surface luminance above which text is darkened rather than lightened.
LIGHT_SURFACE_LUMINANCE = 0.18

#: How far each step of ``readable_on`` moves a colour, and its most steps.
READABLE_STEP = 0.08
READABLE_MAX_STEPS = 40


def rgb(color):
    """``#RRGGBB`` as three 0-255 ints."""
    color = color.lstrip("#")

    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


def hex_of(channels):
    """Three 0-255 numbers as ``#RRGGBB``, clamped."""
    return "#" + "".join(f"{round(max(0, min(255, value))):02X}" for value in channels)


def blend(color, under, alpha):
    """``color`` at ``alpha`` over ``under``, as the opaque colour seen."""
    return hex_of(
        alpha * top + (1 - alpha) * bottom
        for top, bottom in zip(rgb(color), rgb(under))
    )


def luminance(color):
    """WCAG relative luminance, 0 to 1."""
    linear = []

    for value in rgb(color):
        value /= 255
        linear.append(
            value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = linear

    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first, second):
    """WCAG contrast ratio, 1 to 21."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)

    return (lighter + 0.05) / (darker + 0.05)


def readable_on(color, surface, minimum=WCAG_TEXT_CONTRAST):
    """``color`` darkened (on a light surface) or lightened (on a dark one)
    in small steps until it reaches ``minimum`` contrast with ``surface``."""
    target = "#000000" if luminance(surface) > LIGHT_SURFACE_LUMINANCE else "#FFFFFF"

    for _step in range(READABLE_MAX_STEPS):
        if contrast(color, surface) >= minimum:
            break

        color = blend(target, color, READABLE_STEP)

    return color


def label_on(fill):
    """Black or white, whichever reads better on ``fill``."""
    return max(("#000000", "#FFFFFF"), key=lambda text: contrast(text, fill))
