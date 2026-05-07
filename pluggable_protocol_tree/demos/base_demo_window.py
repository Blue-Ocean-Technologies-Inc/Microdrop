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
    # Default width sized so the legacy-style StatusBar's full label
    # row (Total Time / Step Time / Phase Time / Repeat Protocol /
    # Step X/Y / Repetition X/Y / Most Recent Step / Next Step) fits
    # without horizontal clipping at moderate step-name lengths.
    window_size: tuple[int, int] = (1500, 650)

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

    # Demo-specific wiring that needs the constructed window (e.g. wiring
    # a side-panel widget's set_active_row to the executor's step_started,
    # or installing a dramatiq actor that captures a window attribute).
    # Called as the FINAL step of __init__ — all base scaffolding (executor,
    # status bar, toolbar, routing) is already in place.
    post_build_setup: Callable[[Any], None] = field(
        default_factory=lambda: (lambda window: None)
    )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(label: str) -> str:
    """Slugify a status-readout label for use as a Dramatiq actor name suffix.

    'Voltage' -> 'voltage'
    'Magnet Height (mm)' -> 'magnet_height_mm'
    """
    return _SLUG_RE.sub("_", label.lower()).strip("_")


# Actor-name prefixes used by demo processes. The purge loop only touches
# subscribers matching one of these — real listeners (other processes'
# controllers, etc.) are never purged. New demos with their own actors
# must add their prefix here. ``ppt11_demo_`` is forward-declared for the
# planned PPT-11 demo refactor; no actors with that prefix exist yet.
_DEMO_PREFIXES = (
    "ppt_demo_", "ppt4_demo_", "ppt5_demo_", "ppt6_demo_", "ppt11_demo_",
    "ppt12_demo_", "ppt_vf_demo_", "integration_demo_",
)


def _is_purgable_demo_actor_name(name: str) -> bool:
    """True if an actor name matches a known demo-prefix convention.
    Used by the stale-subscriber purger to leave real listeners alone."""
    return name.startswith(_DEMO_PREFIXES)


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

from pyface.qt.QtCore import Qt, QModelIndex, QTimer, Signal
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow,
    QSplitter, QStatusBar, QToolBar, QVBoxLayout, QWidget,
)

from microdrop_application.dialogs.pyface_wrapper import error as error_dialog

