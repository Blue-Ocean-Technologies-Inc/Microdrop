# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""News, Qt-free: Blue Ocean Technologies' and Sci-Bots' combined feed as a
drawer section, contributed through the notifications plugin's public
section API alone (``notifications.consts``): its look, its contents
factory, ``alert_widget`` for reveals, and a SectionAlert for each post
that arrives, which the drawer pops up, counts on the bell and marks new.
"""

# Enthought library imports.
from traits.api import Int, Set, Str, observe

# Microdrop package imports.
from examples.demos.notifications_pane.sci_bots_feed_controller import (
    SciBotsFeedController,
)
from examples.demos.notifications_pane.sci_bots_feed_groups import group_for
from examples.demos.notifications_pane.sci_bots_feed_releases import (
    ChangelogFeedSource,
)
from examples.demos.notifications_pane.sci_bots_feed_section import (
    SciBotsFeedSection,
)
from examples.demos.notifications_pane.sci_bots_feed_sources import (
    demo_feed_sources,
)
from notifications.consts import SectionAlert

# Microdrop style imports.
from microdrop_style.colors import PRIMARY_SHADE
from microdrop_style.icons.logos import BLUE_OCEAN_SCI_BOTS_LOGO

# Local imports.
from .demo_categories import NEWS_NEW_POSTS

NEWS_SECTION_ID = "notifications_ux_demo.news"
NEWS_SECTION_TITLE = "News"
NEWS_SECTION_ORDER = 10

#: News's header accent, ``(light theme, dark theme)``.
NEWS_ACCENT = ("#227938", PRIMARY_SHADE[400])

#: Who a post is from when it does not say: the feed file is Sci-Bots'.
NEWS_DEFAULT_SOURCE = "Sci-Bots"


class NewsSection(SciBotsFeedSection):
    """The combined feed as the drawer's News section, with its
    sub-sections' state kept for the session and a "N new" chip while new
    posts are unseen or marked new."""

    id = NEWS_SECTION_ID
    title = NEWS_SECTION_TITLE
    order = NEWS_SECTION_ORDER
    glyph = "newspaper"
    accent = NEWS_ACCENT
    logo = str(BLUE_OCEAN_SCI_BOTS_LOGO)

    #: At natural height, like every section of the column.
    max_height = 0

    #: Group ids whose sub-section is collapsed.
    collapsed_groups = Set(Str)

    #: Group ids whose sub-section shows all its posts, not only the newest.
    expanded_groups = Set(Str)

    #: Posts arrived and not yet seen, or seen and still marked new.
    new_count = Int()

    #: Ids of the posts known so far: those at start-up count as seen.
    _known_ids = Set(Str)

    def traits_init(self):
        self._known_ids = {post.id for post in self.controller.model.posts}

    def build_contents(self, parent):
        """The feed's sub-sections, at natural height."""
        from .feed_column import FeedColumn

        return FeedColumn(self, parent)

    def alert_widget(self, contents, alert):
        """The post's frame, its sub-section opened up."""
        return contents.frame_for(alert.key)

    def new_post_ids(self):
        """Ids of the posts marked new."""
        return {alert.key for alert in self.alerts if alert.unread or alert.is_new}

    @observe("controller:model:posts")
    def _alert_new_posts(self, event):
        """An alert per post the feed gains: a push, the creator's Send, or a
        reload bringing one not seen before. An updated post does not."""
        posts = self.controller.model.posts
        new = [post for post in posts if post.id not in self._known_ids]

        self._known_ids |= {post.id for post in posts}

        for post in new:
            source = post.source_label or NEWS_DEFAULT_SOURCE
            group = group_for(post)

            self.alerts.append(
                SectionAlert(
                    key=post.id,
                    title=post.title,
                    detail=post.summary,
                    source=f"{source} · {post.kind.title()}",
                    accent=group.accent if group is not None else (),
                    category_id=NEWS_NEW_POSTS,
                )
            )

    @observe("alerts.items.[unread, is_new]")
    def _count_new(self, event):
        self.new_count = len(self.new_post_ids())

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
        sources=[*demo_feed_sources(), ChangelogFeedSource()]
    )
    controller.reload()

    return NewsSection(controller=controller, expanded=True)
