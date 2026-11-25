# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The look and timing of the drawer, its sections and cards, the toasts and
the bell. View tuning only: nothing another plugin needs."""

# Local imports.
from ..consts import PKG

# ---------------------------------------------------------------------------
# Drawer
# ---------------------------------------------------------------------------
#: Object names of the panel's isolated roots (``isolation.isolate``): the
#: drawer, each toast and the settings window. Plain identifiers, as the
#: roots' style sheets select them by name.
DRAWER_OBJECT_NAME = f"{PKG}Drawer"
TOAST_OBJECT_NAME = f"{PKG}Toast"
SETTINGS_OBJECT_NAME = f"{PKG}Settings"

#: Space (px) between the drawer's edges and its contents.
DRAWER_PADDING_PX = 6

#: Opacity (0-1) of the drawer's background behind the cards, which lets
#: what lies beneath show faintly; 1.0 makes it opaque. The header, the
#: sections and the cards are always opaque.
DRAWER_OPACITY = 0.92

#: Repaints per second of what lies beneath the drawer (a camera feed, a
#: live plot) past which the open drawer turns opaque until closed: a
#: translucent drawer is repainted with whatever is beneath it.
DRAWER_BACKDROP_PAINTS_PER_S = 4

#: Whether a click in the main window outside the drawer closes it. The
#: click is then used up, so it never also actuates what lies beneath;
#: except on a drawer the app opened and the user has not used yet, where
#: it also reaches what was clicked (``outside_press_passes_through``).
DRAWER_CLOSES_ON_CLICK_OUTSIDE = True

#: Duration (ms) of the drawer's slide in from the right; 0 opens it at once.
DRAWER_SLIDE_MS = 160

#: How often (ms) the open drawer repaints its relative times ("2 min ago").
TIME_REFRESH_MS = 30_000

#: Most pixels an expanded traceback takes before it scrolls.
DETAIL_MAX_HEIGHT = 200

# ---------------------------------------------------------------------------
# Toasts
# ---------------------------------------------------------------------------
#: Width (px) of a toast; a narrower window gets narrower toasts.
TOAST_WIDTH = 360

#: Space (px) between toasts, and between the stack and the window's edges.
TOAST_GAP = 8
TOAST_MARGIN = 12

#: Durations (ms) of a toast sliding in, re-stacking, and flying to the bell.
TOAST_ENTER_MS = 240
TOAST_RESTACK_MS = 180
TOAST_FLY_MS = 420

# ---------------------------------------------------------------------------
# Bell
# ---------------------------------------------------------------------------
#: Counts above this show as "99+".
BADGE_MAX_COUNT = 99

#: Duration (ms) of the bell's swing when its count goes up.
BELL_PULSE_MS = 650

#: The range (px) the drawer's left edge drags its width in.
DRAWER_MIN_WIDTH = 320
DRAWER_MAX_WIDTH = 760

#: Room (px) the widest drawer leaves of the window on its left.
WINDOW_LEFT_IN_VIEW = 160

#: Width (px) of the grab strip along the drawer's left edge.
DRAWER_GRIP_WIDTH = 6

#: The drawer floats: inset (px) from the window's right edge, the status
#: bar and the top, with rounded corners of this radius (px).
DRAWER_INSET = 8
DRAWER_RADIUS = 10

#: The drawer's height follows its contents, never below this (px).
DRAWER_MIN_HEIGHT = 140

#: Duration (ms) of the drawer's height following its contents; changes
#: under DRAWER_FIT_STEP_PX (a section folding, frame by frame) follow at
#: once, and under 2 px not at all.
DRAWER_FIT_MS = 180
DRAWER_FIT_STEP_PX = 24

# ---------------------------------------------------------------------------
# Sections and cards
# ---------------------------------------------------------------------------
#: Duration (ms) of a section opening or closing.
SECTION_ANIMATION_MS = 180

#: Height (px) of a brand mark shown in a section header.
SECTION_LOGO_HEIGHT = 30

#: Lines of a card's text shown before "Show more".
CARD_BODY_LINES = 2

#: Corner radius (px) of cards and toasts.
CARD_RADIUS = 8

#: A card's thumbnail box (width, height px), 4:3, in the drawer and in a
#: toast; the picture is cover-cropped to it, never scaled up.
THUMBNAIL_SIZE = (72, 54)
TOAST_THUMBNAIL_SIZE = (64, 48)

#: Activity's cards built at first, and per batch as the scroll nears the
#: end.
HISTORY_PAGE = 25

#: Most milliseconds a GUI turn spends building cards; the rest are built
#: in the turns after, so opening the drawer or scrolling never stalls.
BUILD_BUDGET_MS = 12

#: Pixels from the end of the column within which the next batch is built.
LOAD_AHEAD_PX = 600

#: Duration (ms) of a revealed card's highlight fading out, and of the
#: scroll to it.
HIGHLIGHT_MS = 1600
REVEAL_SCROLL_MS = 260
