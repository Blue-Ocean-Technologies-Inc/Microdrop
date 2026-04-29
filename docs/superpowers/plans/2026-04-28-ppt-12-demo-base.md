# PPT-12 Demo Base Window + Integration Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a composition-based `BasePluggableProtocolDemoWindow` for shared demo UX (active-row highlight, status bar with timers, button state machine, Save/Load, etc.), refactor the 4 existing demos to use it, and add a new full-stack integration demo that exercises every column type at once.

**Architecture:** New `BasePluggableProtocolDemoWindow(QMainWindow)` takes a `DemoConfig` dataclass — no subclassing required. `DemoConfig` declares columns, sample steps, demo-specific routing, ack-driven status readouts, and an optional side panel factory. The base owns the tree widget, executor, status bar, button state machine, Dramatiq routing scaffolding, and lifecycle. Each refactored demo collapses to ~50-100 LOC of just-its-stuff.

**Tech Stack:** Python 3.x, PySide6/Qt (QMainWindow + Qt signals), Dramatiq + Redis pub/sub, pytest, dataclasses.

**Spec:** `src/docs/superpowers/specs/2026-04-28-ppt-12-demo-base-design.md`

**Branch:** `feat/ppt-12-demo-base` (already created from main with PPT-5 merged in).

**Test runner:** `pixi run pytest …` from outer repo root `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py`.

---

## Task 1: `DemoConfig` + `StatusReadout` dataclasses + slug helper

**Files:**
- Create: `src/pluggable_protocol_tree/demos/base_demo_window.py` (initial — dataclasses + helper only; window class added in Task 2)
- Create: `src/pluggable_protocol_tree/tests/test_base_demo_window.py`

**Why:** Pure-Python data scaffolding. No Qt yet. Lays the contract demos will build against. The `slug()` helper turns a status-readout label into a Dramatiq actor name suffix.

- [ ] **Step 1: Write the failing tests**

```python
# src/pluggable_protocol_tree/tests/test_base_demo_window.py
"""Tests for the demo base window + DemoConfig + StatusReadout."""

import pytest

from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.base_demo_window import (
    DemoConfig, StatusReadout, _slug,
)


def test_status_readout_required_fields():
    r = StatusReadout(label="Voltage", topic="dropbot/signals/voltage_applied",
                      fmt=lambda m: f"{int(m)} V")
    assert r.label == "Voltage"
    assert r.topic == "dropbot/signals/voltage_applied"
    assert r.fmt("100") == "100 V"
    assert r.initial == "--"   # default


def test_status_readout_initial_overridable():
    r = StatusReadout(label="Magnet", topic="x/applied",
                      fmt=lambda m: m, initial="idle")
    assert r.initial == "idle"


def test_demo_config_minimum_required_fields():
    cfg = DemoConfig(columns_factory=lambda: [])
    assert cfg.title == "Pluggable Protocol Tree Demo"
    assert cfg.window_size == (1100, 650)
    assert cfg.phase_ack_topic == ELECTRODES_STATE_APPLIED   # default
    assert cfg.status_readouts == []
    assert cfg.side_panel_factory is None


def test_demo_config_pre_populate_default_is_no_op():
    cfg = DemoConfig(columns_factory=lambda: [])
    # Default pre_populate is a no-op lambda accepting one arg.
    cfg.pre_populate(None)   # must not raise


def test_demo_config_routing_setup_default_is_no_op():
    cfg = DemoConfig(columns_factory=lambda: [])
    cfg.routing_setup(None)


def test_demo_config_phase_ack_can_be_none():
    cfg = DemoConfig(columns_factory=lambda: [], phase_ack_topic=None)
    assert cfg.phase_ack_topic is None


def test_slug_lowercases_and_strips_punctuation():
    """slug('Voltage')='voltage'; slug('Magnet Height (mm)')='magnet_height_mm'."""
    assert _slug("Voltage") == "voltage"
    assert _slug("Magnet Height (mm)") == "magnet_height_mm"
    assert _slug("Step Time") == "step_time"


def test_slug_handles_empty_string():
    assert _slug("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.demos.base_demo_window'`.

- [ ] **Step 3: Implement the dataclasses + slug helper**

Create `src/pluggable_protocol_tree/demos/base_demo_window.py`:

```python
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

from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Add DemoConfig + StatusReadout dataclasses + slug helper"
```

---

## Task 2: `BasePluggableProtocolDemoWindow` minimum constructor

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (add window class)
- Create: `src/pluggable_protocol_tree/tests/conftest.py` (qapp fixture)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add window construction tests)

**Why:** Stand up the bare minimum window — `RowManager` + `ProtocolTreeWidget` + `ProtocolExecutor` constructed from the config's `columns_factory`. Title and window size applied. No status bar yet, no toolbar yet. Subsequent tasks add features incrementally.

- [ ] **Step 1: Write the qapp fixture (shared for all Qt-needing tests)**

Create `src/pluggable_protocol_tree/tests/conftest.py`:

```python
"""Shared fixtures for pluggable_protocol_tree tests."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication so Qt widget tests can construct
    QMainWindow + child widgets without crashing."""
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit — pytest-qt doesn't either; lets subsequent test
    # modules reuse the same QApplication.
```

- [ ] **Step 2: Write the failing tests**

Append to `src/pluggable_protocol_tree/tests/test_base_demo_window.py`:

