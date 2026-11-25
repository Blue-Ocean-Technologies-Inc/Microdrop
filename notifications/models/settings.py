# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""How notifications arrive, Qt-free: the drawer at start-up, toasts, sound,
and the user's choices per notification category.

A category is a kind of notification a plugin posts, like a phone's
notification channel. Its owner declares it in its ``consts.py`` (a
``NotificationCategorySpec``) with the defaults; the user then decides per
category whether it is kept in the drawer, pops up, and which tone it plays.

The choices are saved as a plain dict (``to_state``/``apply_state``), in
settings.json in the notifications data folder
(``services.settings_store``).
"""

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    Event,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
    TraitError,
    observe,
)

# Local imports.
from ..consts import OPEN_AT_START_ENV, TONE_NONE, TONES

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: How long (s) an info or success toast stays by default, hover not
#: counted; and the range the user may choose from.
DEFAULT_TOAST_SECONDS = 6
TOAST_SECONDS_RANGE = (2, 60)

#: The chime's volume (%) by default.
DEFAULT_VOLUME = 80

#: The settings saved, by trait name: the general ones, and each category's.
SAVED_SETTINGS = (
    "open_at_start",
    "auto_dismiss",
    "auto_dismiss_seconds",
    "sound_enabled",
    "sound_volume",
)
SAVED_CATEGORY_CHOICES = ("in_drawer", "popup", "tone")

#: The key of the categories' choices in the saved dict.
CATEGORIES_KEY = "categories"


def opens_at_start(saved, environ):
    """Whether the drawer opens at start-up: as OPEN_AT_START_ENV in
    ``environ`` says when it is "1" or "0", else as ``saved`` says."""
    override = environ.get(OPEN_AT_START_ENV, "").strip()

    if override in ("0", "1"):
        return override == "1"

    return saved


def _take_choices(target, choices, names, prefix=""):
    """Set each of ``names`` found in ``choices`` on ``target``; returns the
    keys (``prefix`` + name) whose values it would not take."""
    rejected = []

    for name in names:
        if name not in choices:
            continue

        try:
            setattr(target, name, choices[name])

        except TraitError:
            rejected.append(f"{prefix}{name}")

    return rejected


class NotificationCategory(HasTraits):
    """A declared category and the user's choices for it."""

    id = Str()
    group = Str()
    label = Str()
    description = Str()
    critical = Bool(False)

    #: Kept in the drawer; off, its notifications are not recorded at all
    #: (errors and Needs attention items still are).
    in_drawer = Bool(True)

    #: Pops up as a toast; off, it goes straight to the drawer and the bell.
    popup = Bool(True)

    #: The tone its arrivals play.
    tone = Enum(*TONES)

    #: The settings' row label, saying when the drawer switch is locked.
    row_label = Property(Str, observe="label, critical")

    def _get_row_label(self):
        return f"{self.label} (always kept)" if self.critical else self.label

    @observe("in_drawer")
    def _keep_critical_listed(self, event):

        if self.critical and not self.in_drawer:
            self.in_drawer = True


def category_from_spec(spec):
    """A category with its owner's defaults."""
    return NotificationCategory(
        id=spec.id,
        group=spec.group,
        label=spec.label,
        description=spec.description,
        critical=spec.critical,
        in_drawer=spec.drawer or spec.critical,
        popup=spec.popup,
        tone=spec.tone,
    )


class NotificationCategoryGroup(HasTraits):
    """One owner's categories, as the settings list them together."""

    name = Str()

    categories = List(Instance(NotificationCategory))


class NotificationSettings(HasTraits):
    """The user's choices on how notifications arrive."""

    #: The drawer opens as the main window first shows, on the plugins
    #: loading; OPEN_AT_START_ENV overrides it.
    open_at_start = Bool(True)

    #: Info and success toasts leave on their own; off, every toast stays
    #: until dismissed or acted on, and no countdown is drawn.
    auto_dismiss = Bool(True)

    #: Seconds an info or success toast stays, hover not counted.
    auto_dismiss_seconds = Range(*TOAST_SECONDS_RANGE, value=DEFAULT_TOAST_SECONDS)

    #: ``auto_dismiss_seconds`` in milliseconds.
    timeout_ms = Property(Int, observe="auto_dismiss_seconds")

    #: A chime as the bell rings for a new arrival, and its volume (%).
    sound_enabled = Bool(True)
    sound_volume = Range(0, 100, DEFAULT_VOLUME)

    #: The tone the Test button plays.
    test_tone = Enum(*[tone for tone in TONES if tone != TONE_NONE])
    test_sound = Button("Test")

    #: What the chime last did, and last did not, and why: shown in the
    #: settings so a silence can be explained without the log.
    last_sound = Str("Last sound: none yet")
    last_skipped = Str("Last skipped: none yet")

    #: Fired as the settings window opens: the sounds load then.
    opened = Event()

    #: The declared categories, by owner, in declaration order.
    groups = List(Instance(NotificationCategoryGroup))

    #: The categories by id.
    _by_id = Dict(Str, Instance(NotificationCategory))

    #: The saved choices per category id, as ``to_state`` writes them: a
    #: category declared later (its plugin loads later) takes them then, and
    #: those of categories not declared this session are saved again.
    _saved_choices = Dict(Str, Dict)

    def _get_timeout_ms(self):
        return self.auto_dismiss_seconds * 1000

    def declare(self, specs):
        """Add the categories ``specs`` declare, with the saved choices if
        any; ids already known keep the user's choices."""

        for spec in specs:
            if spec.id in self._by_id:
                continue

            category = category_from_spec(spec)
            rejected = self._take_saved_choices(category)

            if rejected:
                logger.warning(f"Saved notification settings ignored: {rejected}")

            self._by_id[spec.id] = category
            self.group(spec.group).categories.append(category)

    # ------------------------------------------------------------------ #
    # Saving                                                              #
    # ------------------------------------------------------------------ #

    def to_state(self):
        """The choices as a JSON-ready dict, for ``apply_state``."""
        choices = dict(self._saved_choices)

        for category_id, category in self._by_id.items():
            choices[category_id] = {
                name: getattr(category, name) for name in SAVED_CATEGORY_CHOICES
            }

        state = {name: getattr(self, name) for name in SAVED_SETTINGS}
        state[CATEGORIES_KEY] = choices

        return state

    def apply_state(self, state):
        """Take the choices in ``state`` (``to_state``'s dict); what it lacks
        keeps its default. Returns the keys whose values were unusable, which
        keep their default too."""
        rejected = _take_choices(self, state, SAVED_SETTINGS)
        choices = state.get(CATEGORIES_KEY, {})

        if not isinstance(choices, dict):
            rejected.append(CATEGORIES_KEY)
            choices = {}

        self._saved_choices = {
            category_id: category_choices
            for category_id, category_choices in choices.items()
            if isinstance(category_choices, dict)
        }

        for category in self._by_id.values():
            rejected += self._take_saved_choices(category)

        return rejected

    def _take_saved_choices(self, category):
        choices = self._saved_choices.get(category.id, {})
        prefix = f"{CATEGORIES_KEY}.{category.id}."

        return _take_choices(category, choices, SAVED_CATEGORY_CHOICES, prefix)

    def group(self, name):
        """The group named ``name``, made empty if new."""

        for group in self.groups:
            if group.name == name:
                return group

        group = NotificationCategoryGroup(name=name)
        self.groups.append(group)

        return group

    def category(self, category_id):
        """The category ``category_id``, or None (uncategorised, unknown)."""
        return self._by_id.get(category_id)
