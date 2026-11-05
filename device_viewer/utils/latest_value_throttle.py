# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Coalesce a stream of values (a dragged slider's) into at most one call
per interval, always ending on the latest value."""

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Any, Bool, Callable, Float, HasTraits, Instance


class LatestValueThrottle(HasTraits):
    """Call ``callback`` with the latest submitted value, once ``interval``
    after the first value of a burst; values submitted meanwhile only
    replace the pending one. The timer fires on the GUI thread."""

    #: Called with the latest submitted value.
    callback = Callable()

    #: Seconds from a burst's first value to the call.
    interval = Float(0.1)

    #: Builds the single-shot timer from ``interval`` and ``callback``
    #: keywords; tests inject a timer they fire by hand.
    timer_factory = Callable(CallbackTimer)

    #: A value awaits the timer.
    pending = Bool(False)

    #: The value the timer will deliver.
    _value = Any()

    #: Delivers the pending value: a single-shot pyface ICallbackTimer,
    #: built on first use.
    _timer = Instance(HasTraits)

    def __timer_default(self):
        return self.timer_factory(interval=self.interval, callback=self.flush)

    def submit(self, value):
        """Make ``value`` the one delivered when the timer fires, starting
        the timer unless a value is already pending."""
        self._value = value

        if self.pending:
            return

        self.pending = True
        self._timer.repeat = 1
        self._timer.start()

    def flush(self):
        """Deliver the pending value now, if any."""
        self._timer.stop()

        if not self.pending:
            return

        value = self._value
        self.pending = False
        self._value = None

        self.callback(value)

    def cancel(self):
        """Drop the pending value, if any, without delivering it."""
        self._timer.stop()
        self.pending = False
        self._value = None
