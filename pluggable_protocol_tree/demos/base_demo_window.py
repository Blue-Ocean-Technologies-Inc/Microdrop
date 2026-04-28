"""Composition-based base window for pluggable protocol tree demos.

Demos build a DemoConfig (declarative dataclass) and call
BasePluggableProtocolDemoWindow.run(config). The base owns the standard
UX scaffolding: protocol tree widget, executor, active-row highlight,
status bar, button state machine, Dramatiq routing, Save/Load.

Each demo declares only its specific bits: columns, sample steps,
demo-specific responder subscriptions, ack-driven status readouts,
and an optional side panel.

See PPT-12 spec for design rationale (composition vs inheritance).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import dramatiq

from microdrop_utils.broker_server_helpers import (
    remove_middleware_from_dramatiq_broker,
)
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)


from logger.logger_service import get_logger

logger = get_logger(__name__)


# Strip Prometheus middleware once at module import time — every
# downstream demo needs this and the stripping is idempotent.
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)


@dataclass
class StatusReadout:
    """One ack-driven readout label in the status bar.

    The base creates one Dramatiq actor per StatusReadout (auto-named
    ppt12_demo_<label_slug>_listener) that subscribes to ``topic``,
    emits a Qt signal, and updates a QLabel in the status bar with
    ``f"{label}: {fmt(message)}"``. Until the first ack, the label
    shows ``f"{label}: {initial}"``.
    """
    label: str
    topic: str
    fmt: Callable[[str], str]
    initial: str = "--"


@dataclass
class DemoConfig:
    """Declarative demo configuration. Only ``columns_factory`` is required;
    all other fields have sensible defaults."""

    # Required.
    columns_factory: Callable[[], list]

    # Cosmetic.
    title: str = "Pluggable Protocol Tree Demo"
    window_size: tuple[int, int] = (1100, 650)

    # Optional sample steps populated after RowManager construction.
    pre_populate: Callable[[Any], None] = field(
        default_factory=lambda: (lambda rm: None)
    )

    # Subscribe demo responders / additional listeners on the router.
    # Called AFTER the base wires the standard PPT-3 electrode chain
    # + the phase-ack listener (if phase_ack_topic is set) +
    # the StatusReadout listeners.
    routing_setup: Callable[[Any], None] = field(
        default_factory=lambda: (lambda router: None)
    )

    # Single ack topic that drives the per-phase timer.
    # If None: only step-elapsed timer shown, no per-phase timer.
    phase_ack_topic: str | None = ELECTRODES_STATE_APPLIED

    # Right-side status bar readouts.
    status_readouts: list[StatusReadout] = field(default_factory=list)

    # Side panel (e.g. SimpleDeviceViewer for PPT-3 / integration demo).
    # Returns a QWidget or None. Called once during window setup.
    side_panel_factory: Callable[[Any], Any] | None = None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(label: str) -> str:
    """Slugify a status-readout label for use as a Dramatiq actor name suffix.

    'Voltage' -> 'voltage'
    'Magnet Height (mm)' -> 'magnet_height_mm'
    """
    return _SLUG_RE.sub("_", label.lower()).strip("_")


class _PerSlugEmitter:
    """Tiny shim that exposes .emit(message) and forwards to the
    window's per-instance readout_acked signal with a fixed slug."""
    __slots__ = ("_signal", "_slug")

    def __init__(self, signal, slug):
        self._signal = signal
        self._slug = slug

    def emit(self, message):
        self._signal.emit(self._slug, message)


# Module-level target for the phase-ack listener actor. The actor runs
# on a Dramatiq worker thread; it emits a Qt signal that auto-connection
# delivers on the GUI thread.
_phase_ack_target = {"window": None}


@dramatiq.actor(actor_name="ppt12_demo_phase_ack_listener", queue_name="default")
def _phase_ack_listener(message: str, topic: str, timestamp: float = None):
    window = _phase_ack_target.get("window")
    if window is None:
        return
    window.phase_acked.emit()


# Module-level target for status-readout listeners. Each actor reads
# its own message and forwards (slug, message) to the bound window.
_readout_target = {"window": None}


def _make_readout_actor(slug: str):
    """Register a Dramatiq actor named ppt12_demo_<slug>_listener that
    emits the window's readout_acked signal on every message received.
    Idempotent — safe to call repeatedly with the same slug."""
    actor_name = f"ppt12_demo_{slug}_listener"
    broker = dramatiq.get_broker()
    try:
        broker.get_actor(actor_name)
        return actor_name   # already registered
    except dramatiq.errors.ActorNotFound:
        pass

    @dramatiq.actor(actor_name=actor_name, queue_name="default")
    def _listener(message: str, topic: str, timestamp: float = None):
        window = _readout_target.get("window")
        if window is None:
            return
        window.readout_acked.emit(slug, message)

    return actor_name


