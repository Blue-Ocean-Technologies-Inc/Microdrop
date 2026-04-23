"""QObject carrying the executor's UI-facing signals.

Lives on a QObject (not the Traits-based ProtocolExecutor) so Qt's
queued-connection machinery can marshal emissions from the executor's
worker thread to slots living on the GUI thread automatically.

UI consumers connect directly:
    executor.qsignals.step_started.connect(tree_model.set_active_node)
"""

from pyface.qt.QtCore import QObject, Signal


class ExecutorSignals(QObject):
    # Lifecycle
    protocol_started   = Signal()
    protocol_paused    = Signal()
    protocol_resumed   = Signal()
    protocol_finished  = Signal()           # ran to completion
    protocol_aborted   = Signal()           # user pressed Stop
    protocol_error     = Signal(str)        # exception raised in a hook

    # Per-step
    step_started       = Signal(object)     # row
    step_finished      = Signal(object)     # row
    # Tuple of (group_name, rep_idx_1based, rep_total) entries describing
    # the active rep context for the current step (outermost-first).
    # Empty tuple means "no repeating ancestor". Emitted just before
    # each step_started so UI labels can update in lockstep.
    step_repetition    = Signal(object)