from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.navigation_bar import (
    NavigationBar, StatusBar, make_separator,
)
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

        # Side panel widget if side_panel_factory yielded one, else None.
        # post_build_setup callbacks should reach the side panel via this
        # attribute rather than walking the central widget's children.
        self._side_panel = None

        # Tree-or-splitter goes inside a vertical container with the
        # NavigationBar (built later in __init__) sitting above it. The
        # nav bar is created after the executor so its button slots can
        # bind directly to executor.start / .stop / pause-toggle.
        if self.config.side_panel_factory is not None:
            side = self.config.side_panel_factory(self.manager)
            if side is not None:
                self._side_panel = side
                splitter = QSplitter(Qt.Horizontal)
                splitter.addWidget(self.widget)
                splitter.addWidget(side)
                splitter.setSizes([
                    int(self.config.window_size[0] * 0.65),
                    int(self.config.window_size[0] * 0.35),
                ])
                self._central_content = splitter
            else:
                self._central_content = self.widget
        else:
            self._central_content = self.widget

        # Pre-populate sample steps BEFORE the executor is built.
        config.pre_populate(self.manager)

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

        self._router = None

        # Per-step / per-phase timing state. Mutated from GUI thread only.
        self._step_index = 0
        self._step_total = 0
        self._step_started_at: float | None = None
        self._phase_started_at: float | None = None
        self._phase_target: float | None = None
        self._current_row = None
        # Auto-repeat state. Driven by the StatusBar's
        # edit_repeat_protocol spinbox at play-button time.
        self._repeats_total = 1
        self._repeats_completed = 0
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
        self._build_navigation_bar()
        self._wire_button_state_machine()
        self._set_idle_button_state()

        # Final: demo-specific wiring that needs the constructed window.
        config.post_build_setup(self)

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

            broker = dramatiq.get_broker()
            broker.flush_all()
            router = MessageRouterActor()

            # Purge stale demo subscribers — actor names recorded in
            # Redis by prior demo processes whose actors aren't
            # registered in this process. Without this, a previous
            # demo's spy/listener leaves behind a subscription that
            # fires ActorNotFound on every publish to its topic.
            #
            # Only touch demo-prefixed names — leave real listeners
            # belonging to other processes alone.
            broker_topics_to_check = (
                ELECTRODES_STATE_CHANGE, ELECTRODES_STATE_APPLIED,
            )
            extra_topics = []
            if self.config.phase_ack_topic is not None:
                extra_topics.append(self.config.phase_ack_topic)
            for r in self.config.status_readouts:
                extra_topics.append(r.topic)
            # Dedupe — phase_ack_topic often equals one of the standard
            # electrode topics (default is ELECTRODES_STATE_APPLIED).
            topics_to_check = {*broker_topics_to_check, *extra_topics}
            for topic in topics_to_check:
                try:
                    subs = router.message_router_data.get_subscribers_for_topic(topic)
                except Exception:
                    continue
                for entry in subs:
                    actor_name = entry[0] if isinstance(entry, tuple) else entry
                    if not _is_purgable_demo_actor_name(actor_name):
                        continue
                    try:
                        broker.get_actor(actor_name)
                    except dramatiq.errors.ActorNotFound:
                        try:
                            router.message_router_data.remove_subscriber_from_topic(
                                topic=topic,
                                subscribing_actor_name=actor_name,
                            )
                            logger.info("purged stale demo subscriber %s on %s",
                                        actor_name, topic)
                        except Exception:
                            logger.warning(
                                "failed to purge %s on %s (likely wrong "
                                "listener_queue from another router)",
                                actor_name, topic,
                            )

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
        except ValueError as e:
            if "already registered" not in str(e):
                logger.warning("Demo Dramatiq routing setup failed: %s", e)
        except Exception as e:
            logger.warning(
                "Demo Dramatiq routing setup failed (Redis not running?): %s",
                e,
            )

    def _build_status_bar(self):
        """Build the legacy-style StatusBar widget (mounted under the nav
        bar in _build_navigation_bar) plus a thin bottom QStatusBar that
        only hosts demo-specific per-readout labels.

        Old single-attribute names (``_status_step_label`` etc.) are
        retained as aliases onto the StatusBar widget's labels so test
        coverage and demo subclasses keep working.
        """
        self.status_bar = StatusBar()
        # Reveal the phase time slot only when the demo cares about
        # per-phase acks; otherwise it stays hidden so the top bar
        # doesn't show a frozen "Phase 0.00s / 0.00s" forever.
        phase_enabled = self.config.phase_ack_topic is not None
        self.status_bar.lbl_phase_time.setVisible(phase_enabled)

        # Aliases for backward compat with tests + demo subclasses.
        # _status_row_label is intentionally dropped — the new layout
        # has no row-name slot (per design discussion).
        self._status_step_label = self.status_bar.lbl_step_progress
        self._status_step_time_label = self.status_bar.lbl_step_time
        self._status_reps_label = self.status_bar.lbl_step_repetition
        self._status_phase_time_label = (
            self.status_bar.lbl_phase_time if phase_enabled else None
        )

        # Bottom QStatusBar — only readouts live here now.
        sb = QStatusBar()
        self.setStatusBar(sb)
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
        self.executor.qsignals.step_finished.connect(self._on_step_finished)
        self.executor.qsignals.step_repetition.connect(self._on_step_repetition)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        self.executor.qsignals.protocol_error.connect(self._on_error)
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
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        # Recent / next-step labels — show the actual step name of the
        # currently-running row plus the upcoming one. Walking
        # iter_execution_steps once per step is fine; protocols stay
        # under a few hundred steps.
        self.status_bar.lbl_recent_step.setText(
            f"Most Recent Step: {row.name}"
        )
        self.status_bar.lbl_next_step.setText(
            f"Next Step: {self._next_step_name(row)}"
        )
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _next_step_name(self, current):
        """Return the display name of the step that follows ``current`` in
        execution order, or "-" if ``current`` is the last step."""
        steps = self.manager.iter_execution_steps()
        cur_path = tuple(current.path)
        # Advance past the current row, return the next one.
        for row in steps:
            if tuple(row.path) == cur_path:
                next_row = next(steps, None)
                return next_row.name if next_row is not None else "-"
        return "-"

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

    def _on_step_repetition(self, rep_chain):
        """Render the active rep context (e.g. "rep 2/3 of 'Wash'") into
        the status bar. Empty chain (no repeating ancestor) clears."""
        if not rep_chain:
            self._status_reps_label.setText("")
            return
        parts = [
            f"rep {idx}/{total} of '{name}'" for name, idx, total in rep_chain
        ]
        self._status_reps_label.setText(" · ".join(parts))

    def _on_step_finished(self, _row):
        # Freeze the elapsed-time labels at the step's actual elapsed.
        # They stay visible until the next step_started resets to 0.00s.
        self._refresh_status()

    def _on_error(self, msg):
        """protocol_error → reset to idle and show a styled error dialog.
        Repeat state is cleared so a half-finished run doesn't auto-rerun."""
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._clear_all_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
        error_dialog(parent=self, title="Protocol error", message=str(msg))

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
        """Top QToolBar holds the Add/Save/Load utility actions; the
        playback + step-navigation buttons live on the NavigationBar
        below the toolbar (built next in ``_build_navigation_bar``)."""
        tb = QToolBar("Protocol")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())
        tb.addAction("Add Group", lambda: self.manager.add_group())
        tb.addSeparator()
        tb.addAction("Save…", self._save)
        tb.addAction("Load…", self._load)
        self._toolbar = tb

    def _build_navigation_bar(self):
        """Build the NavigationBar (ported from protocol_grid) and wire
        each button to the executor / step-cursor navigation. Mounts the
        bar above the central content (tree or tree+side-panel splitter)."""
        self.navigation_bar = NavigationBar()

        # Playback.
        self.navigation_bar.btn_play.clicked.connect(self._on_play_clicked)
        self.navigation_bar.btn_resume.clicked.connect(self._toggle_pause)
        self.navigation_bar.btn_stop.clicked.connect(self.executor.stop)

        # Step navigation (cursor only — no protocol mutation).
        self.navigation_bar.btn_first.clicked.connect(self._navigate_to_first_step)
        self.navigation_bar.btn_prev.clicked.connect(self._navigate_to_previous_step)
        self.navigation_bar.btn_next.clicked.connect(self._navigate_to_next_step)
        self.navigation_bar.btn_last.clicked.connect(self._navigate_to_last_step)

        # Phase navigation: per-phase cursor isn't implemented yet (PPT-10
        # scope item). Buttons stay visually present but disabled until
        # the phase cursor arrives.
        self.navigation_bar.set_phase_navigation_enabled(False, False)

        # Wrap navigation bar + status bar + existing central content
        # in a vertical layout. The status bar (legacy-style) sits
        # directly under the nav bar, mirroring the old protocol_grid
        # layout — separator between status and tree only.
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation_bar)
        layout.addWidget(self.status_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self._central_content)
        self.setCentralWidget(container)

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
            error_dialog(parent=self, title="Save error", message=str(e))

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
            error_dialog(parent=self, title="Load error", message=str(e))

    def _wire_button_state_machine(self):
        self.executor.qsignals.protocol_started.connect(self._set_running_button_state)
        self.executor.qsignals.protocol_paused.connect(self._on_protocol_paused)
        self.executor.qsignals.protocol_resumed.connect(self._on_protocol_resumed)
        # Split protocol_finished from protocol_aborted so the auto-repeat
        # logic only fires on natural completion (not user Stop).
        self.executor.qsignals.protocol_finished.connect(self._on_protocol_finished)
        self.executor.qsignals.protocol_aborted.connect(self._on_protocol_aborted)

    def _set_idle_button_state(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_play_state()
        nb.btn_stop.setEnabled(False)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)

    def _set_running_button_state(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)         # acts as Pause while running
        nb.show_pause_state()
        nb.btn_stop.setEnabled(True)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)

    def _on_play_clicked(self):
        """While idle: start the protocol from the currently-selected
        step (or from the beginning if nothing is selected), and prime
        the auto-repeat counter from the StatusBar's spinbox. While
        running/paused: toggle pause. Mirrors the legacy
        protocol_grid play-button behaviour."""
        if self._is_protocol_active():
            self._toggle_pause()
            return
        self._repeats_total = self.status_bar.edit_repeat_protocol.value()
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self.executor.start(start_step_path=self._selected_step_path())

    def _update_repeat_status_label(self):
        """Reflect the current repeat counter into 'X/' (the X in
        'X/<total>' shown on the status bar)."""
        self.status_bar.lbl_repeat_protocol_status.setText(
            f"{self._repeats_completed}/"
        )

    def _selected_step_path(self):
        """Return the path tuple of the currently-selected row, but only
        if it's a step row that actually appears in execution order;
        else None (which causes the executor to start from the
        beginning)."""
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget._index_to_path(idx)
        for row in self.manager.iter_execution_steps():
            if tuple(row.path) == path:
                return path
        return None

    def _is_protocol_active(self):
        """True iff the executor is currently running or paused. The
        Stop button's enabled state tracks this exactly (via the
        protocol_started / protocol_finished / protocol_aborted signal
        chain), so use it as the source of truth."""
        return self.navigation_bar.btn_stop.isEnabled()

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
        else:
            self.executor.pause()

    def _on_protocol_paused(self):
        self.navigation_bar.show_resume_state()
        self._tick_timer.stop()

    def _on_protocol_resumed(self):
        self.navigation_bar.show_pause_state()
        if self._current_row is not None:
            self._tick_timer.start()

    def _on_protocol_finished(self):
        """Natural completion. Bump the repeat counter; if more reps
        remain, re-queue executor.start() on the next event-loop tick
        (the worker thread emits protocol_finished from inside its
        finally block — calling start() now would no-op against
        ``_thread.is_alive()``)."""
        self._repeats_completed += 1
        self._update_repeat_status_label()
        if self._repeats_completed < self._repeats_total:
            QTimer.singleShot(50, self._restart_for_next_rep)
            return
        self._on_protocol_terminated()

    def _restart_for_next_rep(self):
        # Each repeat runs the protocol from the beginning — start_step_path
        # is intentionally None.
        self.executor.start()

    def _on_protocol_aborted(self):
        """User pressed Stop. Clear the repeat state (no auto-restart)."""
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._on_protocol_terminated()

    def _on_protocol_terminated(self):
        self._clear_all_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()

    # --- step-cursor navigation ----------------------------------------

    def _navigate_to_first_step(self):
        steps = list(self.manager.iter_execution_steps())
        if steps:
            self._select_step(steps[0])

    def _navigate_to_last_step(self):
        steps = list(self.manager.iter_execution_steps())
        if steps:
            self._select_step(steps[-1])

    def _navigate_to_previous_step(self):
        steps = list(self.manager.iter_execution_steps())
        if not steps:
            return
        cur = self._current_step_in(steps)
        if cur is None:
            self._select_step(steps[0])
            return
        if cur > 0:
            self._select_step(steps[cur - 1])

    def _navigate_to_next_step(self):
        steps = list(self.manager.iter_execution_steps())
        if not steps:
            return
        cur = self._current_step_in(steps)
        if cur is None:
            self._select_step(steps[0])
            return
        if cur < len(steps) - 1:
            self._select_step(steps[cur + 1])
            return
        # At end of execution order — clone the currently-selected step
        # and insert it after, at the same parent level. Mirrors the
        # legacy protocol_grid Next-button behaviour where pressing
        # Next at the end of the protocol creates a new step.
        self._duplicate_step_after(steps[cur])

    def _duplicate_step_after(self, row):
        """Insert a copy of ``row`` immediately after it under the same
        parent. Column values are read off the source row via each
        column's model.col_id and round-tripped through the same
        add_step API the toolbar uses."""
        path = tuple(row.path)
        parent_path = path[:-1]
        insert_idx = path[-1] + 1
        values = {}
        for col in self.manager.columns:
            cid = col.model.col_id
            if hasattr(row, cid):
                values[cid] = getattr(row, cid)
        new_path = self.manager.add_step(
            parent_path=parent_path, index=insert_idx, values=values,
        )
        new_row = self.manager.get_row(new_path)
        self._select_step(new_row)

    def _current_step_in(self, steps):
        """Index of the tree's current row inside ``steps``, or None if
        the current row isn't a step (e.g. a group is selected)."""
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        # Walk the QModelIndex chain back to a path tuple.
        path = self.widget._index_to_path(idx)
        for i, row in enumerate(steps):
            if tuple(row.path) == path:
                return i
        return None

    def _select_step(self, row):
        idx = self.widget._node_to_index(row)
        if not idx.isValid():
            return
        # Expand any collapsed ancestor groups so the row is visible.
        parent = idx.parent()
        while parent.isValid():
            self.widget.tree.expand(parent)
            parent = parent.parent()
        self.widget.tree.setCurrentIndex(idx)
        self.widget.tree.scrollTo(idx)

    def _clear_all_highlights(self):
        """Restore an idle visual state at protocol end."""
        self.widget.highlight_active_row(None)
        self.widget.tree.clearSelection()
        self.widget.tree.setCurrentIndex(QModelIndex())

        # Reset step / row / timer state.
        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None
        self._current_row = None
        # Reset to the StatusBar widget's initial label texts so the
        # idle visual state matches a freshly-constructed window.
        self._status_step_label.setText("Step 0/0")
        self._status_step_time_label.setText("Step Time: 0 s")
        self._status_reps_label.setText("Repetition 0/0")
        self.status_bar.lbl_recent_step.setText("Most Recent Step: -")
        self.status_bar.lbl_next_step.setText("Next Step: -")
        if self._status_phase_time_label is not None:
            self._status_phase_time_label.setText("Phase 0.00s / 0.00s")

        # Reset readout labels to initial text.
        for readout in self.config.status_readouts:
            slug = _slug(readout.label)
            label = self._readout_labels.get(slug)
            if label is not None:
                label.setText(f"{readout.label}: {readout.initial}")

    @classmethod
    def run(cls, config: DemoConfig) -> int:
        """One-shot main(): build the window, show it, run app.exec().
        Reuses an existing QApplication if one is already running.

        Calls ``style_app`` so the Material Symbols icon font (used by
        the NavigationBar buttons) is registered before the window
        is built — without it the icon glyphs render as boxes."""
        from microdrop_style.helpers import style_app

        app = QApplication.instance() or QApplication([])
        style_app(app)
        w = cls(config)
        w.show()
        return app.exec()
