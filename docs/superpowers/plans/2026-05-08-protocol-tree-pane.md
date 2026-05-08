# Protocol Tree Pane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract a reusable `ProtocolTreePane(QWidget)` from `BasePluggableProtocolDemoWindow`, wire the experiment-bar against the live `ExperimentManager` + `StickyWindowManager` services in the Envisage dock pane, and register `PluggableProtocolTreePlugin` in the full-app run script so the new dock pane is usable beyond demos.

**Architecture:** New `pluggable_protocol_tree/views/protocol_tree_pane.py` owns manager + tree + executor + nav/status/experiment bars + button state machine. Optional service params (`application`, `experiment_manager`, `sticky_manager`) activate production wiring; passing nothing keeps the demo's log-only stub behavior. `BasePluggableProtocolDemoWindow` delegates via `@property` aliases so the existing test suite passes unchanged. `PluggableProtocolDockPane` constructs the real services and passes them in. The two protocol panes (legacy `protocol_grid` and new pluggable) coexist for this PR; PPT-9 removes the legacy.

**Tech Stack:** Python 3.13, PySide6/Qt (`QWidget`, `QVBoxLayout`), Traits/Pyface (`@observe`, `TraitsDockPane`), Envisage plugin framework, pytest with `qapp` session fixture.

**Spec:** `src/docs/superpowers/specs/2026-05-08-protocol-tree-pane-design.md`

**Branch:** `ppt-10.1-protocol-tree-pane` (already created from `main`; spec already committed).

**Test runner:** Run tests from outer pixi repo root via `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest <args>"`. The `cd src` puts pytest at the same root the application uses for imports.

---

## Task 1: Port `ExperimentLabel` to pluggable views

**Files:**
- Create: `src/pluggable_protocol_tree/views/experiment_label.py`
- Create: `src/pluggable_protocol_tree/tests/test_experiment_label.py`

**Why:** `ProtocolTreePane` needs a clickable, theme-aware experiment label with the legacy UX (link colour on the experiment id, tooltip-toggle context menu). The legacy widget has it at `protocol_grid/extra_ui_elements.py:39-127`. Porting it now keeps the pane self-contained and decouples PPT-10.1 from PPT-9's eventual deletion of `protocol_grid`.

- [ ] **Step 1: Write the failing tests**

```python
# src/pluggable_protocol_tree/tests/test_experiment_label.py
"""Tests for the ported ExperimentLabel widget."""

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QMouseEvent
from pyface.qt.QtCore import QPointF


def test_label_default_text_when_no_experiment(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    assert "Experiment" in lbl.text()


def test_update_experiment_id_renders_id(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    lbl.update_experiment_id("2026-05-08T12-00-00Z")
    assert "2026-05-08T12-00-00Z" in lbl.text()


def test_update_experiment_id_remembers_last_value(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    lbl.update_experiment_id("exp-1")
    # Calling with None re-renders the last set id (used by theme-change re-style).
    lbl.update_experiment_id(None)
    assert "exp-1" in lbl.text()


def test_left_click_emits_clicked(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    fired = []
    lbl.clicked.connect(lambda: fired.append(True))
    event = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(0, 0),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    lbl.mousePressEvent(event)
    assert fired == [True]


def test_right_click_does_not_emit_clicked(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    fired = []
    lbl.clicked.connect(lambda: fired.append(True))
    event = QMouseEvent(
        QMouseEvent.MouseButtonPress, QPointF(0, 0),
        Qt.RightButton, Qt.RightButton, Qt.NoModifier,
    )
    lbl.mousePressEvent(event)
    assert fired == []


def test_handle_tooltip_toggle_toggles_tooltip(qapp):
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    lbl = ExperimentLabel()
    assert lbl.toolTip() != ""
    lbl.handle_tooltip_toggle(False)
    assert lbl.toolTip() == ""
    lbl.handle_tooltip_toggle(True)
    assert lbl.toolTip() != ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_experiment_label.py -v"
```
Expected: `ModuleNotFoundError: No module named 'pluggable_protocol_tree.views.experiment_label'`.

- [ ] **Step 3: Implement `ExperimentLabel`**

```python
# src/pluggable_protocol_tree/views/experiment_label.py
"""Clickable, theme-aware experiment label.

Ported from ``protocol_grid/extra_ui_elements.py`` ``ExperimentLabel``
(legacy). Stays in pluggable_protocol_tree so PPT-9 can delete
protocol_grid without breaking the new dock pane.
"""

from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtGui import QAction, QContextMenuEvent
from pyface.qt.QtWidgets import QApplication, QLabel, QMenu

from microdrop_style.helpers import is_dark_mode


class ExperimentLabel(QLabel):
    """QLabel that emits ``clicked`` on left-click and renders the
    active experiment id with a theme-aware link colour. Right-click
    opens a context menu with an Enable Tooltip toggle."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("<b>Experiment: </b>")
        self.setToolTip("Active Experiment (Click to open folder)")
        self.setCursor(Qt.PointingHandCursor)

        self._experiment_id = None
        self._tooltip_visible = True

        self.apply_styling()
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_styling)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def handle_tooltip_toggle(self, checked):
        self._tooltip_visible = checked
        if checked:
            self.setToolTip("Active Experiment (Click to open folder)")
        else:
            self.setToolTip("")

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = QMenu(self)
        action = QAction("Enable Tooltip", checkable=True,
                         checked=self._tooltip_visible)
        action.triggered.connect(self.handle_tooltip_toggle)
        menu.addAction(action)
        menu.exec(event.globalPos())

    def update_experiment_id(self, experiment_id=None):
        if experiment_id is None:
            experiment_id = self._experiment_id

        link_color = "#82B1FF" if is_dark_mode() else "#0066CC"
        self.setText(
            f"<b>Experiment: </b> "
            f"<span style='text-decoration: underline; color: {link_color};'>"
            f"{experiment_id}</span>"
        )
        self._experiment_id = experiment_id

    def apply_styling(self):
        text_color = "#f0f0f0" if is_dark_mode() else "#333333"
        hover_bg = "#3a3a3a" if is_dark_mode() else "#e0e0e0"
        self.setStyleSheet(
            f"QLabel {{ color: {text_color}; border: none; }}"
            f"QLabel:hover {{ background-color: {hover_bg}; }}"
        )
        self.update_experiment_id()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_experiment_label.py -v"
```
Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/experiment_label.py src/pluggable_protocol_tree/tests/test_experiment_label.py
git -C microdrop-py/src commit -m "[PPT-10.1] Port ExperimentLabel into pluggable views"
```

---

## Task 2: `ProtocolTreePane` skeleton — manager + tree + bars + central layout

**Files:**
- Create: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Create: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

**Why:** Build the pane's structural skeleton first — constructor accepting either a column list or a pre-built `RowManager`, the layout (NavigationBar above StatusBar above the tree), and the experiment bar populated into the nav bar's left slot. No executor or button state machine yet — those land in Task 3.

- [ ] **Step 1: Write the failing skeleton tests**

```python
# src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
"""Tests for ProtocolTreePane — the reusable host widget for the
pluggable protocol tree's full UX (navigation, status, experiment
bar, executor, button state machine)."""


