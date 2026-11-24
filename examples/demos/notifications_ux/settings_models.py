# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Notification settings, Qt-free: toasts, sound, and per-category choices.

A category is a kind of notification a plugin posts, like a phone's
notification channel. Its owner declares it as data (a
``NotificationCategorySpec``, in its ``consts.py`` once ported) with the
defaults; the user then decides per category whether it is kept in the
drawer, pops up, and which tone it plays. A message names its category by
id; one without a category behaves as before.
"""

# Standard library imports.
from typing import Literal

# Third-party imports.
from pydantic import BaseModel

# Enthought library imports.
from traits.api import (
    Bool,
    Button,
    Dict,
    Enum,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Range,
    Str,
    observe,
)

# Local imports.
from .ux_consts import TOAST_TIMEOUT_MS

#: The tones a category can play: none, the soft chime, the alert chime, or
#: the longer completion beeps.
TONE_NONE = "none"
TONE_SOFT = "soft"
TONE_ALERT = "alert"
TONE_COMPLETION = "completion"
TONES = (TONE_NONE, TONE_SOFT, TONE_ALERT, TONE_COMPLETION)

#: How each tone is named in the settings.
TONE_LABELS = {
    TONE_NONE: "None",
    TONE_SOFT: "Soft",
    TONE_ALERT: "Alert",
    TONE_COMPLETION: "Completion",
}


class NotificationCategorySpec(BaseModel):
    """A category as its owner declares it, with the defaults."""

    #: Unique id messages name, e.g. "protocol.step_completed".
    id: str

    #: The owner, as the settings group it: "Protocol".
    group: str

    #: What it is, short: "Step completed".
    label: str

    #: One line on when it is posted.
    description: str = ""

    #: Defaults: kept in the drawer, popping up, and the tone it plays.
    drawer: bool = True
    popup: bool = True
    tone: Literal[TONES] = TONE_NONE

    #: Always kept in the drawer: the user cannot turn that off.
    critical: bool = False


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
    """How notifications arrive: the user's choice, a sketch of what a
    preferences helper would hold once ported."""

    #: Info and success toasts leave on their own; off, every toast stays
    #: until dismissed or acted on, and no countdown is drawn.
    auto_dismiss = Bool(True)

    #: Seconds an info or success toast stays, hover not counted.
    auto_dismiss_seconds = Int(TOAST_TIMEOUT_MS // 1000)

    #: ``auto_dismiss_seconds`` in milliseconds.
    timeout_ms = Property(Int, observe="auto_dismiss_seconds")

    #: A chime as the bell rings for a new arrival, and its volume (%).
    sound_enabled = Bool(True)
    sound_volume = Range(0, 100, 40)

    #: The tone the Test button plays.
    test_tone = Enum(TONE_SOFT, TONE_ALERT, TONE_COMPLETION)
    test_sound = Button("Test")

    #: The declared categories, by owner, in declaration order.
    groups = List(Instance(NotificationCategoryGroup))

    #: The categories by id.
    _by_id = Dict(Str, Instance(NotificationCategory))

    def _get_timeout_ms(self):
        return self.auto_dismiss_seconds * 1000

    def declare(self, specs):
        """Add the categories ``specs`` declare; ids already known keep the
        user's choices."""

        for spec in specs:
            if spec.id in self._by_id:
                continue

            category = category_from_spec(spec)
            self._by_id[spec.id] = category
            self.group(spec.group).categories.append(category)

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
