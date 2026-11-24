# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications UX prototype's contract: what a notification may carry
beyond the product's ``NotificationMessage`` (a second button, a "needs
attention" flag), and the look and timing of toasts, drawer and sections.

Everything here is a candidate for ``notifications/consts.py`` once ported.
"""

# Standard library imports.
from collections import namedtuple
from typing import Annotated, Literal, Union

# Third-party imports.
from pydantic import BaseModel, Field

# Microdrop package imports.
from notifications.consts import (
    DRAWER_WIDTH,
    NOTIFICATION_POST,
    NotificationMessage,
)
from plugin_management.consts import LOAD_STATUS_SECTION_ID

# Microdrop style imports.
from microdrop_style.colors import ACCENT_COLOR, INFO_COLOR, PRIMARY_COLOR
from microdrop_style.icons.logos import BLUE_OCEAN_SCI_BOTS_LOGO

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])

# ---------------------------------------------------------------------------
# A notification's second button
# ---------------------------------------------------------------------------


class HelpAction(BaseModel):
    """A link-styled button opening the tutorial for what to do."""

    kind: Literal["help"] = "help"

    #: The link's text.
    label: str = "How do I…?"

    #: The tutorial or help page to open, e.g. "Calibrating the device".
    tutorial: str = Field(min_length=1)


class SnoozeAction(BaseModel):
    """A button moving the card out of Needs attention, for later."""

    kind: Literal["snooze"] = "snooze"

    label: str = "Later"


#: What a notification's second button does, as data.
SecondaryAction = Annotated[
    Union[HelpAction, SnoozeAction], Field(discriminator="kind")
]


class UxNotificationMessage(NotificationMessage):
    """A NotificationMessage with the prototype's additions."""

    #: The second, quieter button: a tutorial link or "Later".
    secondary_action: SecondaryAction | None = None

    #: The user has to do something: listed under Needs attention, kept by
    #: Clear all, and its toast stays until acted on or dismissed.
    needs_attention: bool = False

    #: Names the condition that raised it, e.g. "dropbot.chip_missing": a
    #: NOTIFICATION_RESOLVE with this id clears the card once the condition
    #: does, with no button pressed.
    condition_id: str = ""

    #: The declared notification category it belongs to, e.g.
    #: "protocol.step_completed"; empty, it behaves as an uncategorised one.
    category_id: str = ""

    #: Posts with the same thread id update one entry in place (its title
    #: and detail, counted once), e.g. a run's step progress.
    thread_id: str = ""


#: Extension point: NotificationCategorySpecs, the kinds of notification
#: each plugin posts, for the user to tune per kind.
NOTIFICATION_CATEGORIES = f"{PKG}.categories"


#: Posts on the product topic; the prototype's handler reads the additions.
ux_notification_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATION_POST, validator_class=UxNotificationMessage
)

#: A condition cleared (NotificationResolveRequest): its cards leave Needs
#: attention, marked with what cleared it.
NOTIFICATION_RESOLVE = "ui/notifications/resolve"


class NotificationResolveRequest(BaseModel):
    """A condition that raised Needs attention cards has cleared."""

    #: The cards' ``condition_id``.
    condition_id: str = Field(min_length=1)

    #: What cleared it, shown on the cards, e.g. "Chip detected".
    resolution: str = "Resolved"


ux_resolve_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATION_RESOLVE, validator_class=NotificationResolveRequest
)

# ---------------------------------------------------------------------------
# Toasts
# ---------------------------------------------------------------------------
#: Toasts shown at once; the rest go straight to the bell, counted on a
#: "+N more" pill above the stack.
TOAST_LIMIT = 3

#: How long (ms) an info or success toast stays, hover not counted.
TOAST_TIMEOUT_MS = 6000

#: Countdown resolution (ms) of the toasts' timers.
TOAST_TICK_MS = 50

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

#: Duration (ms) of the bell's nudge when its count goes up.
BELL_PULSE_MS = 650

