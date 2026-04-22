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

from pyface.qt.QtCore import Qt, QTimer
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox, QStatusBar,
    QToolBar,
)

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.message_column import make_message_column
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


def _columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_repetitions_column(),
        make_duration_column(),
        make_message_column(),
    ]


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pluggable Protocol Tree — Demo (PPT-2)")
        self.resize(1000, 600)

        self.manager = RowManager(columns=_columns())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.setCentralWidget(self.widget)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Per-step timing state (mutated from GUI thread only).
        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._step_total_duration = None
        self._current_row = None
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)   # 10 Hz elapsed-time display
        self._tick_timer.timeout.connect(self._refresh_status)

        self._build_status_bar()
        self._wire_signals()
        self._build_toolbar()
        self._reset_status()

    def _wire_signals(self):
        # Active-row highlight. Only step_started + terminal signals
        # touch the highlight — step_finished does NOT clear it, so the
        # highlight stays on the just-finished row through the gap until
        # the next step_started replaces it. (Clearing on step_finished
        # makes the highlight flash off between steps and is invisible.)
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row
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
        self._status_time_label = QLabel("")
        # Row label takes any remaining width via stretch=1.
        sb.addWidget(self._status_step_label)
        sb.addWidget(self._status_row_label, stretch=1)
        sb.addPermanentWidget(self._status_reps_label)
        sb.addPermanentWidget(self._status_time_label)

    def _reset_status(self):
        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._step_total_duration = None
        self._current_row = None
        self._status_step_label.setText("Idle")
        self._status_row_label.setText("")
        self._status_reps_label.setText("")
        self._status_time_label.setText("")

    def _refresh_status(self):
        if self._step_started_at is None or self._current_row is None:
            return
        elapsed = time.monotonic() - self._step_started_at
        if self._step_total_duration is not None:
            self._status_time_label.setText(
                f"{elapsed:5.2f}s / {self._step_total_duration:.2f}s"
            )
        else:
            self._status_time_label.setText(f"{elapsed:5.2f}s")

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
        self._step_index += 1
        self._current_row = row
        self._step_started_at = time.monotonic()
        try:
            self._step_total_duration = float(getattr(row, "duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._step_total_duration = None
        path = ".".join(str(i + 1) for i in row.path) if row.path else ""
        path_str = f" (path {path})" if path else ""
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        self._status_row_label.setText(f"{row.name}{path_str}")
        self._refresh_status()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _on_step_finished(self, _row):
        # Freeze the time label at the step's actual elapsed; keep the
        # step labels visible until the next step_started replaces them.
        if self._step_started_at is not None:
            elapsed = time.monotonic() - self._step_started_at
            if self._step_total_duration is not None:
                self._status_time_label.setText(
                    f"{elapsed:5.2f}s / {self._step_total_duration:.2f}s"
                )
            else:
                self._status_time_label.setText(f"{elapsed:5.2f}s")

    def _on_protocol_paused(self):
        self._pause_action.setText("Resume")
        # Stop the elapsed-time tick during pause; resume restarts it.
        self._tick_timer.stop()

    def _on_protocol_resumed(self):
        self._pause_action.setText("Pause")
        if self._step_started_at is not None:
            self._tick_timer.start()

    def _on_protocol_terminated(self):
        self.widget.highlight_active_row(None)
        self._set_idle_button_state()
        self._tick_timer.stop()
        self._reset_status()

    def _on_error(self, msg):
        self.widget.highlight_active_row(None)
        self._set_idle_button_state()
        self._tick_timer.stop()
        self._reset_status()
        QMessageBox.critical(self, "Protocol error", msg)

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
            self.manager = RowManager.from_json(data, columns=_columns())
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
            return
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.setCentralWidget(self.widget)
        # Re-wire executor against the new manager
        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )
        self._wire_signals()


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
    main()
