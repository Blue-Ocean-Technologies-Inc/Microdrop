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
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

#: Extension-point id: QWidget instances to show in the app status bar.
STATUS_BAR_ICONS = "status_bar_icons"

#: Uniform gap (px) between adjacent contributed status-bar icons.
ICON_SPACING = 10

#: Status-bar message shown from startup until something replaces it.
DEFAULT_STATUS_MESSAGE = "Free Mode"

#: Contents margins (left, top, right, bottom) of the status bar.
STATUS_BAR_CONTENTS_MARGINS = (30, 0, 30, 0)

#: Contributors may set ``widget.status_bar_icon_priority`` (plain int
#: attribute) on a contributed widget to order it in the bar: lower =
#: further left, ties keep arrival order. Unset means ICON_PRIORITY_DEFAULT.
ICON_PRIORITY_DEFAULT = 0
ICON_PRIORITY_LEFT = -1
ICON_PRIORITY_LEFTMOST = -2
