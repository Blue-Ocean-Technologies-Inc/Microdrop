# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed's groups: which posts go under which header, in what
order, and how each header looks. Qt-free; data, not branches.

A post goes in the first group that takes it: pinned posts in Top stories
whatever their kind, then by kind. Empty groups are not shown.
"""

# Standard library imports.
from typing import NamedTuple

# Microdrop style imports.
from microdrop_style.colors import (
    GOLD,
    GREY,
    PRIMARY_SHADE,
    SECONDARY_SHADE,
    TEAL,
)

#: Cards a group shows before its "Show all".
GROUP_PREVIEW_COUNT = 3

#: How a header's subtitle reads: the post count, or the newest title.
SUBTITLE_COUNT = "count"
SUBTITLE_LATEST = "latest"


class FeedGroupSpec(NamedTuple):
    """One group of the feed."""

    #: Stable id, e.g. "releases".
    id: str

    #: The header, e.g. "What's new".
    title: str

    #: The kinds it takes; with ``pinned``, only pinned posts of them.
    kinds: tuple

    #: Whether it takes the pinned posts (before any other group).
    pinned: bool

    #: Header and link colour: (on a light theme, on a dark theme). Large
    #: bold text, so each keeps at least 3:1 against its card colour.
    accent: tuple

    #: Material Symbols ligature shown before the header.
    glyph: str

    #: SUBTITLE_COUNT ("3 issues") or SUBTITLE_LATEST ("latest v1.46.0").
    subtitle: str

    #: (singular, plural) of what the group lists.
    noun: tuple


#: The groups, top first.
FEED_GROUPS = (
    FeedGroupSpec(
        id="pinned",
        title="Top stories",
        kinds=("announcement", "product", "newsletter", "post", "release"),
        pinned=True,
        accent=(GOLD["light"], GOLD["dark"]),
        glyph="push_pin",
        subtitle=SUBTITLE_COUNT,
        noun=("story", "stories"),
    ),
    FeedGroupSpec(
        id="releases",
        title="What's new",
        kinds=("release",),
        pinned=False,
        accent=(PRIMARY_SHADE[900], PRIMARY_SHADE[200]),
        glyph="new_releases",
        subtitle=SUBTITLE_LATEST,
        noun=("release", "releases"),
    ),
    FeedGroupSpec(
        id="newsletters",
        title="Newsletters",
        kinds=("newsletter",),
        pinned=False,
        accent=(TEAL["light"], TEAL["dark"]),
        glyph="mail",
        subtitle=SUBTITLE_COUNT,
        noun=("issue", "issues"),
    ),
    FeedGroupSpec(
        id="announcements",
        title="Announcements",
        kinds=("announcement", "product"),
        pinned=False,
        accent=(SECONDARY_SHADE[700], SECONDARY_SHADE[300]),
        glyph="campaign",
        subtitle=SUBTITLE_COUNT,
        noun=("update", "updates"),
    ),
    FeedGroupSpec(
        id="posts",
        title="Updates",
        kinds=("post",),
        pinned=False,
        accent=(GREY["dark"], GREY["lighter"]),
        glyph="forum",
        subtitle=SUBTITLE_COUNT,
        noun=("post", "posts"),
    ),
)


def group_for(post, specs=FEED_GROUPS):
    """The first group in ``specs`` that takes ``post``, or None."""

    for spec in specs:
        if post.kind in spec.kinds and (post.pinned or not spec.pinned):
            return spec

    return None


def group_posts(posts, specs=FEED_GROUPS):
    """``(spec, posts)`` for each group that takes any of ``posts``, in
    ``specs`` order; each post in the first group that takes it, the
    posts keeping their given order."""
    grouped = {spec.id: [] for spec in specs}

    for post in posts:
        spec = group_for(post, specs)

        if spec is not None:
            grouped[spec.id].append(post)

    return [(spec, grouped[spec.id]) for spec in specs if grouped[spec.id]]


def group_subtitle(spec, posts):
    """The muted line beside a header, e.g. "3 issues" or "latest v1.46.0"."""

    if spec.subtitle == SUBTITLE_LATEST and posts:
        return f"latest {posts[0].title.split()[-1]}"

    singular, plural = spec.noun

    return f"{len(posts)} {singular if len(posts) == 1 else plural}"
