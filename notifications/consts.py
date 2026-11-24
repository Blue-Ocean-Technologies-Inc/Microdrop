# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications plugin's contract: its topics and their payloads, the
pane's section extension point, and the log-forwarding settings.

Any plugin posts a notification by importing only this module::

    from notifications.consts import notification_publisher

    notification_publisher.publish(
        {"title": "Protocol finished", "severity": "success", "category": "protocol"}
    )
"""

# Standard library imports.
import logging
import time
from typing import Annotated, Literal, Union

# Third-party imports.
from pydantic import BaseModel, ConfigDict, Field

# Enthought library imports.
from traits.api import Bool, Callable, HasTraits, Int, Str

# Microdrop style imports.
from microdrop_style.colors import (
    ERROR_COLOR,
    INFO_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
)
from microdrop_style.icons.icons import (
    ICON_CHECK_CIRCLE,
    ICON_ERROR,
    ICON_INFO,
    ICON_WARNING,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher

# This module's package.
PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

#: The plugin's Envisage id: a plugin checks for it before routing the
#: user here, falling back to its own UI when the plugin is not loaded.
NOTIFICATIONS_PLUGIN_ID = f"{PKG}.plugin"

# ---------------------------------------------------------------------------
# Severities, in ascending urgency, with their glyph and colour.
# ---------------------------------------------------------------------------
SEVERITY_INFO = "info"
SEVERITY_SUCCESS = "success"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

SEVERITIES = (SEVERITY_INFO, SEVERITY_SUCCESS, SEVERITY_WARNING, SEVERITY_ERROR)

SEVERITY_GLYPHS = {
    SEVERITY_INFO: ICON_INFO,
    SEVERITY_SUCCESS: ICON_CHECK_CIRCLE,
    SEVERITY_WARNING: ICON_WARNING,
    SEVERITY_ERROR: ICON_ERROR,
}

SEVERITY_COLORS = {
    SEVERITY_INFO: INFO_COLOR,
    SEVERITY_SUCCESS: SUCCESS_COLOR,
    SEVERITY_WARNING: WARNING_COLOR,
    SEVERITY_ERROR: ERROR_COLOR,
}

#: Categories the app posts under; any other string is accepted too.
CATEGORY_GENERAL = "general"
CATEGORY_LOG = "log"
CATEGORY_PLUGINS = "plugins"

# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------
#: Post a notification (NotificationMessage).
NOTIFICATION_POST = "ui/notifications/post"

#: Show the notifications pane, optionally expanding one of its sections
#: (ShowNotificationsPanelRequest).
NOTIFICATIONS_SHOW_PANEL = "ui/notifications/show_panel"

LISTENER_NAME = f"{PKG}_listener"
ACTOR_TOPIC_DICT = {LISTENER_NAME: [NOTIFICATION_POST, NOTIFICATIONS_SHOW_PANEL]}

#: The payload models build their validators on first use, not on import:
#: every plugin imports this module at launch, few post at once.
_DEFERRED_BUILD = ConfigDict(defer_build=True)


class PublishAction(BaseModel):
    """A notification button that publishes ``message`` on ``topic``."""

    model_config = _DEFERRED_BUILD

    kind: Literal["publish"] = "publish"

    #: The button's text, e.g. "Open report".
    label: str = Field(min_length=1)

    topic: str = Field(min_length=1)
    message: str = ""


class OpenPathAction(BaseModel):
    """A notification button that opens a file or folder."""

    model_config = _DEFERRED_BUILD

    kind: Literal["open_path"] = "open_path"

    #: The button's text, e.g. "Show folder".
    label: str = Field(min_length=1)

    path: str = Field(min_length=1)


#: What a notification's button does, as data: never a callable, so a
#: notification can cross the message broker.
NotificationAction = Annotated[
    Union[PublishAction, OpenPathAction], Field(discriminator="kind")
]


class NotificationMessage(BaseModel):
    """One notification, as posted on NOTIFICATION_POST."""

    model_config = _DEFERRED_BUILD

    #: One line, e.g. "Protocol finished".
    title: str = Field(min_length=1)

    #: Optional longer text shown when the entry is expanded; a traceback
    #: shows monospace.
    detail: str = ""

    severity: Literal[SEVERITIES] = SEVERITY_INFO

    #: Free text grouping, e.g. "plugins", "log", "protocol", "hardware".
    category: str = CATEGORY_GENERAL

    #: Seconds since the epoch.
    timestamp: float = Field(default_factory=time.time)

    #: Who posted it, e.g. the posting plugin's PKG.
    source: str = ""

    action: NotificationAction | None = None


class ShowNotificationsPanelRequest(BaseModel):
    """Show the notifications pane, expanding ``section_id`` if given."""

    model_config = _DEFERRED_BUILD

    section_id: str = ""


notification_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATION_POST, validator_class=NotificationMessage
)
show_notifications_panel_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATIONS_SHOW_PANEL, validator_class=ShowNotificationsPanelRequest
)

# ---------------------------------------------------------------------------
# Extension point: sections shown above the notifications, e.g. the plugin
# loading list. Contributors import only this module.
# ---------------------------------------------------------------------------
NOTIFICATION_SECTIONS = f"{PKG}.sections"


class NotificationSection(HasTraits):
    """A collapsible section at the top of the notifications pane.

    Its contents are built the first time the section is expanded, by
    ``factory(parent)``, which returns a QWidget or a TraitsUI ``UI`` (from
    ``edit_traits(kind="subpanel", parent=parent)``); a UI is disposed with
    the pane.
    """

    #: Unique id; NOTIFICATIONS_SHOW_PANEL names a section by it.
    id = Str()

    #: The section header, e.g. "Plugins".
    title = Str()

    #: One line beside the title, kept current by the contributor.
    summary = Str()

    #: Sections sort by this, lowest first.
    order = Int(0)

    #: Whether the section's contents are shown.
    expanded = Bool(False)

    #: Most pixels the contents take before they scroll; 0 for no cap.
    max_height = Int()

    #: ``factory(parent)`` -> QWidget or TraitsUI UI.
    factory = Callable()

    def _max_height_default(self):
        return SECTION_MAX_HEIGHT


# ---------------------------------------------------------------------------
# Drawer, entries and status-bar bell
# ---------------------------------------------------------------------------
#: Object name of the drawer widget, for style sheets and tests.
DRAWER_OBJECT_NAME = f"{PKG}.drawer"

#: Width (px) of the open drawer; a narrower window gets a drawer as wide as
#: itself.
DRAWER_WIDTH = 400

#: Space (px) between the drawer's edges and its contents.
DRAWER_PADDING_PX = 6

#: Opacity (0-1) of the drawer's background behind the cards, which lets
#: what lies beneath show faintly; 1.0 makes it opaque. The header, the
#: sections and the cards are always opaque.
DRAWER_OPACITY = 0.92

#: Repaints per second of what lies beneath the drawer (a camera feed, a
#: live plot) past which the open drawer turns opaque until closed: a
#: translucent drawer is repainted with whatever is beneath it.
DRAWER_BACKDROP_PAINTS_PER_S = 4

#: Whether a click in the main window outside the drawer closes it. The
#: click is then used up, so it never also actuates what lies beneath.
DRAWER_CLOSES_ON_CLICK_OUTSIDE = True

#: Duration (ms) of the drawer's slide in from the right; 0 opens it at once.
DRAWER_SLIDE_MS = 160

#: Entries kept for the session; the oldest go first.
MAX_ENTRIES = 300

#: Characters of a notification's first line shown as its title.
TITLE_MAX_CHARS = 160

#: How often (ms) the shown list repaints its relative times ("2 min ago").
TIME_REFRESH_MS = 30_000

#: Most pixels an expanded detail takes before it scrolls.
DETAIL_MAX_HEIGHT = 240

#: Most pixels an expanded section takes before it scrolls.
SECTION_MAX_HEIGHT = 300

# ---------------------------------------------------------------------------
# Log records forwarded as notifications
# ---------------------------------------------------------------------------
#: Records below this level are not forwarded.
LOG_MIN_LEVEL = logging.WARNING

#: Records not forwarded: ``(logger name, message regex)``. The name also
#: covers its child loggers; the regex is matched at the message's start.
#: Routine lines logged above INFO, and failures the plugin load records
#: already report (as a "failed to load" notification), go here.
LOG_IGNORE_RULES = (
    # Logged at CRITICAL on every launch.
    ("microdrop_application.application", r"Application Initialized"),
    # A saved layout naming a pane whose plugin loads later or is disabled.
    ("pyface.ui.qt.tasks.main_window_layout", r"Cannot retrieve dock widget"),
    # Start-up order: the device viewer publishes before its SVG is in.
    ("device_viewer.models.main_model", r"Unable to push svg filename"),
    (
        "device_viewer.controllers.device_viewer_publish_controller",
        r"Unable to publish device view model yet|Publishing calibration message",
    ),
    # Recorded in the plugin load status, which posts them itself.
    ("microdrop_utils.isolating_plugin_manager", r"Plugin \S+ failed to start"),
)

#: Records arriving within this many milliseconds reach the pane together.
LOG_FLUSH_INTERVAL_MS = 250

#: Records held between flushes; a flood beyond this drops the oldest.
LOG_BUFFER_LIMIT = 5000

#: Distinct records posted per GUI turn, and the pause between turns (ms).
LOG_DELIVERY_CHUNK = 25
LOG_CHUNK_PAUSE_MS = 30
