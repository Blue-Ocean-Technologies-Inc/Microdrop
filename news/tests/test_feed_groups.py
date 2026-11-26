# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The feed's groups: pinned posts first whatever their kind, then by kind
in the configured order, empty groups left out, the first few shown until
Show all, and a subtitle per header."""

# Standard library imports.
import datetime

# Third-party imports.
import pytest

# Microdrop package imports.
from news.models.feed_groups import (
    FEED_GROUPS,
    GROUP_PREVIEW_COUNT,
    group_posts,
    group_subtitle,
)
from news.models.feed_model import FeedGroup, FeedPost

SPECS = {spec.id: spec for spec in FEED_GROUPS}


def _post(post_id, kind="post", pinned=False):
    return FeedPost(
        id=post_id,
        title=f"MicroDrop {post_id}",
        kind=kind,
        pinned=pinned,
        date=datetime.date(2026, 11, 20),
    )


def _ids(grouped):
    return [(spec.id, [post.id for post in posts]) for spec, posts in grouped]


def test_each_post_goes_in_the_first_group_that_takes_it():
    posts = [
        _post("r1", "release"),
        _post("pinned-release", "release", pinned=True),
        _post("n1", "newsletter"),
        _post("a1", "announcement"),
        _post("pr1", "product"),
        _post("p1", "post"),
    ]

    assert _ids(group_posts(posts)) == [
        ("pinned", ["pinned-release"]),
        ("announcements", ["a1", "pr1"]),
        ("releases", ["r1"]),
        ("newsletters", ["n1"]),
        ("posts", ["p1"]),
    ]


def test_empty_groups_are_left_out_and_order_is_kept():
    posts = [_post("p2"), _post("n1", "newsletter"), _post("p1")]

    assert _ids(group_posts(posts)) == [
        ("newsletters", ["n1"]),
        ("posts", ["p2", "p1"]),
    ]
    assert group_posts([]) == []


def test_every_kind_has_a_group():
    kinds = {kind for spec in FEED_GROUPS if not spec.pinned for kind in spec.kinds}

    assert kinds == {
        "announcement",
        "product",
        "offer",
        "newsletter",
        "post",
        "release",
    }


def test_a_group_shows_its_first_few_until_show_all():
    posts = [_post(f"p{number}") for number in range(GROUP_PREVIEW_COUNT + 4)]
    group = FeedGroup(spec=SPECS["posts"], posts=posts)

    assert group.visible_posts == posts[:GROUP_PREVIEW_COUNT]
    assert group.hidden_count == 4

    group.show_all = True

    assert group.visible_posts == posts
    assert group.hidden_count == 0


@pytest.mark.parametrize(
    "spec_id, count, expected",
    [
        ("newsletters", 1, "1 issue"),
        ("newsletters", 3, "3 issues"),
        ("pinned", 2, "2 stories"),
        ("releases", 3, "latest v1.46.0"),
    ],
)
def test_subtitles(spec_id, count, expected):
    posts = [_post("v1.46.0", "release")] + [_post(f"x{n}") for n in range(count - 1)]

    assert group_subtitle(SPECS[spec_id], posts) == expected


def test_each_accent_reads_on_its_theme():
    """Large bold header text needs 3:1 against the card it sits by."""

    def luminance(color):
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92
            if channel <= 0.03928
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]

        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(first, second):
        high, low = sorted((luminance(first), luminance(second)), reverse=True)

        return (high + 0.05) / (low + 0.05)

    for spec in FEED_GROUPS:
        light, dark = spec.accent

        assert contrast(light, "#ffffff") >= 3, spec.id
        assert contrast(dark, "#2b2b2b") >= 3, spec.id
