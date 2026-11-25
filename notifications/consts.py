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
drawer's section and category extension points, and the log-forwarding
settings.

Any plugin posts a notification by importing only this module::

    from notifications.consts import notification_publisher

    notification_publisher.publish(
        {"title": "Protocol finished", "severity": "success", "category": "protocol"}
    )
"""

# Standard library imports.
import logging
import time
from pathlib import Path
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

# Third-party imports.
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# Enthought library imports.
from traits.api import Bool, Callable, Event, HasTraits, Instance, Int, List, Str, Tuple
from traits.etsconfig.api import ETSConfig

# Microdrop package imports.
from user_help_plugin.consts import HELP_AVAILABILITY

# Microdrop style imports.
from microdrop_style.colors import (
    ERROR_COLOR,
    INFO_COLOR,
    SUCCESS_COLOR,
    TAUPE,
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

#: Free-text groupings the app posts under; any other string is accepted too.
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

#: A condition that raised Needs attention cards has cleared
#: (NotificationResolveRequest).
NOTIFICATION_RESOLVE = "ui/notifications/resolve"

LISTENER_NAME = f"{PKG}_listener"
ACTOR_TOPIC_DICT = {
    LISTENER_NAME: [
        NOTIFICATION_POST,
        NOTIFICATIONS_SHOW_PANEL,
        NOTIFICATION_RESOLVE,
        # The help links follow whether tutorials can be opened.
        HELP_AVAILABILITY,
    ]
}

#: Payload validators build on first use: every plugin imports this at launch.
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


class HelpAction(BaseModel):
    """A link-styled second button opening help on what to do. With no
    first button it is the card's one control."""

    model_config = _DEFERRED_BUILD

    kind: Literal["help"] = "help"

    #: The link's text.
    label: str = "How do I…?"

    #: The tutorial to open: ``"<tutorial id>"`` or ``"<tutorial id>#<section
    #: id>"``, e.g. "dropbot_status#self-tests" (``help_target`` builds it).
    #: The id is the tutorial page's (``user_help_plugin.consts.tutorial_id``),
    #: the section an ``id`` in its HTML. The link is disabled while no
    #: tutorial can be opened (the help plugin not loaded yet).
    target: str = Field(min_length=1)


def help_target(tutorial_id, anchor=None):
    """A HelpAction ``target`` naming ``tutorial_id``, at the section
    ``anchor`` if given."""
    return f"{tutorial_id}#{anchor}" if anchor else tutorial_id


def parse_help_target(target):
    """``(tutorial_id, anchor)`` from a HelpAction ``target``; the anchor is
    None when it names none."""
    tutorial_id, _hash, anchor = target.partition("#")

    return tutorial_id.strip(), anchor.strip() or None


class SnoozeAction(BaseModel):
    """A quiet second button moving the card out of Needs attention, into
    Activity, still to do."""

    model_config = _DEFERRED_BUILD

    kind: Literal["snooze"] = "snooze"

    label: str = "Later"


#: What a notification's second button does, as data.
SecondaryAction = Annotated[
    Union[HelpAction, SnoozeAction], Field(discriminator="kind")
]


def local_path(value):
    """``value`` if it is a local path (or empty); raises ValueError for a
    URL or a ``data:`` blob. One letter before a colon is a Windows drive."""

    if len(urlparse(value).scheme) > 1:
        raise ValueError(f"not a local path: {value[:60]!r}")

    return value


class DetailLink(BaseModel):
    """A span of a notification's ``detail`` shown as a link opening a
    local folder: a folder's path opens it, a file's path opens the folder
    holding it. A file is never opened or run by a link."""

    model_config = _DEFERRED_BUILD

    #: The span: its first occurrence in the detail, e.g. a file name.
    #: Text only, so the detail stays plain text wherever it is shown.
    text: str = Field(min_length=1)

    #: The local file or folder, also shown as the link's tooltip.
    path: Annotated[str, AfterValidator(local_path)] = Field(min_length=1)


