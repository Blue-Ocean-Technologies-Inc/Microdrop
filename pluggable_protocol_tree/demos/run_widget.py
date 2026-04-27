"""Standalone demo — open ProtocolTreeWidget in a QMainWindow with
Run / Pause / Stop toolbar buttons and active-row highlighting.

No envisage, no dramatiq broker required for the in-process demo (the
MessageColumn publishes to Dramatiq but the publish call no-ops if no
broker is configured — the demo still exercises the executor's full
control flow). For the round-trip with real subscribers, run the
integration test or the full app.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget
"""

import json
import logging
import sys
import threading
import time

import dramatiq
from pyface.qt.QtCore import Qt, QTimer, Signal
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox, QStatusBar,
    QToolBar, QSplitter,
)

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import make_soft_start_column
from pluggable_protocol_tree.builtins.trail_length_column import make_trail_length_column
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.ack_roundtrip_column import (
    DEMO_APPLIED_TOPIC, DEMO_REQUEST_TOPIC, RESPONDER_ACTOR_NAME,
    make_ack_roundtrip_column,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
from pluggable_protocol_tree.demos.message_column import make_message_column
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

# remove prometheus metrics for now
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(middleware_name="dramatiq.middleware.prometheus", broker=dramatiq.get_broker())
logger = logging.getLogger(__name__)

# Module-level Dramatiq actor for live overlay updates. Captures
# self.device_view via a global hook set by DemoWindow.__init__.
_overlay_target = {"viewer": None}

# Module-level hook for the phase-ack listener. The actor runs on a
# Dramatiq worker thread; it emits a Qt signal that auto-connection
# delivers on the GUI thread, where the timers are mutated.
_ack_target = {"window": None}


@dramatiq.actor(actor_name="ppt_demo_actuation_overlay_listener",
                queue_name="default")
def _overlay_listener(message: str, topic: str, timestamp: float = None):
    viewer = _overlay_target["viewer"]
    if viewer is None:
        return
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return
    electrodes = payload.get("electrodes", []) or []
    # Cross-thread emit — auto-connection delivers on the GUI thread.
    viewer.actuation_changed.emit(list(electrodes))


@dramatiq.actor(actor_name="ppt_demo_phase_ack_listener",
                queue_name="default")
def _phase_ack_listener(message: str, topic: str, timestamp: float = None):
    """Fires on each ELECTRODES_STATE_APPLIED ack so the status bar
    can start the per-phase / per-step timers from the moment hardware
    actually confirmed the actuation, not from the upstream
    publish_message call (which can sit in the worker queue for
    1-2 seconds on a cold broker)."""
    window = _ack_target["window"]
    if window is None:
        return
    window.phase_acked.emit()


def _columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_repetitions_column(),
        make_duration_column(),
        make_electrodes_column(),
        make_routes_column(),
        make_trail_length_column(),
        make_trail_overlay_column(),
        make_soft_start_column(),
        make_soft_end_column(),
        make_repeat_duration_column(),
        make_linear_repeats_column(),
        make_message_column(),
        make_ack_roundtrip_column(),
    ]


