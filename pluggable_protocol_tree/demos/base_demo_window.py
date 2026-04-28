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

import logging
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


logger = logging.getLogger(__name__)


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


import threading

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QApplication, QMainWindow, QSplitter,
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

    def __init__(self, config: DemoConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle(config.title)
        self.resize(*config.window_size)

        self.manager = RowManager(columns=config.columns_factory())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
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
        self._setup_dramatiq_routing_internal()
        if self._router is not None:
            # Demo-specific responders / listeners — called AFTER the
            # standard chain so the demo can rely on it being in place.
            config.routing_setup(self._router)

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

    def closeEvent(self, event):
        if self._dramatiq_worker is not None:
            try:
                self._dramatiq_worker.stop()
            except Exception:
                logger.exception("Error stopping demo dramatiq worker")
        super().closeEvent(event)