```python
def test_window_constructs_with_minimum_config(qapp):
    """Window builds successfully with just a columns_factory."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [
            make_type_column(), make_id_column(), make_name_column(),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w.windowTitle() == "Pluggable Protocol Tree Demo"
    # Has the manager + executor + tree widget wired
    assert w.manager is not None
    assert w.executor is not None
    assert w.widget is not None
    # Window size matches default
    assert (w.width(), w.height()) == (1100, 650)


def test_window_applies_custom_title_and_size(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        title="My Demo",
        window_size=(800, 500),
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w.windowTitle() == "My Demo"
    assert (w.width(), w.height()) == (800, 500)


def test_window_columns_match_factory_output(qapp):
    """RowManager has the columns returned by columns_factory."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [
        make_type_column(), make_id_column(), make_name_column(),
    ])
    w = BasePluggableProtocolDemoWindow(cfg)
    ids = [c.model.col_id for c in w.manager.columns]
    assert ids == ["type", "id", "name"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 8 dataclass tests pass; 3 new window tests FAIL with `ImportError: cannot import name 'BasePluggableProtocolDemoWindow'`.

- [ ] **Step 4: Implement the window class (minimum)**

Append to `src/pluggable_protocol_tree/demos/base_demo_window.py`:

```python
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

        self.executor = ProtocolExecutor(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/conftest.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Add BasePluggableProtocolDemoWindow minimum constructor"
```

---

## Task 3: `pre_populate` hook + standard PPT-3 electrode chain auto-wired

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (call pre_populate after manager construction; setup_dramatiq_routing skeleton with electrode chain + routing_setup callback)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 3 tests)

**Why:** Two things demos always need: a place to add sample steps (pre_populate), and the standard PPT-3 electrode-actuation chain wired automatically (so demos don't all reimplement the same `add_subscriber_to_topic` calls). Demos that need extra responders use `routing_setup`.

- [ ] **Step 1: Append the failing tests**

Append to `src/pluggable_protocol_tree/tests/test_base_demo_window.py`:

```python
def test_pre_populate_runs_after_manager_construction(qapp):
    """The pre_populate callback receives the live RowManager and
    rows added there are present after window construction."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )

    def populate(rm):
        rm.add_step(values={"name": "S1", "duration_s": 0.1})
        rm.add_step(values={"name": "S2", "duration_s": 0.2})

    cfg = DemoConfig(
        columns_factory=lambda: [
            make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(),
        ],
        pre_populate=populate,
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    assert len(w.manager.root.children) == 2
    assert w.manager.root.children[0].name == "S1"
    assert w.manager.root.children[1].name == "S2"


def test_routing_setup_called_after_standard_chain(qapp, monkeypatch):
    """The routing_setup callback receives the router AFTER the base
    wires the PPT-3 electrode chain. Verify by recording the order."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )

    call_log = []

    def fake_router_setup_inner(self):
        # Replace the real broker setup with a recording fake.
        call_log.append("base_routing_setup")
        # Need to set self._router so routing_setup can be called with it.
        self._router = "fake-router"

    monkeypatch.setattr(
        BasePluggableProtocolDemoWindow,
        "_setup_dramatiq_routing_internal",
        fake_router_setup_inner,
    )

    def my_routing(router):
        call_log.append(("routing_setup", router))

    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        routing_setup=my_routing,
    )
    BasePluggableProtocolDemoWindow(cfg)
    assert call_log == ["base_routing_setup", ("routing_setup", "fake-router")]


def test_window_has_router_attribute_after_construction(qapp):
    """self._router exists (may be None if Redis unavailable, that's fine)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert hasattr(w, "_router")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 11 prior tests pass; 3 new tests FAIL — `pre_populate` not called yet, no `_router` attribute.

- [ ] **Step 3: Implement pre_populate + routing setup skeleton**

Add imports near the top of `src/pluggable_protocol_tree/demos/base_demo_window.py`:

```python
import logging

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
```

Update `BasePluggableProtocolDemoWindow.__init__` to call `pre_populate` and the routing setup:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Add pre_populate hook + standard electrode chain + routing_setup callback"
```

---

## Task 4: Status bar (step counter + row name + step elapsed timer + tick) + active-row highlight

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (status bar, tick timer, executor signal wiring for highlight + step transitions)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 4 tests)

**Why:** Visual scaffolding always present — step counter / row name / step elapsed timer + the active-row highlight (executor's `step_started` signal connected to the tree widget's `highlight_active_row`). Tick timer at 10 Hz refreshes the elapsed-time label.

- [ ] **Step 1: Append the failing tests**

```python
def test_window_has_status_bar_with_step_label(qapp):
    """Status bar exists with the step counter label."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    sb = w.statusBar()
    assert sb is not None
    # Step label and row label should be there.
    assert w._status_step_label.text() == "Idle"
    assert w._status_row_label.text() == ""


def test_window_status_step_elapsed_label_exists(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._status_step_time_label is not None


def test_window_executor_step_started_connected_to_tree_highlight(qapp):
    """The executor's step_started signal must connect to the tree
    widget's highlight_active_row slot — verifies the active-row
    highlight wiring is in place."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    # Indirect check: emit step_started with a fake row, watch tree's
    # highlight_active_row receive it.
    received = []
    orig = w.widget.highlight_active_row
    w.widget.highlight_active_row = lambda r: received.append(r)
    try:
        w.executor.qsignals.step_started.emit("fake-row")
        assert received == ["fake-row"]
    finally:
        w.widget.highlight_active_row = orig


def test_window_tick_timer_runs_at_10_hz(qapp):
    """Tick timer interval should be 100 ms (10 Hz)."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._tick_timer.interval() == 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 14 prior pass; 4 new FAIL.

- [ ] **Step 3: Implement status bar + highlight + tick timer**

Add imports:

```python
import time

from pyface.qt.QtCore import QTimer
from pyface.qt.QtWidgets import QLabel, QStatusBar
```

Update `BasePluggableProtocolDemoWindow.__init__` — add the calls at the end (after the routing setup):

```python
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

        self._build_status_bar()
        self._wire_executor_signals()
```

Add the methods:

```python
    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_step_label = QLabel("Idle")
        self._status_row_label = QLabel("")
        self._status_step_time_label = QLabel("")
        sb.addWidget(self._status_step_label)
        sb.addWidget(self._status_row_label, stretch=1)
        sb.addPermanentWidget(self._status_step_time_label)

    def _wire_executor_signals(self):
        # Active-row highlight on each step start.
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row
        )
        # Status bar updates.
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)

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
        self._step_started_at = time.monotonic()
        path = ".".join(str(i + 1) for i in row.path) if row.path else ""
        path_str = f" (path {path})" if path else ""
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        self._status_row_label.setText(f"{row.name}{path_str}")
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _refresh_status(self):
        if self._step_started_at is None:
            return
        elapsed = time.monotonic() - self._step_started_at
        self._status_step_time_label.setText(f"Step {elapsed:5.2f}s")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Status bar + active-row highlight + 10Hz tick timer"
```

---

## Task 5: Phase ack listener + phase-elapsed timer (when phase_ack_topic set)

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (phase ack listener actor + phase timer label)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 3 tests)