class NotificationMessage(BaseModel):
    """One notification, as posted on NOTIFICATION_POST. Every field past
    ``action`` is optional; a message without them behaves as before."""

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

    #: The second, quieter button: a help link or "Later".
    secondary_action: SecondaryAction | None = None

    #: The user has to do something: listed under Needs attention, kept by
    #: Clear all, and its toast stays until acted on or dismissed.
    needs_attention: bool = False

    #: The declared category (NOTIFICATION_CATEGORIES) it belongs to, e.g.
    #: "protocol.step_completed"; empty, it is uncategorised.
    category_id: str = ""

    #: Posts with the same thread id update one entry in place, its state
    #: replaced whole and counted once, e.g. a run's step progress.
    thread_id: str = ""

    #: The condition that raised it, e.g. "dropbot.chip_missing": a
    #: NOTIFICATION_RESOLVE naming it clears the card, no button pressed.
    condition_id: str = ""

    #: The sender's choice for this message: False lists it (Needs
    #: attention, the bell's count) with no toast and no sound, e.g. a
    #: reminder re-posted at every launch. The user's category switch
    #: still turns pop-ups off for a category; this only turns one off.
    pop_up: bool = True

    #: Within Needs attention, higher sorts first (ties newest first), e.g.
    #: a calibration that is missing above one that is only stale.
    priority: int = 0

    #: A small picture beside the text: a local image file's path, never a
    #: URL or the picture's data. A file that is missing, or not a readable
    #: image (e.g. a video), shows a placeholder glyph of its kind instead.
    #: Clicking it does what the card's button does.
    thumbnail: Annotated[str, AfterValidator(local_path)] = ""

    #: Spans of ``detail`` shown as links to local folders (DetailLink).
    links: list[DetailLink] = Field(default_factory=list)


class ShowNotificationsPanelRequest(BaseModel):
    """Show the notifications pane, expanding ``section_id`` if given."""

    model_config = _DEFERRED_BUILD

    section_id: str = ""


class NotificationResolveRequest(BaseModel):
    """The condition behind Needs attention cards has cleared: they leave
    Needs attention, read, marked with ``resolution``."""

    model_config = _DEFERRED_BUILD

    #: The cards' ``condition_id``.
    condition_id: str = Field(min_length=1)

    #: What cleared it, shown on the cards, e.g. "Chip detected".
    resolution: str = "Resolved"


# ---------------------------------------------------------------------------
# Where the notifications feature keeps its state
# ---------------------------------------------------------------------------
#: The folder, in the application home, for everything the notifications
#: feature persists: one small JSON file per concern, each written only by
#: the plugin that owns it (news_state.json by the news plugin,
#: self_test.json by the DropBot tools menu, settings.json by this plugin).
NOTIFICATIONS_DATA_DIRNAME = "notifications"

#: The user's notification settings, in the data folder.
NOTIFICATION_SETTINGS_FILENAME = "settings.json"

#: "1" opens the drawer at start-up, "0" keeps it closed, whatever the saved
#: setting: for tests, demos and automation.
OPEN_AT_START_ENV = "MICRODROP_NOTIFICATIONS_OPEN_AT_START"


def notifications_data_dir():
    """The notifications feature's data folder. Resolved at call time, after
    the application has configured ``ETSConfig``; made on the first write,
    by ``microdrop_utils.json_state_file.write_json_state``."""
    return Path(ETSConfig.application_home) / NOTIFICATIONS_DATA_DIRNAME


notification_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATION_POST, validator_class=NotificationMessage
)
show_notifications_panel_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATIONS_SHOW_PANEL, validator_class=ShowNotificationsPanelRequest
)
notification_resolve_publisher = ValidatedTopicPublisher(
    topic=NOTIFICATION_RESOLVE, validator_class=NotificationResolveRequest
)

# ---------------------------------------------------------------------------
# Extension point: the kinds of notification each plugin posts, for the
# user to choose per kind: kept in the drawer, popping up, and its tone.
# ---------------------------------------------------------------------------
NOTIFICATION_CATEGORIES = f"{PKG}.categories"

