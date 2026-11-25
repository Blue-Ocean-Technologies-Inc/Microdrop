# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""NewsPlugin — Blue Ocean Technologies' and Sci-Bots' news and MicroDrop's
release notes as the News section of the notifications drawer.

A deferred frontend plugin: it starts after the main window has painted,
reads the feed file shipped in ``news/resources/feed.json`` (and, on one
machine, ``news/resources/local/local_posts.json``) and CHANGELOG.md, and
contributes the section through ``notifications.consts`` alone. Posts not
seen before are new: they are marked in the drawer, and a launch toasts at
most twice, once for this version's release notes and once for the rest.
What has been seen is kept in ``news_state.json`` in the notifications data
folder (``notifications.consts.notifications_data_dir``).

While this plugin is loaded, MicroDrop does not open its What's New dialog
at launch: the release notes are the What's new sub-section and its toast.

Add a post by hand by editing ``feed.json`` (see ``feed.schema.json`` beside
it), or with the feed creator::

    python -m news.feed_creator [FEED.json] [--theme light|dark]
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from envisage.api import Plugin
from traits.api import Any, List
from traits.etsconfig.api import ETSConfig

# Microdrop package imports.
from microdrop_application.consts import CHANGELOG_PATH, PREVIOUS_CHANGELOG_FILENAME
from notifications.consts import (
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_SECTIONS,
    notifications_data_dir,
)

# Microdrop utils imports.
from microdrop_utils.json_state_file import move_state_file

# Local imports.
from .consts import NEWS_CATEGORIES, NEWS_PLUGIN_ID, NEWS_STATE_FILENAME, PKG_name

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NewsPlugin(Plugin):
    """Contributes the News section and raises its alerts."""

    id = NEWS_PLUGIN_ID
    name = f"{PKG_name} Plugin"

    #: The News section.
    sections = List(contributes_to=NOTIFICATION_SECTIONS)

    #: Its kind of notification.
    notification_categories = List(
        NEWS_CATEGORIES, contributes_to=NOTIFICATION_CATEGORIES
    )

    #: Raises the alerts and records what has been seen.
    _alerts = Any()

    def _sections_default(self):
        from .services.news_feed import make_news_section

        return [make_news_section()]

    def start(self):
        """Load what has been seen, and mark what has not."""
        from .controllers.news_alerts import NewsAlertsController, release_version
        from .services.seen_state import NewsSeenState

        section = self.sections[0]
        home = Path(ETSConfig.application_home)
        state_path = notifications_data_dir() / NEWS_STATE_FILENAME
        releases = [
            p.id for p in section.controller.model.posts if release_version(p.id)
        ]

        # It used to sit in the application home itself.
        move_state_file(home / NEWS_STATE_FILENAME, state_path)

        state = NewsSeenState(
            path=str(state_path),
            changelog_path=str(CHANGELOG_PATH),
            previous_changelog_path=str(home / PREVIOUS_CHANGELOG_FILENAME),
        )
        state.load(release_version(releases[0]) if releases else "")

        self._alerts = NewsAlertsController(section=section, state=state)
        self._alerts.raise_launch_alerts()

    def stop(self):
        self._alerts = None
