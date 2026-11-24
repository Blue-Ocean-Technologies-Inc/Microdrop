# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The toast settings as a small window: a sketch of a future Notifications
tab in Preferences. Runs standalone against just its model::

    ToastSettings().configure_traits(view=ToastSettingsView)
"""

# Enthought library imports.
from traitsui.api import Item, OKButton, RangeEditor, VGroup, View

#: The range the seconds spinner allows.
SECONDS_LOW = 2
SECONDS_HIGH = 60

ToastSettingsView = View(
    VGroup(
        Item(
            "auto_dismiss",
            label="Toasts time out automatically",
            tooltip="Off: every pop-up stays until you dismiss it or act on it",
        ),
        Item(
            "auto_dismiss_seconds",
            label="Seconds on screen",
            editor=RangeEditor(low=SECONDS_LOW, high=SECONDS_HIGH, mode="spinner"),
            enabled_when="auto_dismiss",
            tooltip="How long info and success pop-ups stay; hovering pauses",
        ),
        label="Pop-up notifications",
        show_border=True,
    ),
    title="Notification settings",
    buttons=[OKButton],
    kind="live",
    resizable=True,
)