def test_pane_constructs_with_columns_list(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
    ])
    assert pane.manager is not None
    ids = [c.model.col_id for c in pane.manager.columns]
    assert ids == ["type", "id", "name"]


def test_pane_constructs_with_existing_manager(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    rm = RowManager(columns=[make_type_column()])
    pane = ProtocolTreePane(rm)
    assert pane.manager is rm


def test_pane_has_tree_widget(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

    pane = ProtocolTreePane([make_type_column()])
    assert isinstance(pane.widget, ProtocolTreeWidget)


def test_pane_has_navigation_bar_with_play_button(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.navigation_bar is not None
    assert pane.navigation_bar.btn_play is not None


def test_pane_has_status_bar(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.status_bar is not None
    assert pane.status_bar.lbl_step_progress.text() == "Step 0/0"


def test_pane_has_experiment_bar_widgets(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.btn_new_exp is not None
    assert pane.btn_new_note is not None
    assert isinstance(pane.experiment_label, ExperimentLabel)


def test_pane_phase_ack_topic_default_is_electrodes_state_applied(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane.phase_ack_topic == ELECTRODES_STATE_APPLIED


def test_pane_phase_ack_topic_can_be_none(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic=None)
    assert pane.phase_ack_topic is None
    assert pane.status_bar.lbl_phase_time.isVisible() is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v"
```
Expected: `ModuleNotFoundError: No module named 'pluggable_protocol_tree.views.protocol_tree_pane'`.

- [ ] **Step 3: Implement the skeleton**

```python
# src/pluggable_protocol_tree/views/protocol_tree_pane.py
"""Reusable host widget for the pluggable protocol tree's full UX.

Owns the RowManager + ProtocolTreeWidget + ProtocolExecutor + the
NavigationBar / StatusBar / experiment-bar trio. Mounted by both the
demo window (BasePluggableProtocolDemoWindow) and the full-app dock
pane (PluggableProtocolDockPane).

Service injection (``application``, ``experiment_manager``,
``sticky_manager``) is optional. When None, the corresponding
experiment-bar buttons stay log-only stubs (matches today's demo UX).
When supplied, the pane connects the real handlers — see Task 6 of
PPT-10.1 for the full wiring rules.
"""

from __future__ import annotations

from pyface.qt.QtCore import Qt, QTimer, Signal
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import (
    QLabel, QToolButton, QVBoxLayout, QWidget,
)

from microdrop_style.button_styles import ICON_FONT_FAMILY

from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
from pluggable_protocol_tree.views.navigation_bar import (
    NavigationBar, StatusBar, make_separator,
)
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ProtocolTreePane(QWidget):
    """Hosts the pluggable protocol tree with full UX scaffolding.

    Layered top-to-bottom:
      NavigationBar  (playback + step nav + experiment bar in left slot)
      StatusBar      (step/phase elapsed, repetition counter, recent/next labels)
      separator
      ProtocolTreeWidget
    """

    phase_acked = Signal()

    def __init__(
        self,
        columns_or_manager,
        *,
        application=None,
        experiment_manager=None,
        sticky_manager=None,
        phase_ack_topic=ELECTRODES_STATE_APPLIED,
        executor_factory=None,
        parent=None,
    ):
        super().__init__(parent)

        if isinstance(columns_or_manager, RowManager):
            self.manager = columns_or_manager
        else:
            self.manager = RowManager(columns=list(columns_or_manager))

        self.application = application
        self.experiment_manager = experiment_manager
        self.sticky_manager = sticky_manager
        self.phase_ack_topic = phase_ack_topic
        self._executor_factory = executor_factory

        self.widget = ProtocolTreeWidget(self.manager, parent=self)

        self._build_status_bar()
        self._build_navigation_bar()
        self._build_experiment_bar()
        self._build_layout()

    def _build_status_bar(self):
        self.status_bar = StatusBar()
        phase_enabled = self.phase_ack_topic is not None
        self.status_bar.lbl_phase_time.setVisible(phase_enabled)

    def _build_navigation_bar(self):
        self.navigation_bar = NavigationBar()

    def _build_experiment_bar(self):
        icon_font = QFont(ICON_FONT_FAMILY)
        icon_font.setPixelSize(20)

        self.btn_new_exp = QToolButton()
        self.btn_new_exp.setText("note_add")
        self.btn_new_exp.setFont(icon_font)
        self.btn_new_exp.setToolTip("New Experiment")
        self.btn_new_exp.setCursor(Qt.PointingHandCursor)
        self.btn_new_exp.clicked.connect(self._on_new_experiment)

        self.experiment_label = ExperimentLabel()

        self.btn_new_note = QToolButton()
        self.btn_new_note.setText("sticky_note")
        self.btn_new_note.setFont(icon_font)
        self.btn_new_note.setToolTip("New Note")
        self.btn_new_note.setCursor(Qt.PointingHandCursor)
        self.btn_new_note.clicked.connect(self._on_new_note)

        self.experiment_label.clicked.connect(self._on_experiment_label_clicked)

        self.navigation_bar.add_widget_to_left_slot(self.btn_new_exp)
        self.navigation_bar.add_widget_to_left_slot(self.experiment_label)
        self.navigation_bar.add_widget_to_left_slot(self.btn_new_note)

    def _build_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation_bar)
        layout.addWidget(self.status_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self.widget)

    # --- experiment-bar stubs (Task 6 wires real services) -------------

    def _on_new_experiment(self):
        logger.info("New Experiment requested")

    def _on_new_note(self):
        logger.info("New Note requested")

    def _on_experiment_label_clicked(self):
        logger.info("Experiment label clicked")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v"
```
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.1] ProtocolTreePane skeleton: manager+tree+nav/status/exp bars"
```

---

## Task 3: Add executor + signal wiring + button state machine + tick timer

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

**Why:** Add the runtime guts of the pane — `ProtocolExecutor` construction, `qsignals` wiring, the state machine that swaps button states on protocol_started / paused / resumed / finished / aborted / error, and the 10 Hz tick timer that drives the elapsed-time labels. This is a verbatim move from `BasePluggableProtocolDemoWindow` `__init__` lines 267-302 and the `_wire_executor_signals` / `_set_*_button_state` methods. After this task, the pane runs an executor end-to-end without any external scaffolding.

- [ ] **Step 1: Append the executor / button-state machine tests**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_has_executor_and_pause_event(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert isinstance(pane.executor, ProtocolExecutor)
    assert pane.executor.pause_event is not None
    assert pane.executor.stop_event is not None


def test_pane_executor_factory_can_be_overridden(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    sentinel = object()

    def fake_factory(row_manager, qsignals, pause_event, stop_event):
        return sentinel

    pane = ProtocolTreePane([make_type_column()], executor_factory=fake_factory)
    assert pane.executor is sentinel


def test_pane_idle_button_state(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    nb = pane.navigation_bar
    assert nb.btn_play.isEnabled()
    assert not nb.btn_stop.isEnabled()
    for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
        assert btn.isEnabled()


def test_pane_running_button_state_after_protocol_started(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    pane.executor.qsignals.protocol_started.emit()
    nb = pane.navigation_bar
    assert nb.btn_stop.isEnabled()
    for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
        assert not btn.isEnabled()


def test_pane_returns_to_idle_after_protocol_finished(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    pane.executor.qsignals.protocol_started.emit()
    pane.executor.qsignals.protocol_finished.emit()
    nb = pane.navigation_bar
    assert not nb.btn_stop.isEnabled()


def test_pane_step_started_updates_status_label(qapp):
    """Emitting step_started increments the step counter label."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeRow:
        path = []
        name = "Step A"
        duration_s = 0.0

    pane = ProtocolTreePane([make_type_column()])
    pane._step_total = 3
    pane.executor.qsignals.step_started.emit(FakeRow())
    assert pane._status_step_label.text() == "Step 1 / 3"


def test_pane_tick_timer_runs_at_10_hz(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    assert pane._tick_timer.interval() == 100


def test_pane_phase_acked_signal_resets_phase_timer(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()], phase_ack_topic="x/applied")
    pane._current_row = object()
    pane._step_started_at = None
    pane.phase_acked.emit()
    assert pane._phase_started_at is not None
    assert pane._step_started_at is not None


def test_pane_protocol_error_resets_to_idle_and_calls_dialog(qapp, monkeypatch):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp

    calls = []

    def fake_error_dialog(parent=None, title="", message="", **kwargs):
        calls.append((title, message))

    monkeypatch.setattr(ptp, "error_dialog", fake_error_dialog)

    pane = ptp.ProtocolTreePane([make_type_column()])
    pane.executor.qsignals.protocol_started.emit()
    assert pane.navigation_bar.btn_stop.isEnabled()
    pane.executor.qsignals.protocol_error.emit("kaboom")
    assert not pane.navigation_bar.btn_stop.isEnabled()
    assert not pane._tick_timer.isActive()
    assert calls == [("Protocol error", "kaboom")]
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_has_executor_and_pause_event -v"
```
Expected: `AttributeError: 'ProtocolTreePane' object has no attribute 'executor'`.

- [ ] **Step 3: Add executor construction + signal wiring + state machine**

Update the imports at the top of `src/pluggable_protocol_tree/views/protocol_tree_pane.py`:

```python
from __future__ import annotations

import threading
import time

from pyface.qt.QtCore import Qt, QTimer, Signal
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import (
    QLabel, QToolButton, QVBoxLayout, QWidget,
)

from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
from microdrop_style.button_styles import ICON_FONT_FAMILY

from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
from pluggable_protocol_tree.views.navigation_bar import (
    NavigationBar, StatusBar, make_separator,
)
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

from logger.logger_service import get_logger

logger = get_logger(__name__)
```

Replace the `__init__` body (everything after `self._build_layout()`) with the version that wires the executor and state machine. The full updated `__init__` plus the new methods:

```python
    def __init__(
        self,
        columns_or_manager,
        *,
        application=None,
        experiment_manager=None,
        sticky_manager=None,
        phase_ack_topic=ELECTRODES_STATE_APPLIED,
        executor_factory=None,
        parent=None,
    ):
        super().__init__(parent)

        if isinstance(columns_or_manager, RowManager):
            self.manager = columns_or_manager
        else:
            self.manager = RowManager(columns=list(columns_or_manager))

        self.application = application
        self.experiment_manager = experiment_manager
        self.sticky_manager = sticky_manager
        self.phase_ack_topic = phase_ack_topic

        self.widget = ProtocolTreeWidget(self.manager, parent=self)

        self._build_status_bar()
        self._build_navigation_bar()
        self._build_experiment_bar()
        self._build_layout()

        self.executor = self._build_executor(executor_factory)

        self._step_index = 0
        self._step_total = 0
        self._step_started_at: float | None = None
        self._phase_started_at: float | None = None
        self._phase_target: float | None = None
        self._current_row = None
        self._repeats_total = 1
        self._repeats_completed = 0
        self._current_run_preview_mode = False

        self._status_step_label = self.status_bar.lbl_step_progress
        self._status_step_time_label = self.status_bar.lbl_step_time
        self._status_reps_label = self.status_bar.lbl_step_repetition
        self._status_phase_time_label = (
            self.status_bar.lbl_phase_time if self.phase_ack_topic is not None
            else None
        )

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)
        self._tick_timer.timeout.connect(self._refresh_status)

        self._wire_executor_signals()
        self._wire_button_state_machine()
        self._wire_navigation_buttons()
        self._set_idle_button_state()

    def _build_executor(self, executor_factory):
        factory = executor_factory or self._default_executor_factory
        return factory(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

    @staticmethod
    def _default_executor_factory(row_manager, qsignals, pause_event, stop_event):
        return ProtocolExecutor(
            row_manager=row_manager,
            qsignals=qsignals,
            pause_event=pause_event,
            stop_event=stop_event,
        )

    def _wire_executor_signals(self):
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row,
        )
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.step_finished.connect(self._on_step_finished)
        self.executor.qsignals.step_repetition.connect(self._on_step_repetition)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        self.executor.qsignals.protocol_error.connect(self._on_error)
        if self.phase_ack_topic is not None:
            self.phase_acked.connect(self._on_phase_ack)

    def _wire_button_state_machine(self):
        self.executor.qsignals.protocol_started.connect(
            self._set_running_button_state,
        )
        self.executor.qsignals.protocol_paused.connect(self._on_protocol_paused)
        self.executor.qsignals.protocol_resumed.connect(self._on_protocol_resumed)
        self.executor.qsignals.protocol_finished.connect(self._on_protocol_finished)
        self.executor.qsignals.protocol_aborted.connect(self._on_protocol_aborted)

    def _wire_navigation_buttons(self):
        nb = self.navigation_bar
        nb.btn_play.clicked.connect(self._on_play_clicked)
        nb.btn_resume.clicked.connect(self._toggle_pause)
        nb.btn_stop.clicked.connect(self.executor.stop)

    # --- step lifecycle handlers --------------------------------------

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
        self._phase_started_at = None
        try:
            self._phase_target = float(getattr(row, "duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._phase_target = None
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        self.status_bar.lbl_recent_step.setText(f"Most Recent Step: {row.name}")
        self.status_bar.lbl_next_step.setText(
            f"Next Step: {self._next_step_name(row)}"
        )
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _next_step_name(self, current):
        steps = self.manager.iter_execution_steps()
        cur_path = tuple(current.path)
        for row in steps:
            if tuple(row.path) == cur_path:
                next_row = next(steps, None)
                return next_row.name if next_row is not None else "-"
        return "-"

    def _on_phase_ack(self):
        if self._current_row is None:
            return
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now

    def _on_step_repetition(self, rep_chain):
        if not rep_chain:
            self._status_reps_label.setText("")
            self._status_reps_label.setVisible(False)
            return
        parts = [
            f"rep {idx}/{total} of '{name}'" for name, idx, total in rep_chain
        ]
        self._status_reps_label.setText(" · ".join(parts))
        self._status_reps_label.setVisible(True)

    def _on_step_finished(self, _row):
        self._refresh_status()

    def _on_error(self, msg):
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._tick_timer.stop()
        self._set_idle_button_state()
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

    # --- button state machine ----------------------------------------

    def _set_idle_button_state(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_play_state()
        nb.btn_stop.setEnabled(False)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)
        nb.action_preview.setEnabled(True)

    def _set_running_button_state(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_pause_state()
        nb.btn_stop.setEnabled(True)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)
        nb.action_preview.setEnabled(False)

    def _on_play_clicked(self):
        if self._is_protocol_active():
            self._toggle_pause()
            return
        self._start_protocol_run(
            preview_mode=self.navigation_bar.is_preview_mode(),
        )

    def _start_protocol_run(self, preview_mode):
        self._repeats_total = self.status_bar.edit_repeat_protocol.value()
        self._repeats_completed = 0
        self._current_run_preview_mode = preview_mode
        self._update_repeat_status_label()
        self.executor.start(
            start_step_path=self._selected_step_path(),
            preview_mode=preview_mode,
        )

    def _update_repeat_status_label(self):
        self.status_bar.lbl_repeat_protocol_status.setText(
            f"{self._repeats_completed}/"
        )

    def _selected_step_path(self):
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget._index_to_path(idx)
        for row in self.manager.iter_execution_steps():
            if tuple(row.path) == path:
                return path
        return None

    def _is_protocol_active(self):
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
        self._repeats_completed += 1
        self._update_repeat_status_label()
        if self._repeats_completed < self._repeats_total:
            QTimer.singleShot(50, self._restart_for_next_rep)
            return
        self._on_protocol_terminated()

    def _restart_for_next_rep(self):
        self.executor.start(preview_mode=self._current_run_preview_mode)

    def _on_protocol_aborted(self):
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._on_protocol_terminated()

    def _on_protocol_terminated(self):
        self._set_idle_button_state()
        self._tick_timer.stop()
```

(The phase-navigation pause logic is added in Task 4 — for now `_on_protocol_paused` / `_on_protocol_resumed` just toggle the pause/resume icon; the phase-controls swap arrives next.)

- [ ] **Step 4: Run all pane tests to verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v"
```
Expected: 17 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.1] ProtocolTreePane: executor + button state machine + tick timer"
```

---

## Task 4: Phase-navigation pause logic

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

**Why:** When a running protocol pauses, the play button splits into a `prev_phase` / `resume` / `next_phase` trio that lets the user step through the paused row's phase list visually. Computed locally — the worker thread's iter_phases position isn't reachable. Verbatim move from `BasePluggableProtocolDemoWindow` lines 919-997.

- [ ] **Step 1: Append phase-nav tests**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_pause_splits_play_button_into_phase_nav(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeRow:
        path = [0]
        name = "S"
        duration_s = 1.0
        electrodes = []
        routes = []
        trail_length = 1
        trail_overlay = 0
        soft_start = False
        soft_end = False
        repeat_duration = 0.0
        linear_repeats = False
        repetitions = 1

    pane = ProtocolTreePane([make_type_column()])
    pane._current_row = FakeRow()
    pane.executor.qsignals.protocol_started.emit()
    pane.executor.qsignals.protocol_paused.emit()
    assert pane.navigation_bar.is_phase_navigation_active()


def test_pane_resume_merges_phase_nav_back_to_play_button(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeRow:
        path = [0]
        name = "S"
        duration_s = 1.0
        electrodes = []
        routes = []
        trail_length = 1
        trail_overlay = 0
        soft_start = False
        soft_end = False
        repeat_duration = 0.0
        linear_repeats = False
        repetitions = 1

    pane = ProtocolTreePane([make_type_column()])
    pane._current_row = FakeRow()
    pane.executor.qsignals.protocol_started.emit()
    pane.executor.qsignals.protocol_paused.emit()
    assert pane.navigation_bar.is_phase_navigation_active()
    pane.executor.qsignals.protocol_resumed.emit()
    assert not pane.navigation_bar.is_phase_navigation_active()


def test_pane_phase_nav_publishes_electrodes_state_change(qapp, monkeypatch):
    """next_phase click publishes ELECTRODES_STATE_CHANGE for the targeted phase."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    captured = []

    def fake_publish(topic, message, **kwargs):
        captured.append((topic, message))

    monkeypatch.setattr(ptp, "publish_message", fake_publish)

    pane = ptp.ProtocolTreePane([make_type_column()])
    pane._pause_phases = [{"e1"}, {"e1", "e2"}]
    pane._pause_phase_idx = 0
    pane.manager.protocol_metadata["electrode_to_channel"] = {"e1": 1, "e2": 2}
    pane._on_next_phase()
    assert captured  # something was published
    topic, _ = captured[0]
    assert topic == ptp.ELECTRODES_STATE_CHANGE
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_pause_splits_play_button_into_phase_nav -v"
```
Expected: pause does NOT yet split the button — so `is_phase_navigation_active()` returns False.

- [ ] **Step 3: Add the phase-nav module imports + state + handlers**

Add to imports at top of `src/pluggable_protocol_tree/views/protocol_tree_pane.py`:

```python
import json

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.services.phase_math import iter_phases
```

(Replace the existing single-import line for `ELECTRODES_STATE_APPLIED` with the joint form above.)

Add the phase-nav state to `__init__` (right after `self._current_run_preview_mode = False`):

```python
        self._pause_phases: list = []
        self._pause_phase_idx: int = 0
```

Wire the navigation_bar's phase buttons in `_wire_navigation_buttons`:

```python
    def _wire_navigation_buttons(self):
        nb = self.navigation_bar
        nb.btn_play.clicked.connect(self._on_play_clicked)
        nb.btn_resume.clicked.connect(self._toggle_pause)
        nb.btn_stop.clicked.connect(self.executor.stop)
        nb.btn_prev_phase.clicked.connect(self._on_prev_phase)
        nb.btn_next_phase.clicked.connect(self._on_next_phase)
        nb.set_phase_navigation_enabled(False, False)
```

Replace `_on_protocol_paused` / `_on_protocol_resumed` / `_on_protocol_terminated`:

```python
    def _on_protocol_paused(self):
        self.navigation_bar.show_resume_state()
        self._tick_timer.stop()
        if self._current_row is not None:
            self._compute_pause_phase_state(self._current_row)
            self.navigation_bar.split_play_button_to_phase_controls()
            self._update_phase_nav_buttons()

    def _on_protocol_resumed(self):
        self.navigation_bar.show_pause_state()
        if self._current_row is not None:
            self._tick_timer.start()
        self.navigation_bar.merge_phase_controls_to_play_button()

    def _on_protocol_terminated(self):
        self._set_idle_button_state()
        self._tick_timer.stop()
        self.navigation_bar.merge_phase_controls_to_play_button()
        self._pause_phases = []
        self._pause_phase_idx = 0
```

Append the phase-nav handlers:

```python
    # --- pause-time phase navigation ---------------------------------

    def _compute_pause_phase_state(self, row):
        try:
            self._pause_phases = list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=float(getattr(row, "repeat_duration", 0.0)),
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
        except Exception as e:
            logger.warning(f"phase navigation: iter_phases failed: {e}")
            self._pause_phases = []
        self._pause_phase_idx = 0

    def _on_prev_phase(self):
        if self._pause_phases and self._pause_phase_idx > 0:
            self._pause_phase_idx -= 1
            self._publish_paused_phase()
            self._update_phase_nav_buttons()

    def _on_next_phase(self):
        if (self._pause_phases
                and self._pause_phase_idx < len(self._pause_phases) - 1):
            self._pause_phase_idx += 1
            self._publish_paused_phase()
            self._update_phase_nav_buttons()

    def _publish_paused_phase(self):
        if not self._pause_phases:
            return
        phase = self._pause_phases[self._pause_phase_idx]
        mapping = self.manager.protocol_metadata.get(
            "electrode_to_channel", {},
        )
        electrodes = sorted(phase)
        channels = sorted(mapping[e] for e in electrodes if e in mapping)
        payload = {"electrodes": electrodes, "channels": channels}
        if self._current_run_preview_mode:
            payload["preview"] = True
        try:
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps(payload),
            )
        except Exception as e:
            logger.warning(f"phase navigation publish failed: {e}")

    def _update_phase_nav_buttons(self):
        prev_enabled = self._pause_phase_idx > 0
        next_enabled = (
            bool(self._pause_phases)
            and self._pause_phase_idx < len(self._pause_phases) - 1
        )
        self.navigation_bar.set_phase_navigation_enabled(
            prev_enabled, next_enabled,
        )
```

**Important — the test `test_pane_phase_nav_publishes_electrodes_state_change` requires that the test target — the index used — is permitted to advance. The test uses `_pause_phases = [{"e1"}, {"e1","e2"}]` (length 2) and starts at index 0; `_on_next_phase` advances to index 1 and publishes.**

- [ ] **Step 4: Run all pane tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v"
```
Expected: 20 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.1] ProtocolTreePane: phase-navigation pause logic"
```

---

## Task 5: Step-cursor navigation + save/load helpers

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

**Why:** First/Prev/Next/Last buttons drive the tree's selection cursor (they don't mutate the protocol). The Next button at the end-of-protocol clones the last step. Save/Load helpers expose JSON round-trip via `QFileDialog`. Verbatim move from `BasePluggableProtocolDemoWindow` lines 999-1108 + 747-772.

- [ ] **Step 1: Append step-cursor + save/load tests**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_navigate_to_first_step_selects_first_row(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "A", "duration_s": 0.1})
    pane.manager.add_step(values={"name": "B", "duration_s": 0.1})
    pane.navigate_to_first_step()
    idx = pane.widget.tree.currentIndex()
    assert idx.isValid()


def test_pane_navigate_to_next_at_end_duplicates_step(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "A", "duration_s": 0.1})
    pane.navigate_to_last_step()
    pane.navigate_to_next_step()
    assert len(pane.manager.root.children) == 2


def test_pane_save_writes_manager_to_json(qapp, tmp_path, monkeypatch):
    from pyface.qt.QtWidgets import QFileDialog

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.builtins.id_column import make_id_column
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    import json

    pane = ProtocolTreePane([
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
    ])
    pane.manager.add_step(values={"name": "S1", "duration_s": 0.1})

    save_path = tmp_path / "out.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **kw: (str(save_path), ""))
    pane.save_to_dialog()
    payload = json.loads(save_path.read_text())
    assert payload["columns"][0]["id"] == "type"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_save_writes_manager_to_json -v"
```
Expected: `AttributeError: 'ProtocolTreePane' object has no attribute 'save_to_dialog'`.

- [ ] **Step 3: Add navigation + save/load methods**

Add to imports:

```python
from pyface.qt.QtCore import QModelIndex
from pyface.qt.QtWidgets import QFileDialog
```

Wire the step-cursor buttons inside `_wire_navigation_buttons`:

```python
    def _wire_navigation_buttons(self):
        nb = self.navigation_bar
        nb.btn_play.clicked.connect(self._on_play_clicked)
        nb.btn_resume.clicked.connect(self._toggle_pause)
        nb.btn_stop.clicked.connect(self.executor.stop)
        nb.btn_first.clicked.connect(self.navigate_to_first_step)
        nb.btn_prev.clicked.connect(self.navigate_to_previous_step)
        nb.btn_next.clicked.connect(self.navigate_to_next_step)
        nb.btn_last.clicked.connect(self.navigate_to_last_step)
        nb.btn_prev_phase.clicked.connect(self._on_prev_phase)
        nb.btn_next_phase.clicked.connect(self._on_next_phase)
        nb.set_phase_navigation_enabled(False, False)
```

Append the navigation + save/load helpers + `clear_highlights` (needed by Task 7):

```python
    # --- step-cursor navigation -------------------------------------

    def navigate_to_first_step(self):
        steps = list(self.manager.iter_execution_steps())
        if steps:
            self._select_step(steps[0])

    def navigate_to_last_step(self):
        steps = list(self.manager.iter_execution_steps())
        if steps:
            self._select_step(steps[-1])

    def navigate_to_previous_step(self):
        steps = list(self.manager.iter_execution_steps())
        if not steps:
            return
        cur = self._current_step_in(steps)
        if cur is None:
            self._select_step(steps[0])
            return
        if cur > 0:
            self._select_step(steps[cur - 1])

    def navigate_to_next_step(self):
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
        self._duplicate_step_after(steps[cur])

    def _duplicate_step_after(self, row):
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
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget._index_to_path(idx)
        for i, row in enumerate(steps):
            if tuple(row.path) == path:
                return i
        return None

    def _select_step(self, row):
        idx = self.widget._node_to_index(row)
        if not idx.isValid():
            return
        parent = idx.parent()
        while parent.isValid():
            self.widget.tree.expand(parent)
            parent = parent.parent()
        self.widget.tree.setCurrentIndex(idx)
        self.widget.tree.scrollTo(idx)

    def clear_highlights(self):
        """Reset the tree's selection + active-row highlight + per-step
        labels to the idle visual state."""
        self.widget.highlight_active_row(None)
        self.widget.tree.clearSelection()
        self.widget.tree.setCurrentIndex(QModelIndex())

        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None
        self._current_row = None

        self._status_step_label.setText("Step 0/0")
        self._status_step_time_label.setText("Step Time: 0 s")
        self._status_reps_label.setText("Repetition 0/0")
        self._status_reps_label.setVisible(True)
        self.status_bar.lbl_recent_step.setText("Most Recent Step: -")
        self.status_bar.lbl_next_step.setText("Next Step: -")
        if self._status_phase_time_label is not None:
            self._status_phase_time_label.setText("Phase 0.00s / 0.00s")

    # --- save / load -----------------------------------------------

    def save_to_dialog(self, parent=None):
        """Open a file dialog and persist the manager's JSON state."""
        path, _ = QFileDialog.getSaveFileName(
            parent or self, "Save Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.manager.to_json(), f, indent=2)
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Save error", message=str(e))

    def load_from_dialog(self, columns_factory, parent=None):
        """Open a file dialog and replace the manager's state from JSON.

        ``columns_factory`` rebuilds the column list (consumed by
        ``set_state_from_json``); the dock pane and demo window each
        own a different source of truth for it."""
        path, _ = QFileDialog.getOpenFileName(
            parent or self, "Load Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.manager.set_state_from_json(data, columns=columns_factory())
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Load error", message=str(e))
```

Update `_on_protocol_terminated` to also call `clear_highlights`:

```python
    def _on_protocol_terminated(self):
        self.clear_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
        self.navigation_bar.merge_phase_controls_to_play_button()
        self._pause_phases = []
        self._pause_phase_idx = 0
```

Update `_on_error` to also call `clear_highlights`:

```python
    def _on_error(self, msg):
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self.clear_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
        error_dialog(parent=self, title="Protocol error", message=str(msg))
```

- [ ] **Step 4: Run all pane tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v"
```
Expected: 23 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.1] ProtocolTreePane: step-cursor nav + save/load + clear_highlights"
```

---

## Task 6: Real-mode service wiring + experiment-changed observation

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

**Why:** Convert the experiment-bar stub handlers into real-mode handlers that invoke the injected services when present. `application` observation uses the `experiment_changed` Event (not the `current_experiment_directory` Property — that doesn't fire reliable notifications, see spec risks).

- [ ] **Step 1: Append the real-mode service tests**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_stub_mode_buttons_log_only(qapp):
    """Without injected services, button clicks log and never raise."""
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    pane = ProtocolTreePane([make_type_column()])
    pane.btn_new_exp.click()
    pane.btn_new_note.click()
    pane.experiment_label.clicked.emit()


def test_pane_real_mode_new_experiment_calls_service(qapp):
    """With an experiment_manager + application, New Experiment dispatches."""
    from pathlib import Path
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    new_dir = Path("/tmp/new-exp-id")
    exp_mgr = MagicMock()
    exp_mgr.initialize_new_experiment.return_value = new_dir
    exp_mgr.get_experiment_directory.return_value = new_dir

    app = MagicMock()
    app.current_experiment_directory = Path("/tmp/old-exp-id")

    pane = ProtocolTreePane(
        [make_type_column()],
        application=app,
        experiment_manager=exp_mgr,
    )
    pane.btn_new_exp.click()
    exp_mgr.initialize_new_experiment.assert_called_once()
    assert app.current_experiment_directory == new_dir


def test_pane_real_mode_new_experiment_returning_none_does_not_overwrite(qapp):
    from pathlib import Path
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    exp_mgr = MagicMock()
    exp_mgr.initialize_new_experiment.return_value = None
    app = MagicMock()
    app.current_experiment_directory = Path("/tmp/old-exp-id")

    pane = ProtocolTreePane(
        [make_type_column()],
        application=app,
        experiment_manager=exp_mgr,
    )
    pane.btn_new_exp.click()
    assert app.current_experiment_directory == Path("/tmp/old-exp-id")


def test_pane_real_mode_new_note_calls_sticky_manager(qapp):
    from pathlib import Path
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    base_dir = Path("/tmp/exp-1")
    exp_mgr = MagicMock()
    exp_mgr.get_experiment_directory.return_value = base_dir
    sticky_mgr = MagicMock()

    pane = ProtocolTreePane(
        [make_type_column()],
        experiment_manager=exp_mgr,
        sticky_manager=sticky_mgr,
    )
    pane.btn_new_note.click()
    sticky_mgr.request_new_note.assert_called_once_with(base_dir, "exp-1")


def test_pane_real_mode_label_click_opens_experiment_directory(qapp):
    from unittest.mock import MagicMock

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    exp_mgr = MagicMock()
    pane = ProtocolTreePane(
        [make_type_column()],
        experiment_manager=exp_mgr,
    )
    pane.experiment_label.clicked.emit()
    exp_mgr.open_experiment_directory.assert_called_once()


def test_pane_observes_experiment_changed_event_to_update_label(qapp):
    """When application.experiment_changed fires, the label re-reads
    application.current_experiment_directory and updates."""
    from pathlib import Path

    from traits.api import Directory, Event, HasTraits, Property

    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    class FakeApp(HasTraits):
        current_experiment_directory = Property(Directory)
        experiment_changed = Event()
        _value = Path("/tmp/initial")

        def _get_current_experiment_directory(self):
            return self._value

        def _set_current_experiment_directory(self, value):
            self._value = Path(value)
            self.experiment_changed = True

    app = FakeApp()
    pane = ProtocolTreePane([make_type_column()], application=app)
    app.current_experiment_directory = "/tmp/2026-05-08T12-00-00Z"
    assert "2026-05-08T12-00-00Z" in pane.experiment_label.text()
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_real_mode_new_experiment_calls_service -v"
```
Expected: FAIL — `initialize_new_experiment` not called (pane currently logs only).

- [ ] **Step 3: Replace the experiment-bar stub handlers + add observation**

Replace the three stub methods at the bottom of `src/pluggable_protocol_tree/views/protocol_tree_pane.py`:

```python
    # --- experiment-bar handlers ------------------------------------

    def _on_new_experiment(self):
        if self.experiment_manager is None or self.application is None:
            logger.info("New Experiment requested (stub: no services injected)")
            return
        new_dir = self.experiment_manager.initialize_new_experiment()
        if new_dir is None:
            logger.warning("initialize_new_experiment returned None; label unchanged")
            return
        self.application.current_experiment_directory = new_dir
        self.experiment_label.update_experiment_id(new_dir.stem)
        logger.info(f"Started new experiment: {new_dir.stem}")

    def _on_new_note(self):
        if self.sticky_manager is None or self.experiment_manager is None:
            logger.info("New Note requested (stub: no services injected)")
            return
        base_dir = self.experiment_manager.get_experiment_directory()
        experiment_name = base_dir.stem
        self.sticky_manager.request_new_note(base_dir, experiment_name)

    def _on_experiment_label_clicked(self):
        if self.experiment_manager is None:
            logger.info("Experiment label clicked (stub: no service injected)")
            return
        self.experiment_manager.open_experiment_directory()
```

Wire the `experiment_changed` observation. Add to the bottom of `__init__` (after `self._set_idle_button_state()`):

```python
        if self.application is not None:
            self.application.observe(
                self._on_experiment_changed, "experiment_changed",
            )
            # Render the initial experiment id into the label.
            try:
                cur = self.application.current_experiment_directory
                if cur is not None:
                    self.experiment_label.update_experiment_id(cur.stem)
            except Exception as e:
                logger.warning(f"could not read initial experiment dir: {e}")
```

Add the handler method:

```python
    def _on_experiment_changed(self, _event):
        try:
            cur = self.application.current_experiment_directory
        except Exception as e:
            logger.warning(f"experiment_changed: failed to read dir: {e}")
            return
        if cur is None:
            return
        self.experiment_label.update_experiment_id(cur.stem)
```

- [ ] **Step 4: Run all pane tests to verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v"
```
Expected: 29 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.1] ProtocolTreePane: real-mode service wiring + experiment_changed observe"
```

---

## Task 7: Refactor `BasePluggableProtocolDemoWindow` to delegate

**Files:**
- Modify: `src/pluggable_protocol_tree/demos/base_demo_window.py`

**Why:** Strip the now-duplicated scaffolding from the demo window (~600 LOC) and replace it with a `ProtocolTreePane` instance + thin window-only chrome (toolbar with Add/Save/Load, side-panel splitter, status-readout labels, Dramatiq routing). Keep `@property` aliases so the existing `test_base_demo_window.py` keeps passing without edits.

- [ ] **Step 1: Run the existing demo-window tests as a baseline**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_base_demo_window.py -v"
```
Expected: all PASSED (current state). Note the count — must match after refactor.

- [ ] **Step 2: Rewrite `base_demo_window.py`**

Replace the entire content of `src/pluggable_protocol_tree/demos/base_demo_window.py` with the slimmed delegating version. Preserve the module-level Dramatiq actor / `DemoConfig` / `StatusReadout` / `_slug` / `_DEMO_PREFIXES` / `_is_purgable_demo_actor_name` / `_PerSlugEmitter` / `_phase_ack_target` / `_readout_target` / `_make_readout_actor` definitions verbatim from the existing file (lines 1-190 stay byte-for-byte the same). Only the `BasePluggableProtocolDemoWindow` class body changes.

The new class body:

```python
class BasePluggableProtocolDemoWindow(QMainWindow):
    """Hosts a ProtocolTreePane + the demo-only toolbar / readouts /
    Dramatiq routing scaffolding. See PPT-10.1 for the pane refactor."""

    phase_acked = Signal()                    # forwarded to pane.phase_acked
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
        # keep working unchanged.
        self.pane.phase_acked.connect(self.phase_acked.emit)

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
    #
    # test_base_demo_window.py + existing demos reach into many of the
    # pane's attributes via the window. These properties forward.

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
        # Reset readout labels to initial text — they're demo-only state.
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
```

Drop the now-unused imports at the top of `base_demo_window.py`:

```python
# REMOVE these — no longer used after delegation:
#   from pluggable_protocol_tree.execution.events import PauseEvent
#   from pluggable_protocol_tree.execution.executor import ProtocolExecutor
#   from pluggable_protocol_tree.execution.signals import ExecutorSignals
#   from pluggable_protocol_tree.models.row_manager import RowManager
#   from pluggable_protocol_tree.views.navigation_bar import NavigationBar, StatusBar, make_separator
#   from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget
#   import threading, time
#   from pyface.qt.QtCore import QModelIndex
#   from pyface.qt.QtWidgets import QFileDialog
#   from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
```

The remaining imports actually used by the new class body:

```python
import dramatiq

from pyface.qt.QtCore import Qt, Signal
from pyface.qt.QtWidgets import (
    QApplication, QLabel, QMainWindow, QSplitter, QStatusBar, QToolBar, QWidget,
)

from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.demos.electrode_responder import (
    DEMO_RESPONDER_ACTOR_NAME,
)
```

(`QWidget` import retained because the module-level dataclasses still reference it.)

- [ ] **Step 3: Run the existing demo-window test suite to verify aliases hold**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_base_demo_window.py -v"
```
Expected: same number of PASSED tests as the baseline in Step 1, no failures.

- [ ] **Step 4: Run the entire pluggable_protocol_tree test suite for regressions**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ -v --ignore=pluggable_protocol_tree/tests/tests_with_redis_server_need"
```
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/demos/base_demo_window.py
git -C microdrop-py/src commit -m "[PPT-10.1] BasePluggableProtocolDemoWindow delegates to ProtocolTreePane"
```

---

## Task 8: Wire `PluggableProtocolDockPane` to real services

**Files:**
- Modify: `src/pluggable_protocol_tree/views/dock_pane.py`
- Create: `src/pluggable_protocol_tree/tests/test_dock_pane.py`

**Why:** The dock pane now constructs an `ExperimentManager` from the application's experiment directory, instantiates a `StickyWindowManager`, and passes both into the pane along with the application reference for trait observation. Title renamed to "Protocol (pluggable)" so it's distinguishable from the legacy pane during coexistence.

- [ ] **Step 1: Write the failing dock-pane tests**

```python
# src/pluggable_protocol_tree/tests/test_dock_pane.py
"""Tests for PluggableProtocolDockPane wiring."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_dock_pane_with_mocked_app(qapp, columns):
    """Returns (dock_pane, mock_app, mock_task) — call create_contents
    after attaching task->window->application chain."""
    from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane

    mock_app = MagicMock()
    mock_app.current_experiment_directory = Path("/tmp/exp-1")
    mock_window = MagicMock()
    mock_window.application = mock_app
    mock_task = MagicMock()
    mock_task.window = mock_window

    dp = PluggableProtocolDockPane(columns=columns)
    dp.task = mock_task
    return dp, mock_app, mock_task


def test_dock_pane_id_and_name(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    assert dp.id == "pluggable_protocol_tree.dock_pane"
    assert dp.name == "Protocol (pluggable)"


def test_dock_pane_create_contents_returns_protocol_tree_pane(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane

    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    contents = dp.create_contents(parent=None)
    assert isinstance(contents, ProtocolTreePane)


def test_dock_pane_constructs_experiment_manager_with_app_dir(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dp, app, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    with patch(
        "pluggable_protocol_tree.views.dock_pane.ExperimentManager"
    ) as ExpMgrClass:
        dp.create_contents(parent=None)
    ExpMgrClass.assert_called_once_with(app.current_experiment_directory)


def test_dock_pane_constructs_sticky_manager(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dp, _, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    with patch(
        "pluggable_protocol_tree.views.dock_pane.StickyWindowManager"
    ) as StickyClass:
        dp.create_contents(parent=None)
    StickyClass.assert_called_once_with()


def test_dock_pane_passes_application_into_pane(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column

    dp, app, _ = _make_dock_pane_with_mocked_app(qapp, [make_type_column()])
    contents = dp.create_contents(parent=None)
    assert contents.application is app
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_dock_pane.py -v"
```
Expected: FAIL — current `PluggableProtocolDockPane.name` is `"Protocol"` and `create_contents` returns a `ProtocolTreeWidget`, not a `ProtocolTreePane`.

- [ ] **Step 3: Rewrite `dock_pane.py`**

Replace the contents of `src/pluggable_protocol_tree/views/dock_pane.py`:

```python
"""Pyface TaskPane hosting ProtocolTreePane.

Receives its column set from the plugin on construction and constructs
the experiment + sticky-note services from the live Envisage
application so the experiment-bar buttons drive real handlers."""

from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str

from microdrop_utils.sticky_notes import StickyWindowManager
from protocol_grid.services.experiment_manager import ExperimentManager

from pluggable_protocol_tree.interfaces.i_column import IColumn


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = Str("Protocol (pluggable)")

    columns = List(Instance(IColumn))

    def create_contents(self, parent):
        # Local import to avoid pulling Qt at plugin-import time —
        # ProtocolTreePane imports PySide6 widgets eagerly.
        from pluggable_protocol_tree.views.protocol_tree_pane import (
            ProtocolTreePane,
        )

        app = self.task.window.application
        experiment_manager = ExperimentManager(app.current_experiment_directory)
        sticky_manager = StickyWindowManager()

        return ProtocolTreePane(
            list(self.columns),
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            parent=parent,
        )
```

- [ ] **Step 4: Run dock-pane tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_dock_pane.py -v"
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add src/pluggable_protocol_tree/views/dock_pane.py src/pluggable_protocol_tree/tests/test_dock_pane.py
git -C microdrop-py/src commit -m "[PPT-10.1] PluggableProtocolDockPane wires real ExperimentManager + StickyWindowManager"
```

---

## Task 9: Register `PluggableProtocolTreePlugin` + manual smoke

**Files:**
- Modify: `src/examples/plugin_consts.py`

**Why:** Activate the new dock pane in the actual app launch path so coexistence with `protocol_grid` is testable end-to-end. Manual verification covers the launch path and click behavior — automated coverage at this layer would require a full Envisage application stand-up which is out of proportion for this PR.

- [ ] **Step 1: Uncomment the import + the FRONTEND_PLUGINS entry**

Edit `src/examples/plugin_consts.py`. Find:

```python
# from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin   # may not exist on disk
```

If a commented import line exists for `PluggableProtocolTreePlugin`, uncomment it. Otherwise add the import alongside the others (alphabetical block at the top is the convention here):

```python
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
```

In the `FRONTEND_PLUGINS` list, change line 70 from:

```python
    # PluggableProtocolTreePlugin,
```
to:
```python
    PluggableProtocolTreePlugin,
```

Verify the rest of the commented-out plugins (`DropbotProtocolControlsPlugin`, etc.) **stay** commented — only `PluggableProtocolTreePlugin` is being activated.

- [ ] **Step 2: Run the existing examples test suite as a regression check**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest examples/tests/ -v --ignore=examples/tests/tests_with_redis_server_need --ignore=examples/tests/tests_with_dropbot_connection_need"
```
Expected: same pass/fail outcome as before this task (no new failures introduced by activating the plugin).

- [ ] **Step 3: Manual smoke — launch the full app**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python examples/run_device_viewer_pluggable.py"
```

Verify in the live UI:

1. Two protocol-related dock panes are visible. The old one is titled **"Protocol Grid Controller"** (or similar — legacy). The new one is **"Protocol (pluggable)"**.
2. The new pane shows the navigation bar (play / step / stop), status row, and experiment row (`note_add` / `Experiment: …` / `sticky_note`).
3. Click the **`note_add`** icon on the new pane → the experiment label updates to a new timestamped id.
4. Click the **experiment label** itself → the OS file explorer opens at the new experiment directory.
5. Click the **`sticky_note`** icon → a new sticky window opens with the experiment's name in the title.
6. Verify the legacy pane's experiment label also updates (both observe `experiment_changed`).
7. Close the app cleanly.

- [ ] **Step 4: Commit**

```bash
git -C microdrop-py/src add src/examples/plugin_consts.py
git -C microdrop-py/src commit -m "[PPT-10.1] Register PluggableProtocolTreePlugin in FRONTEND_PLUGINS"
```

- [ ] **Step 5: Push the branch and open a PR**

```bash
git -C microdrop-py/src push -u origin ppt-10.1-protocol-tree-pane
gh pr create --repo Blue-Ocean-Technologies-Inc/Microdrop --title "[PPT-10.1] Build full-app dock pane: ProtocolTreePane refactor + service wiring (#411)" --body "$(cat <<'EOF'
## Summary
- Extracts `ProtocolTreePane(QWidget)` from `BasePluggableProtocolDemoWindow` so the demo window and the full-app dock pane share scaffolding (NavigationBar + StatusBar + experiment-bar + executor + button state machine + phase-nav).
- Optional service injection (`application`, `experiment_manager`, `sticky_manager`) — the dock pane supplies real services; demos pass nothing and keep today's stub UX.
- `PluggableProtocolDockPane` constructs `ExperimentManager` + `StickyWindowManager` from the live Envisage application; observes `application.experiment_changed` to keep the label in sync.
- Registers `PluggableProtocolTreePlugin` in `examples/plugin_consts.py` alongside the legacy `ProtocolGridControllerUIPlugin`. Pane title is **"Protocol (pluggable)"** for unambiguity during coexistence.
- Resolves #411. Out of scope: legacy removal (#371 / PPT-9), full message-listener parity (separate follow-up).

## Test plan
- [ ] `pluggable_protocol_tree/tests/test_protocol_tree_pane.py` — 29 tests covering construction, executor wiring, button state machine, phase-nav pause logic, step-cursor navigation, save/load, real-mode service handlers, experiment_changed observation
- [ ] `pluggable_protocol_tree/tests/test_dock_pane.py` — 5 tests covering create_contents wiring + service construction
- [ ] `pluggable_protocol_tree/tests/test_experiment_label.py` — 6 tests covering ExperimentLabel mouse/text/tooltip behavior
- [ ] `pluggable_protocol_tree/tests/test_base_demo_window.py` — full existing suite passes unchanged via `@property` aliases on the window
- [ ] Manual: launch `examples/run_device_viewer_pluggable.py`, confirm two panes coexist, exercise New Experiment / experiment-label click / New Note on the new pane

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review

**Spec coverage:**
- [x] §1 architecture & file layout → Tasks 1–8 create/modify all listed files
- [x] §2 constructor signature → Task 2 + Task 6 (services added later)
- [x] §3 service wiring table → Task 6
- [x] §4 dock-pane sketch → Task 8
- [x] §5 demo-window slimming + alias contract → Task 7
- [x] §6 data flow (Play click) → exercised by manual smoke in Task 9 + automated in Task 3 button-state-machine tests
- [x] §7 plugin registration → Task 9
- [x] §8 testing strategy enumerated tests → split across Tasks 1, 2, 3, 4, 5, 6, 7, 8
- [x] §9 acceptance criteria → mapped 1:1 onto Task outputs and the Task 9 manual smoke
- [x] §10 risks (StickyWindowManager singleton, ExperimentManager cleanup hooks, experiment_changed Event, coexistence) — captured in code (handler null-checks, dock-pane comments) and in the PR-body summary

**Placeholder scan:** No "TBD"/"TODO"/"similar to"/"add appropriate"/etc.

**Type/method consistency:**
- `save_to_dialog` and `load_from_dialog` (Task 5) referenced from `_save` / `_load` on the demo window (Task 7) ✓
- `clear_highlights` (Task 5) called from `_on_protocol_terminated` and `_on_error` ✓
- `_on_experiment_changed` (Task 6) connected via `application.observe(..., "experiment_changed")` ✓
- `experiment_label.clicked` signal wired to `_on_experiment_label_clicked` in Task 2, real-mode handler swapped in Task 6 ✓
- All `@property` alias names in Task 7 match the pane attribute names introduced in Tasks 2–6 ✓
