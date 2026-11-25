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
panel at start-up, toasts, sound, and each owner's kinds of notification;
and one owner's page listing only its kinds. Both edit the same category
objects, so they stay in step. Run standalone against just the model::

    view, context = settings_view(settings)
    settings.edit_traits(view=view, context=context)

The window opens compact (``SettingsWindowState``), at most 80 % of the
screen's height, and keeps its size: each tab's contents scroll inside it,
under the tab bar, over the buttons.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets
from traits.api import Instance
from traitsui.api import (
    Action,
    CustomEditor,
    EnumEditor,
    Handler,
    HGroup,
    Item,
    OKButton,
    RangeEditor,
    VGroup,
    View,
)

# Local imports.
from ..consts import OPEN_AT_START_ENV, TONE_LABELS, TONE_NONE
from ..models.settings import TOAST_SECONDS_RANGE
from ..models.settings_window import (
    MIN_WINDOW_SIZE,
    SettingsWindowState,
    fitted_window_size,
)
from .settings_kinds import kinds_panel

#: The tone choices, in order, as EnumEditor wants them.
TONE_CHOICES = {
    tone: f"{index}:{label}" for index, (tone, label) in enumerate(TONE_LABELS.items())
}

#: The tones the Test button can play.
TEST_TONE_CHOICES = {
    tone: label for tone, label in TONE_CHOICES.items() if tone != TONE_NONE
}


#: The button restoring every kind's declared defaults.
RESET_KINDS_ACTION = Action(
    name="Reset all kinds",
    action="reset_all_kinds",
    tooltip="Restore every kind's Drawer, Pop-up and Sound defaults",
)


class SettingsWindowHandler(Handler):
    """Sizes the window to the screen and remembers its size and tab in
    ``window``; resets the kinds."""

    window = Instance(SettingsWindowState, ())

    def init(self, info):
        control = info.ui.control
        tabs = control.findChild(QtWidgets.QTabWidget)

        # The tabs' own scroll areas: no frame inside the tab's.
        for area in control.findChildren(QtWidgets.QScrollArea):
            area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        if tabs is not None:
            tabs.setCurrentIndex(min(self.window.tab_index, tabs.count() - 1))
            tabs.currentChanged.connect(self._remember_tab)

        return True

    def position(self, info):
        """Centre the window, at its remembered size, on its parent."""
        super().position(info)

        control = info.ui.control
        screen = control.screen().availableGeometry()
        width, height = fitted_window_size(self.window.size, screen.height())
        centre = control.frameGeometry().center()

        control.setMinimumSize(*MIN_WINDOW_SIZE)
        control.resize(width, height)
        control.move(centre - QtCore.QPoint(width // 2, height // 2))
        control.installEventFilter(_RememberSize(self.window, control))

    def reset_all_kinds(self, info):
        info.object.reset_categories()

    def _remember_tab(self, index):
        self.window.tab_index = index


class _RememberSize(QtCore.QObject):
    """Keeps the window's size in its state as it is resized."""

    def __init__(self, window, parent):
        super().__init__(parent)

        self._window = window

    def eventFilter(self, watched, event):

        if event.type() == QtCore.QEvent.Type.Resize:
            self._window.size = (event.size().width(), event.size().height())

        return False


def _kinds_item(window, group_name=""):
    """The kinds' panel (``settings_kinds``) as the item filling its tab."""
    return Item(
        "groups",
        show_label=False,
        editor=CustomEditor(kinds_panel, window, group_name),
        resizable=True,
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
        scrollable=True,
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
        scrollable=True,
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
        scrollable=True,
    ),
]


def settings_view(settings, window=None):
    """The whole settings window: a tab per general group, then "By kind",
    each owner's kinds. ``window`` keeps its size, tab and sections for the
    session; a new one each time if None. Returns the View and its
    context."""
    window = window or SettingsWindowState()
    context = {"object": settings}

    view = View(
        *GENERAL_GROUPS,
        VGroup(_kinds_item(window), label="By kind"),
        title="Notification settings",
        buttons=[RESET_KINDS_ACTION, OKButton],
        handler=SettingsWindowHandler(window=window),
        kind="live",
        resizable=True,
    )

    return view, context


def group_settings_view(settings, name):
    """One owner's page: only its kinds, e.g. for the protocol tree's own
    preferences. Returns the View and its context."""
    context = {"object": settings}

    view = View(
        VGroup(_kinds_item(SettingsWindowState(), name)),
        title=f"{name} notifications",
        buttons=[OKButton],
        handler=SettingsWindowHandler(),
        kind="live",
        resizable=True,
    )

    return view, context
