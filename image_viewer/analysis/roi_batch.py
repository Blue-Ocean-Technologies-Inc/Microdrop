# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Off-GUI batch computation: a daemon orchestrator thread (the plugin's
established off-GUI pattern) fans the images out to a lazily-created,
persistent thread pool and streams results back through a thread-safe
queue that the dock pane's drain timer empties on the GUI thread.

Threads, not processes. The work is cv2 and numpy, both of which drop
the GIL, and measured against a process pool threads returned their
first result 17x sooner on small frames (0.03 s against 0.50 s) and
finished a 60-frame 1200x1600 batch in 1.20 s against 1.96 s. Spawn
also made every worker re-import the launcher on Windows, running the
app's self-update and leaving stray processes behind.

The pool is created once (module-level, lock-guarded) and reused, so
it is never shut down. One batch at a time:
start() cancels any running one and swaps in a fresh queue, so a
superseded batch's stragglers die with the old queue."""

# Standard library imports.
import os
import queue
import threading
from concurrent.futures import (
    BrokenExecutor,
    ThreadPoolExecutor,
    as_completed,
)

# Enthought library imports.
from traits.api import Any, HasTraits

# Local imports.
from .roi_compute import compute_image_stats

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Queue message kinds: per-image batch result, end-of-batch marker, and
#: the single-image instant-feedback result.
BATCH_RESULT = "result"
BATCH_FINISHED = "finished"
INSTANT_RESULT = "instant"

_executor = None
_executor_lock = threading.Lock()


def _pool_workers():
    return max((os.cpu_count() or 2) - 1, 1)


def _shared_executor():
    """The one thread pool reused across every batch, created on first
    use — which costs microseconds, so a batch starts reporting almost
    at once."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=_pool_workers(), thread_name_prefix="roi-stats"
            )
        return _executor


def pool_is_warm():
    """Whether the shared pool already exists. Threads start in
    microseconds, so this is nearly always true by the time anything is
    painted; it earns its keep only if the pool ever goes back to
    processes."""
    with _executor_lock:
        return _executor is not None


def _discard_executor(executor):
    """Drop a broken shared pool so the next batch rebuilds it (the
    persistent pool otherwise has no recovery path after a worker
    crash kills it)."""
    global _executor
    with _executor_lock:
        if _executor is executor:
            _executor = None
    executor.shutdown(wait=False, cancel_futures=True)


class RoiBatchRunner(HasTraits):
    """Runs compute_image_stats over a work list off the GUI thread."""

    #: GUI-drained result queue of (kind, payload) tuples; replaced on
    #: every start() so a cancelled batch's late results are discarded.
    results = Any()

    _thread = Any()
    _cancel = Any()

    def _results_default(self):
        return queue.SimpleQueue()

    def __cancel_default(self):
        return threading.Event()

    def start(self, work_items):
        """``work_items``: [(path, effective_rois, correction), ...] with
        ``effective_rois`` = roi_id -> (kind, geometry tuple) and
        ``correction`` = (gap_px, thickness_px, ball_radius_px,
        perspective_matrix) — RoiAnalysisSession.correction_key()."""
        self.cancel()
        self.results = queue.SimpleQueue()
        self._cancel = threading.Event()
        cancel, results = self._cancel, self.results
        self._thread = threading.Thread(
            target=self._run, args=(list(work_items), cancel, results), daemon=True
        )
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    def compute_single(self, path, effective_rois, correction):
        """Instant feedback for a freshly drawn/edited ROI on the shown
        image: one off-thread compute, reported on the same queue."""
        results = self.results
        thread = threading.Thread(
            target=lambda: results.put(
                (INSTANT_RESULT, compute_image_stats(path, effective_rois, *correction))
            ),
            daemon=True,
        )
        thread.start()

    @staticmethod
    def _run(work_items, cancel, results):
        # No `with`: this is the shared, persistent executor — it must
        # outlive this batch for the next one to reuse it.
        executor = _shared_executor()
        futures = [
            executor.submit(compute_image_stats, path, rois, *correction)
            for path, rois, correction in work_items
        ]
        for future in as_completed(futures):
            if cancel.is_set():
                for pending in futures:
                    pending.cancel()
                return
            try:
                results.put((BATCH_RESULT, future.result()))
            except BrokenExecutor as error:
                logger.warning(f"ROI pool broke, rebuilding on next batch: {error}")
                _discard_executor(executor)
            except Exception as error:
                # Pool infrastructure failure (the work unit itself
                # reports its errors inside the payload).
                logger.warning(f"ROI batch worker failed: {error}")
        if not cancel.is_set():
            results.put((BATCH_FINISHED, None))
