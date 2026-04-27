"""Standalone demo — PPT-4 voltage/frequency column integration.

Opens a QMainWindow with:
- Protocol tree on the left (PPT-3 builtins + Voltage + Frequency columns)
- SimpleDeviceViewer on the right
- Run / Pause / Stop toolbar
- Active-row highlight
- Status bar with step counter, step name/path, elapsed timers, AND
  real-time voltage/frequency readouts that update as the protocol runs

Three sample steps are pre-populated so you can click Run immediately
and see the V/F status labels update (100V/10kHz → 120V/5kHz → 75V/1kHz).

No envisage required. Redis + Dramatiq workers are started in-process
when run as __main__.

Run: pixi run python -m dropbot_protocol_controls.demos.run_widget_with_vf
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
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder,
)

# Strip Prometheus middleware — raises on every actor publish otherwise.
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(middleware_name="dramatiq.middleware.prometheus", broker=dramatiq.get_broker())

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level targets for cross-thread actor → Qt signal bridging.
# Each actor runs on a Dramatiq worker thread; it emits a Qt Signal that
# auto-connection delivers on the GUI thread.
# ---------------------------------------------------------------------------

_overlay_target = {"viewer": None}  # SimpleDeviceViewer (electrode overlay)
_ack_target = {"window": None}       # DemoWindow (phase-ack timer trigger)
_vf_target = {"window": None}        # DemoWindow (voltage/frequency readouts)


# ---------------------------------------------------------------------------
# Module-level Dramatiq actors
# ---------------------------------------------------------------------------

@dramatiq.actor(actor_name="ppt4_demo_actuation_overlay_listener",
                queue_name="default")
def _overlay_listener(message: str, topic: str, timestamp: float = None):
    """Paints the live electrode overlay in the device viewer."""
    viewer = _overlay_target["viewer"]
    if viewer is None:
        return
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return
    electrodes = payload.get("electrodes", []) or []
    viewer.actuation_changed.emit(list(electrodes))


@dramatiq.actor(actor_name="ppt4_demo_phase_ack_listener",
                queue_name="default")
def _phase_ack_listener(message: str, topic: str, timestamp: float = None):
    """Fires on each ELECTRODES_STATE_APPLIED ack so the status bar can
    start the per-phase / per-step timers from the moment hardware actually
    confirmed the actuation, not from the upstream publish_message call."""
    window = _ack_target["window"]
    if window is None:
        return
    window.phase_acked.emit()


@dramatiq.actor(actor_name="ppt4_demo_voltage_applied_listener",
                queue_name="default")
def _voltage_applied_listener(message: str, topic: str,
                               timestamp: float = None):
    """Updates the status-bar voltage readout when a VOLTAGE_APPLIED ack lands."""
    window = _vf_target.get("window")
    if window is None:
        return
    try:
        window.voltage_acked.emit(int(message))
    except (TypeError, ValueError):
        pass


@dramatiq.actor(actor_name="ppt4_demo_frequency_applied_listener",
                queue_name="default")
def _frequency_applied_listener(message: str, topic: str,
                                  timestamp: float = None):
    """Updates the status-bar frequency readout when a FREQUENCY_APPLIED ack lands."""
    window = _vf_target.get("window")
    if window is None:
        return
    try:
        window.frequency_acked.emit(int(message))
    except (TypeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Column list
# ---------------------------------------------------------------------------

def _columns():
    """PPT-3 builtins + voltage + frequency columns."""
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
        make_voltage_column(),
        make_frequency_column(),
    ]


# ---------------------------------------------------------------------------
# Main demo window
# ---------------------------------------------------------------------------

class DemoWindow(QMainWindow):

    # Cross-thread signals — Dramatiq worker threads emit; auto-connection
    # delivers all slots on the GUI thread.
    phase_acked = Signal()
    voltage_acked = Signal(int)
    frequency_acked = Signal(int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPT-4 Demo — Voltage + Frequency Columns")
        self.resize(1100, 650)

        self.manager = RowManager(columns=_columns())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.device_view = SimpleDeviceViewer(self.manager, parent=self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        splitter.addWidget(self.device_view)
        splitter.setSizes([750, 400])
        self.setCentralWidget(splitter)

        # Seed the electrode→channel mapping. e00..e24 → channels 0..24.
        self.manager.protocol_metadata["electrode_to_channel"] = {
            f"e{i:02d}": i for i in range(GRID_W * GRID_H)
        }

        # Wire the module-level actor targets to this window.
        _overlay_target["viewer"] = self.device_view
        _ack_target["window"] = self
        _vf_target["window"] = self

        self.phase_acked.connect(self._on_phase_ack)
        self.voltage_acked.connect(self._on_voltage_ack)
        self.frequency_acked.connect(self._on_frequency_ack)

        # Pre-populate sample steps so the user can hit Run immediately
        # and see V/F change. Must happen BEFORE the executor is built.
        self.manager.add_step(values={
            "name": "Step 1: 100V / 10kHz on e00,e01",
            "duration_s": 0.3,
            "electrodes": ["e00", "e01"],
            "voltage": 100,
            "frequency": 10000,
        })
        self.manager.add_step(values={
            "name": "Step 2: 120V / 5kHz on e02,e03",
            "duration_s": 0.3,
            "electrodes": ["e02", "e03"],
            "voltage": 120,
            "frequency": 5000,
        })
        self.manager.add_step(values={
            "name": "Step 3: 75V / 1kHz cooldown",
            "duration_s": 0.3,
            "voltage": 75,
            "frequency": 1000,
        })

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Per-step / per-phase timing state.  All timestamps are
        # time.monotonic() from the moment the corresponding ack arrives.
        # None means "not yet started; display 0.00s".
        # Mutated from the GUI thread only (via Qt signals).
        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None
        self._current_row = None
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)   # 10 Hz elapsed-time display
        self._tick_timer.timeout.connect(self._refresh_status)

        self._dramatiq_worker = None
        self._setup_dramatiq_routing()

        self._build_status_bar()
        self._wire_signals()
        self._build_toolbar()
        self._reset_status()

    # ------------------------------------------------------------------
    # Dramatiq routing
    # ------------------------------------------------------------------

    def _setup_dramatiq_routing(self):
        """Register subscriptions for all demo actors and start a worker.

        Best-effort: if Redis isn't running, columns will time out at
        runtime and surface as protocol_error in the dialog.
        """
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor
            from dramatiq import Worker

            broker = dramatiq.get_broker()
            # Drop any queued messages from prior demo runs.
            broker.flush_all()

            router = MessageRouterActor()

            # Purge stale demo subscribers — actor names recorded in
            # Redis by prior demo processes whose actors aren't
            # registered in this process. Without this, a previous demo
            # (e.g. run_voltage_frequency_demo's ppt_vf_demo_spy) leaves
            # behind a subscription that fires ActorNotFound on every
            # publish.
            #
            # Only touch demo-namespaced actor names — leave real
            # listeners (e.g., dropbot_controller_listener subscribed
            # from the full app running in another process) alone.
            _demo_prefixes = ("ppt_demo_", "ppt4_demo_", "ppt_vf_demo_")
            _demo_topics = (
                ELECTRODES_STATE_CHANGE, ELECTRODES_STATE_APPLIED,
                PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
                VOLTAGE_APPLIED, FREQUENCY_APPLIED,
            )
            for topic in _demo_topics:
                try:
                    subs = router.message_router_data.get_subscribers_for_topic(topic)
                except Exception:
                    continue
                for entry in subs:
                    actor_name = entry[0] if isinstance(entry, tuple) else entry
                    if not actor_name.startswith(_demo_prefixes):
                        continue
                    try:
                        broker.get_actor(actor_name)
                    except Exception:
                        try:
                            router.message_router_data.remove_subscriber_from_topic(
                                topic=topic, subscribing_actor_name=actor_name,
                            )
                            logger.info("purged stale demo subscriber %s on %s",
                                        actor_name, topic)
                        except Exception:
                            logger.warning("failed to purge %s on %s: %s",
                                           actor_name, topic,
                                           "wrong listener_queue (likely from another router)")

            # PPT-3: electrode actuation chain
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
            )
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_APPLIED,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
            # Live electrode overlay in the device viewer
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name="ppt4_demo_actuation_overlay_listener",
            )
            # Phase-ack listener — drives per-phase / per-step timers
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_APPLIED,
                subscribing_actor_name="ppt4_demo_phase_ack_listener",
            )

            # PPT-4: voltage/frequency demo responder + executor listener
            subscribe_demo_responder(router)

            # PPT-4: status-bar V/F readout listeners
            router.message_router_data.add_subscriber_to_topic(
                topic=VOLTAGE_APPLIED,
                subscribing_actor_name="ppt4_demo_voltage_applied_listener",
            )
            router.message_router_data.add_subscriber_to_topic(
                topic=FREQUENCY_APPLIED,
                subscribing_actor_name="ppt4_demo_frequency_applied_listener",
            )

            self._router = router
        except ValueError as e:
            # MessageRouterActor() raises if message_router_actor is
            # already registered (e.g. demo loaded a second time in the
            # same process). Reuse — don't double-register.
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

    # ------------------------------------------------------------------
    # Qt wiring
    # ------------------------------------------------------------------

    def _wire_signals(self):
        # Active-row highlight. step_started sets; terminal signals clear.
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row
        )

        # Device viewer follows tree selection AND the executor's running step.
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

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_step_label = QLabel("Idle")
        self._status_row_label = QLabel("")
        self._status_reps_label = QLabel("")
        self._status_step_time_label = QLabel("")
        self._status_phase_time_label = QLabel("")
        # PPT-4: voltage/frequency readouts
        self._status_voltage_label = QLabel("Voltage: --")
        self._status_frequency_label = QLabel("Frequency: --")

        # Row label takes remaining width via stretch=1.
        sb.addWidget(self._status_step_label)
        sb.addWidget(self._status_row_label, stretch=1)
        sb.addPermanentWidget(self._status_reps_label)
        sb.addPermanentWidget(self._status_step_time_label)
        sb.addPermanentWidget(self._status_phase_time_label)
        sb.addPermanentWidget(self._status_voltage_label)
        sb.addPermanentWidget(self._status_frequency_label)

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
        """Recompute the two timer labels from the ack-driven timestamps.
        Both show 0.00s until the corresponding ack lands."""
        if self._current_row is None:
            return
        target = self._phase_target if self._phase_target is not None else 0.0
        step_elapsed = (
            0.0 if self._step_started_at is None
            else time.monotonic() - self._step_started_at
        )
        phase_elapsed = (
            0.0 if self._phase_started_at is None
            else time.monotonic() - self._phase_started_at
        )
        self._status_step_time_label.setText(f"Step {step_elapsed:5.2f}s")
        self._status_phase_time_label.setText(
            f"Phase {phase_elapsed:5.2f}s / {target:.2f}s"
        )

    # ------------------------------------------------------------------
    # Protocol state slots
    # ------------------------------------------------------------------

    def _on_protocol_started(self):
        self._set_running_button_state()
        try:
            self._step_total = sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            self._step_total = 0
        self._step_index = 0
        self._status_step_label.setText(f"Step 0 / {self._step_total}")

    def _on_step_repetition(self, rep_chain):
        """Render the active rep context into the status bar."""
        if not rep_chain:
            self._status_reps_label.setText("")
            return
        parts = [f"rep {idx}/{total} of '{name}'"
                 for name, idx, total in rep_chain]
        self._status_reps_label.setText(" · ".join(parts))

    def _on_step_started(self, row):
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
        """Each ELECTRODES_STATE_APPLIED ack (re)starts the per-phase timer.
        The first ack of a step also starts the per-step timer."""
        if self._current_row is None:
            return
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now

    def _on_voltage_ack(self, voltage: int):
        """Update the status-bar voltage label when a VOLTAGE_APPLIED ack lands."""
        self._status_voltage_label.setText(f"Voltage: {voltage} V")

    def _on_frequency_ack(self, frequency: int):
        """Update the status-bar frequency label when a FREQUENCY_APPLIED ack lands."""
        self._status_frequency_label.setText(f"Frequency: {frequency} Hz")

    def _on_step_finished(self, _row):
        self._refresh_status()

    def _on_protocol_paused(self):
        self._pause_action.setText("Resume")
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
        """Restore an idle visual state at protocol end."""
        from pyface.qt.QtCore import QModelIndex
        self.widget.highlight_active_row(None)
        self.device_view.set_active_row(None)
        self.widget.tree.clearSelection()
        self.widget.tree.setCurrentIndex(QModelIndex())
        # Reset V/F readouts so the next run starts clean.
        self._status_voltage_label.setText("Voltage: --")
        self._status_frequency_label.setText("Frequency: --")

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
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
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )

    with redis_server_context():
        with dramatiq_workers_context():
            main()