**Why:** When `phase_ack_topic` is set, the base wires a Dramatiq listener that emits a Qt signal restarting the per-phase timer from the actual ack moment (matches PPT-3/4's semantic). When `phase_ack_topic=None`, no phase timer label.

- [ ] **Step 1: Append the failing tests**

```python
def test_phase_ack_topic_none_hides_phase_timer(qapp):
    """When phase_ack_topic=None, no phase elapsed label in status bar."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()],
                     phase_ack_topic=None)
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._status_phase_time_label is None


def test_phase_ack_topic_set_creates_phase_label(qapp):
    """When phase_ack_topic set, phase elapsed label is in status bar."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()],
                     phase_ack_topic="x/applied")
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._status_phase_time_label is not None


def test_phase_acked_signal_resets_phase_timer(qapp):
    """Emitting the phase_acked signal sets _phase_started_at = monotonic()."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()],
                     phase_ack_topic="x/applied")
    w = BasePluggableProtocolDemoWindow(cfg)
    # Set the current row so phase ack handler doesn't early-return.
    w._current_row = object()
    w._step_started_at = None
    before = w._phase_started_at
    w.phase_acked.emit()
    assert w._phase_started_at is not None
    assert w._phase_started_at != before
    # First ack also sets step_started_at if it was None.
    assert w._step_started_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 18 prior pass; 3 new FAIL.

- [ ] **Step 3: Implement phase ack listener + phase label**

Add a Qt signal + slot to the class. Add the import:

```python
from pyface.qt.QtCore import Signal
```

Add the signal as a class-level Signal:

```python
class BasePluggableProtocolDemoWindow(QMainWindow):
    """..."""

    # Cross-thread signal — Dramatiq actor emits via the module-level
    # listener (registered when phase_ack_topic is set); auto-connection
    # delivers _on_phase_ack on the GUI thread.
    phase_acked = Signal()
```

In `__init__`, initialize `_status_phase_time_label = None` BEFORE `_build_status_bar`:

```python
        self._status_phase_time_label = None
        ...
        self._build_status_bar()
```

Update `_build_status_bar` to conditionally add the phase label:

```python
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
```

Update `_wire_executor_signals` to also connect the phase_acked signal:

```python
    def _wire_executor_signals(self):
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row
        )
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        if self.config.phase_ack_topic is not None:
            self.phase_acked.connect(self._on_phase_ack)
```

Add the slot:

```python
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
```

Update `_refresh_status` to also paint phase elapsed:

```python
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
```

Update `_on_step_started` to capture `_phase_target` from row.duration_s:

```python
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
```

Now — register a module-level Dramatiq actor for the phase ack. Add at module level (near `_slug`):

```python
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
```

In `_setup_dramatiq_routing_internal`, after the standard chain block, add (only if `phase_ack_topic` set):

```python
            if self.config.phase_ack_topic is not None:
                _phase_ack_target["window"] = self
                router.message_router_data.add_subscriber_to_topic(
                    topic=self.config.phase_ack_topic,
                    subscribing_actor_name="ppt12_demo_phase_ack_listener",
                )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Phase ack listener + per-phase elapsed timer"
```

---

## Task 6: `StatusReadout` listeners — auto-named actors + Qt signals + labels

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (per-readout actor + signal + label)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 3 tests)

**Why:** Every demo with ack-driven readouts (V/F for PPT-4, magnet for PPT-5, all three for the integration demo) declares them as `StatusReadout` entries. Base creates one Dramatiq actor + one Qt signal + one QLabel per entry, named `ppt12_demo_<slug>_listener`.

- [ ] **Step 1: Append the failing tests**

```python
def test_status_readout_creates_label_with_initial_text(qapp):
    """Each StatusReadout adds a QLabel with `<label>: <initial>` text."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Voltage", "v/applied", lambda m: f"{int(m)} V"),
            StatusReadout("Frequency", "f/applied", lambda m: f"{int(m)} Hz"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    labels = list(w._readout_labels.values())
    assert len(labels) == 2
    assert labels[0].text() == "Voltage: --"
    assert labels[1].text() == "Frequency: --"


def test_status_readout_label_updates_on_signal(qapp):
    """Emitting the per-readout Qt signal updates the label text."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Voltage", "v/applied", lambda m: f"{int(m)} V"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    w._readout_signals["voltage"].emit("100")
    assert w._readout_labels["voltage"].text() == "Voltage: 100 V"


