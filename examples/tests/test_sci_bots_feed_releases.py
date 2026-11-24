# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Recent releases as feed posts: the changelog parsed as commitizen
writes it, releases with features preferred, summaries taken verbatim
from the changelog and capped, and teased by their first item."""

# Standard library imports.
import datetime

# Third-party imports.
import pytest

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_model import (
    FeedPost,
    summary_teaser,
)
from examples.demos.notifications_pane.sci_bots_feed_releases import (
    DEFAULT_CHANGELOG_PATH,
    ChangelogFeedSource,
    clean_entry,
    parse_changelog,
    release_post,
    select_releases,
)
from examples.demos.notifications_pane.sci_bots_feed_schema import (
    parse_feed_payload,
)
from examples.demos.notifications_pane.sci_bots_feed_sources import FeedLoadError

LINK = "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop"


def _entry(text, sha="5a4ae80"):
    return f"- {text} ([`{sha}`]({LINK}/commit/{sha}0000))"


CHANGELOG = "\n".join(
    [
        f"## [v1.4.1]({LINK}/releases/tag/v1.4.1) (2026-11-20)",
        "",
        "### Fix",
        "",
        _entry("**viewer**: keep the zoom"),
        "",
        f"## [v1.4.0]({LINK}/releases/tag/v1.4.0) (2026-11-18)",
        "",
        "### Feat",
        "",
        *[_entry(f"**viewer**: feature {number}") for number in range(1, 8)],
        "",
        "### Fix",
        "",
        _entry("a fix"),
        "",
        "## Unreleased notes",
        "- not part of any release",
        "",
        "## [v1.3.0] (2026-13-40)",
        "### Feat",
        "- bad date heading",
        "",
        "## v1.2.0 (2026-11-01)",
        "### Feat",
        _entry("**plugins**: `hot` reload with [docs](https://x.com/docs)"),
        "### Docs",
        _entry("only docs"),
        "",
        "## v1.1.0 (2026-10-01)",
        "### Feat",
        _entry("old feature"),
    ]
)


def _versions(releases):
    return [release.version for release in releases]


def test_releases_are_parsed_and_malformed_headings_skipped():
    releases = parse_changelog(CHANGELOG)

    assert _versions(releases) == ["1.4.1", "1.4.0", "1.2.0", "1.1.0"]
    assert releases[1].date == datetime.date(2026, 11, 18)
    assert len(releases[1].sections["Feat"]) == 7
    assert releases[2].sections["Docs"] == ["only docs"]


def test_entries_lose_markdown_and_commit_links():
    assert clean_entry(
        f"**plugins**: `hot` reload with [docs](https://x.com) ([`abc1234`]({LINK}))"
    ) == ("plugins: hot reload with docs")


def test_releases_with_features_come_first():
    releases = parse_changelog(CHANGELOG)

    assert _versions(select_releases(releases)) == ["1.4.0", "1.2.0", "1.1.0"]
    assert _versions(select_releases(releases, need_features=False)) == [
        "1.4.1",
        "1.4.0",
        "1.2.0",
    ]


def test_too_few_feature_releases_are_filled_with_the_newest_others():
    releases = parse_changelog(CHANGELOG)

    assert _versions(select_releases(releases, count=5)) == [
        "1.4.1",
        "1.4.0",
        "1.2.0",
        "1.1.0",
    ]


def test_a_summary_lists_five_features_and_counts_the_rest():
    post = release_post(parse_changelog(CHANGELOG)[1])

    assert post["summary_html"] == (
        "<p>New:</p><ul>"
        + "".join(f"<li>viewer: feature {number}</li>" for number in range(1, 6))
        + "</ul><p>and 2 more</p>"
    )
    assert post["id"] == "release-v1.4.0"
    assert post["title"] == "MicroDrop v1.4.0"
    assert post["url"] == f"{LINK}/releases/tag/v1.4.0"


def test_a_fix_only_release_lists_its_fixes():
    post = release_post(parse_changelog(CHANGELOG)[0])

    assert (
        post["summary_html"] == "<p>Fixes:</p><ul><li>viewer: keep the zoom</li></ul>"
    )


@pytest.mark.parametrize(
    "index, expected", [(1, "viewer: feature 1"), (0, "viewer: keep the zoom")]
)
def test_a_collapsed_release_teases_its_first_item(index, expected):
    post = release_post(parse_changelog(CHANGELOG)[index])

    assert summary_teaser(FeedPost(summary=post["summary"])) == expected


def test_a_teaser_without_a_list_is_the_first_line():
    assert summary_teaser(FeedPost(summary="First line.\nSecond.")) == "First line."
    assert summary_teaser(FeedPost()) == ""


def test_release_posts_are_valid_feed_posts(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG, encoding="utf-8")

    parsed = parse_feed_payload(ChangelogFeedSource(path=str(path)).load())

    assert parsed.errors == []
    assert [post.kind for post in parsed.posts] == ["release"] * 3


@pytest.mark.parametrize("text", [None, "# Changelog\n\nnothing released yet\n"])
def test_a_missing_or_empty_changelog_fails_with_a_reason(tmp_path, text):
    path = tmp_path / "CHANGELOG.md"

    if text is not None:
        path.write_text(text, encoding="utf-8")

    with pytest.raises(FeedLoadError):
        ChangelogFeedSource(path=str(path)).load()


def test_the_real_changelog_parses():
    releases = parse_changelog(DEFAULT_CHANGELOG_PATH.read_text(encoding="utf-8"))
    posts = ChangelogFeedSource().load()

    assert releases
    assert len(posts) == 3
    assert parse_feed_payload(posts).errors == []
