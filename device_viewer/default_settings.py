# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Microdrop style imports.
from microdrop_style.colors import (
    ACCENT_COLOR,
    BLACK,
    INFO_COLOR,
    PRIMARY_COLOR,
    PRIMARY_SHADE,
    SECONDARY_SHADE,
    WARNING_COLOR,
    WHITE,
)

ELECTRODE_ON = SECONDARY_SHADE[600]
ELECTRODE_OFF = SECONDARY_SHADE[900]
ELECTRODE_NO_CHANNEL = WARNING_COLOR
ELECTRODE_DISABLED = "#CC4444"
ELECTRODE_LINE = SECONDARY_SHADE[400]
ELECTRODE_TEXT_COLOR = WHITE
ELECTRODE_CHANNEL_EDITING = "teal"

CONNECTION_LINE_OFF = WHITE
CONNECTION_LINE_ON_DEFAULT = PRIMARY_COLOR

PERSPECTIVE_RECT_COLOR = "red"
PERSPECTIVE_RECT_COLOR_EDITING = "orange"

ROUTE_SELECTED = "yellow"
ROUTE_CW_LOOP = "red"
ROUTE_CCW_LOOP = "orange"
ROUTE_COLOR_POOL = (
    PRIMARY_SHADE[300],
    PRIMARY_SHADE[400],
    PRIMARY_SHADE[500],
    PRIMARY_SHADE[600],
)
# The slug preview's tint, one hue per route layer in layer order, so the
# path being drawn stands apart from the ones before it. Neighbouring hues
# alternate warm and cool, and none is the yellow, red, orange or pink
# reserved above; the route lines keep the colours above.
ROUTE_SHAPE_COLOR_POOL = (
    INFO_COLOR,  # blue
    "#C2185B",  # magenta
    "#00A3B4",  # cyan
    "#8D6E63",  # brown
    ACCENT_COLOR,  # purple
    "#9E9D24",  # olive
    "#3949AB",  # indigo
    PRIMARY_COLOR,  # green
    "#546E7A",  # slate
)
AUTOROUTE_COLOR = "pink"
# The halo under the selected route's slug outline, and how much of the
# Route Head alpha it takes.
SLUG_HALO_COLOR = BLACK
SLUG_HALO_ALPHA_FACTOR = 0.6

routes_key = "Route"
#: The live slug preview: the electrodes a route's slug would actuate.
route_shape_key = "Route Shape"
#: The outline of the selected route's slug at its most recent phase.
route_head_key = "Route Head"
connections_key = "Connections"
electrode_fill_key = "Electrode fill"
actuated_electrodes_key = "Actuated electrodes"
electrode_text_key = "Electrode text"
electrode_outline_key = "Electrode outline"
video_key = "Video"
zones_key = "Zones"
hovered_electrode_key = "Hovered Electrode"
hovered_actuation_key = "Hovered Actuation"

hovered_electrode_lightness = 20
hovered_actuated_lightness = 30

alpha_keys = [
    routes_key,
    route_shape_key,
    route_head_key,
    connections_key,
    electrode_fill_key,
    actuated_electrodes_key,
    electrode_text_key,
    electrode_outline_key,
    video_key,
    zones_key,
    hovered_electrode_key,
    hovered_actuation_key,
]

values = [100] * len(alpha_keys[:-2]) + [20, 30]

default_alphas = dict(zip(alpha_keys, values))
# Light enough to read each electrode's own state through the preview tint.
default_alphas[route_shape_key] = 35

default_visibility = {key: True for key in default_alphas}
