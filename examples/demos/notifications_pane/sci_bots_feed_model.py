# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free state of the Sci-Bots Feed: its posts, their groups and its
status line.

State only: SciBotsFeedController loads, pushes and removes posts, and
opens their links. Posts arrive as validated FeedPostMessages
(``sci_bots_feed_schema``); the helpers here say how a date reads.
"""

# Standard library imports.
import datetime

# Enthought library imports.
from traits.api import (
    Any,
    Bool,
    Callable,
    Date,
    Enum,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
)

# Local imports.
from .sci_bots_feed_groups import GROUP_PREVIEW_COUNT, group_subtitle
from .sci_bots_feed_html import PLAIN_TEXT_BULLET
from .sci_bots_feed_schema import FEED_KINDS, PRECISION_DAY, PRECISION_MONTH

#: How a month-only date reads, e.g. "September 2026".
MONTH_DISPLAY_FORMAT = "%B %Y"

#: Posts up to this many days old read as "N days ago", older ones as a date.
RELATIVE_AGE_MAX_DAYS = 30

#: Where a post came from: the feed source, or a push.
ORIGIN_SOURCE = "source"
ORIGIN_PUSHED = "pushed"


def format_post_date(post):
    """A post's date as its card shows it: "September 2026" when only the
    month is known, else the ISO day."""

    if post.date_precision == PRECISION_MONTH:
        return post.date.strftime(MONTH_DISPLAY_FORMAT)

    return post.date.isoformat()


def format_post_age(post, today):
    """How long ago ``post`` came out: "today", "yesterday", "N days ago"
    within RELATIVE_AGE_MAX_DAYS, else its date (also for a future one or a
    month-only one)."""

    if post.date_precision == PRECISION_MONTH:
        return format_post_date(post)

    days = (today - post.date).days

    if days == 0:
        return "today"

    if days == 1:
        return "yesterday"

    if 0 < days <= RELATIVE_AGE_MAX_DAYS:
        return f"{days} days ago"

    return post.date.isoformat()


def summary_teaser(post):
    """A post's summary in one line, for a collapsed card: its first list
    item (a release's first feature), else its first line; "" for none."""
    lines = post.summary.splitlines()
    items = [line for line in lines if line.startswith(PLAIN_TEXT_BULLET)]
    first = (items or lines or [""])[0]

    return first.removeprefix(PLAIN_TEXT_BULLET).strip()


class FeedPost(HasTraits):
    """One post as the feed shows it."""

    #: Stable id; a push with the same id replaces the post.
    id = Str()

    #: One line, the card's heading.
    title = Str()

    #: What it is: one of FEED_KINDS.
    kind = Enum(*FEED_KINDS)

    #: When it came out; a month-only date's first day.
    date = Date()

    #: Whether ``date`` is the day, or only stands for its month.
    date_precision = Enum(PRECISION_DAY, PRECISION_MONTH)

    #: Plain text; the tooltip, and shown when there is no summary_html.
    summary = Str()

    #: Sanitised rich text, shown instead of summary when set.
    summary_html = Str()

    #: Where Read more goes: an http or https page.
    url = Str()

    #: Its picture: an absolute path, an https URL, or "" for none.
    image = Str()

    #: Shown before the unpinned posts, whatever its date.
    pinned = Bool(False)

    #: Where it came from, e.g. "LinkedIn"; shown beside the kind.
    source_label = Str()

    #: Hidden after this day, if set.
    expires = Date(allow_none=True)

    #: Whether it came from the feed source or was pushed.
    origin = Enum(ORIGIN_SOURCE, ORIGIN_PUSHED)

    #: Whether the whole summary shows, not just its first lines.
    expanded = Bool(False)


class FeedGroup(HasTraits):
    """One header's posts, the first GROUP_PREVIEW_COUNT unless all shown."""

    #: Its FeedGroupSpec: title, accent, glyph.
    spec = Any()

    #: Its posts, pinned first then newest first.
    posts = List(Instance(FeedPost))

    #: Whether every post shows, not just the first few.
    show_all = Bool(False)

    #: The posts on show.
    visible_posts = Property(List(Instance(FeedPost)), observe="posts.items, show_all")

    #: Posts behind "Show all".
    hidden_count = Property(Int, observe="posts.items, show_all")

    #: The muted line beside the header, e.g. "3 issues".
    subtitle = Property(Str, observe="posts.items")

    def _get_visible_posts(self):
        return self.posts if self.show_all else self.posts[:GROUP_PREVIEW_COUNT]

    def _get_hidden_count(self):
        return 0 if self.show_all else max(len(self.posts) - GROUP_PREVIEW_COUNT, 0)

    def _get_subtitle(self):
        return group_subtitle(self.spec, self.posts)


class SciBotsFeed(HasTraits):
    """The posts on show, pinned first then newest first, grouped under
    their headers, and what the last action made of its input."""

    #: The posts on show.
    posts = List(Instance(FeedPost))

    #: The posts under their headers, top group first; empty ones left out.
    groups = List(Instance(FeedGroup))

    #: The last action's outcome and its problems, one per line; "" if none.
    status_text = Str()

    #: Whether status_text reports problems.
    status_is_error = Bool(False)

    #: ``today()``: the current date unless replaced.
    today = Callable(datetime.date.today)

    #: One line for the section header, e.g. "11 posts · newest 3 days ago".
    summary = Property(Str, observe="posts.items, status_is_error")

    def _get_summary(self):
        if not self.posts:
            return "unavailable" if self.status_is_error else "no posts"

        count = len(self.posts)
        newest = max(self.posts, key=lambda post: post.date)
        age = format_post_age(newest, self.today())

        return f"{count} post{'s' if count > 1 else ''} · newest {age}"
