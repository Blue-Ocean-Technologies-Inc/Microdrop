# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Display Scale model: the interface scale being chosen, and what
it buys on the panel it is being chosen for."""

from apptools.preferences.api import PreferencesHelper
from traits.api import HasTraits, Int, Property, Range, Str

from ..consts import (
    DISPLAY_SCALE_DEFAULT_PERCENT,
    DISPLAY_SCALE_MAX_PERCENT,
    DISPLAY_SCALE_MIN_PERCENT,
)


class DisplayScaleModel(HasTraits):
    """SOURCE OF TRUTH for the scale under the slider. Qt-free, so the
    view can be prototyped against a made-up panel size."""

    #: The scale being chosen, as a percentage of the panel's native
    #: scale. Below 100% everything shrinks and more panes fit.
    scale_percent = Range(
        DISPLAY_SCALE_MIN_PERCENT,
        DISPLAY_SCALE_MAX_PERCENT,
        DISPLAY_SCALE_DEFAULT_PERCENT,
    )

    #: The panel's native size in pixels. Zero means "unknown", and the
    #: summary then drops the arithmetic rather than inventing it.
    screen_width = Int()
    screen_height = Int()

    #: One line telling the user what the chosen scale does to the room
    #: they have.
    summary = Property(Str, observe="scale_percent,screen_width,screen_height")

    def _get_summary(self):
        if not (self.screen_width and self.screen_height):
            return f"Interface scale: {self.scale_percent}%."

        width = round(self.screen_width * 100 / self.scale_percent)
        height = round(self.screen_height * 100 / self.scale_percent)

        return (
            f"This {self.screen_width} x {self.screen_height} panel holds "
            f"{width} x {height} points of interface at {self.scale_percent}%."
        )


class DisplayScalePreferences(PreferencesHelper):
    """The persisted scale, restored by the plugin on every start."""

    preferences_path = "microdrop.portable.display_scale"

    scale_percent = Range(
        DISPLAY_SCALE_MIN_PERCENT,
        DISPLAY_SCALE_MAX_PERCENT,
        DISPLAY_SCALE_DEFAULT_PERCENT,
        desc="interface scale in percent of the panel's native scale",
    )
