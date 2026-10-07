# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A single background thread that only ever works on the newest request,
handing results back to the GUI thread through a queue the dock pane's
drain timer empties — the image loader's hand-back, reusable."""

# Standard library imports.
import queue
import threading

# Enthought library imports.
from traits.api import Any, Callable, HasTraits, Instance, Str

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class LatestWinsWorker(HasTraits):
    """Runs ``work`` on a daemon thread, newest request only: a request
    submitted while another is still waiting replaces it, so a burst of
    requests costs one run, not one each."""

    #: request -> result, called on the worker thread: it must not touch
    #: traits or Qt objects.
    work = Callable()

    #: The thread's name, for debuggers and py-spy dumps.
    name = Str("latest-wins-worker")

    #: Finished results, emptied on the GUI thread by drain().
    _results = Instance(queue.SimpleQueue, ())

    #: The newest not-yet-started request, None when there is none.
    _pending = Any(None)

    _lock = Any()
    _wakeup = Any()
    _thread = Any()

    def __lock_default(self):
        return threading.Lock()

    def __wakeup_default(self):
        return threading.Event()

    def submit(self, request):
        """Queue ``request`` (never None), replacing any still waiting."""
        with self._lock:
            self._pending = request
            self._wakeup.set()

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run, name=self.name, daemon=True
            )
            self._thread.start()

    def drain(self):
        """The results finished since the last drain, oldest first."""
        results = []

        while True:
            try:
                results.append(self._results.get_nowait())
            except queue.Empty:
                return results

    def _run(self):
        while True:
            self._wakeup.wait()

            with self._lock:
                request = self._pending
                self._pending = None
                self._wakeup.clear()

            if request is None:
                continue

            try:
                self._results.put(self.work(request))
            except Exception as error:
                logger.error(f"{self.name} failed on {request!r}: {error}")
