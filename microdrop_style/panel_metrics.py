# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Surface metrics shared by the floating panels laid over the main window:
the notifications drawer and its cards, and the protocol pre-flight card."""

#: Corner radius (px) of a floating panel.
DRAWER_RADIUS = 10

#: Space (px) between a panel's edges and its contents.
DRAWER_PADDING_PX = 6

#: Corner radius (px) of the cards inside a panel, and of toasts.
CARD_RADIUS = 8

#: Duration (ms) of a panel's opening slide; 0 opens it at once.
DRAWER_SLIDE_MS = 160

#: Width (px) of the severity stripe down a card's left edge.
STRIPE_WIDTH = 4