#: The tones a category can play, weakest first.
TONE_NONE = "none"
TONE_SOFT = "soft"
TONE_CONNECTED = "connected"
TONE_DISCONNECTED = "disconnected"
TONE_ALERT = "alert"
TONE_COMPLETION = "completion"
TONES = (TONE_NONE, TONE_SOFT, TONE_CONNECTED, TONE_DISCONNECTED, TONE_ALERT)
TONES += (TONE_COMPLETION,)

#: How each tone is named in the settings.
TONE_LABELS = {
    TONE_NONE: "None",
    TONE_SOFT: "Soft",
    TONE_CONNECTED: "Connected",
    TONE_DISCONNECTED: "Disconnected",
    TONE_ALERT: "Alert",
    TONE_COMPLETION: "Completion",
}


class NotificationCategorySpec(BaseModel):
    """A kind of notification, as its owner declares it in its consts.py,
    with the defaults the user may change.

    A plugin contributes its specs with
    ``List(SPECS, contributes_to=NOTIFICATION_CATEGORIES)`` and names one in
    a message's ``category_id``.
    """

    model_config = _DEFERRED_BUILD

    #: Unique id messages name, e.g. "protocol.step_completed".
    id: str = Field(min_length=1)

    #: The owner, as the settings group it: "Protocol".
    group: str = Field(min_length=1)

    #: What it is, short: "Step completed".
    label: str = Field(min_length=1)

    #: One line on when it is posted.
    description: str = ""

    #: Defaults: kept in the drawer, popping up, and the tone it plays.
    drawer: bool = True
    popup: bool = True
    tone: Literal[TONES] = TONE_NONE

    #: Always kept in the drawer: the user cannot turn that off.
    critical: bool = False


#: This plugin's own kinds of notification.
CATEGORY_ID_LOG = f"{PKG}.log"
CATEGORY_ID_PLUGIN_LOAD_FAILED = f"{PKG}.plugin_load_failed"
CATEGORIES_GROUP = "MicroDrop"

NOTIFICATIONS_CATEGORIES = [
    NotificationCategorySpec(
        id=CATEGORY_ID_LOG,
        group=CATEGORIES_GROUP,
        label="Warnings and errors in the log",
        description="Anything the app logs as a warning or an error.",
        popup=True,
        tone=TONE_ALERT,
    ),
    NotificationCategorySpec(
        id=CATEGORY_ID_PLUGIN_LOAD_FAILED,
        group=CATEGORIES_GROUP,
        label="Plugin load failures",
        description="A plugin could not start.",
        tone=TONE_ALERT,
        critical=True,
    ),
]

# ---------------------------------------------------------------------------
# Extension point: sections of the drawer's column, between Needs attention
# and Activity, e.g. the plugin loading list. Contributors import only this
# module.
# ---------------------------------------------------------------------------
NOTIFICATION_SECTIONS = f"{PKG}.sections"

#: The drawer's own sections: what needs the user, then everything else.
#: NOTIFICATIONS_SHOW_PANEL may name them too.
ATTENTION_SECTION_ID = f"{PKG}.attention"
HISTORY_SECTION_ID = f"{PKG}.history"

#: A contributed section's look when it sets none: a taupe puzzle piece.
DEFAULT_SECTION_GLYPH = "widgets"
DEFAULT_SECTION_ACCENT = (TAUPE["light"], TAUPE["dark"])


class SectionAlert(HasTraits):
    """Something new in a section, e.g. a news post: it pops up as a toast,
    counts on the bell and is marked new, but is never listed in Activity.

    The contributor appends it to its section's ``alerts``; the drawer keeps
    ``unread`` and ``is_new`` current, for the contributor's own "new"
    marks. A click on its toast opens the drawer on the section and asks
    the section for the alert's widget (``NotificationSection.alert_widget``)
    to scroll to.
    """

    #: Unique within the section, e.g. the post's id.
    key = Str()

    title = Str()
    detail = Str()

    #: Who it is from, shown on its toast.
    source = Str()

    #: The toast's stripe ``(light theme, dark theme)``; the section's
    #: accent when empty.
    accent = Tuple()

    #: The declared category it belongs to, for its pop-up and tone.
    category_id = Str()

    #: Whether it pops up as a toast; off, it is only marked new and
    #: counted, e.g. one of many summed up by another alert's toast.
    pop_up = Bool(True)

    #: Whether it counts on the bell; off for an alert summing up others.
    counted = Bool(True)

    #: Not seen yet in the open drawer with its section expanded.
    unread = Bool(True)

    #: Seen in the drawer open now: marked new until it closes.
    is_new = Bool(False)

    #: Fired when the user dismisses its toast.
    dismissed = Event()


