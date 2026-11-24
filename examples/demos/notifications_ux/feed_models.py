# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed in the prototype, Qt-free: its drawer section with the
session's sub-section state and its "N new" chip, and the watcher that
turns a newly arrived post into an alert (a toast, a bell count, a "new"
mark) like a notification's.
"""

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, Int, List, Set, Str, observe

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_section import (
    SciBotsFeedSection,
)
from notifications.consts import SEVERITY_INFO

# Local imports.
from .ux_consts import CATEGORY_FEED, FEED_SECTION_TITLE
from .ux_models import UxNotification, UxPaneModel

#: The kicker before a feed post's kind on its toast: "Sci-Bots · Newsletter".
FEED_KICKER = "Sci-Bots"


class UxFeedSection(SciBotsFeedSection):
    """The feed section, with its sub-sections' state kept for the session
    and a "N new" chip while new posts are unseen or marked new."""

    title = FEED_SECTION_TITLE

    #: Group ids whose sub-section is collapsed.
    collapsed_groups = Set(Str)

    #: Group ids whose sub-section shows all its posts, not only the
    #: newest.
    expanded_groups = Set(Str)

    #: Posts arrived and not yet seen in the drawer, or seen and still
    #: marked new.
    new_count = Int()

    @observe("controller.model.summary, new_count")
    def _follow_summary(self, event):
        summary = self.controller.model.summary

        self.summary = (
            f"{self.new_count} new · {summary}" if self.new_count else summary
        )


class FeedAlertWatcher(HasTraits):
    """Alerts for each post the feed gains: a push, the creator's Send, or
    a reload that brings a post not seen before. An updated post does not
    alert."""

    #: The feed's section; its controller's model lists the posts.
    section = Instance(UxFeedSection)

    #: The drawer's model, whose ``feed_alerts`` hold the alerts.
    pane_model = Instance(UxPaneModel)

    #: ``offer(entry)``: the toast controller's, to pop an alert up.
    offer = Any()

    #: Ids of the posts known so far: those at start-up count as seen.
    _known_ids = Set(Str)

    #: The alerts' posts' ids, for the "new" marks.
    alerted_ids = List(Str)

    def traits_init(self):
        self._known_ids = {post.id for post in self.section.controller.model.posts}

    @observe("section:controller:model:posts")
    def _alert_new_posts(self, event):
        posts = self.section.controller.model.posts
        new = [post for post in posts if post.id not in self._known_ids]

        self._known_ids |= {post.id for post in posts}

        for post in new:
            entry = UxNotification(
                key=(CATEGORY_FEED, post.id),
                title=post.title,
                detail=post.summary,
                severity=SEVERITY_INFO,
                category=CATEGORY_FEED,
                source=f"{FEED_KICKER} · {post.kind.title()}",
                feed_post_id=post.id,
            )
            self.pane_model.feed_alerts.append(entry)

            if self.offer is not None:
                self.offer(entry)

    @observe("pane_model:feed_alerts.items.[unread, is_new]")
    def _count_new(self, event):
        alerts = [
            entry
            for entry in self.pane_model.feed_alerts
            if entry.unread or entry.is_new
        ]

        self.alerted_ids = [entry.feed_post_id for entry in alerts]
        self.section.new_count = len(alerts)