def test_status_readout_actor_names_are_slug_prefixed(qapp):
    """Each readout's auto-registered Dramatiq actor uses the slug-based
    naming convention. Verify by inspecting the broker's registered actors."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Magnet Height (mm)", "m/applied",
                          lambda m: f"{m} mm"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    # Actor name = ppt12_demo_<slug>_listener
    expected_name = "ppt12_demo_magnet_height_mm_listener"
    broker = dramatiq.get_broker()
    # Should not raise
    broker.get_actor(expected_name)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 21 prior pass; 3 new FAIL.

- [ ] **Step 3: Implement readout listeners**

In `BasePluggableProtocolDemoWindow.__init__`, add BEFORE `_build_status_bar`:

```python
        # Per-readout state — populated below in _build_status_bar.
        self._readout_labels: dict[str, QLabel] = {}
        self._readout_signals: dict[str, Signal] = {}
```

Update `_build_status_bar` to add readout labels at the end:

```python
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
```

Add a method to emit-on-ack via per-instance signals. Since Qt signals are class-level, we instead hold a dispatcher: a single `readout_acked = Signal(str, str)` (slug, message) signal that the listener actors emit, and a slot that updates the right label:

Add to the class declaration (alongside `phase_acked`):

```python
    # Cross-thread signal for status-readout updates: (slug, message)
    readout_acked = Signal(str, str)
```

In `__init__`, after `_build_status_bar`:

```python
        # Wire readout updates: one signal-emit handler per slug → label update.
        self._readout_fmts = {
            _slug(r.label): (r.label, r.fmt) for r in self.config.status_readouts
        }
        # Convenience: per-slug Signal accessors that just emit on the
        # shared readout_acked. Tests can do w._readout_signals[slug].emit(msg).
        # We wrap the shared signal so per-slug emission is ergonomic.
        self._readout_signals = {
            slug: _PerSlugEmitter(self.readout_acked, slug)
            for slug in self._readout_fmts
        }
        self.readout_acked.connect(self._on_readout_ack)
```

Add the `_PerSlugEmitter` helper at module level (just below `_slug`):

```python
class _PerSlugEmitter:
    """Tiny shim that exposes .emit(message) and forwards to the
    window's per-instance readout_acked signal with a fixed slug."""
    __slots__ = ("_signal", "_slug")
    def __init__(self, signal, slug):
        self._signal = signal
        self._slug = slug
    def emit(self, message):
        self._signal.emit(self._slug, message)
```

Add the slot:

```python
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
```

Now the per-readout Dramatiq actors. Add at module level (after `_phase_ack_listener`):

```python
# Module-level target for status-readout listeners. Each actor reads
# its own message and forwards (slug, message) to the bound window.
_readout_target = {"window": None}


def _make_readout_actor(slug: str):
    """Register a Dramatiq actor named ppt12_demo_<slug>_listener that
    emits the window's readout_acked signal on every message received."""
    actor_name = f"ppt12_demo_{slug}_listener"

    @dramatiq.actor(actor_name=actor_name, queue_name="default")
    def _listener(message: str, topic: str, timestamp: float = None):
        window = _readout_target.get("window")
        if window is None:
            return
        window.readout_acked.emit(slug, message)

    return actor_name
```

In `_setup_dramatiq_routing_internal`, after the phase-ack subscription, add:

```python
            # StatusReadout listeners — auto-named actor per readout.
            _readout_target["window"] = self
            for readout in self.config.status_readouts:
                slug = _slug(readout.label)
                actor_name = _make_readout_actor(slug)
                router.message_router_data.add_subscriber_to_topic(
                    topic=readout.topic,
                    subscribing_actor_name=actor_name,
                )
