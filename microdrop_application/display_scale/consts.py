# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Constants for Display Scale — the app-wide interface zoom, for
benches whose screen is smaller than the layout assumes (the portable
rig's panel) or larger than the user's eyes like."""

PKG = ".".join(__name__.split(".")[:-1])

#: Where the chosen scale is persisted. Read straight out of
#: preferences.ini at startup, before there is an application (let
#: alone a QApplication) to ask.
SCALE_PREFERENCES_NODE = "microdrop.app"
SCALE_PREFERENCE_NAME = "ui_scale_percent"
PREFERENCES_FILENAME = "preferences.ini"

#: Slider bounds, as a percentage of the screen's native scale. Below
#: 100% the whole interface shrinks and more of it fits on the panel;
#: above 100% it grows.
SCALE_MIN_PERCENT = 50
SCALE_MAX_PERCENT = 200
SCALE_DEFAULT_PERCENT = 100

#: Qt reads this once, while QGuiApplication is being constructed, and
#: exposes no runtime equivalent — which is why applying a new scale
#: means relaunching the process.
SCALE_ENV_VAR = "QT_SCALE_FACTOR"
