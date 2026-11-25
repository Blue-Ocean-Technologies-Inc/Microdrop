# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What is new in the news, and how loud: a launch toasts at most twice
(the release, and a summary of the rest), a later arrival on its own; what
was seen is kept across launches, and the old What's New dialog's cache
counts as notes already shown."""

# Standard library imports.
import json

# Microdrop package imports.
from news.controllers.feed_controller import SciBotsFeedController
from news.controllers.news_alerts import (
    ROLE_POST,
    ROLE_RELEASE,
    ROLE_SUMMARY,
    SUMMARY_KEY,
    NewsAlertsController,
    plan_launch_alerts,
    release_version,
)
from news.models.news_section import NewsSection
from news.services.feed_sources import JsonFileFeedSource
from news.services.seen_state import NewsSeenState, changelog_has_version

RELEASE = "release-v1.51.0"


def _popped(plans):
    return [(plan.key, plan.role) for plan in plans if plan.pop_up]


def test_a_first_run_toasts_the_release_and_one_summary():
    plans = plan_launch_alerts([RELEASE, "a", "b", "c"], RELEASE)

    assert _popped(plans) == [(RELEASE, ROLE_RELEASE), (SUMMARY_KEY, ROLE_SUMMARY)]

    # Every post is marked new and counted; the summary counts nothing.
    counted = [plan.key for plan in plans if plan.counted]
    summary = next(plan for plan in plans if plan.role == ROLE_SUMMARY)

    assert counted == [RELEASE, "a", "b", "c"]
    assert summary.covers == ("a", "b", "c")


def test_an_upgrade_alone_toasts_only_the_release():
    assert _popped(plan_launch_alerts([RELEASE], RELEASE)) == [(RELEASE, ROLE_RELEASE)]


def test_a_single_other_post_toasts_as_itself():
    plans = plan_launch_alerts(["a"])

    assert _popped(plans) == [("a", ROLE_POST)]
    assert all(plan.role != ROLE_SUMMARY for plan in plans)


def test_nothing_new_raises_nothing():
    assert plan_launch_alerts([]) == []


def test_release_version_reads_a_release_post_id():
    assert release_version(RELEASE) == "1.51.0"
    assert release_version("newsletter-15") == ""


def test_seen_state_persists_and_records_release_notes(tmp_path):
    path = tmp_path / "news_state.json"
    state = NewsSeenState(path=str(path))
    state.load()

    assert not state.existed

    state.mark_seen(["a", RELEASE], "1.51.0")
    again = NewsSeenState(path=str(path))
    again.load()

    assert again.existed
    assert again.seen_post_ids == {"a", RELEASE}
    assert again.release_notes_shown_version == "1.51.0"
    assert json.loads(path.read_text())["seen_post_ids"] == ["a", RELEASE]


def test_a_first_run_takes_notes_the_old_dialog_showed(tmp_path):
    cache = tmp_path / ".previous_changelog"
    cache.write_text("# Changelog\n\n## v1.51.0 (2026-11-20)\n\n- x\n")
    state = NewsSeenState(
        path=str(tmp_path / "news_state.json"), previous_changelog_path=str(cache)
    )
    state.load("1.51.0")

    assert state.release_notes_shown_version == "1.51.0"
    assert changelog_has_version(cache.read_text(), "1.51.0")
    assert not changelog_has_version(cache.read_text(), "1.52.0")


def test_showing_notes_refreshes_the_old_dialogs_cache(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    cache = tmp_path / ".previous_changelog"
    changelog.write_text("## v1.52.0\n")
    state = NewsSeenState(
        path=str(tmp_path / "s.json"),
        changelog_path=str(changelog),
        previous_changelog_path=str(cache),
    )

    state.mark_seen(["release-v1.52.0"], "1.52.0")

    assert cache.read_text() == "## v1.52.0\n"


def _section(tmp_path, posts):
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({"posts": posts}), encoding="utf-8")
    controller = SciBotsFeedController(sources=[JsonFileFeedSource(path=str(feed))])
    controller.reload()

    return NewsSection(controller=controller), feed


def _post(number):
    return {
        "id": f"post-{number}",
        "title": f"Post {number}",
        "date": f"2026-11-{10 + number:02d}",
        "kind": "post",
        "url": f"https://example.com/{number}",
    }


def test_launch_then_a_later_arrival_and_seen_recording(tmp_path):
    section, feed = _section(tmp_path, [_post(1), _post(2), _post(3)])
    state = NewsSeenState(path=str(tmp_path / "state.json"))
    state.mark_seen(["post-1"])
    state.existed = True
    alerts = NewsAlertsController(section=section, state=state)

    alerts.raise_launch_alerts()

    popped = [alert.key for alert in section.alerts if alert.pop_up]

    assert {alert.key for alert in section.alerts} == {"post-2", "post-3", SUMMARY_KEY}
    assert popped == [SUMMARY_KEY]

    # Reading the summary records every post it stands for.
    next(a for a in section.alerts if a.key == SUMMARY_KEY).unread = False

    assert state.seen_post_ids == {"post-1", "post-2", "post-3"}

    # A post arriving later in the session toasts on its own.
    feed.write_text(json.dumps({"posts": [_post(n) for n in (1, 2, 3, 4)]}))
    section.controller.reload()
    arrival = section.alerts[-1]

    assert (arrival.key, arrival.pop_up) == ("post-4", True)

    arrival.dismissed = True

    assert "post-4" in state.seen_post_ids
