"""Runnable headed demo for the magnet compound column.

Builds a protocol with the existing PPT-3 builtins + the magnet
compound column. Auto-populates 3 sample steps so the user can
immediately verify:

  1. Two columns render ('Magnet' checkbox + 'Magnet Height (mm)'
     spinner) for the one compound contribution
  2. The Height cell is read-only when Magnet is unchecked (greyed
     out spinner)
  3. The Height spinner displays 'Default' at the sentinel value;
     spinning up shows numeric values
  4. Toggling Magnet flips the Height cell's editability
  5. Run the protocol -- the in-process magnet responder echoes the
     setpoints + the status bar updates with the latest MAGNET_APPLIED
     payload

Run: pixi run python -m peripheral_protocol_controls.demos.run_widget_magnet_demo
"""

import json
import logging
import sys
import threading
import time
from pathlib import Path

import dramatiq

# Centralised middleware strip — see microdrop_utils.broker_server_helpers.
from microdrop_utils.broker_server_helpers import (
    remove_middleware_from_dramatiq_broker,
)
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtWidgets import (
    QApplication, QLabel, QMainWindow, QSplitter, QStatusBar, QToolBar,
)

from peripheral_controller.consts import (
    PROTOCOL_SET_MAGNET, MAGNET_APPLIED,
)
from peripheral_protocol_controls.demos.magnet_responder import (
    subscribe_demo_responder,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    make_magnet_column,
)
from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import ProtocolSession
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


logger = logging.getLogger(__name__)


# Module-level Qt-signal target for the magnet-applied listener. The
# Dramatiq actor runs on a worker thread; it emits a Qt signal so
# auto-connection delivers the slot on the GUI thread.
_magnet_target = {"window": None}


@dramatiq.actor(actor_name="ppt5_demo_magnet_applied_listener", queue_name="default")
def _magnet_applied_listener(message: str, topic: str, timestamp: float = None):
    window = _magnet_target.get("window")
    if window is None:
        return
    window.magnet_acked.emit(message)


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_magnet_column()),
    ]


class DemoWindow(QMainWindow):
    magnet_acked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPT-5 Demo — Magnet Compound Column")
        self.resize(900, 500)

        self.manager = RowManager(columns=_columns())
        # Pre-populate the 3 magnet states.
        self.manager.add_step(values={
            "name": "Step 1: engage at Default (sentinel; uses live pref)",
            "duration_s": 0.2,
            "magnet_on": True,
            # default value at row creation is the sentinel; explicit
            # for clarity in the demo:
            "magnet_height_mm": 0.0,
        })
        self.manager.add_step(values={
            "name": "Step 2: engage at 12.0 mm explicit",
            "duration_s": 0.2,
            "magnet_on": True,
            "magnet_height_mm": 12.0,
        })
        self.manager.add_step(values={
            "name": "Step 3: retract",
            "duration_s": 0.2,
            "magnet_on": False,
            "magnet_height_mm": 0.0,
        })

        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        self.setCentralWidget(splitter)

        # Status bar with latest magnet state.
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._magnet_status = QLabel("Magnet: --")
        sb.addPermanentWidget(self._magnet_status)

        _magnet_target["window"] = self
        self.magnet_acked.connect(self._on_magnet_acked)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        self._dramatiq_worker = None
        self._setup_dramatiq_routing()

        tb = QToolBar("Demo")
        self.addToolBar(tb)
        self._run_action = tb.addAction("Run", self.executor.start)
        self._stop_action = tb.addAction("Stop", self.executor.stop)

    def _setup_dramatiq_routing(self):
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import (
                MessageRouterActor,
            )
            from dramatiq import Worker

            broker = dramatiq.get_broker()
            broker.flush_all()

            router = MessageRouterActor()

            # Demo magnet responder + executor listener for MAGNET_APPLIED
            subscribe_demo_responder(router)

            # Listener for status-bar updates
            router.message_router_data.add_subscriber_to_topic(
                topic=MAGNET_APPLIED,
                subscribing_actor_name="ppt5_demo_magnet_applied_listener",
            )

            self._router = router

            self._dramatiq_worker = Worker(broker, worker_timeout=100)
            self._dramatiq_worker.start()

        except Exception as e:
            logger.warning("Demo Dramatiq routing setup failed (Redis not running?): %s", e)

    def _on_magnet_acked(self, payload: str):
        state = "engaged" if payload == "1" else "retracted"
        self._magnet_status.setText(f"Magnet: {state}")

    def closeEvent(self, event):
        if self._dramatiq_worker is not None:
            try:
                self._dramatiq_worker.stop()
            except Exception:
                logger.exception("Error stopping demo dramatiq worker")
        super().closeEvent(event)


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
