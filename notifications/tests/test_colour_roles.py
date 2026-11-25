# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Every text and icon colour the drawer's colour roles produce meets WCAG
contrast on every surface it can sit on, in both themes: 4.5:1 for text
and 3:1 for icons on dark, 5.5:1 and 4:1 on light, where colours on white
read paler."""

# Third-party imports.
import pytest

# Microdrop package imports.
from notifications.consts import (
    ATTENTION_SECTION_ID,
    DEFAULT_SECTION_ACCENT,
    HISTORY_SECTION_ID,
)
from notifications.models.own_sections import AttentionSection, HistorySection
from notifications.views import colour_roles as roles
from notifications.views.activity_parts import FILTER_CHIP_ACCENTS
from plugin_management.consts import (
    LOAD_STATUS_SECTION_ACCENT,
    LOAD_STATUS_SECTION_ID,
)

# Microdrop style imports.
from microdrop_style.color_contrast import blend, contrast, label_on, readable_on

THEMES = (roles.LIGHT, roles.DARK)

#: Every section header's accent: the drawer's own, the default, and the
#: Plugins section's.
HEADER_ACCENTS = {
    ATTENTION_SECTION_ID: AttentionSection().accent,
    HISTORY_SECTION_ID: HistorySection().accent,
    "default": DEFAULT_SECTION_ACCENT,
    LOAD_STATUS_SECTION_ID: LOAD_STATUS_SECTION_ACCENT,
}


def text_pairs():
    """``(what, text, background)`` for every text pair, both themes."""

    for theme in THEMES:
        surfaces = roles.surfaces(theme)
        minimum = roles.TEXT_CONTRAST[theme]

        for name, surface in surfaces.items():
            yield theme, f"muted text on {name}", roles.muted_text(theme), surface
            yield theme, f"link on {name}", roles.LINK[theme], surface

            # Accent text (coloured titles, kickers) is made readable first.
            for header, accent in HEADER_ACCENTS.items():
                text = readable_on(accent[theme], surface, minimum)
                yield theme, f"{header} accent text on {name}", text, surface

                chip = blend(accent[theme], surface, roles.CHIP_TINT[theme])
                text = readable_on(accent[theme], chip, minimum)
                yield theme, f"{header} chip on {name}", text, chip

        yield (
            theme,
            "primary button label",
            roles.PRIMARY_LABEL[theme],
            roles.PRIMARY_FILL[theme],
        )

        for name, accent in FILTER_CHIP_ACCENTS.items():
            fill = accent[theme]
            yield theme, f"chosen {name} chip label", label_on(fill), fill

    # The bell's badge sits on the status bar, not the drawer: WCAG's floor.
    for theme in THEMES:
        for severity, colour in roles.SEVERITY.items():
            fill = colour[theme]
            yield roles.DARK, f"{severity} bell badge label", label_on(fill), fill


def icon_pairs():
    """``(what, colour, background)`` for every icon or stripe."""

    for theme in THEMES:
        card = roles.surfaces(theme)["card"]

        for severity, colour in roles.SEVERITY.items():
            yield theme, f"{severity} icon on card", colour[theme], card

        yield theme, "unread dot on card", roles.UNREAD[theme], card

        # Header glyphs, discs' marks and rules, in the accent itself.
        for name, surface in roles.surfaces(theme).items():
            for header, accent in HEADER_ACCENTS.items():
                yield theme, f"{header} glyph on {name}", accent[theme], surface


@pytest.mark.parametrize("theme, what, text, background", list(text_pairs()))
def test_text_contrast(theme, what, text, background):
    assert contrast(text, background) >= roles.TEXT_CONTRAST[theme], what


@pytest.mark.parametrize("theme, what, colour, background", list(icon_pairs()))
def test_icon_contrast(theme, what, colour, background):
    assert contrast(colour, background) >= roles.ICON_CONTRAST[theme], what


def test_header_accents_are_one_per_header():
    accents = [pair for pair in HEADER_ACCENTS.values()]

    assert len(set(accents)) == len(accents)