```

Note: `_make_readout_actor` is idempotent on the actor name — Dramatiq's `@dramatiq.actor` decorator raises on duplicate registration. To handle multiple windows being constructed in tests, wrap in try/except:

```python
def _make_readout_actor(slug: str):
    actor_name = f"ppt12_demo_{slug}_listener"
    broker = dramatiq.get_broker()
    try:
        broker.get_actor(actor_name)
        return actor_name   # already registered
    except Exception:
        pass

    @dramatiq.actor(actor_name=actor_name, queue_name="default")
    def _listener(message: str, topic: str, timestamp: float = None):
        window = _readout_target.get("window")
        if window is None:
            return
        window.readout_acked.emit(slug, message)

    return actor_name
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] StatusReadout listeners — auto-named actors + per-slug labels"
```

---

## Task 7: Toolbar with Run/Pause/Resume/Stop button state machine + Add Step/Group

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (toolbar + button state machine + protocol-state slots)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 4 tests)

**Why:** Standard executor controls. Run is initially the only enabled action; once protocol_started fires, Pause + Stop become enabled and Run is disabled. Pause toggles to Resume. Stop returns to idle.

- [ ] **Step 1: Append the failing tests**

```python
def test_toolbar_has_standard_actions(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    actions = [a.text() for a in w.findChildren(__import__("pyface.qt.QtWidgets", fromlist=["QToolBar"]).QToolBar)[0].actions()]
    assert "Add Step" in actions
    assert "Add Group" in actions
    assert "Run" in actions
    assert "Pause" in actions
    assert "Stop" in actions


def test_idle_button_state(qapp):
    """Initially: Run enabled; Pause + Stop disabled."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w._run_action.isEnabled()
    assert not w._pause_action.isEnabled()
    assert not w._stop_action.isEnabled()


def test_protocol_started_swaps_buttons(qapp):
    """When protocol_started fires: Run disabled; Pause + Stop enabled."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    w.executor.qsignals.protocol_started.emit()
    assert not w._run_action.isEnabled()
    assert w._pause_action.isEnabled()
    assert w._stop_action.isEnabled()


def test_protocol_terminated_returns_to_idle(qapp):
    """When protocol_finished fires: back to idle button state."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    w.executor.qsignals.protocol_started.emit()
    w.executor.qsignals.protocol_finished.emit()
    assert w._run_action.isEnabled()
    assert not w._pause_action.isEnabled()
    assert not w._stop_action.isEnabled()
    assert w._pause_action.text() == "Pause"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 24 prior pass; 4 new FAIL.

- [ ] **Step 3: Implement toolbar + button state machine**

Add import:

```python
from pyface.qt.QtWidgets import QToolBar
```

Add to `__init__`, after `_wire_executor_signals()`:

```python
        self._build_toolbar()
        self._wire_button_state_machine()
        self._set_idle_button_state()
```

Add methods:

```python
    def _build_toolbar(self):
        tb = QToolBar("Protocol")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())
        tb.addAction("Add Group", lambda: self.manager.add_group())
        tb.addSeparator()
        # Save/Load added in Task 8.
        self._run_action = tb.addAction("Run", self.executor.start)
        self._pause_action = tb.addAction("Pause", self._toggle_pause)
        self._stop_action = tb.addAction("Stop", self.executor.stop)

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 28 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Toolbar + Run/Pause/Resume/Stop button state machine"
```

---

## Task 8: Save/Load toolbar actions + JSON file dialog

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (Save/Load toolbar buttons)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 2 tests)

**Why:** JSON save/load round-trip via the file dialog. Common to all demos.

- [ ] **Step 1: Append the failing tests**

```python
def test_save_writes_manager_to_json(qapp, tmp_path, monkeypatch):
    """Save button writes manager.to_json() to the chosen file."""
    from pyface.qt.QtWidgets import QFileDialog
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )

    cfg = DemoConfig(
        columns_factory=lambda: [
            make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(),
        ],
        pre_populate=lambda rm: rm.add_step(values={"name": "S1", "duration_s": 0.1}),
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    save_path = tmp_path / "out.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: (str(save_path), ""))
    w._save()
    import json
    payload = json.loads(save_path.read_text())
    assert payload["columns"][0]["id"] == "type"
    assert any(r[3] == "S1" for r in payload["rows"])


def test_load_replaces_manager_state(qapp, tmp_path, monkeypatch):
    """Load button reads JSON and applies via manager.set_state_from_json."""
    from pyface.qt.QtWidgets import QFileDialog
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    import json

    cfg = DemoConfig(columns_factory=lambda: [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])

    # Build a window once, save its empty state, then load it back.
    w = BasePluggableProtocolDemoWindow(cfg)
    w.manager.add_step(values={"name": "Saved Step", "duration_s": 0.5})
    save_path = tmp_path / "in.json"
    save_path.write_text(json.dumps(w.manager.to_json()))

    # Fresh window with empty state.
    w2 = BasePluggableProtocolDemoWindow(cfg)
    assert len(w2.manager.root.children) == 0
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: (str(save_path), ""))
    w2._load()
    assert len(w2.manager.root.children) == 1
    assert w2.manager.root.children[0].name == "Saved Step"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 28 prior pass; 2 new FAIL.

- [ ] **Step 3: Implement Save/Load**

Add imports:

```python
import json
from pyface.qt.QtWidgets import QFileDialog, QMessageBox
```

Update `_build_toolbar` — insert Save/Load between the separator and Run:

```python
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
```

Add methods:

```python
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
            self.manager.set_state_from_json(
                data, columns=self.config.columns_factory(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 30 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Save/Load toolbar actions via JSON file dialog"
```

---

## Task 9: Side panel via splitter (when `side_panel_factory` provided)

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (use QSplitter when side_panel_factory yields a widget)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 2 tests)

**Why:** PPT-3 + integration demo need a side panel (`SimpleDeviceViewer`). PPT-4/5/11 don't. The base supports either via the optional `side_panel_factory` callback.

- [ ] **Step 1: Append the failing tests**

```python
def test_window_no_side_panel_uses_tree_as_central(qapp):
    """When side_panel_factory is None, the central widget IS the tree."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    w = BasePluggableProtocolDemoWindow(cfg)
    assert w.centralWidget() is w.widget


def test_window_side_panel_uses_splitter(qapp):
    """When side_panel_factory returns a widget, central is a splitter
    holding tree + side panel."""
    from pyface.qt.QtWidgets import QLabel, QSplitter
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        side_panel_factory=lambda rm: QLabel("side"),
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    central = w.centralWidget()
    assert isinstance(central, QSplitter)
    assert central.count() == 2   # tree + side panel
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 30 prior pass; 2 new FAIL.

- [ ] **Step 3: Implement side panel**

Replace the existing `setCentralWidget(self.widget)` line in `__init__` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 32 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Side panel via splitter when side_panel_factory provided"
```

---

## Task 10: Stale-subscriber purge + `_clear_all_highlights` + `.run()` classmethod

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py` (purge logic + clear highlights on terminate + .run() classmethod)
- Modify: `src/pluggable_protocol_tree/tests/test_base_demo_window.py` (add 3 tests)

**Why:** Three small lifecycle features: (1) purge stale demo subscribers from prior runs (matches PPT-4's pattern); (2) clear all highlights/labels on protocol end so the next run starts clean; (3) `.run(config)` classmethod for one-line `if __name__ == "__main__"` use.

- [ ] **Step 1: Append the failing tests**

```python
def test_clear_all_highlights_resets_status(qapp):
    """After protocol terminates, status labels reset and step counters cleared."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    cfg = DemoConfig(
        columns_factory=lambda: [make_type_column()],
        status_readouts=[
            StatusReadout("Voltage", "v/applied", lambda m: f"{int(m)} V"),
        ],
    )
    w = BasePluggableProtocolDemoWindow(cfg)
    # Simulate state mid-run.
    w._step_index = 2
    w._step_total = 3
    w._step_started_at = 100.0
    w._readout_labels["voltage"].setText("Voltage: 99 V")
    w._status_step_label.setText("Step 2 / 3")
    # Terminate.
    w._on_protocol_terminated()
    assert w._status_step_label.text() == "Idle"
    assert w._step_started_at is None
    assert w._readout_labels["voltage"].text() == "Voltage: --"


def test_purge_stale_subscribers_only_touches_demo_prefixes(qapp):
    """The purger should ONLY consider actor names with demo prefixes
    (ppt_demo_, ppt4_demo_, ppt5_demo_, ppt11_demo_, ppt12_demo_,
    ppt_vf_demo_). Real listeners are NEVER touched."""
    from pluggable_protocol_tree.demos.base_demo_window import (
        _is_purgable_demo_actor_name,
    )
    assert _is_purgable_demo_actor_name("ppt_demo_electrode_responder")
    assert _is_purgable_demo_actor_name("ppt4_demo_voltage_applied_listener")
    assert _is_purgable_demo_actor_name("ppt5_demo_magnet_responder")
    assert _is_purgable_demo_actor_name("ppt12_demo_voltage_listener")
    assert _is_purgable_demo_actor_name("ppt_vf_demo_spy")
    # Real listeners — must NOT be purgable.
    assert not _is_purgable_demo_actor_name("dropbot_controller_listener")
    assert not _is_purgable_demo_actor_name(
        "dropbot_status_and_controls_listener",
    )
    assert not _is_purgable_demo_actor_name(
        "pluggable_protocol_tree_executor_listener",
    )


def test_run_classmethod_returns_int(qapp, monkeypatch):
    """The .run(config) classmethod calls app.exec() and returns its int result."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.demos.base_demo_window import (
        BasePluggableProtocolDemoWindow,
    )
    from pyface.qt.QtWidgets import QApplication

    # Patch QApplication.exec to return 0 immediately.
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    cfg = DemoConfig(columns_factory=lambda: [make_type_column()])
    rc = BasePluggableProtocolDemoWindow.run(cfg)
    assert rc == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 32 prior pass; 3 new FAIL.

- [ ] **Step 3: Implement purge + clear highlights + .run()**

Add module-level constant + helper:

```python
_DEMO_PREFIXES = (
    "ppt_demo_", "ppt4_demo_", "ppt5_demo_", "ppt11_demo_",
    "ppt12_demo_", "ppt_vf_demo_",
)


def _is_purgable_demo_actor_name(name: str) -> bool:
    """True if an actor name matches a known demo-prefix convention.
    Used by the stale-subscriber purger to leave real listeners alone."""
    return name.startswith(_DEMO_PREFIXES)
```

In `_setup_dramatiq_routing_internal`, after `router = MessageRouterActor()`, add the purge:

```python
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
            for topic in (*broker_topics_to_check, *extra_topics):
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
                    except Exception:
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
```

Update `_on_protocol_terminated` to call clear-all:

```python
    def _on_protocol_terminated(self):
        self._clear_all_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
```

Add `_clear_all_highlights`:

```python
    def _clear_all_highlights(self):
        """Restore an idle visual state at protocol end."""
        from pyface.qt.QtCore import QModelIndex

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
        self._status_step_label.setText("Idle")
        self._status_row_label.setText("")
        self._status_step_time_label.setText("")
        if self._status_phase_time_label is not None:
            self._status_phase_time_label.setText("")

        # Reset readout labels to initial text.
        for readout in self.config.status_readouts:
            slug = _slug(readout.label)
            label = self._readout_labels.get(slug)
            if label is not None:
                label.setText(f"{readout.label}: {readout.initial}")
```

Add the `.run()` classmethod (at the end of the class):

```python
    @classmethod
    def run(cls, config: DemoConfig) -> int:
        """One-shot main(): build the window, show it, run app.exec().
        Reuses an existing QApplication if one is already running."""
        app = QApplication.instance() or QApplication([])
        w = cls(config)
        w.show()
        return app.exec()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_base_demo_window.py -v
```
Expected: 35 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/base_demo_window.py pluggable_protocol_tree/tests/test_base_demo_window.py
git -C src commit -m "[PPT-12] Stale-subscriber purge + clear-all-highlights + .run() classmethod"
```

---

## Task 11: Refactor `pluggable_protocol_tree/demos/run_widget.py` (PPT-3)

**Files:**
- Replace: `src/pluggable_protocol_tree/demos/run_widget.py` (currently 531 LOC → ~80 LOC)

**Why:** First demo refactor. Verifies the base class actually delivers what PPT-3 needed.

- [ ] **Step 1: Replace the file with the refactored shape**

Replace `src/pluggable_protocol_tree/demos/run_widget.py` with:

```python
"""PPT-3 demo — protocol tree + electrodes/routes + device viewer +
PPT-2 ack-roundtrip column.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget
"""

import logging

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
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.ack_roundtrip_column import (
    DEMO_APPLIED_TOPIC, DEMO_REQUEST_TOPIC, RESPONDER_ACTOR_NAME,
    make_ack_roundtrip_column,
)
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)
from pluggable_protocol_tree.demos.message_column import make_message_column
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
        make_message_column(), make_ack_roundtrip_column(),
    ]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }


def _routing_setup(router):
    """PPT-2 ack-roundtrip column responder (specific to run_widget)."""
    router.message_router_data.add_subscriber_to_topic(
        topic=DEMO_REQUEST_TOPIC,
        subscribing_actor_name=RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=DEMO_APPLIED_TOPIC,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )


config = DemoConfig(
    columns_factory=_columns,
    title="Pluggable Protocol Tree — PPT-3 Demo",
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
```

- [ ] **Step 2: Verify import + smoke run**

```bash
pixi run python -c "import pluggable_protocol_tree.demos.run_widget; print('OK')"
```
Expected: `OK`.

```bash
pixi run pytest src/pluggable_protocol_tree/tests/ -v --ignore=src/pluggable_protocol_tree/tests/tests_with_redis_server_need
```
Expected: All non-Redis tests still pass.

- [ ] **Step 3: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/run_widget.py
git -C src commit -m "[PPT-12] Refactor PPT-3 run_widget to use BasePluggableProtocolDemoWindow"
```

---

## Task 12: Refactor `pluggable_protocol_tree/demos/run_widget_compound_demo.py` (PPT-11)

**Files:**
- Replace: `src/pluggable_protocol_tree/demos/run_widget_compound_demo.py` (currently 131 LOC → ~50 LOC)

- [ ] **Step 1: Replace the file**

Replace `src/pluggable_protocol_tree/demos/run_widget_compound_demo.py` with:

```python
"""PPT-11 demo — synthetic enabled+count compound column.

Now uses the BasePluggableProtocolDemoWindow + gains Run/Pause/Stop +
status bar / step elapsed timer for free.

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget_compound_demo
"""

import logging

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)
from pluggable_protocol_tree.demos.enabled_count_compound import (
    make_enabled_count_compound,
)
from pluggable_protocol_tree.models._compound_adapters import _expand_compound


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_enabled_count_compound()),
    ]


