# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Run deferred GUI work one unit at a time, with the event loop free between.

Work deferred past the main window's first paint (staged plugin loading, live
dock-pane mounts, device viewer sidebar sections) is queued here as units, one
GUI-thread callable each. The pacer runs one unit, then leaves the event loop
alone for ``GUI_STEP_PAUSE_MS`` so queued paints, timers and input are handled
before the next. A zero-delay hand-off would not do that: the next unit would
run ahead of them, and chained units would freeze the window for their whole
length. Every deferred chain shares the one process-wide queue, so two
chains never run back to back without a paint either.

Units are submitted from the GUI thread; a worker thread hands its result
over with ``GUI.invoke_later`` first. While the queue is empty nothing is
scheduled. Qt-free: the timer is ``pyface.api.GUI.invoke_after``, and tests
inject their own ``invoke_after`` and ``clock``.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.api import GUI
from traits.api import Bool, Callable, Float, HasTraits, Int, List

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Milliseconds the event loop runs on its own after each unit of paced work.
GUI_STEP_PAUSE_MS = 30


class GuiWorkPacer(HasTraits):
    """A queue of GUI-thread work units, run one per paced turn."""

    #: Milliseconds of free event loop after each unit.
    pause_ms = Int(GUI_STEP_PAUSE_MS)

    #: ``invoke_after(milliseconds, callable)`` on the GUI event loop.
    invoke_after = Callable()

    #: Seconds, monotonic; when the last unit finished is measured with it.
    clock = Callable(time.perf_counter)

    #: The units still to run, as ``(callable, args, kwargs)``.
    _queue = List()

    #: True from the scheduling of a turn until the queue runs empty; units
    #: submitted meanwhile, also by a running unit, just join the queue.
    _scheduled = Bool(False)

    #: ``clock()`` when the last unit finished.
    _last_unit_end = Float(float("-inf"))

    def _invoke_after_default(self):
        return GUI.invoke_after

    def submit(self, callable, *args, **kwargs):
        """Queue ``callable(*args, **kwargs)`` to run on a paced turn."""
        self._queue.append((callable, args, kwargs))

        if self._scheduled:
            return

        # A pause already spent idle counts; the next unit need not wait it
        # again.
        idle_ms = 1000 * (self.clock() - self._last_unit_end)
        self._schedule(round(self.pause_ms - min(idle_ms, self.pause_ms)))

    def _schedule(self, delay_ms):
        self._scheduled = True
        self.invoke_after(delay_ms, self._run_next)

    def _run_next(self):
        """Run one unit, then schedule the next after the pause."""
        callable, args, kwargs = self._queue.pop(0)

        # One failing unit must not stall every chain queued behind it.
        try:
            callable(*args, **kwargs)
        except Exception:
            logger.exception(f"Paced GUI work {callable!r} failed")

        self._last_unit_end = self.clock()

        if self._queue:
            self._schedule(self.pause_ms)
        else:
            self._scheduled = False


#: The process-wide pacer every deferred GUI chain shares.
gui_work_pacer = GuiWorkPacer()


def invoke_paced(callable, *args, **kwargs):
    """Run ``callable(*args, **kwargs)`` on a later paced GUI turn."""
    gui_work_pacer.submit(callable, *args, **kwargs)
