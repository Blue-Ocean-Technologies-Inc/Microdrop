"""Protocol executor — runs a RowManager's rows on a QThread.

Responsibilities:
  * Walk row_manager.iter_execution_steps() in order.
  * For each row, fan the five hooks across priority buckets (sequential
    between buckets, parallel within).
  * Distinguish protocol_finished / protocol_aborted / protocol_error in
    one place (_emit_terminal_signal).
  * Cooperate with stop/pause/error: stop_event short-circuits the loop
    and propagates into ctx.wait_for; pause_event blocks at step
    boundaries only; first hook exception aborts the step and routes to
    protocol_error.

This task ships only the scaffolding + public control API. The run loop,
hook fan-out, and conflict assertion land in subsequent tasks.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from pyface.qt.QtCore import QThread
from traits.api import Any, Callable as CallableTrait, HasTraits, Instance

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager


logger = logging.getLogger(__name__)


class ProtocolExecutor(HasTraits):
    """One executor per RowManager. Reused across runs."""

    row_manager = Instance(RowManager)
    qsignals    = Instance(ExecutorSignals)

    pause_event = Instance(PauseEvent)
    stop_event  = Instance(threading.Event)

    # Internal — set by start() / cleared by run()'s finally.
    _thread = Any
    _error  = Any

    # Injectable for tests (e.g. a synchronous executor for determinism).
    bucket_pool_factory = CallableTrait

    def _bucket_pool_factory_default(self):
        return ThreadPoolExecutor

    # ------- public control API (called from the GUI thread) -------

    def start(self) -> None:
        """Spawn a QThread and call run() on it. Idempotent — a second
        call while already running is ignored."""
        if self._thread is not None and self._thread.isRunning():
            return
        self.pause_event.clear()
        self.stop_event.clear()
        self._error = None
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        self._thread.start()

    def pause(self) -> None:
        """Set pause_event. Effective at the next step boundary."""
        self.pause_event.set()
        self.qsignals.protocol_paused.emit()

    def resume(self) -> None:
        """Clear pause_event so the main loop unblocks."""
        self.pause_event.clear()
        self.qsignals.protocol_resumed.emit()

    def stop(self) -> None:
        """Set stop_event AND clear pause_event so a Stop-while-paused
        doesn't deadlock the main loop in pause_event.wait_cleared()."""
        self.stop_event.set()
        self.pause_event.clear()

    # ------- main loop (overridden in Task 9) -------

    def run(self) -> None:
        """Stub — fully implemented in Task 9."""
        raise NotImplementedError("run() lands in Task 9")