class NotificationSection(HasTraits):
    """A collapsible section of the drawer's scrolling column.

    Its contents are built the first time the section is expanded, by
    ``factory(parent)``, which returns a QWidget or a TraitsUI ``UI`` (from
    ``edit_traits(kind="subpanel", parent=parent)``); a UI is disposed with
    the drawer's contents. They show at their natural height: lists and
    tables in them grow to all their rows, the column scrolls instead.
    """

    #: Unique id; NOTIFICATIONS_SHOW_PANEL names a section by it.
    id = Str()

    #: The section header, e.g. "Plugins".
    title = Str()

    #: One line beside the title, in a chip; kept current by the contributor.
    summary = Str()

    #: Sections sort by this, lowest first.
    order = Int(0)

    #: Whether the section's contents are shown.
    expanded = Bool(False)

    #: Whether the drawer the app opens at start-up shows the section
    #: expanded, also when it arrives after the drawer opened; for what the
    #: user should see first, e.g. News. A drawer the user opened, or one the
    #: user has expanded or collapsed the section in, keeps ``expanded``.
    expanded_at_start = Bool(False)

    #: Most pixels the contents take before they scroll; 0 for no cap.
    max_height = Int()

    #: ``factory(parent)`` -> QWidget or TraitsUI UI.
    factory = Callable()

    #: The header's glyph (a Material Symbols ligature).
    glyph = Str(DEFAULT_SECTION_GLYPH)

    #: The header's accent ``(light theme, dark theme)``: its glyph disc,
    #: its chip, and its alerts' toasts.
    accent = Tuple(DEFAULT_SECTION_ACCENT)

    #: A wide brand mark (a picture's path) shown instead of the glyph.
    logo = Str()

    #: What is new in the section: see SectionAlert.
    alerts = List(Instance(SectionAlert))

    def _max_height_default(self):
        return SECTION_MAX_HEIGHT

    def alert_widget(self, contents, alert):
        """The widget inside ``contents`` (what ``factory`` built) showing
        ``alert``, opened up as need be, for the drawer to scroll to and
        highlight; None if there is none. Override to support reveal."""
        return None


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------
#: Entries kept for the session; the oldest go first.
MAX_ENTRIES = 300

#: Width (px) of the drawer when first opened; the user drags its edge.
DRAWER_WIDTH = 400

#: Characters of a notification's first line shown as its title.
TITLE_MAX_CHARS = 160

#: Most pixels a contributed section's contents take before they scroll.
SECTION_MAX_HEIGHT = 0

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
    # A saved layout naming a pane whose plugin loads later or is disabled.
    ("pyface.ui.qt.tasks.main_window_layout", r"Cannot retrieve dock widget"),
    # Recorded in the plugin load status, which posts them itself.
    ("microdrop_utils.isolating_plugin_manager", r"Plugin \S+ failed to start"),
    ("microdrop_utils.deferred_content", r".* could not be built"),
    ("plugin_management.deferred_loader", r"Deferred plugin \S+ failed to import"),
    ("plugin_management.deferred_loader", r"Deferred plugin \S+ could not be added"),
)

#: Records arriving within this many milliseconds reach the pane together.
LOG_FLUSH_INTERVAL_MS = 250

#: Records held between flushes; a flood beyond this drops the oldest.
LOG_BUFFER_LIMIT = 5000

#: Distinct records posted per GUI turn, and the pause between turns (ms).
LOG_DELIVERY_CHUNK = 25
LOG_CHUNK_PAUSE_MS = 30
