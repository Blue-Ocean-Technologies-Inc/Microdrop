# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The drawer's colour roles, Qt-free: one colour rule per job.

* SEVERITY (info, success, warning, error): notification cards and toasts
  only, their stripe and icon.
* CATEGORY: the header accent map (``ux_consts.HEADER_ACCENTS``), on
  headers, their chips and rules, and their cards' kicker label.
* INTERACTIVE: one link colour for every clickable text that is not a
  primary button; primary buttons a filled dark brand green (green means
  "this does the thing"); help-only buttons outlined in the link colour.
* STATE: the unread dot and the "N new" chip, in the strong text colour,
  so "new" collides with no severity or category.

Every role is ``(light theme, dark theme)``. Text drawn in an accent is
first made readable (``readable_on``) against the surface it sits on, to
WCAG's 4.5:1; ``tests`` check every pair the roles produce.
"""

LIGHT, DARK = 0, 1

#: WCAG's least contrast: normal text, and large text or icons.
TEXT_CONTRAST = 4.5
ICON_CONTRAST = 3.0

#: The drawer's translucent area lets this much of what lies beneath show.
DRAWER_SHOW_THROUGH = 0.08

#: Secondary text is the text colour this far towards the window's.
MUTED_MIX = 0.36

#: The themes' own colours, as the app's palettes give them.
WINDOW = ("#F3F3F3", "#1E1E1E")
TEXT = ("#000000", "#FFFFFF")

# ---------------------------------------------------------------------------
# The roles
# ---------------------------------------------------------------------------
#: Severity: cards' and toasts' stripe and icon. The product's warning
#: yellow and success green are too light for an icon on a light card, so
#: the light theme takes darker shades.
SEVERITY = {
    "info": ("#2F80ED", "#5C9EF2"),
    "success": ("#2E8B47", "#7EE29A"),
    "warning": ("#A86400", "#F5A623"),
    "error": ("#E0002D", "#F05A6E"),
}

#: Interactive: every link-like text (Show more, Read more, How do I…?).
LINK = ("#1A5FB4", "#8AB4F8")

#: Primary buttons: a dark brand green under white labels; hovered, pressed.
PRIMARY_FILL = ("#1B7734", "#1B7734")
PRIMARY_FILL_HOVER = ("#25883F", "#25883F")
PRIMARY_FILL_PRESSED = ("#085822", "#085822")
PRIMARY_LABEL = ("#FFFFFF", "#FFFFFF")

#: State: the unread dot and the "N new" chip.
UNREAD = TEXT

#: Large fills in a severity (a chosen Errors or Needs action chip, a
#: badge): the error red softened on dark, the orange darkened on light.
ERROR_FILL = ("#C62828", "#F28B82")
ATTENTION_FILL = ("#B45309", "#F6A04D")


# ---------------------------------------------------------------------------
# Colour arithmetic
# ---------------------------------------------------------------------------


def rgb(color):
    """``#RRGGBB`` as three 0-255 ints."""
    color = color.lstrip("#")

    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


def hex_of(channels):
    return "#" + "".join(f"{round(max(0, min(255, value))):02X}" for value in channels)


def blend(color, under, alpha):
    """``color`` at ``alpha`` over ``under``, as the opaque colour seen."""
    return hex_of(
        alpha * top + (1 - alpha) * bottom
        for top, bottom in zip(rgb(color), rgb(under))
    )


def luminance(color):
    """WCAG relative luminance."""
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


def readable_on(color, surface, minimum=TEXT_CONTRAST):
    """``color`` darkened (on a light surface) or lightened (on a dark one)
    in small steps until it reaches ``minimum`` contrast with ``surface``."""
    target = "#000000" if luminance(surface) > 0.18 else "#FFFFFF"

    for _step in range(40):
        if contrast(color, surface) >= minimum:
            break

        color = blend(target, color, 0.08)

    return color


def label_on(fill):
    """Black or white, whichever reads better on ``fill``."""
    return max(("#000000", "#FFFFFF"), key=lambda text: contrast(text, fill))


def surfaces(theme):
    """Every background text can sit on in ``theme``: a card, the drawer,
    and the drawer's translucent part over black and over white."""
    window = WINDOW[theme]
    card = "#FFFFFF" if theme == LIGHT else blend("#FFFFFF", window, 0.045)

    return {
        "card": card,
        "drawer": window,
        "drawer over black": blend(window, "#000000", 1 - DRAWER_SHOW_THROUGH),
        "drawer over white": blend(window, "#FFFFFF", 1 - DRAWER_SHOW_THROUGH),
    }


def muted_text(theme):
    """Secondary text (times, sources): as view_styles.muted_text."""
    return blend(TEXT[theme], WINDOW[theme], 1 - MUTED_MIX)
