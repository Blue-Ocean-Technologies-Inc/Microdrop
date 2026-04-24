"""Auto-running variant of run_widget.py for end-to-end PPT-3 verification.

Builds the same QSplitter(tree | SimpleDeviceViewer) window as
run_widget.py, but pre-populates a 3-step protocol with electrodes
+ routes, auto-presses Run shortly after the window appears, prints
verbose tagged log lines for every meaningful event, and quits the
QApplication when the protocol terminates (or after a hard timeout).

Tagged log lines all start with "[AUTO ...]" / "[STEP ...]" /
"[PHASE]" / "[OVERLAY]" so the calling shell / agent can grep through
them after the process exits.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget_auto
"""

import json
import logging
import sys
import threading
import time

import dramatiq
from pyface.qt.QtCore import Qt, QTimer, Signal
from pyface.qt.QtWidgets import (
    QApplication, QMainWindow, QSplitter,
)

from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
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
# Importing the listener module registers its dramatiq actor.
from pluggable_protocol_tree.execution import listener as _listener  # noqa: F401
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


# Strip the Prometheus middleware up front (matches run_widget.py).
for _m in list(dramatiq.get_broker().middleware):
    if _m.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(_m)


logger = logging.getLogger(__name__)


# Module-level hooks for the dramatiq overlay + phase-log actors.
# Both actors run on the worker thread; they touch GUI objects only
# via Qt signals (auto-connection marshals to the GUI thread).
_overlay_target = {"viewer": None}
_phase_log: list = []


PHASE_LOG_ACTOR_NAME = "ppt_auto_phase_log"
# Share the overlay actor name with run_widget.py so that running
# either demo doesn't leave a stale subscription pointing to an actor
# the next process won't have registered. (Stale subs cause an
# ActorNotFound storm that backs up the worker queue and pushes
# wait_for past its timeout.)
OVERLAY_ACTOR_NAME = "ppt_demo_actuation_overlay_listener"
# Same trick for the phase-ack listener that drives the status timers.
ACK_ACTOR_NAME = "ppt_demo_phase_ack_listener"


@dramatiq.actor(actor_name=PHASE_LOG_ACTOR_NAME, queue_name="default")
def _phase_log_actor(message: str, topic: str, timestamp: float = None):
    """Record + print every phase the executor publishes."""
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        print(f"[PHASE] !!! malformed payload: {message!r}", flush=True)
        return
    _phase_log.append(payload)
    print(f"[PHASE] electrodes={payload['electrodes']} "
          f"channels={payload['channels']}", flush=True)


_ack_target = {"window": None}


@dramatiq.actor(actor_name=ACK_ACTOR_NAME, queue_name="default")
def _phase_ack_listener(message: str, topic: str, timestamp: float = None):
    """Each ELECTRODES_STATE_APPLIED ack hops through this actor and
    is forwarded to the GUI via a Qt signal (auto-connection marshals
    to the GUI thread). Drives the per-phase / per-step timers."""
    window = _ack_target["window"]
    if window is None:
        return
    window.phase_acked.emit()


@dramatiq.actor(actor_name=OVERLAY_ACTOR_NAME, queue_name="default")
def _overlay_listener(message: str, topic: str, timestamp: float = None):
    viewer = _overlay_target["viewer"]
    if viewer is None:
        return
    try:
        payload = json.loads(message)
    except (TypeError, ValueError):
        return
    electrodes = payload.get("electrodes", []) or []
    print(f"[OVERLAY] painting cells: {electrodes}", flush=True)
    viewer.actuation_changed.emit(list(electrodes))


def _columns():
    """Canonical PPT-3 column set (no PPT-2 demo columns — the auto
    demo focuses on the actuation chain, not the older state-string
    round-trip)."""
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
    ]