def _pre_populate(rm):
    rm.add_step(values={
        "name": "Step 1: enabled, count=5",
        "duration_s": 0.2,
        "ec_enabled": True, "ec_count": 5,
    })
    rm.add_step(values={
        "name": "Step 2: disabled (count read-only)",
        "duration_s": 0.2,
        "ec_enabled": False, "ec_count": 0,
    })
    rm.add_step(values={
        "name": "Step 3: enabled, count=99",
        "duration_s": 0.2,
        "ec_enabled": True, "ec_count": 99,
    })


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-11 Demo — Compound Column Framework",
    pre_populate=_pre_populate,
    phase_ack_topic=None,    # synthetic compound has no ack-emitting handlers
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
```

- [ ] **Step 2: Verify import + tests**

```bash
pixi run python -c "import pluggable_protocol_tree.demos.run_widget_compound_demo; print('OK')"
pixi run pytest src/pluggable_protocol_tree/tests/ -v --ignore=src/pluggable_protocol_tree/tests/tests_with_redis_server_need
```
Expected: `OK` + all non-Redis tests still pass.

- [ ] **Step 3: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/run_widget_compound_demo.py
git -C src commit -m "[PPT-12] Refactor PPT-11 compound demo to use BasePluggableProtocolDemoWindow"
```

