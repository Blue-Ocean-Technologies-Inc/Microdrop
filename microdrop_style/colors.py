# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

PRIMARY_SHADE = {
    50:  "#E6F4E9",
    100: "#C3E4C9",
    200: "#9DD3A8",
    300: "#75C285",
    400: "#57B66C",
    500: "#37A953",
    600: "#2F9A4A",
    700: "#25883F",
    800: "#1B7734",
    900: "#085822"
}

PRIMARY_COLOR = PRIMARY_SHADE[600]

SECONDARY_SHADE = {
    50:  "#E7E9EF",
    100: "#CED3E0",
    200: "#B6BDD0",
    300: "#9DA7C1",
    400: "#8592B1",
    500: "#6C7CA1",
    600: "#546692",
    700: "#3B5082",
    800: "#233A73",
    900: "#0A2463"
}

SECONDARY_COLOR = SECONDARY_SHADE[500]

# Checked/selected accent for controls whose platform style has no system
# accent of its own (Fusion on Linux). Matched to the Windows accent color
# used on the lab machines so both platforms render the same checked look.
ACCENT_COLOR = "#A94DC1"

INFO_COLOR = "#2F80ED"
SUCCESS_COLOR = "#37A953"
ERROR_COLOR = '#ff0033'
# Softer red used for exception text inside error-dialog HTML bodies
# (ERROR_COLOR is too saturated for paragraph text on white).
DIALOG_ERROR_TEXT_COLOR = "#c0392b"
WARNING_COLOR = "#F5A623"

GREY = {
    # Faint resting-state fill, like the windows11 style's tool buttons.
    "lightest": "#EDEDED",
    "lighter": "#BCBCBC",
    "light": "#D1D1D1",
    "dark":  "#575757"
}

BLACK = "#000000"
WHITE = "#FFFFFF"