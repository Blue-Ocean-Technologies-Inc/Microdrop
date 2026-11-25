# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The News section with its feed loaded: the feed file's posts, the
local-only ones on this machine, and MicroDrop's release notes."""

# Local imports.
from ..controllers.feed_controller import SciBotsFeedController
from ..models.news_section import NewsSection
from .feed_sources import feed_file_sources
from .releases import ChangelogFeedSource


def make_news_section():
    """The News section, open, its feed loaded."""
    controller = SciBotsFeedController(
        sources=[*feed_file_sources(), ChangelogFeedSource()]
    )
    controller.reload()

    return NewsSection(controller=controller, expanded=True)