---

## Task 13: Refactor `dropbot_protocol_controls/demos/run_widget_with_vf.py` (PPT-4)

**Files:**
- Replace: `src/dropbot_protocol_controls/demos/run_widget_with_vf.py` (currently 658 LOC → ~80 LOC)

- [ ] **Step 1: Replace the file**

Replace `src/dropbot_protocol_controls/demos/run_widget_with_vf.py` with:

```python
"""PPT-4 demo — protocol tree with voltage + frequency columns.

Run: pixi run python -m dropbot_protocol_controls.demos.run_widget_with_vf
"""

import logging

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
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig, StatusReadout,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)

from dropbot_controller.consts import VOLTAGE_APPLIED, FREQUENCY_APPLIED
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
        make_voltage_column(), make_frequency_column(),
    ]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }
    rm.add_step(values={
        "name": "Step 1: 100V/10kHz on e00,e01",
        "duration_s": 0.3,
        "electrodes": ["e00", "e01"],
        "voltage": 100, "frequency": 10000,
    })
    rm.add_step(values={
        "name": "Step 2: 120V/5kHz on e02,e03",
        "duration_s": 0.3,
        "electrodes": ["e02", "e03"],
        "voltage": 120, "frequency": 5000,
    })
    rm.add_step(values={
        "name": "Step 3: 75V/1kHz cooldown",
        "duration_s": 0.3,
        "voltage": 75, "frequency": 1000,
    })


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-4 Demo — Voltage + Frequency",
    pre_populate=_pre_populate,
    routing_setup=lambda router: subscribe_demo_responder(router),
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    status_readouts=[
        StatusReadout("Voltage",   VOLTAGE_APPLIED,   lambda m: f"{int(m)} V"),
        StatusReadout("Frequency", FREQUENCY_APPLIED, lambda m: f"{int(m)} Hz"),
    ],
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
```

- [ ] **Step 2: Verify import + tests**

```bash
pixi run python -c "import dropbot_protocol_controls.demos.run_widget_with_vf; print('OK')"
pixi run pytest src/dropbot_protocol_controls/tests/ -v --ignore=src/dropbot_protocol_controls/tests/tests_with_redis_server_need
```
Expected: `OK` + 30 PPT-4 tests pass.

- [ ] **Step 3: Commit**

```bash
git -C src add dropbot_protocol_controls/demos/run_widget_with_vf.py
git -C src commit -m "[PPT-12] Refactor PPT-4 V/F demo to use BasePluggableProtocolDemoWindow"
```

---

## Task 14: Refactor `peripheral_protocol_controls/demos/run_widget_magnet_demo.py` (PPT-5)

**Files:**
- Replace: `src/peripheral_protocol_controls/demos/run_widget_magnet_demo.py` (currently 213 LOC → ~50 LOC). **This task is what enables you to manually test the PPT-5 magnet demo with all the UX features the user wanted.**

- [ ] **Step 1: Replace the file**

Replace `src/peripheral_protocol_controls/demos/run_widget_magnet_demo.py` with:

```python
"""PPT-5 demo — protocol tree with the magnet compound column.

Run: pixi run python -m peripheral_protocol_controls.demos.run_widget_magnet_demo
"""

import logging

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig, StatusReadout,
)
from pluggable_protocol_tree.models._compound_adapters import _expand_compound

from peripheral_controller.consts import MAGNET_APPLIED
from peripheral_protocol_controls.demos.magnet_responder import (
    subscribe_demo_responder,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    make_magnet_column,
)


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_magnet_column()),
    ]


def _pre_populate(rm):
    rm.add_step(values={
        "name": "Step 1: engage at Default (sentinel; uses live pref)",
        "duration_s": 0.2,
        "magnet_on": True, "magnet_height_mm": 0.0,
    })
    rm.add_step(values={
        "name": "Step 2: engage at 12.0 mm explicit",
        "duration_s": 0.2,
        "magnet_on": True, "magnet_height_mm": 12.0,
    })
    rm.add_step(values={
        "name": "Step 3: retract",
        "duration_s": 0.2,
        "magnet_on": False, "magnet_height_mm": 0.0,
    })


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-5 Demo — Magnet",
    pre_populate=_pre_populate,
    routing_setup=lambda router: subscribe_demo_responder(router),
    phase_ack_topic=MAGNET_APPLIED,
    status_readouts=[
        StatusReadout("Magnet", MAGNET_APPLIED,
                      lambda m: "engaged" if m == "1" else "retracted"),
    ],
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
```

- [ ] **Step 2: Verify import + tests**

```bash
pixi run python -c "import peripheral_protocol_controls.demos.run_widget_magnet_demo; print('OK')"
pixi run pytest src/peripheral_protocol_controls/tests/ -v --ignore=src/peripheral_protocol_controls/tests/tests_with_redis_server_need
```
Expected: `OK` + 17 PPT-5 unit tests pass.

- [ ] **Step 3: Commit**

```bash
git -C src add peripheral_protocol_controls/demos/run_widget_magnet_demo.py
git -C src commit -m "[PPT-12] Refactor PPT-5 magnet demo to use BasePluggableProtocolDemoWindow"
```

---

## Task 15: Create `examples/demos/run_full_integration_demo.py`

**Files:**
- Create: `src/examples/demos/run_full_integration_demo.py`