class AutoDemoWindow(QMainWindow):
    AUTO_RUN_DELAY_MS = 800       # let the GUI render first
    POST_DONE_QUIT_MS = 600        # leave a beat for the last paint
    HARD_TIMEOUT_S = 30.0          # safety net

    # Cross-thread signal from the phase-ack actor.
    phase_acked = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pluggable Protocol Tree — Auto Demo (PPT-3)")
        self.resize(1100, 600)

        self.manager = RowManager(columns=_columns())
        self.manager.protocol_metadata["electrode_to_channel"] = {
            f"e{i:02d}": i for i in range(GRID_W * GRID_H)
        }
        self._populate_protocol()

        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.device_view = SimpleDeviceViewer(self.manager, parent=self)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        splitter.addWidget(self.device_view)
        splitter.setSizes([700, 400])
        self.setCentralWidget(splitter)

        _overlay_target["viewer"] = self.device_view
        _ack_target["window"] = self
        self.phase_acked.connect(self._on_phase_ack)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        # Per-step / per-phase timing state. None = "not yet started;
        # display 0.00s". Mutated from GUI thread only.
        self._current_row = None
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None

        self._dramatiq_worker = None
        self._setup_dramatiq_routing()

        self._build_status_bar()
        self._wire_verbose_logging()
        self._wire_terminate_to_quit()

        # Auto-start + safety net.
        QTimer.singleShot(self.AUTO_RUN_DELAY_MS, self._auto_run)
        QTimer.singleShot(int(self.HARD_TIMEOUT_S * 1000), self._hard_timeout)

    def _build_status_bar(self):
        from pyface.qt.QtWidgets import QStatusBar, QLabel
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_step_label = QLabel("Idle")
        self._status_step_time_label = QLabel("")
        self._status_phase_time_label = QLabel("")
        sb.addWidget(self._status_step_label, stretch=1)
        sb.addPermanentWidget(self._status_step_time_label)
        sb.addPermanentWidget(self._status_phase_time_label)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)
        self._tick_timer.timeout.connect(self._refresh_status)

    def _refresh_status(self):
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

    def _on_phase_ack(self):
        if self._current_row is None:
            return
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now
        # Verifiable from stdout when run unattended.
        print(f"[ACK] step_elapsed="
              f"{(now - self._step_started_at):.3f}s; "
              f"phase reset to 0", flush=True)

    def _populate_protocol(self):
        """Three steps that exercise both column types and the
        trail-length config."""
        steps = [
            {
                "name": "Step 1: Hold three-cell pad",
                "duration_s": 0.3,
                "electrodes": ["e00", "e01", "e02"],
            },
            {
                "name": "Step 2: Walk top row (trail=1)",
                "duration_s": 0.3,
                "routes": [["e00", "e01", "e02", "e03", "e04"]],
                "trail_length": 1,
            },
            {
                "name": "Step 3: Walk diagonal with static pad (trail=2)",
                "duration_s": 0.3,
                "electrodes": ["e10"],
                "routes": [["e00", "e06", "e12", "e18", "e24"]],
                "trail_length": 2,
            },
        ]
        for s in steps:
            path = self.manager.add_step(values=s)
            print(f"[AUTO BUILD] step {path}: {s}", flush=True)

    def _setup_dramatiq_routing(self):
        try:
            from dramatiq import Worker
            broker = dramatiq.get_broker()
            # Drop any stale messages from a previous crashed run that
            # could be parked on the queue.
            broker.flush_all()
            print("[AUTO ROUTING] broker flushed", flush=True)

            router = MessageRouterActor()
            self._router = router

            wanted = (
                (ELECTRODES_STATE_CHANGE, DEMO_RESPONDER_ACTOR_NAME),
                (ELECTRODES_STATE_APPLIED,
                 "pluggable_protocol_tree_executor_listener"),
                (ELECTRODES_STATE_CHANGE, PHASE_LOG_ACTOR_NAME),
                (ELECTRODES_STATE_CHANGE, OVERLAY_ACTOR_NAME),
                # Status-bar timer driver — same actor name as
                # run_widget.py so subscriptions stay live across demos.
                (ELECTRODES_STATE_APPLIED, ACK_ACTOR_NAME),
            )
            self._purge_stale_subscribers(broker, router, wanted)
            for topic, actor in wanted:
                router.message_router_data.add_subscriber_to_topic(
                    topic=topic, subscribing_actor_name=actor,
                )
            self._dramatiq_worker = Worker(broker, worker_timeout=100)
            self._dramatiq_worker.start()
            print("[AUTO ROUTING] dramatiq worker + subscriptions ready",
                  flush=True)
        except Exception as e:
            print(f"[AUTO ROUTING] !!! setup failed: {e}", flush=True)
            logger.exception("Routing setup failed")

    def _purge_stale_subscribers(self, broker, router, wanted):
        """For every topic we'll publish on, drop any subscriber whose
        actor isn't registered in this process's broker. Those are
        leftovers from earlier crashed/exited demo processes; if left
        in place they trigger an ActorNotFound storm that backpressures
        the queue and slows the publish/ack handshake down.

        wanted is the (topic, actor) tuples we'll add — the actor names
        in those tuples ARE registered locally, so they survive."""
        topics = {t for t, _ in wanted}
        for topic in topics:
            try:
                subs = router.message_router_data.get_subscribers_for_topic(
                    topic
                )
            except Exception:
                continue
            for entry in subs:
                # entries are (actor_name, queue_name) tuples
                actor_name = entry[0] if isinstance(entry, tuple) else entry
                try:
                    broker.get_actor(actor_name)
                except Exception:
                    try:
                        router.message_router_data.remove_subscriber_from_topic(
                            topic=topic,
                            subscribing_actor_name=actor_name,
                        )
                        print(f"[AUTO ROUTING] purged stale subscriber: "
                              f"{actor_name} on {topic}", flush=True)
                    except Exception as e:
                        print(f"[AUTO ROUTING] failed to purge {actor_name}: "
                              f"{e}", flush=True)

    def _wire_verbose_logging(self):
        sigs = self.executor.qsignals
        sigs.protocol_started.connect(
            lambda: print("[PROTOCOL STARTED]", flush=True))
        sigs.step_started.connect(self._on_step_started_status)
        sigs.step_started.connect(
            lambda r: print(
                f"[STEP STARTED] {r.name!r} "
                f"electrodes={list(getattr(r, 'electrodes', []) or [])} "
                f"routes={list(getattr(r, 'routes', []) or [])} "
                f"trail_length={getattr(r, 'trail_length', None)}",
                flush=True))
        sigs.step_finished.connect(
            lambda r: print(f"[STEP FINISHED] {r.name!r}", flush=True))

        # Tree active-row highlight (blue background) follows the
        # currently-running step.
        sigs.step_started.connect(self.widget.highlight_active_row)
        # Device viewer active-row highlight follows step_started AND
        # the user's tree selection (so clicking a step previews its
        # electrodes/routes; clicking empty space clears the viewer).
        sigs.step_started.connect(self.device_view.set_active_row)
        sel_model = self.widget.tree.selectionModel()
        sel_model.currentRowChanged.connect(
            lambda cur, _prev: self.device_view.set_active_row(
                cur.data(Qt.UserRole) if cur.isValid() else None
            )
        )

    def _on_step_started_status(self, row):
        """Reset the timer state. Both timers stay at 0.00s until the
        first phase ack lands."""
        self._current_row = row
        self._step_started_at = None
        self._phase_started_at = None
        try:
            self._phase_target = float(getattr(row, "duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._phase_target = None
        self._status_step_label.setText(f"Step: {row.name!r}")
        self._refresh_status()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _wire_terminate_to_quit(self):
        sigs = self.executor.qsignals
        sigs.protocol_finished.connect(self._on_finished)
        sigs.protocol_aborted.connect(self._on_aborted)
        sigs.protocol_error.connect(self._on_error)

    def _auto_run(self):
        print(f"[AUTO RUN] starting protocol at "
              f"{time.strftime('%H:%M:%S')}", flush=True)
        self.executor.start()

    def _on_finished(self):
        print(f"[AUTO DONE] FINISHED -- phases published: {len(_phase_log)}",
              flush=True)
        self._clear_all_highlights()
        self._summarize_phases()
        self._shutdown(0)

    def _on_aborted(self):
        print(f"[AUTO DONE] ABORTED -- phases published: {len(_phase_log)}",
              flush=True)
        self._clear_all_highlights()
        self._summarize_phases()
        self._shutdown(2)

    def _on_error(self, msg):
        print(f"[AUTO DONE] ERROR -- {msg}", flush=True)
        self._clear_all_highlights()
        self._summarize_phases()
        self._shutdown(1)

    def _clear_all_highlights(self):
        """Restore an idle visual state at protocol end. Clears, in order:
          - tick timer + status timer state (so labels stop updating)
          - tree active-row highlight (blue executor cursor)
          - device viewer (statics + routes + actuated overlay)
          - tree selection AND current index (last so currentRowChanged
            doesn't fight the explicit set_active_row(None) above)."""
        from pyface.qt.QtCore import QModelIndex
        if self._tick_timer.isActive():
            self._tick_timer.stop()
        self._current_row = None
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None
        self._status_step_label.setText("Idle")
        self._status_step_time_label.setText("")
        self._status_phase_time_label.setText("")
        self.widget.highlight_active_row(None)
        self.device_view.set_active_row(None)
        self.widget.tree.clearSelection()
        self.widget.tree.setCurrentIndex(QModelIndex())

    def _hard_timeout(self):
        if self.executor._thread is None or not self.executor._thread.is_alive():
            return     # already done
        print(f"[AUTO TIMEOUT] protocol still running after "
              f"{self.HARD_TIMEOUT_S}s; stopping", flush=True)
        self.executor.stop()
        # Give stop a moment to propagate, then force-quit.
        QTimer.singleShot(2000, lambda: self._shutdown(3))

    def _summarize_phases(self):
        if not _phase_log:
            print("[AUTO SUMMARY] no phases recorded", flush=True)
            return
        for i, p in enumerate(_phase_log):
            print(f"[AUTO SUMMARY] phase {i}: electrodes={p['electrodes']} "
                  f"channels={p['channels']}", flush=True)

    def _shutdown(self, exit_code: int):
        # Drop the auto-only PHASE_LOG_ACTOR subscription so it doesn't
        # become a stale entry in Redis that ActorNotFound-storms a
        # future run. (The auto-purger handles leftovers anyway, but
        # cleaning up explicitly here keeps Redis tidier between runs.)
        # _shutdown can fire twice (once on terminal signal, once on
        # closeEvent); guard with hasattr so the second call is a no-op.
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        router = getattr(self, "_router", None)
        if router is not None:
            try:
                router.message_router_data.remove_subscriber_from_topic(
                    topic=ELECTRODES_STATE_CHANGE,
                    subscribing_actor_name=PHASE_LOG_ACTOR_NAME,
                )
                print(f"[AUTO SHUTDOWN] removed subscription "
                      f"{PHASE_LOG_ACTOR_NAME}", flush=True)
            except Exception as e:
                print(f"[AUTO SHUTDOWN] subscription cleanup failed: {e}",
                      flush=True)
        # Stop the worker before quitting so the process can exit
        # cleanly (worker threads aren't daemons).
        if self._dramatiq_worker is not None:
            try:
                self._dramatiq_worker.stop()
                print("[AUTO SHUTDOWN] dramatiq worker stopped", flush=True)
            except Exception as e:
                print(f"[AUTO SHUTDOWN] worker stop failed: {e}", flush=True)
            self._dramatiq_worker = None
        QApplication.instance().setProperty("auto_exit_code", exit_code)
        QTimer.singleShot(self.POST_DONE_QUIT_MS, QApplication.instance().quit)

    def closeEvent(self, event):
        self._shutdown(0)
        super().closeEvent(event)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = QApplication.instance() or QApplication(sys.argv)
    w = AutoDemoWindow()
    w.show()
    rc = app.exec()
    auto_rc = app.property("auto_exit_code")
    final_rc = int(auto_rc) if auto_rc is not None else rc
    print(f"[AUTO EXIT] qt rc={rc} auto rc={auto_rc} "
          f"phases={len(_phase_log)} -> final {final_rc}", flush=True)
    return final_rc


if __name__ == "__main__":
    sys.exit(main())
