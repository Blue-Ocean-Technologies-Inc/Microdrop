# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""News publishers, Qt-free: who publishes a feed (name, logo, colour,
where its posts come from), the drawer section showing it, and the watcher
turning a newly arrived post into an alert (a toast, a bell count, a "new"
mark) like a notification's.

The drawer shows one news section per publisher, in ``default_publishers()``
order; nothing here is particular to any one of them.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import (
    Any,
    Bool,
    HasTraits,
    Instance,
    Int,
    Property,
    Set,
    Str,
    observe,
)

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
from microdrop_application.consts import scibots_icon_path
from notifications.consts import SEVERITY_INFO

# Microdrop style imports.
from microdrop_style.colors import PRIMARY_COLOR, SECONDARY_SHADE

# Local imports.
from .ux_consts import CATEGORY_FEED, NEWS_GLYPH, NEWS_SECTION_PREFIX, SectionStyle
from .ux_models import UxNotification, UxPaneModel

#: The placeholder Blue Ocean Technologies feed: samples, not a real feed.
SAMPLE_BLUE_OCEAN_FEED_PATH = Path(__file__).with_name("sample_blue_ocean_feed.json")


class NewsPublisher(HasTraits):
    """Who publishes a news feed, and how the drawer shows it."""

    #: Stable id, e.g. "scibots".
    id = Str()

    #: The section's title: short, as the header has little room.
    short_name = Str()

    #: The full name: the header's tooltip and the toasts' kicker.
    full_name = Str()

    #: Its logo (a picture's path); "" draws ``monogram`` on a disc.
    logo = Str()
    monogram = Str()

    #: Its colour: the monogram's disc, the toasts' stripe, the bell's.
    accent = Str()

    #: Its feed file, and whether MicroDrop's release notes join it.
    feed_path = Str()
    with_releases = Bool(False)

    #: Where a pushed sample post links to.
    home_url = Str()

    #: Whether its section starts open.
    starts_expanded = Bool(False)

    #: How its section header looks.
    section_style = Property(observe="accent, logo, monogram, full_name")

    def _get_section_style(self):
        return SectionStyle(
            NEWS_GLYPH, self.accent, self.logo, self.monogram, self.full_name
        )

    def make_section(self, order):
        """Its drawer section at ``order``, its feed loaded."""
        sources = [JsonFileFeedSource(path=self.feed_path)]

        if self.with_releases:
            sources.append(ChangelogFeedSource())

        controller = SciBotsFeedController(sources=sources)
        controller.reload()

        return NewsSection(
            publisher=self,
            controller=controller,
            id=f"{NEWS_SECTION_PREFIX}{self.id}",
            title=self.short_name,
            order=order,
            expanded=self.starts_expanded,
        )


class NewsSection(SciBotsFeedSection):
    """A publisher's feed as a drawer section, with its sub-sections' state
    kept for the session and a "N new" chip while new posts are unseen or
    marked new."""

    #: Whose feed it shows.
    publisher = Instance(NewsPublisher)

    #: Group ids whose sub-section is collapsed.
    collapsed_groups = Set(Str)

    #: Group ids whose sub-section shows all its posts, not only the
    #: newest.
    expanded_groups = Set(Str)

    #: Posts arrived and not yet seen in the drawer, or seen and still
    #: marked new.
    new_count = Int()

    #: How its header looks: the publisher's.
    section_style = Property(observe="publisher.section_style")

    def _get_section_style(self):
        return self.publisher.section_style

    @observe("controller.model.summary, new_count")
    def _follow_summary(self, event):
        summary = self.controller.model.summary

        self.summary = (
            f"{self.new_count} new · {summary}" if self.new_count else summary
        )


class FeedAlertWatcher(HasTraits):
    """Alerts for each post a news section's feed gains: a push, the
    creator's Send, or a reload that brings a post not seen before. An
    updated post does not alert."""

    #: The section watched; its controller's model lists the posts.
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
        publisher = self.section.publisher

        self._known_ids |= {post.id for post in posts}

        for post in new:
            entry = UxNotification(
                key=(CATEGORY_FEED, self.section.id, post.id),
                title=post.title,
                detail=post.summary,
                severity=SEVERITY_INFO,
                category=CATEGORY_FEED,
                source=f"{publisher.full_name} · {post.kind.title()}",
                feed_post_id=post.id,
                feed_section_id=self.section.id,
                feed_accent=publisher.accent,
                feed_logo=publisher.logo,
                feed_monogram=publisher.monogram,
            )
            self.pane_model.feed_alerts.append(entry)

            if self.offer is not None:
                self.offer(entry)

    @observe("pane_model:feed_alerts.items.[unread, is_new]")
    def _count_new(self, event):
        self.section.new_count = sum(
            entry.feed_section_id == self.section.id and (entry.unread or entry.is_new)
            for entry in self.pane_model.feed_alerts
        )


def default_publishers():
    """The news publishers, in the drawer's order.

    Sci-Bots' feed is the notifications_pane demo's, with MicroDrop's release
    notes. Blue Ocean Technologies has no feed yet: its posts are labelled
    samples, and its logo a monogram until there is one to ship.
    """
    return [
        NewsPublisher(
            id="scibots",
            short_name="Sci-Bots",
            full_name="Sci-Bots",
            logo=str(scibots_icon_path),
            accent=PRIMARY_COLOR,
            feed_path=str(DEFAULT_FEED_PATH),
            with_releases=True,
            home_url="https://www.linkedin.com/company/sci-bots-inc./posts/",
            starts_expanded=True,
        ),
        NewsPublisher(
            id="blue_ocean",
            short_name="Blue Ocean",
            full_name="Blue Ocean Technologies",
            monogram="BO",
            accent=SECONDARY_SHADE[700],
            feed_path=str(SAMPLE_BLUE_OCEAN_FEED_PATH),
            home_url="https://github.com/Blue-Ocean-Technologies-Inc/Microdrop",
        ),
    ]
