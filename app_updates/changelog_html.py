# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The changelog pane's HTML: a release's markdown rendered in the app's
light or dark theme."""

# Microdrop style imports.
from microdrop_style.colors import BLACK, GREY, PRIMARY_SHADE, WHITE
from microdrop_style.helpers import is_dark_mode

# Microdrop utils imports.
from microdrop_utils.pyside_helpers import markdown_text_to_html

#: Overrides the colours and fonts QTextDocument writes inline into the
#: rendered changelog, so the page matches the dialog's theme.
CHANGELOG_STYLE = """<style>
html, body {{ background: {background} !important; }}
body {{ margin: 8px; }}
body, body * {{
    color: {text} !important;
    font-family: "Inter", "Segoe UI", sans-serif !important;
}}
a, a * {{ color: {link} !important; }}
</style>"""


def themed_changelog_html(markdown_text):
    """Render ``markdown_text`` with the dialog's background, text colour,
    link colour and font, in light and dark mode."""
    if is_dark_mode():
        colors = {
            "background": GREY["darker"],
            "text": WHITE,
            "link": PRIMARY_SHADE[300],
        }
    else:
        colors = {"background": WHITE, "text": BLACK, "link": PRIMARY_SHADE[800]}

    style = CHANGELOG_STYLE.format(**colors)

    return markdown_text_to_html(markdown_text).replace("</head>", f"{style}</head>", 1)
