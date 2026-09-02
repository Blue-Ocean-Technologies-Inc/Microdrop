# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from microdrop_style.colors import (
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
AUTOROUTE_COLOR = "pink"

routes_key = "Route"
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

default_visibility = {key: True for key in default_alphas}
