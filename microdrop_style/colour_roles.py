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
* SECTION accents: each section's own (``NotificationSection.accent``), on
  its header's disc and chip, and its alerts' toasts.
* INTERACTIVE: one link colour for every clickable text that is not a
  primary button; primary buttons a filled dark brand green; help-only
  buttons outlined in the link colour.
* STATE: the unread dot and the "N new" chip, in the strong text colour,
  so "new" collides with no severity or section.

Every role is ``(light theme, dark theme)``. Text drawn in an accent is
first made readable (``readable_on``) against the surface it sits on; the
tests check every pair the roles produce.
"""

# Microdrop style imports.
from microdrop_style.color_contrast import blend
from microdrop_style.colors import GREY

LIGHT, DARK = 0, 1

#: Least contrast, ``(light theme, dark theme)``: text, and icons or glyphs.
#: WCAG's 4.5:1 and 3:1, with a margin in the light theme, where colours on
#: white read paler than their ratio suggests.
TEXT_CONTRAST = (5.5, 4.5)
ICON_CONTRAST = (4.0, 3.0)

#: How strongly an accent tints its chip, and its header's glyph disc.
CHIP_TINT = (0.22, 0.16)
DISC_TINT = (0.26, 0.18)

#: The drawer's translucent area lets this much of what lies beneath show.
DRAWER_SHOW_THROUGH = 0.08

#: Secondary text is the text colour this far towards the window's.
MUTED_MIX = 0.34

#: The themes' own colours, as the app's palettes give them.
WINDOW = ("#F3F3F3", "#1E1E1E")
TEXT = ("#000000", "#FFFFFF")

#: Severity: cards' and toasts' stripe and icon. The product's warning
#: yellow and success green are too light for an icon on a light card, so
#: the light theme takes darker shades.
SEVERITY = {
    "info": ("#2568C2", "#5C9EF2"),
    "success": ("#26763C", "#7EE29A"),
    "warning": ("#9B5C00", "#F5A623"),
    "error": ("#D7002B", "#F05A6E"),
}

#: Interactive: every link-like text (Show more, How do I…?).
LINK = ("#17549F", "#8AB4F8")

#: Primary buttons: a dark brand green under white labels; hovered, pressed.
PRIMARY_FILL = ("#1B7734", "#1B7734")
PRIMARY_FILL_HOVER = ("#25883F", "#25883F")
PRIMARY_FILL_PRESSED = ("#085822", "#085822")
PRIMARY_LABEL = ("#FFFFFF", "#FFFFFF")

#: State: the unread dot and the "N new" chip.
UNREAD = TEXT

#: Large fills in a severity (a chosen Errors or Needs action chip): the
#: error red softened on dark, the orange darkened on light.
ERROR_FILL = ("#C62828", "#F28B82")
ATTENTION_FILL = ("#9A4708", "#F6A04D")

#: Activity's "All" chip: a quiet grey.
NEUTRAL_FILL = (GREY["dark"], GREY["lighter"])


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
    """Secondary text (times, sources), as ``theme.muted_text`` draws it."""
    return blend(TEXT[theme], WINDOW[theme], 1 - MUTED_MIX)
