# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Heater-sample loading off the GUI thread, by the image loader's
latest-wins pattern (``controller.py``): a request replaces any that
has not started, one daemon worker tails the logs, and the results
wait on a queue for the GUI thread's drain tick. A burst of image-list
changes during a run so costs one read of the newly written lines."""

# Standard library imports.
import queue
import threading

# Enthought library imports.
from traits.api import Any, HasTraits, Instance, Int

# Local imports.
from .heater_log import HeaterLogReader

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class HeaterSamplesLoader(HasTraits):
    """request() from the GUI thread, latest_result() from its drain
    tick; load_now() for a caller that needs the samples at once (the
    CSV export). Results of a request older than the newest delivered
    or cancelled one are dropped, so a slow read never lands on top of
    a newer one."""

    #: The incremental reader; only ever used under ``_reader_lock``.
    reader = Instance(HeaterLogReader, ())

    #: The newest not-yet-started request — (seq, folder, experiment
    #: directory, start epoch, end epoch) — or None.
    _pending = Any(None)

    #: Sequence number of the newest request (or cancellation).
    _requested_seq = Int(0)

    #: Results with a seq at or below this are stale. GUI thread only.
    _delivered_seq = Int(0)

    #: (seq, HeaterSamples) from the worker, drained by latest_result().
    _results = Instance(queue.SimpleQueue, ())

    _pending_lock = Instance(object)
    _reader_lock = Instance(object)
    _wakeup = Instance(object)
    _worker = Instance(object)

    def __pending_lock_default(self):
        return threading.Lock()

    def __reader_lock_default(self):
        return threading.Lock()

    def __wakeup_default(self):
        return threading.Event()

    def request(self, folder, experiment_directory, start_epoch, end_epoch):
        """Load the samples for this capture range in the background,
        replacing any request still waiting."""

        with self._pending_lock:
            self._requested_seq += 1
            self._pending = (
                self._requested_seq,
                folder,
                experiment_directory,
                start_epoch,
                end_epoch,
            )
            self._wakeup.set()

        self._ensure_worker()

    def load_now(self, folder, experiment_directory, start_epoch, end_epoch):
        """HeaterSamples resolved on the calling thread; whatever the
        worker finishes for an earlier request is dropped."""

        with self._pending_lock:
            self._requested_seq += 1
            seq = self._requested_seq

        with self._reader_lock:
            result = self.reader.resolve(
                folder, experiment_directory, start_epoch, end_epoch
            )

        self._delivered_seq = max(self._delivered_seq, seq)

        return result

    def cancel(self):
        """Drop the waiting request and anything in flight."""

        with self._pending_lock:
            self._pending = None
            self._requested_seq += 1
            self._delivered_seq = self._requested_seq

    def reset(self):
        """cancel(), and forget every tailed log and sibling search —
        another experiment, or other heater settings."""
        self.cancel()

        with self._reader_lock:
            self.reader = HeaterLogReader()

    def latest_result(self):
        """GUI thread: the newest finished HeaterSamples nothing has
        superseded, or None."""
        newest = None

        while True:
            try:
                seq, result = self._results.get_nowait()

            except queue.Empty:
                return newest

            if seq > self._delivered_seq:
                self._delivered_seq = seq
                newest = result

    def _ensure_worker(self):
        if self._worker is not None and self._worker.is_alive():
            return

        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self):
        """Daemon worker: resolve the newest pending request, report it
        on the results queue, wait for the next."""

        while True:
            self._wakeup.wait()

            with self._pending_lock:
                pending = self._pending
                self._pending = None
                self._wakeup.clear()

            if pending is None:
                continue

            seq, *arguments = pending

            # Anything a log can throw is caught: a dead worker would
            # silently end every later load.
            try:
                with self._reader_lock:
                    result = self.reader.resolve(*arguments)

            except Exception as error:
                logger.error(f"Heater log load failed: {error}")
                continue

            self._results.put((seq, result))
