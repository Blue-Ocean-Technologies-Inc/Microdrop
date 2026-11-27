# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Extension-point id: QWidget instances to show in the app status bar.
STATUS_BAR_ICONS = "status_bar_icons"

#: Uniform gap (px) between adjacent contributed status-bar icons, left or right.
ICON_SPACING = 10

#: Gap (px) between adjacent left widgets of one ``status_bar_group``.
CHIP_GAP = 6

#: Status-bar message shown from startup until something replaces it: none,
#: as the protocol's step navigator says which step or mode is current.
DEFAULT_STATUS_MESSAGE = ""

#: Contents margins (left, top, right, bottom) of the status bar.
STATUS_BAR_CONTENTS_MARGINS = (30, 0, 30, 0)

#: Contributors may set ``widget.status_bar_icon_priority`` (plain int
#: attribute) on a right-hand widget to order it in the icon container: lower =
#: further left, ties keep arrival order. Unset means ICON_PRIORITY_DEFAULT.
ICON_PRIORITY_DEFAULT = 0
ICON_PRIORITY_LEFT = -1
ICON_PRIORITY_LEFTMOST = -2
ICON_PRIORITY_RIGHTMOST = 2

#: Contributors may set ``widget.status_bar_side = STATUS_BAR_SIDE_LEFT``
#: (plain str attribute) to place a widget on the bar's left, before the
#: status message, instead of in the right-hand icon container. Unset means
#: the right.
STATUS_BAR_SIDE_LEFT = "left"

#: ``widget.status_bar_side = STATUS_BAR_SIDE_TOP_EDGE`` lays the widget
#: along the bar's top edge instead: full width, as tall as its own height,
#: over the bar's contents and transparent to the mouse, e.g. a thin
#: progress line. The widget draws nothing when it has nothing to show.
STATUS_BAR_SIDE_TOP_EDGE = "top_edge"

#: Left widgets order by their own ``widget.status_bar_left_priority``
#: (plain int attribute): lower = further left, ties keep arrival order.
#: Unset sorts last. The slots, left to right: a readiness indicator, step
#: navigation, the primary file (the protocol) and a secondary file (the
#: device).
LEFT_PRIORITY_READINESS = 10
LEFT_PRIORITY_NAVIGATION = 20
LEFT_PRIORITY_PRIMARY_FILE = 30
LEFT_PRIORITY_SECONDARY_FILE = 40
LEFT_PRIORITY_DEFAULT = 1000

#: Contributors may set ``widget.status_bar_group`` (plain str attribute) on
#: left widgets that belong together: the members share one row, CHIP_GAP
#: apart instead of ICON_SPACING, in the slot of the member with the lowest
#: left priority.
STATUS_BAR_GROUP_FILE_CHIPS = "file_chips"
