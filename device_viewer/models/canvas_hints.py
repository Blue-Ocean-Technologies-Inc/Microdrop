# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hints shown in the pill at the top of the device canvas (#1211)."""

# Enthought library imports.
from pyface.action.api import StatusBarManager
from pyface.timer.api import do_after
from traits.api import Dict, Property, Str

# Local imports.
from ..consts import CANVAS_HINT_SEPARATOR


class CanvasHints(StatusBarManager):
    """The canvas's hint lines: a mode's instructions while it is active,
    and passing notes that leave on their own.

    A StatusBarManager that never builds a status bar: a layer or plugin
    written against the status-bar API (``messages += [...]``, ``remove``),
    the gamepad's HUD among them, lands in the pill unchanged.
    """

    #: The pill's text: the hints up now, in arrival order.
    text = Property(Str, observe="messages.items")

    #: The pending removal of each passing note, by its text.
    _note_timers = Dict(Str)

    def _get_text(self):
        return CANVAS_HINT_SEPARATOR.join(filter(None, self.messages))

    def remove(self, message):
        """Take ``message`` down."""
        self.messages = [shown for shown in self.messages if shown != message]

    def show_for(self, message, duration_ms):
        """Show ``message`` for ``duration_ms``; showing it again before
        then restarts its time instead of adding it twice."""
        timer = self._note_timers.pop(message, None)

        if timer is not None:
            timer.stop()

        if message not in self.messages:
            self.messages += [message]

        self._note_timers[message] = do_after(duration_ms, self._end_note, message)

    def _end_note(self, message):
        self._note_timers.pop(message, None)
        self.remove(message)