class DemoWindow(QMainWindow):

    # Cross-thread signal for the phase-ack listener. The Dramatiq
    # worker thread emits via _phase_ack_listener; auto-connection
    # delivers _on_phase_ack on the GUI thread.
    phase_acked = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pluggable Protocol Tree — Demo (PPT-2)")
        self.resize(1000, 600)

        self.manager = RowManager(columns=_columns())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.device_view = SimpleDeviceViewer(self.manager, parent=self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        splitter.addWidget(self.device_view)
        splitter.setSizes([700, 400])
        self.setCentralWidget(splitter)

        # Seed the electrode→channel mapping. e00..e24 → channels 0..24.
        # The RoutesHandler reads this from ProtocolContext.scratch.
        self.manager.protocol_metadata["electrode_to_channel"] = {
            f"e{i:02d}": i for i in range(GRID_W * GRID_H)
        }

        # Wire the overlay + ack listener targets to this window.
        _overlay_target["viewer"] = self.device_view
        _ack_target["window"] = self
        self.phase_acked.connect(self._on_phase_ack)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Per-step / per-phase timing state. All timestamps are
        # ``time.monotonic()`` from the moment the corresponding ack
        # arrives — not from when step_started fires. None means "not
        # yet started; display 0.00s". Mutated from GUI thread only.
        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None    # set on first ack of step
        self._phase_started_at = None    # set on each ack
        self._phase_target = None        # row.duration_s, captured at step_started
        self._current_row = None
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)   # 10 Hz elapsed-time display
        self._tick_timer.timeout.connect(self._refresh_status)

        # Set up Dramatiq routing + a worker so the ack-roundtrip
        # column's publish → wait_for actually completes. Best-effort:
        # if Redis isn't running, the column will time out at runtime
        # and surface as protocol_error in the dialog.
        self._dramatiq_worker = None
        self._setup_dramatiq_routing()

        self._build_status_bar()
        self._wire_signals()
        self._build_toolbar()
        self._reset_status()

    def _setup_dramatiq_routing(self):
        """Best-effort: register subscriptions for the ack-roundtrip
        column's request/applied topics, and spin up an in-process
        Dramatiq worker so the responder + executor_listener actors
        actually receive messages."""
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor
            from dramatiq import Worker
            import dramatiq

            router = MessageRouterActor()
            router.message_router_data.add_subscriber_to_topic(
                topic=DEMO_REQUEST_TOPIC,
                subscribing_actor_name=RESPONDER_ACTOR_NAME,
            )
            router.message_router_data.add_subscriber_to_topic(
                topic=DEMO_APPLIED_TOPIC,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
            # PPT-3: actuation chain
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
            )
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_APPLIED,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
            # And a tiny consumer that paints the live overlay in the demo.
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name="ppt_demo_actuation_overlay_listener",
            )
            # Status-bar phase-ack listener — drives the per-phase /
            # per-step timers from the actual hardware ack moment.
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_APPLIED,
                subscribing_actor_name="ppt_demo_phase_ack_listener",
            )
            self._router = router
        except ValueError as e:
            # MessageRouterActor() raises if message_router_actor is
            # already registered (e.g. demo loaded a second time in
            # the same process via Load…). Reuse — don't double-register.
            if "already registered" not in str(e):
                logger.warning("Demo Dramatiq routing setup failed: %s", e)
        except Exception as e:
            logger.warning(
                "Demo Dramatiq routing setup failed (Redis not running?): %s", e,
            )

    def closeEvent(self, event):
        if self._dramatiq_worker is not None:
            try:
                self._dramatiq_worker.stop()
            except Exception:
                logger.exception("Error stopping demo dramatiq worker")
        super().closeEvent(event)

    def _wire_signals(self):
        # Active-row highlight. Only step_started + terminal signals
        # touch the highlight — step_finished does NOT clear it, so the
        # highlight stays on the just-finished row through the gap until
        # the next step_started replaces it. (Clearing on step_finished
        # makes the highlight flash off between steps and is invisible.)
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row
        )

        # PPT-3: device viewer follows the tree's selection AND the
        # executor's currently-running step.
        sel_model = self.widget.tree.selectionModel()
        sel_model.currentRowChanged.connect(
            lambda cur, _prev: self.device_view.set_active_row(
                cur.data(Qt.UserRole) if cur.isValid() else None
            )
        )
        self.executor.qsignals.step_started.connect(
            self.device_view.set_active_row
        )
        # Status bar updates
        self.executor.qsignals.step_repetition.connect(self._on_step_repetition)
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.step_finished.connect(self._on_step_finished)
        # Button state machine
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        self.executor.qsignals.protocol_paused.connect(self._on_protocol_paused)
        self.executor.qsignals.protocol_resumed.connect(self._on_protocol_resumed)
        for sig in (
            self.executor.qsignals.protocol_finished,
            self.executor.qsignals.protocol_aborted,
        ):
            sig.connect(self._on_protocol_terminated)
        self.executor.qsignals.protocol_error.connect(self._on_error)

    def _build_toolbar(self):
        tb = QToolBar("Protocol")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())
        tb.addAction("Add Group", lambda: self.manager.add_group())
        tb.addSeparator()
        tb.addAction("Save…", self._save)
        tb.addAction("Load…", self._load)
        tb.addSeparator()
        self._run_action = tb.addAction("Run", self.executor.start)
        self._pause_action = tb.addAction("Pause", self._toggle_pause)
        self._stop_action = tb.addAction("Stop", self.executor.stop)
        # Initial state: only Run is enabled.
        self._set_idle_button_state()

    def _set_idle_button_state(self):
        self._run_action.setEnabled(True)
        self._pause_action.setEnabled(False)
        self._pause_action.setText("Pause")
        self._stop_action.setEnabled(False)

    def _set_running_button_state(self):
        self._run_action.setEnabled(False)
        self._pause_action.setEnabled(True)
        self._pause_action.setText("Pause")
        self._stop_action.setEnabled(True)

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
        else:
            self.executor.pause()

    # --- status bar (step counter + elapsed time + step name/path) ---

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_step_label = QLabel("Idle")
        self._status_row_label = QLabel("")
        self._status_reps_label = QLabel("")
        self._status_step_time_label = QLabel("")
        self._status_phase_time_label = QLabel("")
        # Row label takes any remaining width via stretch=1.
        sb.addWidget(self._status_step_label)
        sb.addWidget(self._status_row_label, stretch=1)
        sb.addPermanentWidget(self._status_reps_label)
        sb.addPermanentWidget(self._status_step_time_label)
        sb.addPermanentWidget(self._status_phase_time_label)

    def _reset_status(self):
        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None
        self._current_row = None
        self._status_step_label.setText("Idle")
        self._status_row_label.setText("")
        self._status_reps_label.setText("")
        self._status_step_time_label.setText("")
        self._status_phase_time_label.setText("")

    def _refresh_status(self):
        """Recompute the two timer labels from the ack-driven
        timestamps. Both show 0.00s until the corresponding ack lands."""
        if self._current_row is None:
            return
        target = self._phase_target if self._phase_target is not None else 0.0
        if self._step_started_at is None:
            step_elapsed = 0.0
        else:
            step_elapsed = time.monotonic() - self._step_started_at
        if self._phase_started_at is None:
            phase_elapsed = 0.0
        else:
            phase_elapsed = time.monotonic() - self._phase_started_at
        self._status_step_time_label.setText(
            f"Step {step_elapsed:5.2f}s"
        )
        self._status_phase_time_label.setText(
            f"Phase {phase_elapsed:5.2f}s / {target:.2f}s"
        )

    # --- protocol-state slot handlers ---

    def _on_protocol_started(self):
        self._set_running_button_state()
        # Pre-count total steps after rep expansion. This forces a one-
        # time walk of iter_execution_steps; for huge protocols the cost
        # is O(N) but acceptable here. Re-counted because reps may have
        # changed since last run.
        try:
            self._step_total = sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            self._step_total = 0
        self._step_index = 0
        self._status_step_label.setText(f"Step 0 / {self._step_total}")

    def _on_step_repetition(self, rep_chain):
        """Render the active rep context — e.g. "rep 2/3 of 'Wash'" —
        into the status bar. Empty chain (no repeating ancestor) clears."""
        if not rep_chain:
            self._status_reps_label.setText("")
            return
        parts = [f"rep {idx}/{total} of '{name}'"
                 for name, idx, total in rep_chain]
        self._status_reps_label.setText(" · ".join(parts))

    def _on_step_started(self, row):
        # Reset the timer state — both timers stay at 0.00s until the
        # first phase ack lands. The ack handler (_on_phase_ack)
        # bumps the timestamps from None to monotonic() at the actual
        # hardware-confirmed moment.
        self._step_index += 1
        self._current_row = row
        self._step_started_at = None
        self._phase_started_at = None
        try:
            self._phase_target = float(getattr(row, "duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._phase_target = None
        path = ".".join(str(i + 1) for i in row.path) if row.path else ""
        path_str = f" (path {path})" if path else ""
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        self._status_row_label.setText(f"{row.name}{path_str}")
        self._refresh_status()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _on_phase_ack(self):
        """Each ELECTRODES_STATE_APPLIED ack (re)starts the per-phase
        timer. The first ack of a step also starts the per-step timer.
        Subsequent acks within the step leave the step timer running
        and only restart the phase timer, so the phase value reflects
        the dwell time on the current actuation snapshot."""
        if self._current_row is None:
            return     # ack outside an active step (e.g., late stragglers)
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now

    def _on_step_finished(self, _row):
        # Freeze the time labels at the step's actual elapsed; keep
        # them visible until the next step_started resets to 0.00s.
        # If no ack ever arrived (e.g., a step with no actuation), the
        # labels already show 0.00s — leave them.
        self._refresh_status()

    def _on_protocol_paused(self):
        self._pause_action.setText("Resume")
        # Stop the elapsed-time tick during pause; resume restarts it.
        self._tick_timer.stop()

    def _on_protocol_resumed(self):
        self._pause_action.setText("Pause")
        if self._current_row is not None:
            self._tick_timer.start()

    def _on_protocol_terminated(self):
        self._clear_all_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
        self._reset_status()

    def _on_error(self, msg):
        self._clear_all_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
        self._reset_status()
        QMessageBox.critical(self, "Protocol error", msg)

    def _clear_all_highlights(self):
        """Restore an idle visual state at protocol end. Clears, in order:
          - tree active-row highlight (blue executor cursor)
          - device viewer (statics + routes + actuated overlay)
          - tree selection AND current index (last so currentRowChanged
            doesn't fight the explicit set_active_row(None) above)."""
        from pyface.qt.QtCore import QModelIndex
        self.widget.highlight_active_row(None)
        self.device_view.set_active_row(None)
        self.widget.tree.clearSelection()
        self.widget.tree.setCurrentIndex(QModelIndex())

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.manager.to_json(), f, indent=2)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            self.manager.set_state_from_json(data, columns=_columns())
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
            return
        # self.widget = ProtocolTreeWidget(self.manager, parent=self)
        # self.setCentralWidget(self.widget)
        # # Re-wire executor against the new manager
        # self.executor = ProtocolExecutor(
        #     row_manager=self.manager,
        #     qsignals=ExecutorSignals(),
        #     pause_event=PauseEvent(),
        #     stop_event=threading.Event(),
        # )
        # self._wire_signals()


def main():
    # Surface the executor's INFO-level step transition logs so the
    # demo user sees them in the terminal as the protocol runs.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = QApplication.instance() or QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    app.exec()


if __name__ == "__main__":

    from microdrop_utils.broker_server_helpers import redis_server_context, dramatiq_workers_context

    with redis_server_context():
        with dramatiq_workers_context():
            main()