**Why:** The integration demo. Exercises every column type at once. Verifies priority bucketing in practice (V/F/magnet at priority 20 complete before electrode actuation at priority 30).

- [ ] **Step 1: Create the file**

Create `src/examples/demos/run_full_integration_demo.py`:

```python
"""Full-stack integration demo: PPT-3 electrodes/routes + PPT-4 voltage/
frequency + PPT-5 magnet, all in one window. Verifies priority bucketing
in practice (priority 20 V/F/magnet bucket completes before priority 30
RoutesHandler publishes electrodes).

Run: pixi run python -m examples.demos.run_full_integration_demo
"""

import logging

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
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig, StatusReadout,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
from pluggable_protocol_tree.models._compound_adapters import _expand_compound

from dropbot_controller.consts import VOLTAGE_APPLIED, FREQUENCY_APPLIED
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder as subscribe_vf_responder,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)

from peripheral_controller.consts import MAGNET_APPLIED
from peripheral_protocol_controls.demos.magnet_responder import (
    subscribe_demo_responder as subscribe_magnet_responder,
)
from peripheral_protocol_controls.protocol_columns.magnet_column import (
    make_magnet_column,
)


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
        # PPT-4
        make_voltage_column(), make_frequency_column(),
        # PPT-5 (compound, expanded)
        *_expand_compound(make_magnet_column()),
    ]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }
    rm.add_step(values={
        "name": "Step 1: 100V/10kHz, magnet=Default, route top row",
        "duration_s": 0.3,
        "voltage": 100, "frequency": 10000,
        "magnet_on": True, "magnet_height_mm": 0.0,   # sentinel = Default
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Step 2: 120V/5kHz, magnet=12mm, diagonal",
        "duration_s": 0.3,
        "voltage": 120, "frequency": 5000,
        "magnet_on": True, "magnet_height_mm": 12.0,
        "routes": [["e00", "e06", "e12", "e18", "e24"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Step 3: 75V/1kHz cooldown, retract magnet",
        "duration_s": 0.3,
        "voltage": 75, "frequency": 1000,
        "magnet_on": False, "magnet_height_mm": 0.0,
    })


def _routing_setup(router):
    """All three demo responders. The PPT-3 electrode chain is wired
    by the base automatically."""
    subscribe_vf_responder(router)
    subscribe_magnet_responder(router)


config = DemoConfig(
    columns_factory=_columns,
    title="Full Integration Demo — PPT-3 routes + PPT-4 V/F + PPT-5 magnet",
    window_size=(1300, 700),
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    status_readouts=[
        StatusReadout("Voltage",   VOLTAGE_APPLIED,   lambda m: f"{int(m)} V"),
        StatusReadout("Frequency", FREQUENCY_APPLIED, lambda m: f"{int(m)} Hz"),
        StatusReadout("Magnet",    MAGNET_APPLIED,
                      lambda m: "engaged" if m == "1" else "retracted"),
    ],
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
```

- [ ] **Step 2: Verify import**

```bash
pixi run python -c "import examples.demos.run_full_integration_demo; print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git -C src add examples/demos/run_full_integration_demo.py
git -C src commit -m "[PPT-12] Add examples/demos/run_full_integration_demo.py"
```

---

## Task 16: Final verification

**Files:** none (verification only)

- [ ] **Step 1: All PPT-12 + regression suites**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/ -v
pixi run pytest src/dropbot_protocol_controls/tests/ -v --ignore=src/dropbot_protocol_controls/tests/tests_with_redis_server_need
pixi run pytest src/peripheral_protocol_controls/tests/ -v --ignore=src/peripheral_protocol_controls/tests/tests_with_redis_server_need
pixi run pytest src/dropbot_controller/tests/ -v
pixi run pytest src/peripheral_controller/tests/ -v
```
Expected: all suites pass (with the one pre-existing peripheral_controller failure noted in PPT-5).

- [ ] **Step 2: Demo scripts import cleanly**

```bash
pixi run python -c "import pluggable_protocol_tree.demos.run_widget; print('PPT-3 OK')"
pixi run python -c "import pluggable_protocol_tree.demos.run_widget_compound_demo; print('PPT-11 OK')"
pixi run python -c "import dropbot_protocol_controls.demos.run_widget_with_vf; print('PPT-4 OK')"
pixi run python -c "import peripheral_protocol_controls.demos.run_widget_magnet_demo; print('PPT-5 OK')"
pixi run python -c "import examples.demos.run_full_integration_demo; print('Integration OK')"
```
Expected: 5 `OK` lines.

- [ ] **Step 3: git status clean**

```bash
git -C src status
```
Expected: clean working tree (besides any pre-existing untracked files unrelated to PPT-12).

- [ ] **Step 4: Show the PPT-12 commit history**

```bash
git -C src log --oneline main..HEAD
```
Expected: ~16 commits all prefixed `[PPT-12]`.

---

## Implementation Notes

**Branch hygiene:** branch is `feat/ppt-12-demo-base`, branched from main (PPT-3, PPT-4, PPT-5, PPT-11 already merged). When PR opens, target main.

**Layering:** all framework changes live inside `pluggable_protocol_tree/demos/`. Each demo refactor touches exactly one file. The integration demo is the only file outside the existing tree (`examples/demos/run_full_integration_demo.py`).

**The composition shape** is the load-bearing decision: demos become small declarative scripts; the base is a polished, well-tested Qt class. If a future PR finds the composition limits expressiveness, the alternative is inheritance — but four real consumers built fine on composition, so don't switch without strong evidence.

**Phase-ack listener pattern** is per-demo Dramatiq actor + Qt signal. This is the same pattern used by PPT-3/4. Issue #386 tracks replacing it with an executor-emitted `step_phase_started` signal — depends on PPT-12 merging first.

**If a test fails unexpectedly during execution:** use `superpowers:systematic-debugging`. Most likely failure modes: (1) Qt widget tests need a `qapp` fixture — make sure `conftest.py` exports it; (2) Dramatiq actor name conflicts when running multiple `BasePluggableProtocolDemoWindow` instances in tests — `_make_readout_actor` should idempotently return existing actors.
