# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Sci-Bots Feed as a notifications drawer section, below the Plugins
one.

Its summary follows the feed; its cards are built the first time it is
expanded, through the feed's controller. Its header collapses it, and
expanded it is capped, scrolling inside itself, so it never pushes the
notifications out of view.
"""

# Enthought library imports.
from traits.api import Instance, observe

# Microdrop package imports.
from notifications.consts import NotificationSection

# Local imports.
from .sci_bots_feed_controller import SciBotsFeedController

#: The section's id, header and place: after the Plugins section (order 0).
FEED_SECTION_ID = "demo.sci_bots_feed"
FEED_SECTION_TITLE = "Sci-Bots Feed"
FEED_SECTION_ORDER = 10

#: Most pixels the expanded feed takes in the drawer before it scrolls
#: inside itself: room enough for a lead card, while the notifications
#: below stay in view at the demo's window size.
FEED_SECTION_MAX_HEIGHT = 340


class SciBotsFeedSection(NotificationSection):
    """The feed's posts as a notifications pane section."""

    id = FEED_SECTION_ID
    title = FEED_SECTION_TITLE
    order = FEED_SECTION_ORDER

    max_height = FEED_SECTION_MAX_HEIGHT

    #: Fills the feed shown and acts on its cards.
    controller = Instance(SciBotsFeedController, ())

    def _factory_default(self):
        return self.build_contents

    def build_contents(self, parent):
        """The feed's cards, embedded."""
        from .sci_bots_feed_view import SciBotsFeedView

        return self.controller.edit_traits(
            view=SciBotsFeedView, kind="subpanel", parent=parent
        )

    @observe("controller.model.summary")
    def _follow_summary(self, event):
        self.summary = self.controller.model.summary
