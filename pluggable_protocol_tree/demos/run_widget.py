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
import sys
import threading

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QToolBar,
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

        self._wire_signals()
        self._build_toolbar()

    def _wire_signals(self):
        # Active-row highlighting
        self.executor.qsignals.step_started.connect(
            self.widget.model.set_active_node
        )
        self.executor.qsignals.step_finished.connect(
            lambda _row: self.widget.model.set_active_node(None)
        )
        # Clean up highlight on terminal lifecycle signals
        for sig in (
            self.executor.qsignals.protocol_finished,
            self.executor.qsignals.protocol_aborted,
        ):
            sig.connect(lambda: self.widget.model.set_active_node(None))
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
        tb.addAction("Run",   self.executor.start)
        self._pause_action = tb.addAction("Pause", self._toggle_pause)
        tb.addAction("Stop",  self.executor.stop)

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
            self._pause_action.setText("Pause")
        else:
            self.executor.pause()
            self._pause_action.setText("Resume")

    def _on_error(self, msg):
        self.widget.model.set_active_node(None)
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
    app = QApplication.instance() or QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