import threading
import time

from pyface.qt.QtCore import Qt, QTimer, Signal
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox,
    QSplitter, QStatusBar, QToolBar,
)

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


class BasePluggableProtocolDemoWindow(QMainWindow):
    """Hosts a ProtocolTreeWidget + ProtocolExecutor with the standard
    UX scaffolding. See PPT-12 spec for the full feature list.

    Construct with a DemoConfig; call .show() and .exec() OR use the
    .run(config) classmethod for one-shot main() convenience."""

    # Cross-thread signal — Dramatiq actor emits via the module-level
    # listener (registered when phase_ack_topic is set); auto-connection
    # delivers _on_phase_ack on the GUI thread.
    phase_acked = Signal()

    # Cross-thread signal for status-readout updates: (slug, message)
    readout_acked = Signal(str, str)

    def __init__(self, config: DemoConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle(config.title)
        self.resize(*config.window_size)

        self.manager = RowManager(columns=config.columns_factory())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)

        # Central layout: just the tree, OR a splitter with tree + side panel.
        if self.config.side_panel_factory is not None:
            side = self.config.side_panel_factory(self.manager)
            if side is not None:
                splitter = QSplitter(Qt.Horizontal)
                splitter.addWidget(self.widget)
                splitter.addWidget(side)
                splitter.setSizes([
                    int(self.config.window_size[0] * 0.65),
                    int(self.config.window_size[0] * 0.35),
                ])
                self.setCentralWidget(splitter)
            else:
                self.setCentralWidget(self.widget)
        else:
            self.setCentralWidget(self.widget)

        # Pre-populate sample steps BEFORE the executor is built.
        config.pre_populate(self.manager)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        self._router = None
        self._dramatiq_worker = None

        # Per-step / per-phase timing state. Mutated from GUI thread only.
        self._step_index = 0
        self._step_total = 0
        self._step_started_at: float | None = None
        self._phase_started_at: float | None = None
        self._phase_target: float | None = None
        self._current_row = None
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)   # 10 Hz
        self._tick_timer.timeout.connect(self._refresh_status)

        self._status_phase_time_label = None

        # Per-readout state — _readout_labels is populated by _build_status_bar;
        # _readout_signals is populated afterwards from _readout_fmts.
        self._readout_labels: dict[str, QLabel] = {}

        self._build_status_bar()

        # Wire readout updates: one signal-emit handler per slug → label update.
        self._readout_fmts = {
            _slug(r.label): (r.label, r.fmt) for r in self.config.status_readouts
        }
        # Per-slug Signal accessors that just emit on the shared readout_acked.
        # Tests can do w._readout_signals[slug].emit(msg).
        self._readout_signals: dict[str, _PerSlugEmitter] = {
            slug: _PerSlugEmitter(self.readout_acked, slug)
            for slug in self._readout_fmts
        }
        self.readout_acked.connect(self._on_readout_ack)

        # Bind the module-level target so readout actor callbacks reach this window.
        # Warn if a previous live window will be displaced (multi-window collision).
        existing = _readout_target.get("window")
        if existing is not None and existing is not self:
            logger.warning(
                "Multiple live BasePluggableProtocolDemoWindow instances detected. "
                "Only the most recent window will receive readout messages."
            )
        _readout_target["window"] = self

        # Actor registration is broker-agnostic; topic subscription happens in
        # _setup_dramatiq_routing_internal.
        for readout in self.config.status_readouts:
            _make_readout_actor(_slug(readout.label))

        self._setup_dramatiq_routing_internal()
        if self._router is not None:
            # Demo-specific responders / listeners — called AFTER the
            # standard chain so the demo can rely on it being in place.
            config.routing_setup(self._router)

        self._wire_executor_signals()
        self._build_toolbar()
        self._wire_button_state_machine()
        self._set_idle_button_state()

    def _setup_dramatiq_routing_internal(self):
        """Wires the standard PPT-3 electrode actuation chain
        (electrode_responder + executor listener for ELECTRODES_STATE_APPLIED).

        Best-effort: if Redis isn't reachable, sets self._router = None
        and logs a warning. Runtime calls to ctx.wait_for() will then
        time out at protocol-run time and surface as protocol_error.
        """
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import (
                MessageRouterActor,
            )
            from dramatiq import Worker

            broker = dramatiq.get_broker()
            broker.flush_all()
            router = MessageRouterActor()

            # Standard PPT-3 electrode chain.
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_CHANGE,
                subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
            )
            router.message_router_data.add_subscriber_to_topic(
                topic=ELECTRODES_STATE_APPLIED,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )

            if self.config.phase_ack_topic is not None:
                existing_phase = _phase_ack_target.get("window")
                if existing_phase is not None and existing_phase is not self:
                    logger.warning(
                        "Multiple live BasePluggableProtocolDemoWindow instances "
                        "detected. Only the most recent window will receive "
                        "phase-ack messages."
                    )
                _phase_ack_target["window"] = self
                router.message_router_data.add_subscriber_to_topic(
                    topic=self.config.phase_ack_topic,
                    subscribing_actor_name="ppt12_demo_phase_ack_listener",
                )

            # StatusReadout listeners — actors already registered in __init__;
            # here we only add the topic subscription.
            for readout in self.config.status_readouts:
                slug = _slug(readout.label)
                actor_name = f"ppt12_demo_{slug}_listener"
                router.message_router_data.add_subscriber_to_topic(
                    topic=readout.topic,
                    subscribing_actor_name=actor_name,
                )

            self._router = router
            self._dramatiq_worker = Worker(broker, worker_timeout=100)
            self._dramatiq_worker.start()
        except ValueError as e:
            if "already registered" not in str(e):
                logger.warning("Demo Dramatiq routing setup failed: %s", e)
        except Exception as e:
            logger.warning(
                "Demo Dramatiq routing setup failed (Redis not running?): %s",
                e,
            )

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_step_label = QLabel("Idle")
        self._status_row_label = QLabel("")
        self._status_step_time_label = QLabel("")
        sb.addWidget(self._status_step_label)
        sb.addWidget(self._status_row_label, stretch=1)
        sb.addPermanentWidget(self._status_step_time_label)
        if self.config.phase_ack_topic is not None:
            self._status_phase_time_label = QLabel("")
            sb.addPermanentWidget(self._status_phase_time_label)
        # StatusReadout labels.
        for readout in self.config.status_readouts:
            slug = _slug(readout.label)
            label = QLabel(f"{readout.label}: {readout.initial}")
            sb.addPermanentWidget(label)
            self._readout_labels[slug] = label

    def _wire_executor_signals(self):
        # Active-row highlight on each step start.
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row
        )
        # Status bar updates.
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        if self.config.phase_ack_topic is not None:
            self.phase_acked.connect(self._on_phase_ack)

    def _on_protocol_started(self):
        try:
            self._step_total = sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            self._step_total = 0
        self._step_index = 0
        self._status_step_label.setText(f"Step 0 / {self._step_total}")

    def _on_step_started(self, row):
        self._step_index += 1
        self._current_row = row
        # Reset phase timestamps; the phase ack handler restarts them.
        self._step_started_at = time.monotonic()
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
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _on_phase_ack(self):
        """Each ack restarts the per-phase timer. The first ack of a step
        also starts the per-step timer (overrides the time.monotonic()
        set in _on_step_started so timers run from the actual ack moment)."""
        if self._current_row is None:
            return
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now

    def _on_readout_ack(self, slug: str, message: str):
        spec = self._readout_fmts.get(slug)
        if spec is None:
            return
        label_prefix, fmt = spec
        label_widget = self._readout_labels.get(slug)
        if label_widget is None:
            return
        try:
            text = fmt(message)
        except Exception as e:
            text = f"<error: {e}>"
        label_widget.setText(f"{label_prefix}: {text}")

    def _refresh_status(self):
        if self._step_started_at is None:
            return
        step_elapsed = time.monotonic() - self._step_started_at
        self._status_step_time_label.setText(f"Step {step_elapsed:5.2f}s")
        if self._status_phase_time_label is not None:
            phase_elapsed = (
                0.0 if self._phase_started_at is None
                else time.monotonic() - self._phase_started_at
            )
            target = self._phase_target if self._phase_target is not None else 0.0
            self._status_phase_time_label.setText(
                f"Phase {phase_elapsed:5.2f}s / {target:.2f}s"
            )

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
        self._toolbar = tb

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.manager.to_json(), f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            self.manager.set_state_from_json(
                data, columns=self.config.columns_factory(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))

    def _wire_button_state_machine(self):
        self.executor.qsignals.protocol_started.connect(self._set_running_button_state)
        self.executor.qsignals.protocol_paused.connect(self._on_protocol_paused)
        self.executor.qsignals.protocol_resumed.connect(self._on_protocol_resumed)
        for sig in (
            self.executor.qsignals.protocol_finished,
            self.executor.qsignals.protocol_aborted,
        ):
            sig.connect(self._on_protocol_terminated)

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

    def _on_protocol_paused(self):
        self._pause_action.setText("Resume")
        self._tick_timer.stop()

    def _on_protocol_resumed(self):
        self._pause_action.setText("Pause")
        if self._current_row is not None:
            self._tick_timer.start()

    def _on_protocol_terminated(self):
        self._set_idle_button_state()
        self._tick_timer.stop()

    def closeEvent(self, event):
        if self._dramatiq_worker is not None:
            try:
                self._dramatiq_worker.stop()
            except Exception:
                logger.exception("Error stopping demo dramatiq worker")
        super().closeEvent(event)
