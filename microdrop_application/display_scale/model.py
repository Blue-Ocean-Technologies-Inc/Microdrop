# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Display Scale model: the scale the user is choosing, plus what
that scale buys them on the screen they are choosing it on."""

# Enthought library imports.
from traits.api import Bool, HasTraits, Int, Property, Range, Str

# Local imports.
from .consts import SCALE_DEFAULT_PERCENT, SCALE_MAX_PERCENT, SCALE_MIN_PERCENT


class DisplayScaleModel(HasTraits):
    """SOURCE OF TRUTH for the interface scale being edited.

    Qt-free by design, so the view can be prototyped against a made-up
    screen size without an application behind it.
    """

    #: The scale the user is choosing, as a percentage of the screen's
    #: native scale. Below 100% everything shrinks and more of the
    #: interface fits; above 100% it grows.
    scale_percent = Range(SCALE_MIN_PERCENT, SCALE_MAX_PERCENT, SCALE_DEFAULT_PERCENT)

    #: The scale the running process was actually started at — what the
    #: slider is compared against to decide whether a relaunch is owed.
    active_scale_percent = Int(SCALE_DEFAULT_PERCENT)

    #: Size of the screen the window is on, in interface points at
    #: 100% scale. Injected by the controller, which derives it from the
    #: scale currently in effect so the figure holds still while the
    #: slider moves. Zero means "unknown", and the summary then drops
    #: the arithmetic rather than inventing it.
    screen_width = Int()
    screen_height = Int()

    #: One line telling the user what the chosen scale does to the
    #: room they have.
    summary = Property(Str, observe="scale_percent,screen_width,screen_height")

    #: Whether the choice differs from the scale already in effect.
    relaunch_needed = Property(Bool, observe="scale_percent,active_scale_percent")

    #: The relaunch warning, blank while none is owed (an always-present
    #: line that empties keeps the dialog from resizing under the user).
    relaunch_note = Property(Str, observe="relaunch_needed")

    def _get_summary(self):
        if not (self.screen_width and self.screen_height):
            return f"Interface scale: {self.scale_percent}%."

        width = round(self.screen_width * 100 / self.scale_percent)
        height = round(self.screen_height * 100 / self.scale_percent)

        return (
            f"This {self.screen_width} x {self.screen_height} screen holds "
            f"{width} x {height} points of interface at "
            f"{self.scale_percent}%."
        )

    def _get_relaunch_needed(self):
        return self.scale_percent != self.active_scale_percent

    def _get_relaunch_note(self):
        if not self.relaunch_needed:
            return ""

        return (
            "Qt fixes the scale when it starts, so Microdrop has to "
            "restart to apply this."
        )
