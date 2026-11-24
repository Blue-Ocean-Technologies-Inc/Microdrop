# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""News, Qt-free: Blue Ocean Technologies' and Sci-Bots' combined feed as
the drawer's News section, and the watcher turning a newly arrived post
into an alert (a toast, a bell count, a "new" mark) like a notification's.
"""

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, Int, Set, Str, observe

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_controller import (
    SciBotsFeedController,
)
from examples.demos.notifications_pane.sci_bots_feed_releases import (
    ChangelogFeedSource,
)
from examples.demos.notifications_pane.sci_bots_feed_section import (
    SciBotsFeedSection,
)
from examples.demos.notifications_pane.sci_bots_feed_sources import (
    DEFAULT_FEED_PATH,
    JsonFileFeedSource,
)
from notifications.consts import SEVERITY_INFO

# Local imports.
from .ux_consts import (
    CATEGORY_FEED,
    NEWS_DEFAULT_SOURCE,
    NEWS_SECTION_ID,
    NEWS_SECTION_ORDER,
    NEWS_SECTION_TITLE,
)
from .ux_models import UxNotification, UxPaneModel


class NewsSection(SciBotsFeedSection):
    """The combined feed as the drawer's News section, with its
    sub-sections' state kept for the session and a "N new" chip while new
    posts are unseen or marked new."""

    id = NEWS_SECTION_ID
    title = NEWS_SECTION_TITLE
    order = NEWS_SECTION_ORDER

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


def make_news_section():
    """The News section, open, its feed loaded: the feed file's posts and
    MicroDrop's release notes."""
    controller = SciBotsFeedController(
        sources=[JsonFileFeedSource(path=str(DEFAULT_FEED_PATH)), ChangelogFeedSource()]
    )
    controller.reload()

    return NewsSection(controller=controller, expanded=True)


class FeedAlertWatcher(HasTraits):
    """Alerts for each post the News feed gains: a push, the creator's
    Send, or a reload that brings a post not seen before. An updated post
    does not alert."""

    #: The News section; its controller's model lists the posts.
    section = Instance(NewsSection)

    #: The drawer's model, whose ``feed_alerts`` hold the alerts.
    pane_model = Instance(UxPaneModel)

    #: ``offer(entry)``: the toast controller's, to pop an alert up.
    offer = Any()

    #: Ids of the posts known so far: those at start-up count as seen.
    _known_ids = Set(Str)

    def traits_init(self):
        self._known_ids = {post.id for post in self.section.controller.model.posts}

    @observe("section:controller:model:posts")
    def _alert_new_posts(self, event):
        posts = self.section.controller.model.posts
        new = [post for post in posts if post.id not in self._known_ids]

        self._known_ids |= {post.id for post in posts}

        for post in new:
            source = post.source_label or NEWS_DEFAULT_SOURCE
            entry = UxNotification(
                key=(CATEGORY_FEED, post.id),
                title=post.title,
                detail=post.summary,
                severity=SEVERITY_INFO,
                category=CATEGORY_FEED,
                source=f"{source} · {post.kind.title()}",
                feed_post_id=post.id,
            )
            self.pane_model.feed_alerts.append(entry)

            if self.offer is not None:
                self.offer(entry)

    @observe("pane_model:feed_alerts.items.[unread, is_new]")
    def _count_new(self, event):
        self.section.new_count = sum(
            entry.unread or entry.is_new for entry in self.pane_model.feed_alerts
        )
