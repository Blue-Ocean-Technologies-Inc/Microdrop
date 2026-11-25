# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The news plugin's constants: its id, the News section's look, where the
feed file, its schema and the local-only posts live, its kind of
notification, and the name of its "seen" state file.

The feed file is ``news/resources/feed.json`` (schema beside it); posts kept
on one machine only go in ``news/resources/local/local_posts.json``, which
is never committed. MicroDrop's release cards come from CHANGELOG.md.
"""

# Standard library imports.
from pathlib import Path

# Microdrop package imports.
from notifications.consts import TONE_SOFT, NotificationCategorySpec

# Microdrop style imports.
from microdrop_style.colors import PRIMARY_SHADE
from microdrop_style.icons.logos import BLUE_OCEAN_SCI_BOTS_MARKS

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: The plugin's Envisage id.
NEWS_PLUGIN_ID = f"{PKG}.plugin"

# ---------------------------------------------------------------------------
# The feed's files
# ---------------------------------------------------------------------------
RESOURCES_DIR = Path(__file__).parent / "resources"

#: The feed file shipped with the app, and its JSON Schema.
FEED_PATH = RESOURCES_DIR / "feed.json"
FEED_SCHEMA_PATH = RESOURCES_DIR / "feed.schema.json"

#: Posts kept on this machine only, merged in when the file exists: never
#: committed (excluded locally, not in .gitignore).
LOCAL_POSTS_PATH = RESOURCES_DIR / "local" / "local_posts.json"

#: The "seen" state, in the notifications data folder
#: (``notifications.consts.notifications_data_dir``): written only by this
#: plugin, the moment it changes. It used to sit in the application home
#: itself, and is moved on first use.
NEWS_STATE_FILENAME = "news_state.json"

# ---------------------------------------------------------------------------
# The News section
# ---------------------------------------------------------------------------
NEWS_SECTION_ID = f"{PKG}.section"
NEWS_SECTION_TITLE = "News"
NEWS_SECTION_ORDER = 10
NEWS_SECTION_GLYPH = "newspaper"
NEWS_SECTION_ACCENT = ("#227938", PRIMARY_SHADE[400])
NEWS_SECTION_LOGO = str(BLUE_OCEAN_SCI_BOTS_MARKS)

#: Who a post is from when it does not say: the feed file is Sci-Bots'.
NEWS_DEFAULT_SOURCE = "Sci-Bots"

#: The feed group holding MicroDrop's release notes ("What's new").
RELEASES_GROUP_ID = "releases"

#: Titles of a launch's two toasts: the release, and the other new posts.
RELEASE_TOAST_TEMPLATE = "MicroDrop v{version} · what's new"
SUMMARY_TOAST_TEMPLATE = "{count} new posts from {source}"

#: The summary toast names this many of the new posts' titles.
SUMMARY_TITLES = 2

# ---------------------------------------------------------------------------
# Its kind of notification (NOTIFICATION_CATEGORIES)
# ---------------------------------------------------------------------------
NEWS_NEW_POSTS = f"{PKG}.new_posts"

NEWS_CATEGORIES = [
    NotificationCategorySpec(
        id=NEWS_NEW_POSTS,
        group="News",
        label="New posts",
        description="A newsletter, announcement or MicroDrop release arrives.",
        tone=TONE_SOFT,
    ),
]
