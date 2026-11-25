# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The News section's alerts, Qt-free: which posts are new, and how many
toasts they make.

At launch every post not in the seen state is new, and marked so (on a
first run, releases older than this one are history, not news). A first
run or the first launch after an upgrade has many at once, so they make at
most two toasts: one for this version's release notes, and one summing up
the rest (a single other post toasts as itself). A post arriving later in
the session (a reload) toasts on its own. A post is recorded as seen once
its alert is read (the News section seen in the open drawer) or its toast
dismissed; the release notes as shown with it.
"""

# Standard library imports.
from collections import namedtuple

# Enthought library imports.
from traits.api import Bool, Dict, HasTraits, Instance, Set, Str, observe

# Microdrop package imports.
from notifications.consts import SectionAlert

# Local imports.
from ..consts import (
    NEWS_DEFAULT_SOURCE,
    NEWS_NEW_POSTS,
    RELEASE_TOAST_TEMPLATE,
    SUMMARY_TITLES,
    SUMMARY_TOAST_TEMPLATE,
)
from ..models.feed_groups import group_for
from ..models.news_section import NewsSection
from ..services.seen_state import NewsSeenState

#: A release post's id is this prefix and its version.
RELEASE_ID_PREFIX = "release-v"

#: The key of the alert summing up a launch's other new posts.
SUMMARY_KEY = "news.summary"

#: What a launch raises for its new posts: an alert per post, which pops up
#: or not and counts on the bell or not, and which post ids it stands for.
AlertPlan = namedtuple("AlertPlan", "key covers pop_up counted role")

ROLE_POST = "post"
ROLE_RELEASE = "release"
ROLE_SUMMARY = "summary"


def release_version(post_id):
    """The version a release post's id names; "" for any other post."""

    if post_id.startswith(RELEASE_ID_PREFIX):
        return post_id[len(RELEASE_ID_PREFIX) :]

    return ""


def plan_launch_alerts(new_ids, release_id=""):
    """The alerts for a launch's new posts ``new_ids`` (newest first), with
    ``release_id`` this version's release post if its notes are new.

    Every new post gets an alert marking it new and counting on the bell.
    Only two pop up at most: the release's, and either the one other new
    post or, for several, a summary alert counting nothing itself."""
    others = [post_id for post_id in new_ids if post_id != release_id]
    plans = [
        AlertPlan(post_id, (post_id,), len(others) == 1, True, ROLE_POST)
        for post_id in others
    ]

    if release_id:
        plans.insert(0, AlertPlan(release_id, (release_id,), True, True, ROLE_RELEASE))

    if len(others) > 1:
        plans.append(AlertPlan(SUMMARY_KEY, tuple(others), True, False, ROLE_SUMMARY))

    return plans


class NewsAlertsController(HasTraits):
    """Raises the News section's alerts and records what has been seen."""

    #: The section whose alerts these are.
    section = Instance(NewsSection)

    #: What has been seen, across launches.
    state = Instance(NewsSeenState)

    #: The post ids each alert stands for, by the alert's key.
    _covers = Dict(Str, Set(Str))

    #: Posts known in this session: a later post not among them is an
    #: arrival.
    _known_ids = Set(Str)

    #: Whether the launch's alerts are up.
    _launched = Bool(False)

    def raise_launch_alerts(self):
        """Mark every unseen post new; toast the release and a summary."""
        posts = self._posts()
        release = self._newest_release(posts)
        version = release_version(release.id) if release else ""

        # Notes already shown (by the old dialog, before this state existed).
        if release is not None and self.state.release_notes_shown_version == version:
            self.state.mark_seen([release.id])

        # A first run: releases older than this one predate it, history.
        if not self.state.existed:
            older = [p.id for p in posts if release_version(p.id) and p is not release]
            self.state.mark_seen(older)

        new_ids = [post.id for post in posts if not self.state.is_seen(post.id)]
        release_id = release.id if release is not None and release.id in new_ids else ""

        self._known_ids = {post.id for post in posts}
        self._launched = True

        self._raise(plan_launch_alerts(new_ids, release_id))

    # ------------------------------------------------------------------ #
    # Following the section                                               #
    # ------------------------------------------------------------------ #

    @observe("section:controller:model:posts")
    def _toast_later_arrivals(self, event):
        """A post the session had not seen yet (a reload) toasts alone."""

        if not self._launched:
            return

        arrivals = [p.id for p in self._posts() if p.id not in self._known_ids]
        self._known_ids |= set(arrivals)

        fresh = [post_id for post_id in arrivals if not self.state.is_seen(post_id)]
        self._raise([AlertPlan(i, (i,), True, True, ROLE_POST) for i in fresh])

    @observe("section:alerts:items:unread")
    def _record_read(self, event):

        if not event.new:
            self._record_seen(event.object)

    @observe("section:alerts:items:dismissed")
    def _record_dismissed(self, event):
        self._record_seen(event.object)

    def _record_seen(self, alert):
        covers = self._covers.get(alert.key, {alert.key})
        versions = [release_version(post_id) for post_id in covers]

        self.state.mark_seen(covers, next((v for v in versions if v), ""))

    # ------------------------------------------------------------------ #
    # Private interface                                                   #
    # ------------------------------------------------------------------ #

    def _raise(self, plans):
        posts = {post.id: post for post in self._posts()}
        alerts = []

        for plan in plans:
            self._covers[plan.key] = set(plan.covers)
            alerts.append(self._alert(plan, posts))

        self.section.alerts.extend(alerts)

    def _alert(self, plan, posts):
        """The SectionAlert for ``plan``: a post's own, the release's, or
        the summary of several."""

        if plan.role == ROLE_SUMMARY:
            covered = [posts[post_id] for post_id in plan.covers]
            titles = [f"• {post.title}" for post in covered[:SUMMARY_TITLES]]
            title = SUMMARY_TOAST_TEMPLATE.format(
                count=len(covered), source=NEWS_DEFAULT_SOURCE
            )

            return SectionAlert(
                key=plan.key,
                title=title,
                detail="\n".join(titles),
                source=NEWS_DEFAULT_SOURCE,
                category_id=NEWS_NEW_POSTS,
                pop_up=plan.pop_up,
                counted=plan.counted,
            )

        post = posts[plan.key]
        group = group_for(post)
        title = post.title

        if plan.role == ROLE_RELEASE:
            title = RELEASE_TOAST_TEMPLATE.format(version=release_version(post.id))

        return SectionAlert(
            key=post.id,
            title=title,
            detail=post.summary,
            source=f"{post.source_label or NEWS_DEFAULT_SOURCE} · {post.kind.title()}",
            accent=group.accent if group is not None else (),
            category_id=NEWS_NEW_POSTS,
            pop_up=plan.pop_up,
            counted=plan.counted,
        )

    def _posts(self):
        return list(self.section.controller.model.posts)

    @staticmethod
    def _newest_release(posts):
        releases = [post for post in posts if release_version(post.id)]

        return releases[0] if releases else None
