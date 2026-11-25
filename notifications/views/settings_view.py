# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notification settings window, opened from the drawer's gear: the
panel at start-up, toasts, sound, and each owner's categories; and one
owner's page listing only its categories. Both edit the same category
objects, so they stay in step. Run standalone against just the model::

    view, context = settings_view(settings)
    settings.edit_traits(view=view, context=context)
"""

# Enthought library imports.
from traits.api import Str
from traitsui.api import (
    EnumEditor,
    HGroup,
    Item,
    ObjectColumn,
    OKButton,
    RangeEditor,
    TableEditor,
    VGroup,
    View,
)
from traitsui.extras.checkbox_column import CheckboxColumn

# Local imports.
from ..consts import OPEN_AT_START_ENV, TONE_LABELS, TONE_NONE
from ..models.settings import TOAST_SECONDS_RANGE

#: The tone choices, in order, as EnumEditor wants them.
TONE_CHOICES = {
    tone: f"{index}:{label}" for index, (tone, label) in enumerate(TONE_LABELS.items())
}

#: The tones the Test button can play.
TEST_TONE_CHOICES = {
    tone: label for tone, label in TONE_CHOICES.items() if tone != TONE_NONE
}


class _LabelColumn(ObjectColumn):
    """The category's name; its description as the tooltip."""

    def get_tooltip(self, object):
        return object.description


class _SwitchColumn(CheckboxColumn):
    """A category's switch: locked on for a critical category's drawer, and
    off-limits while the category is not kept in the drawer."""

    #: The row trait that must be on for the switch to change, and the one
    #: that locks it.
    requires = Str()
    locked_by = Str()

    def is_editable(self, object):

        if self.locked_by and getattr(object, self.locked_by):
            return False

        return not self.requires or getattr(object, self.requires)


class _ToneColumn(ObjectColumn):
    """A category's tone, chosen from a list; none while not kept."""

    def get_value(self, object):
        return TONE_LABELS[object.tone if object.in_drawer else TONE_NONE]

    def is_editable(self, object):
        return object.in_drawer


def category_table():
    """A table of one group's categories: its name, then its switches."""
    return TableEditor(
        columns=[
            _LabelColumn(name="row_label", label="Notification", editable=False),
            _SwitchColumn(
                name="in_drawer", label="Drawer", locked_by="critical", width=70
            ),
            _SwitchColumn(name="popup", label="Pop-up", requires="in_drawer", width=70),
            _ToneColumn(
                name="tone",
                label="Sound",
                editor=EnumEditor(values=TONE_CHOICES),
                width=110,
            ),
        ],
        editable=True,
        sortable=False,
        configurable=False,
        deletable=False,
        show_toolbar=False,
        auto_size=False,
        row_factory=None,
    )


def _group_item(key, group):
    return VGroup(
        Item(f"{key}.categories", show_label=False, editor=category_table()),
        label=group.name,
        show_border=True,
    )


GENERAL_GROUPS = [
    VGroup(
        Item(
            "open_at_start",
            label="Open the notifications panel at start-up",
            tooltip=(
                "Shows the panel as MicroDrop starts, on the plugins loading; "
                f"{OPEN_AT_START_ENV}=0 or 1 overrides this"
            ),
        ),
        label="Notifications panel",
        show_border=True,
    ),
    VGroup(
        Item(
            "auto_dismiss",
            label="Toasts time out automatically",
            tooltip="Off: every pop-up stays until you dismiss it or act on it",
        ),
        Item(
            "auto_dismiss_seconds",
            label="Seconds on screen",
            editor=RangeEditor(
                low=TOAST_SECONDS_RANGE[0], high=TOAST_SECONDS_RANGE[1], mode="spinner"
            ),
            enabled_when="auto_dismiss",
            tooltip="How long info and success pop-ups stay; hovering pauses",
        ),
        label="Pop-up notifications",
        show_border=True,
    ),
    VGroup(
        Item("sound_enabled", label="Play a sound for new notifications"),
        Item(
            "sound_volume",
            label="Volume",
            editor=RangeEditor(low=0, high=100, mode="slider"),
            enabled_when="sound_enabled",
        ),
        HGroup(
            Item(
                "test_tone",
                label="Hear a tone",
                editor=EnumEditor(values=TEST_TONE_CHOICES),
                enabled_when="sound_enabled",
            ),
            Item("test_sound", show_label=False, enabled_when="sound_enabled"),
        ),
        Item("last_sound", show_label=False, style="readonly"),
        Item("last_skipped", show_label=False, style="readonly"),
        label="Sound",
        show_border=True,
    ),
]


def settings_view(settings):
    """The whole settings window: general switches, then each owner's
    categories. Returns the View and the context it needs (the tables'
    cells edit only with an "object" key in a custom context)."""
    context = {"object": settings}
    groups = []

    for index, group in enumerate(settings.groups):
        key = f"group_{index}"
        context[key] = group
        groups.append(_group_item(key, group))

    view = View(
        *GENERAL_GROUPS,
        VGroup(*groups, label="By kind", show_border=False),
        title="Notification settings",
        buttons=[OKButton],
        kind="live",
        resizable=True,
        width=560,
    )

    return view, context


def group_settings_view(settings, name):
    """One owner's page: only its categories, e.g. for the protocol tree's
    own preferences. Returns the View and its context."""
    group = settings.group(name)
    context = {"object": settings, "group": group}

    view = View(
        _group_item("group", group),
        title=f"{name} notifications",
        buttons=[OKButton],
        kind="live",
        resizable=True,
        width=480,
    )

    return view, context
