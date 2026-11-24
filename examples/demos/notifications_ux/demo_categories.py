# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notification categories the demo's stand-in plugins declare.

Each block is what its owner's ``consts.py`` would hold once ported: the
category ids its messages name, and the specs it contributes to
NOTIFICATION_CATEGORIES.
"""

# Local imports.
from .settings_models import (
    TONE_ALERT,
    TONE_COMPLETION,
    TONE_NONE,
    TONE_SOFT,
    NotificationCategorySpec,
)

# ---------------------------------------------------------------------------
# Protocol (pluggable_protocol_tree/consts.py)
# ---------------------------------------------------------------------------
PROTOCOL_GROUP = "Protocol"
PROTOCOL_STEP_COMPLETED = "protocol.step_completed"
PROTOCOL_STARTED = "protocol.started"
PROTOCOL_FINISHED = "protocol.finished"
PROTOCOL_NEEDS_INPUT = "protocol.needs_input"

PROTOCOL_CATEGORIES = [
    NotificationCategorySpec(
        id=PROTOCOL_STEP_COMPLETED,
        group=PROTOCOL_GROUP,
        label="Step completed",
        description="Each step of a run as it completes; frequent.",
        popup=False,
        tone=TONE_NONE,
    ),
    NotificationCategorySpec(
        id=PROTOCOL_STARTED,
        group=PROTOCOL_GROUP,
        label="Protocol started",
        description="A run begins.",
        tone=TONE_SOFT,
    ),
    NotificationCategorySpec(
        id=PROTOCOL_FINISHED,
        group=PROTOCOL_GROUP,
        label="Protocol finished",
        description="A run ended, with its report and video.",
        tone=TONE_COMPLETION,
    ),
    NotificationCategorySpec(
        id=PROTOCOL_NEEDS_INPUT,
        group=PROTOCOL_GROUP,
        label="Protocol paused or needs input",
        description="A run waits for you, e.g. to insert a chip.",
        tone=TONE_ALERT,
        critical=True,
    ),
]

# ---------------------------------------------------------------------------
# DropBot (dropbot_status_and_controls/consts.py)
# ---------------------------------------------------------------------------
DROPBOT_CONNECTION = "dropbot.connection"
DROPBOT_MAINTENANCE = "dropbot.maintenance"

DROPBOT_CATEGORIES = [
    NotificationCategorySpec(
        id=DROPBOT_CONNECTION,
        group="DropBot",
        label="Connection",
        description="The DropBot connects, disconnects or cannot be reached.",
        tone=TONE_ALERT,
        critical=True,
    ),
    NotificationCategorySpec(
        id=DROPBOT_MAINTENANCE,
        group="DropBot",
        label="Maintenance reminders",
        description="Calibration and self tests that are due.",
        tone=TONE_SOFT,
    ),
]

# ---------------------------------------------------------------------------
# Plugins (plugin_management/consts.py)
# ---------------------------------------------------------------------------
PLUGINS_UPDATES = "plugins.updates"
PLUGINS_LOAD_FAILED = "plugins.load_failed"

PLUGINS_CATEGORIES = [
    NotificationCategorySpec(
        id=PLUGINS_UPDATES,
        group="Plugins",
        label="Updates available",
        description="Newer versions of installed plugins, and updating them.",
        tone=TONE_SOFT,
    ),
    NotificationCategorySpec(
        id=PLUGINS_LOAD_FAILED,
        group="Plugins",
        label="Load failures",
        description="A plugin could not start.",
        tone=TONE_ALERT,
        critical=True,
    ),
]

# ---------------------------------------------------------------------------
# News (the news feed's consts.py)
# ---------------------------------------------------------------------------
NEWS_NEW_POSTS = "news.new_posts"

NEWS_CATEGORIES = [
    NotificationCategorySpec(
        id=NEWS_NEW_POSTS,
        group="News",
        label="New posts",
        description="A newsletter, announcement or release note arrives.",
        tone=TONE_SOFT,
    ),
]
