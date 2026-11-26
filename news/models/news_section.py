# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The News section, Qt-free: Blue Ocean Technologies' and Sci-Bots' feed
and MicroDrop's release notes as a drawer section, contributed through the
notifications plugin's public section API alone (``notifications.consts``):
its look, its contents factory, and ``alert_widget`` for reveals. Its
alerts are raised by ``controllers.news_alerts``.
"""

# Enthought library imports.
from traits.api import Instance, Int, Set, Str, observe

# Microdrop package imports.
from notifications.consts import NotificationSection

# Local imports.
from ..consts import (
    NEWS_SECTION_ACCENT,
    NEWS_SECTION_GLYPH,
    NEWS_SECTION_ID,
    NEWS_SECTION_LOGO,
    NEWS_SECTION_ORDER,
    NEWS_SECTION_TITLE,
)
from ..controllers.feed_controller import SciBotsFeedController
from .feed_groups import FEED_GROUPS


class NewsSection(NotificationSection):
    """The feed as the drawer's News section, with its sub-sections' state
    kept for the session and a "N new" chip while new posts are unseen or
    marked new."""

    id = NEWS_SECTION_ID
    title = NEWS_SECTION_TITLE
    order = NEWS_SECTION_ORDER
    glyph = NEWS_SECTION_GLYPH
    accent = NEWS_SECTION_ACCENT
    logo = NEWS_SECTION_LOGO
    expanded = True
    expanded_at_start = True

    #: At natural height, like every section of the column.
    max_height = 0

    #: Fills the feed shown and acts on its cards.
    controller = Instance(SciBotsFeedController, ())

    #: Group ids whose sub-section is collapsed.
    collapsed_groups = Set(Str)

    #: Group ids whose sub-section shows all its posts, not only the newest.
    expanded_groups = Set(Str)

    #: Posts arrived and not yet seen, or seen and still marked new.
    new_count = Int()

    def _factory_default(self):
        return self.build_contents

    def build_contents(self, parent):
        """The feed's sub-sections, at natural height."""
        from ..views.feed_column import FeedColumn

        return FeedColumn(self, parent)

    def set_all_expanded(self, expanded):
        """Unfold (or fold) every sub-section with the drawer's Expand (or
        Collapse) all; the feed's column follows ``collapsed_groups``."""
        self.collapsed_groups = set() if expanded else {spec.id for spec in FEED_GROUPS}

    def alert_widget(self, contents, alert):
        """The post's frame, its sub-section opened up; for an alert summing
        up several posts, the top of the section."""
        return contents.frame_for(alert.key) or contents

    def new_post_ids(self):
        """Ids of the posts marked new: an alert's key is its post's id."""
        return {alert.key for alert in self.alerts if alert.unread or alert.is_new}

    @observe("alerts.items.[unread, is_new]")
    def _count_new(self, event):
        self.new_count = len(self.new_post_ids() & self._post_ids())

    @observe("controller.model.summary, new_count")
    def _follow_summary(self, event):
        summary = self.controller.model.summary
        new = self.new_count

        self.summary = f"{new} new · {summary}" if new else summary

    def _post_ids(self):
        return {post.id for post in self.controller.model.posts}
