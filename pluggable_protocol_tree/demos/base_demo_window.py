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


from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtWidgets import (
    QApplication, QLabel, QMainWindow, QSplitter, QStatusBar, QToolBar,
)


class BasePluggableProtocolDemoWindow(QMainWindow):
    """Hosts a ProtocolTreePane + the demo-only toolbar / readouts /
    Dramatiq routing scaffolding. See PPT-10.1 for the pane refactor."""

    phase_acked = Signal()                    # forwarded from pane.phase_acked
    readout_acked = Signal(str, str)

    def __init__(self, config: DemoConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle(config.title)
        self.resize(*config.window_size)

        from pluggable_protocol_tree.views.protocol_tree_pane import (
            ProtocolTreePane,
        )

        self.pane = ProtocolTreePane(
            config.columns_factory(),
            phase_ack_topic=config.phase_ack_topic,
            parent=self,
        )

        # Forward the pane's phase_acked into the window's signal so
        # tests / external code that connect to ``window.phase_acked``
        # keep working unchanged. The phase-ack actor (module level)
        # emits ``window.phase_acked``; route that into the pane so
        # _on_phase_ack runs and resets the per-phase timer.
        self.pane.phase_acked.connect(self.phase_acked.emit)
        if config.phase_ack_topic is not None:
            self.phase_acked.connect(self.pane._on_phase_ack)

        self._side_panel = None
        if config.side_panel_factory is not None:
            side = config.side_panel_factory(self.pane.manager)
            if side is not None:
                self._side_panel = side
                splitter = QSplitter(Qt.Horizontal)
                splitter.addWidget(self.pane)
                splitter.addWidget(side)
                splitter.setSizes([
                    int(config.window_size[0] * 0.65),
                    int(config.window_size[0] * 0.35),
                ])
                self._central_content = splitter
            else:
                self._central_content = self.pane
        else:
            self._central_content = self.pane

        self.setCentralWidget(self._central_content)

        # Pre-populate after manager is built; before executor starts.
        config.pre_populate(self.pane.manager)

        self._router = None
        self._readout_labels: dict[str, QLabel] = {}
        self._build_status_readouts()

        self._readout_fmts = {
            _slug(r.label): (r.label, r.fmt) for r in config.status_readouts
        }
        self._readout_signals: dict[str, _PerSlugEmitter] = {
            slug: _PerSlugEmitter(self.readout_acked, slug)
            for slug in self._readout_fmts
        }
        self.readout_acked.connect(self._on_readout_ack)

        existing = _readout_target.get("window")
        if existing is not None and existing is not self:
            logger.warning(
                "Multiple live BasePluggableProtocolDemoWindow instances detected. "
                "Only the most recent window will receive readout messages."
            )
        _readout_target["window"] = self

        for readout in config.status_readouts:
            _make_readout_actor(_slug(readout.label))

        self._setup_dramatiq_routing_internal()
        if self._router is not None:
            config.routing_setup(self._router)

        self._build_toolbar()
        config.post_build_setup(self)

    # --- demo-window-only chrome -----------------------------------

    def _build_status_readouts(self):
        """Bottom QStatusBar hosts only the demo readouts now — the
        legacy-style step / phase / repetition labels live on the
        pane's StatusBar."""
        sb = QStatusBar()
        self.setStatusBar(sb)
        for readout in self.config.status_readouts:
            slug = _slug(readout.label)
            label = QLabel(f"{readout.label}: {readout.initial}")
            sb.addPermanentWidget(label)
            self._readout_labels[slug] = label

    def _build_toolbar(self):
        tb = QToolBar("Protocol")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.pane.manager.add_step())
        tb.addAction("Add Group", lambda: self.pane.manager.add_group())
        tb.addSeparator()
        tb.addAction("Save…", self._save)
        tb.addAction("Load…", self._load)
        self._toolbar = tb

    def _save(self):
        self.pane.save_to_dialog(parent=self)

    def _load(self):
        self.pane.load_from_dialog(self.config.columns_factory, parent=self)

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

    # --- Dramatiq routing (unchanged behavior, just lives here) -----

    def _setup_dramatiq_routing_internal(self):
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import (
                MessageRouterActor,
            )

            broker = dramatiq.get_broker()
            broker.flush_all()
            router = MessageRouterActor()

            broker_topics_to_check = (
                ELECTRODES_STATE_CHANGE, ELECTRODES_STATE_APPLIED,
            )
            extra_topics = []
            if self.config.phase_ack_topic is not None:
                extra_topics.append(self.config.phase_ack_topic)
            for r in self.config.status_readouts:
                extra_topics.append(r.topic)
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
                            logger.info(
                                f"purged stale demo subscriber {actor_name} on {topic}"
                            )
                        except Exception:
                            logger.warning(
                                f"failed to purge {actor_name} on {topic} "
                                "(likely wrong listener_queue from another router)"
                            )

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
                logger.warning(f"Demo Dramatiq routing setup failed: {e}")
        except Exception as e:
            logger.warning(
                f"Demo Dramatiq routing setup failed (Redis not running?): {e}"
            )

    # --- backwards-compat aliases -----------------------------------

    @property
    def manager(self):
        return self.pane.manager

    @property
    def widget(self):
        return self.pane.widget

    @property
    def executor(self):
        return self.pane.executor

    @property
    def navigation_bar(self):
        return self.pane.navigation_bar

    @property
    def status_bar(self):
        return self.pane.status_bar

    @property
    def btn_new_exp(self):
        return self.pane.btn_new_exp

    @property
    def btn_new_note(self):
        return self.pane.btn_new_note

    @property
    def experiment_label(self):
        return self.pane.experiment_label

    @property
    def _status_step_label(self):
        return self.pane._status_step_label

    @property
    def _status_step_time_label(self):
        return self.pane._status_step_time_label

    @property
    def _status_reps_label(self):
        return self.pane._status_reps_label

    @property
    def _status_phase_time_label(self):
        return self.pane._status_phase_time_label

    @property
    def _tick_timer(self):
        return self.pane._tick_timer

    @property
    def _step_index(self):
        return self.pane._step_index

    @_step_index.setter
    def _step_index(self, value):
        self.pane._step_index = value

    @property
    def _step_total(self):
        return self.pane._step_total

    @_step_total.setter
    def _step_total(self, value):
        self.pane._step_total = value

    @property
    def _step_started_at(self):
        return self.pane._step_started_at

    @_step_started_at.setter
    def _step_started_at(self, value):
        self.pane._step_started_at = value

    @property
    def _phase_started_at(self):
        return self.pane._phase_started_at

    @_phase_started_at.setter
    def _phase_started_at(self, value):
        self.pane._phase_started_at = value

    @property
    def _current_row(self):
        return self.pane._current_row

    @_current_row.setter
    def _current_row(self, value):
        self.pane._current_row = value

    def _on_protocol_terminated(self):
        """Test hook — calls the pane's terminator + resets demo readouts."""
        self.pane._on_protocol_terminated()
        for readout in self.config.status_readouts:
            slug = _slug(readout.label)
            label = self._readout_labels.get(slug)
            if label is not None:
                label.setText(f"{readout.label}: {readout.initial}")

    @classmethod
    def run(cls, config: DemoConfig) -> int:
        """One-shot main(): build the window, show it, run app.exec()."""
        from microdrop_style.helpers import style_app

        app = QApplication.instance() or QApplication([])
        style_app(app)
        w = cls(config)
        w.show()
        return app.exec()