# ---------------------------------------------------------------------------
# Drawer
# ---------------------------------------------------------------------------
#: The drawer's width (px) at first, and the range its left edge drags in.
DRAWER_DEFAULT_WIDTH = DRAWER_WIDTH
DRAWER_MIN_WIDTH = 320
DRAWER_MAX_WIDTH = 760

#: Width (px) of the grab strip along the drawer's left edge.
DRAWER_GRIP_WIDTH = 6

# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
ATTENTION_SECTION_ID = f"{PKG}.attention"

#: The drawer's own section titles, kept short: Needs attention, and the one
#: listing every other notification. A news section is titled by its
#: publisher's short name.
ATTENTION_SECTION_TITLE = "Needs attention"
HISTORY_SECTION_TITLE = "Activity"

#: The News section: Blue Ocean Technologies' and Sci-Bots' combined feed.
NEWS_SECTION_ID = f"{PKG}.news"
NEWS_SECTION_TITLE = "News"
NEWS_SECTION_ORDER = 10

#: News's colour (the bell's and the toasts' stripe for new posts), and
#: the height (px) of its header's brand mark.
NEWS_ACCENT = PRIMARY_COLOR
NEWS_LOGO_HEIGHT = 30

#: Who a post is from when it does not say: the feed file is Sci-Bots'.
NEWS_DEFAULT_SOURCE = "Sci-Bots"
HISTORY_SECTION_ID = f"{PKG}.history"

#: Sections sort by order: Needs attention first, the history last.
ATTENTION_SECTION_ORDER = -100
HISTORY_SECTION_ORDER = 1000

#: Duration (ms) of a section opening or closing.
SECTION_ANIMATION_MS = 180

# ---------------------------------------------------------------------------
# The drawer's one-column layout
# ---------------------------------------------------------------------------
#: Activity's filters: every entry, the errors, or those with a button left
#: to press.
FILTER_ALL = "all"
FILTER_ERRORS = "errors"
FILTER_ACTION = "action"

#: Activity's cards built at first, and per batch as the scroll nears the
#: end.
HISTORY_PAGE = 25

#: Most milliseconds a GUI turn spends building cards; the rest are built
#: in the turns after, so opening the drawer or scrolling never stalls.
BUILD_BUDGET_MS = 15

#: Pixels from the end of the column within which the next batch is built.
LOAD_AHEAD_PX = 600

#: Duration (ms) of a revealed card's highlight fading out, and of the
#: scroll to it.
HIGHLIGHT_MS = 1600
REVEAL_SCROLL_MS = 260

#: The bell's "severity" when only new feed posts are counted: below info.
FEED_SEVERITY = "feed"

#: Category of a new feed post's stand-in notification.
CATEGORY_FEED = "feed"

#: A feed sub-section's posts before its "Show N more".
FEED_GROUP_PREVIEW = 1

# ---------------------------------------------------------------------------
# Quiet mode
# ---------------------------------------------------------------------------
#: Who posts the summary when a quiet run ends.
QUIET_SUMMARY_SOURCE = "notifications"

#: Lines of a card's text shown before "Show more".
CARD_BODY_LINES = 2

#: Needs attention's accent: a deep orange, readable as text on both themes
#: where WARNING_COLOR's yellow is not.
ATTENTION_ACCENT = "#E8710A"

#: A section's look: its glyph (a Material Symbols ligature), accent
#: colour, and a wide brand mark (a picture's path) shown instead of the
#: glyph, if any.
SectionStyle = namedtuple("SectionStyle", "glyph accent logo", defaults=("",))

SECTION_STYLES = {
    ATTENTION_SECTION_ID: SectionStyle("priority_high", ATTENTION_ACCENT),
    LOAD_STATUS_SECTION_ID: SectionStyle("extension", ACCENT_COLOR),
    NEWS_SECTION_ID: SectionStyle(
        "newspaper", NEWS_ACCENT, str(BLUE_OCEAN_SCI_BOTS_LOGO)
    ),
    HISTORY_SECTION_ID: SectionStyle("notifications", INFO_COLOR),
}

#: The look of a section with no entry above.
DEFAULT_SECTION_STYLE = SectionStyle("widgets", INFO_COLOR)
