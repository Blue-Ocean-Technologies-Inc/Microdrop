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
contrast on every surface it can sit on, in both themes: 4.5:1 for text,
3:1 for icons and stripes."""

# Third-party imports.
import pytest

# Microdrop package imports.
from examples.demos.notifications_ux import colour_roles as roles
from examples.demos.notifications_ux.column_parts import FILTER_CHIP_ACCENTS
from examples.demos.notifications_ux.ux_consts import HEADER_ACCENTS

THEMES = (roles.LIGHT, roles.DARK)

#: How strongly a chip's accent tints its background.
CHIP_TINT = 0.16


def text_pairs():
    """``(what, text, background)`` for every text pair, both themes."""

    for theme in THEMES:
        surfaces = roles.surfaces(theme)

        for name, surface in surfaces.items():
            yield f"muted text on {name}", roles.muted_text(theme), surface
            yield f"link on {name}", roles.LINK[theme], surface

            # Accent text (coloured titles, kickers) is made readable first.
            for header, accent in HEADER_ACCENTS.items():
                text = roles.readable_on(accent[theme], surface)
                yield f"{header} accent text on {name}", text, surface

                chip = roles.blend(accent[theme], surface, CHIP_TINT)
                text = roles.readable_on(accent[theme], chip)
                yield f"{header} chip on {name}", text, chip

        yield (
            "primary button label",
            roles.PRIMARY_LABEL[theme],
            roles.PRIMARY_FILL[theme],
        )

        for name, accent in FILTER_CHIP_ACCENTS.items():
            fill = accent[theme]
            yield f"chosen {name} chip label", roles.label_on(fill), fill

        for severity, colour in roles.SEVERITY.items():
            fill = colour[theme]
            yield f"{severity} bell badge label", roles.label_on(fill), fill


def icon_pairs():
    """``(what, colour, background)`` for every icon or stripe."""

    for theme in THEMES:
        card = roles.surfaces(theme)["card"]

        for severity, colour in roles.SEVERITY.items():
            yield f"{severity} icon on card", colour[theme], card

        yield "unread dot on card", roles.UNREAD[theme], card

        # Header glyphs, discs' marks and rules, in the accent itself.
        for name, surface in roles.surfaces(theme).items():
            for header, accent in HEADER_ACCENTS.items():
                yield f"{header} glyph on {name}", accent[theme], surface


@pytest.mark.parametrize("what, text, background", list(text_pairs()))
def test_text_contrast(what, text, background):
    assert roles.contrast(text, background) >= roles.TEXT_CONTRAST, what


@pytest.mark.parametrize("what, colour, background", list(icon_pairs()))
def test_icon_contrast(what, colour, background):
    assert roles.contrast(colour, background) >= roles.ICON_CONTRAST, what


def test_header_accents_are_one_per_header():
    accents = [pair for pair in HEADER_ACCENTS.values()]

    assert len(set(accents)) == len(accents)
