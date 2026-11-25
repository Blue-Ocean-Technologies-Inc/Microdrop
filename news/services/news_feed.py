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
local-only ones on this machine, and MicroDrop's release notes.

At launch the deferred loader reads them on its worker thread
(``prepare_news_feed``, the plugin's ``DeferredPlugin.prepare``), so the GUI
thread only shows what was read.
"""

# Local imports.
from ..controllers.feed_controller import SciBotsFeedController, read_feed_sources
from ..models.news_section import NewsSection
from .feed_sources import feed_file_sources
from .releases import ChangelogFeedSource


def news_feed_sources():
    """Where the News section's posts come from."""
    return [*feed_file_sources(), ChangelogFeedSource()]


def prepare_news_feed():
    """Read and validate the feed file and parse CHANGELOG.md into a
    LoadedFeed, on any thread: plain data, no Qt and no shown model."""
    return read_feed_sources(news_feed_sources())


def make_news_section(loaded=None):
    """The News section, open, showing ``loaded`` (a LoadedFeed already
    read), or its feed read now."""
    controller = SciBotsFeedController(sources=news_feed_sources())

    if loaded is None:
        controller.reload()

    else:
        controller.show_loaded(loaded)

    return NewsSection(controller=controller, expanded=True)
