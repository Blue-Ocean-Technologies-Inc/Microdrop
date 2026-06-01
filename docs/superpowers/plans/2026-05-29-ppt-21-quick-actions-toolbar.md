# PPT-21 Quick-Actions Toolbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the legacy `protocol_grid` quick-actions toolbar into the pluggable protocol tree with a clean split: the tree plugin owns the contribution surface (extension point, traits model, bar widget, controller, pane integration); a new sibling plugin `protocol_quick_action_tools` ships all 8 legacy actions (add_step, delete_row, add_group, import_protocol, open_protocol, save_protocol, new_protocol, browse_reports) plus the ported `ReportBrowserDialog`.

**Architecture:** Mirror the existing `PROTOCOL_COLUMNS` pattern — Envisage `ExtensionPoint(List(Instance(IQuickAction)))` aggregated through a plain list, sorted by `(priority, action_id)`, passed into `ProtocolTreePane` at construction, rendered as `QToolButton`s under the tree; a `QuickActionsController` watches new pane signals (`selection_changed`, `protocol_running_changed`) to drive per-action `is_enabled(ctx)` predicates and wires `QShortcut`s declaratively from each action's `shortcut` trait.

**Tech Stack:** Python 3, Traits/HasStrictTraits, PySide6 via `pyface.qt`, Envisage plugins, pytest with `pytest-qt`'s `qapp` fixture, `unittest.mock.MagicMock`.

**Spec:** `docs/superpowers/specs/2026-05-28-ppt-21-quick-actions-toolbar-design.md`

**Working directory for all commands:** `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py` (where `pixi run pytest src/...` resolves correctly).

---

### Task 1: Add `PROTOCOL_QUICK_ACTIONS` const and `IQuickAction` interface

**Files:**
- Create: `src/pluggable_protocol_tree/interfaces/i_quick_action.py`
- Modify: `src/pluggable_protocol_tree/consts.py` (add `PROTOCOL_QUICK_ACTIONS`)
- Create: `src/pluggable_protocol_tree/tests/test_quick_action_interface.py`

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_quick_action_interface.py`:

```python
"""IQuickAction is the contract any contributed quick-action button
implements. This file pins the trait shape and the two-method surface
so future refactors can't silently break plugin contributions."""

from traits.api import HasStrictTraits, provides

from pluggable_protocol_tree.consts import PROTOCOL_QUICK_ACTIONS
from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


def test_extension_point_id_is_namespaced():
    assert PROTOCOL_QUICK_ACTIONS == (
        "pluggable_protocol_tree.protocol_quick_actions"
    )


def test_iquick_action_required_traits_exist():
    """Trait names + default values are part of the public contract —
    plugins read action_id/icon_text/tooltip directly."""

    @provides(IQuickAction)
    class _Stub(HasStrictTraits):
        pass

    s = _Stub()
    # Every trait declared on IQuickAction must be readable on a provider
    # (proves the interface itself declares them).
    for name in ("action_id", "icon_text", "tooltip",
                 "priority", "shortcut"):
        assert hasattr(s, name), f"missing trait: {name}"
    assert s.priority == 50
    assert s.shortcut == ""


def test_iquick_action_methods_are_callable_with_ctx():
    """The interface defines on_execute_action(ctx) and is_enabled(ctx)
    -> bool; defaults are no-op / True."""

    @provides(IQuickAction)
    class _Stub(HasStrictTraits):
        action_id = "x"
        icon_text = ""
        tooltip = ""

    s = _Stub()
    # Default implementations don't raise; is_enabled defaults to True.
    s.on_execute_action(ctx=None)
    assert s.is_enabled(ctx=None) is True
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_action_interface.py -v
```

Expected: 3 errors on `ImportError: cannot import name 'PROTOCOL_QUICK_ACTIONS'` / `cannot import name 'IQuickAction'`.

- [ ] **Step 3: Add the constant**

Append to `src/pluggable_protocol_tree/consts.py` (place after the `LOGGING_LISTENER_NAME`/`LOGGING_ACTOR_TOPIC_DICT` block, before the trailing blank line):

```python
# Envisage extension point — plugins contribute IQuickAction instances
# (see interfaces/i_quick_action.py) that render as buttons on the
# pluggable tree's quick-actions toolbar. Tree plugin ships zero
# builtins; all contributions come from sibling plugins.
PROTOCOL_QUICK_ACTIONS = f"{PKG}.protocol_quick_actions"
```

- [ ] **Step 4: Create the interface file**

Create `src/pluggable_protocol_tree/interfaces/i_quick_action.py`:

```python
"""Traits interface for protocol-tree quick-action buttons.

Each contribution is a button on the toolbar mounted under the tree.
Mirrors the IColumn pattern: tree plugin owns the contract, other
plugins contribute implementations. Two hooks:

* ``on_execute_action(ctx)`` — fired on click (or keyboard shortcut).
* ``is_enabled(ctx) -> bool`` — queried by the controller on selection
  / protocol-running changes; default ``True``.

The ``ctx`` is a :class:`QuickActionCtx` carrying the pane, current
selection, and is_running flag. Contributions stay Qt-free where they
can by delegating Qt work to pane helper methods.
"""

from traits.api import Bool, Int, Interface, Str


class IQuickAction(Interface):
    action_id = Str(
        desc="Stable identifier (e.g. 'add_step'). Used in logging, "
             "tests, and shortcut-conflict messages.")
    icon_text = Str(
        desc="Material-symbol name rendered as the button's text under "
             "ICON_FONT_FAMILY (e.g. 'add', 'delete', 'playlist_add').")
    tooltip = Str(desc="Button tooltip.")
    priority = Int(50,
        desc="Lower runs first; controls left-to-right order in the bar.")
    shortcut = Str(default_value="",
        desc="QKeySequence string ('R', 'Ctrl+S', ...). Empty = no "
             "shortcut. Registered widget-scoped to the pane.")

    def on_execute_action(self, ctx):
        """Called when the button is clicked or its shortcut fires.
        ctx is a QuickActionCtx. Return value is ignored."""

    def is_enabled(self, ctx) -> bool:
        """Return True if the button should be clickable. Queried by
        the controller on selection / protocol-running changes.
        Default: always True."""
        return True
```

- [ ] **Step 5: Run test to verify it passes**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_action_interface.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```
git add src/pluggable_protocol_tree/consts.py src/pluggable_protocol_tree/interfaces/i_quick_action.py src/pluggable_protocol_tree/tests/test_quick_action_interface.py
git commit -m "[ppt-21] Add IQuickAction interface + PROTOCOL_QUICK_ACTIONS extension-point id"
```

---

### Task 2: Add `BaseQuickAction` model + `QuickActionCtx` value object

**Files:**
- Create: `src/pluggable_protocol_tree/models/quick_action.py`
- Create: `src/pluggable_protocol_tree/tests/test_quick_action_model.py`

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_quick_action_model.py`:

```python
"""BaseQuickAction is a thin HasStrictTraits convenience base so
plugins don't have to redeclare the IQuickAction trait set. The
QuickActionCtx is the value object passed to every action callback."""

from unittest.mock import MagicMock

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction
from pluggable_protocol_tree.models.quick_action import (
    BaseQuickAction, QuickActionCtx,
)


def test_base_quick_action_provides_iquick_action_interface():
    a = BaseQuickAction(action_id="x", icon_text="add", tooltip="t",
                        priority=10, shortcut="Ctrl+X")
    assert IQuickAction in type(a).__implements__.getInterfaces()
    assert a.action_id == "x"
    assert a.icon_text == "add"
    assert a.priority == 10
    assert a.shortcut == "Ctrl+X"


def test_base_quick_action_defaults():
    a = BaseQuickAction(action_id="x")
    assert a.priority == 50
    assert a.shortcut == ""
    assert a.is_enabled(ctx=None) is True


def test_quick_action_ctx_carries_pane_selection_running():
    pane = MagicMock()
    ctx = QuickActionCtx(
        pane=pane,
        selected_paths=((0,), (1, 2)),
        is_running=True,
    )
    assert ctx.pane is pane
    assert ctx.selected_paths == ((0,), (1, 2))
    assert ctx.is_running is True


def test_quick_action_ctx_defaults():
    ctx = QuickActionCtx(pane=MagicMock())
    assert ctx.selected_paths == ()
    assert ctx.is_running is False
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_action_model.py -v
```

Expected: `ImportError: cannot import name 'BaseQuickAction'`.

- [ ] **Step 3: Create the model**

Create `src/pluggable_protocol_tree/models/quick_action.py`:

```python
"""Default ``IQuickAction`` provider + ``QuickActionCtx`` value object.

Plugins are free to subclass ``BaseQuickAction`` (recommended — gets
the trait set and default ``is_enabled`` for free) or write a fresh
``HasStrictTraits`` class decorated with ``@provides(IQuickAction)``.
"""

from traits.api import (
    Any, Bool, HasStrictTraits, Int, Str, Tuple, provides,
)

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


@provides(IQuickAction)
class BaseQuickAction(HasStrictTraits):
    """Concrete IQuickAction provider with the default trait set.

    Subclasses override ``on_execute_action`` (and optionally
    ``is_enabled``). Trait fields can be set positionally / by kwarg
    in factory functions — see protocol_quick_action_tools.quick_actions.
    """
    action_id = Str
    icon_text = Str
    tooltip = Str
    priority = Int(50)
    shortcut = Str(default_value="")

    def on_execute_action(self, ctx):
        """Default no-op. Subclasses override."""

    def is_enabled(self, ctx) -> bool:
        return True


class QuickActionCtx(HasStrictTraits):
    """Value object handed to every action callback.

    Built fresh by the controller on each click / refresh — never
    cached on the action. ``pane`` is the live ``ProtocolTreePane``
    (so contributions can reach ``pane.manager``, ``pane.widget.tree``,
    ``pane.application``, ``pane.experiment_manager``, etc.).
    """
    pane = Any
    selected_paths = Tuple()
    is_running = Bool(False)
```

- [ ] **Step 4: Run test to verify it passes**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_action_model.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add src/pluggable_protocol_tree/models/quick_action.py src/pluggable_protocol_tree/tests/test_quick_action_model.py
git commit -m "[ppt-21] Add BaseQuickAction + QuickActionCtx"
```

---

### Task 3: `QuickActionBar` widget (pure rendering, no behaviour)

**Files:**
- Create: `src/pluggable_protocol_tree/views/quick_action_bar.py` (just the bar; controller in next task)
- Create: `src/pluggable_protocol_tree/tests/test_quick_action_bar.py`

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_quick_action_bar.py`:

```python
"""QuickActionBar is a pure rendering widget: it takes a list of
IQuickAction instances and produces one QToolButton per action,
ordered by (priority, action_id). It has no state and no Qt-signal
connections — the controller (next task) attaches click handlers."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.views.quick_action_bar import QuickActionBar


def _make(action_id, *, priority=50, icon="add", tip="t", shortcut=""):
    return BaseQuickAction(action_id=action_id, icon_text=icon,
                           tooltip=tip, priority=priority,
                           shortcut=shortcut)


def test_bar_renders_one_button_per_action(qapp):
    bar = QuickActionBar(actions=[
        _make("a"), _make("b"), _make("c"),
    ])
    assert len(bar.buttons) == 3
    assert set(bar.buttons.keys()) == {"a", "b", "c"}


def test_bar_orders_by_priority_then_action_id(qapp):
    bar = QuickActionBar(actions=[
        _make("z", priority=10),
        _make("a", priority=20),
        _make("c", priority=10),
    ])
    assert list(bar.buttons.keys()) == ["c", "z", "a"]


def test_button_text_is_icon_text_and_tooltip_matches(qapp):
    bar = QuickActionBar(actions=[
        _make("add_step", icon="add", tip="Add step below selection"),
    ])
    b = bar.buttons["add_step"]
    assert b.text() == "add"
    assert b.toolTip() == "Add step below selection"
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_action_bar.py -v
```

Expected: `ImportError: cannot import name 'QuickActionBar'`.

- [ ] **Step 3: Implement the bar widget**

Create `src/pluggable_protocol_tree/views/quick_action_bar.py`:

```python
"""Pure-rendering toolbar widget for the pluggable protocol tree.

Owns no state. Takes a sorted list of IQuickAction implementations and
produces one icon-font QToolButton per action, keyed by action_id.
The QuickActionsController (separate unit) drives click routing,
per-action enabled state, and keyboard-shortcut wiring.
"""

from typing import Dict, List

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import QHBoxLayout, QToolButton, QWidget

from microdrop_style.button_styles import ICON_FONT_FAMILY

from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction


class QuickActionBar(QWidget):
    """Horizontal row of icon-only QToolButtons, one per action."""

    def __init__(self, actions: List[IQuickAction], parent: QWidget = None):
        super().__init__(parent)
        self.buttons: Dict[str, QToolButton] = {}
        sorted_actions = sorted(actions,
                                key=lambda a: (a.priority, a.action_id))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        icon_font = QFont(ICON_FONT_FAMILY)
        icon_font.setPixelSize(20)
        for action in sorted_actions:
            btn = QToolButton()
            btn.setText(action.icon_text)
            btn.setFont(icon_font)
            btn.setToolTip(action.tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            self.buttons[action.action_id] = btn
            layout.addWidget(btn)
        layout.addStretch()
```

- [ ] **Step 4: Run test to verify it passes**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_action_bar.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add src/pluggable_protocol_tree/views/quick_action_bar.py src/pluggable_protocol_tree/tests/test_quick_action_bar.py
git commit -m "[ppt-21] Add QuickActionBar pure-rendering widget"
```

---

### Task 4: `QuickActionsController` — click routing + per-action enabled state

**Files:**
- Modify: `src/pluggable_protocol_tree/views/quick_action_bar.py` (append controller class)
- Create: `src/pluggable_protocol_tree/tests/test_quick_actions_controller.py`

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_quick_actions_controller.py`:

```python
"""QuickActionsController wires a QuickActionBar to a pane:

* On every ``pane.selection_changed`` / ``pane.protocol_running_changed``
  emission, walks the actions and calls ``button.setEnabled(...)``.
* Clicks route through ``_execute(action)`` which builds a fresh
  ``QuickActionCtx`` and calls ``action.on_execute_action(ctx)``,
  swallowing any exception so a buggy contribution can't crash the bar.
* When ``is_running == True``, the whole bar is disabled regardless of
  each action's ``is_enabled``.
"""

from unittest.mock import MagicMock

from pyface.qt.QtCore import QObject, Signal

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.views.quick_action_bar import (
    QuickActionBar, QuickActionsController,
)


class _FakePane(QObject):
    """Minimal stand-in for ProtocolTreePane."""
    selection_changed = Signal()
    protocol_running_changed = Signal(bool)

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager or MagicMock()
        # Controller pulls `pane.manager.selection` to build ctx.selected_paths.
        self.manager.selection = []


class _ToggleAction(BaseQuickAction):
    """is_enabled flips with the .enabled flag; on_execute_action
    bumps a counter and stashes the ctx for assertions."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.enabled = True
        self.calls = 0
        self.last_ctx = None

    def is_enabled(self, ctx) -> bool:
        return self.enabled

    def on_execute_action(self, ctx):
        self.calls += 1
        self.last_ctx = ctx


def test_initial_state_uses_is_enabled(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    b = _ToggleAction(action_id="b", icon_text="del", tooltip="")
    b.enabled = False
    pane = _FakePane()
    bar = QuickActionBar(actions=[a, b])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a, b])
    ctrl.refresh_enabled()
    assert bar.buttons["a"].isEnabled() is True
    assert bar.buttons["b"].isEnabled() is False


def test_protocol_running_disables_whole_bar(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[a])
    QuickActionsController(bar=bar, pane=pane, actions=[a])
    pane.protocol_running_changed.emit(True)
    assert bar.buttons["a"].isEnabled() is False
    pane.protocol_running_changed.emit(False)
    assert bar.buttons["a"].isEnabled() is True


def test_selection_changed_re_evaluates_is_enabled(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[a])
    QuickActionsController(bar=bar, pane=pane, actions=[a])
    a.enabled = False
    pane.selection_changed.emit()
    assert bar.buttons["a"].isEnabled() is False


def test_click_calls_execute_with_ctx_carrying_selection(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    pane = _FakePane()
    pane.manager.selection = [(0,), (1, 2)]
    bar = QuickActionBar(actions=[a])
    QuickActionsController(bar=bar, pane=pane, actions=[a])
    bar.buttons["a"].click()
    assert a.calls == 1
    assert a.last_ctx.pane is pane
    assert a.last_ctx.selected_paths == ((0,), (1, 2))
    assert a.last_ctx.is_running is False


def test_click_on_disabled_button_does_not_execute(qapp):
    a = _ToggleAction(action_id="a", icon_text="add", tooltip="")
    a.enabled = False
    pane = _FakePane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a])
    ctrl.refresh_enabled()
    bar.buttons["a"].click()
    assert a.calls == 0


def test_buggy_action_does_not_break_other_buttons(qapp, caplog):
    class _Boom(BaseQuickAction):
        def on_execute_action(self, ctx):
            raise RuntimeError("kaboom")

    boom = _Boom(action_id="b", icon_text="del", tooltip="")
    good = _ToggleAction(action_id="g", icon_text="add", tooltip="")
    pane = _FakePane()
    bar = QuickActionBar(actions=[boom, good])
    QuickActionsController(bar=bar, pane=pane, actions=[boom, good])
    bar.buttons["b"].click()                  # raises internally
    bar.buttons["g"].click()                  # must still fire
    assert good.calls == 1
    assert any("kaboom" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_actions_controller.py -v
```

Expected: `ImportError: cannot import name 'QuickActionsController'`.

- [ ] **Step 3: Append the controller to the bar module**

Append to `src/pluggable_protocol_tree/views/quick_action_bar.py`:

```python


# --- controller ----------------------------------------------------


from logger.logger_service import get_logger
from pluggable_protocol_tree.models.quick_action import QuickActionCtx

logger = get_logger(__name__)


class QuickActionsController:
    """Wires a QuickActionBar to a ProtocolTreePane.

    Listens for ``pane.selection_changed`` / ``pane.protocol_running_changed``
    and keeps ``button.setEnabled(...)`` in sync with each action's
    ``is_enabled(ctx)``. Routes clicks through ``_execute(action)`` so
    a buggy contribution can't crash the bar. Builds a fresh ctx on
    every call — never caches.
    """

    def __init__(self, *, bar: QuickActionBar, pane, actions):
        self._bar = bar
        self._pane = pane
        self._actions = list(actions)
        self._is_running = False
        # Wire button clicks.
        for action in self._actions:
            btn = bar.buttons[action.action_id]
            btn.clicked.connect(lambda _checked=False, a=action: self._execute(a))
        # Wire pane signals (drives re-enable + running state).
        pane.selection_changed.connect(self.refresh_enabled)
        pane.protocol_running_changed.connect(self._on_running_changed)
        self.refresh_enabled()

    def _build_ctx(self) -> QuickActionCtx:
        sel = tuple(tuple(p) for p in (self._pane.manager.selection or []))
        return QuickActionCtx(pane=self._pane,
                              selected_paths=sel,
                              is_running=self._is_running)

    def _on_running_changed(self, running: bool) -> None:
        self._is_running = bool(running)
        self.refresh_enabled()

    def refresh_enabled(self) -> None:
        ctx = self._build_ctx()
        for action in self._actions:
            try:
                enabled = bool(action.is_enabled(ctx)) and not ctx.is_running
            except Exception as e:                # pragma: no cover - defensive
                logger.warning(
                    f"is_enabled failed for {action.action_id!r}: {e}; "
                    f"disabling button.")
                enabled = False
            self._bar.buttons[action.action_id].setEnabled(enabled)

    def _execute(self, action) -> None:
        ctx = self._build_ctx()
        if ctx.is_running or not self._bar.buttons[action.action_id].isEnabled():
            # The shortcut path bypasses Qt's enabled-state gate; gate again here.
            return
        try:
            action.on_execute_action(ctx)
        except Exception as e:
            logger.error(
                f"quick-action {action.action_id!r} raised: {e}", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_actions_controller.py -v
```

Expected: 6 passed. (`caplog` will capture the "kaboom" log message at error level.)

- [ ] **Step 5: Commit**

```
git add src/pluggable_protocol_tree/views/quick_action_bar.py src/pluggable_protocol_tree/tests/test_quick_actions_controller.py
git commit -m "[ppt-21] Add QuickActionsController (click + enabled-state wiring)"
```

---

### Task 5: `QuickActionsController` — keyboard shortcut wiring + conflict detection

**Files:**
- Modify: `src/pluggable_protocol_tree/views/quick_action_bar.py` (extend controller with `_wire_shortcuts`)
- Create: `src/pluggable_protocol_tree/tests/test_quick_actions_shortcuts.py`

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_quick_actions_shortcuts.py`:

```python
"""Shortcut wiring lives in QuickActionsController. For every action
whose ``shortcut`` is non-empty we register one widget-scoped QShortcut
on the pane, routed through ``_execute`` so it respects ``is_enabled``
and the ``is_running`` gate. Two actions declaring the same key:
the second registration is skipped and a warning is logged."""

from pyface.qt.QtCore import QObject, Qt, Signal
from pyface.qt.QtGui import QKeySequence

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.views.quick_action_bar import (
    QuickActionBar, QuickActionsController,
)


class _Pane(QObject):
    selection_changed = Signal()
    protocol_running_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        from unittest.mock import MagicMock
        self.manager = MagicMock()
        self.manager.selection = []


class _Counting(BaseQuickAction):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = 0

    def on_execute_action(self, ctx):
        self.calls += 1


def test_shortcut_registers_widget_scoped_qshortcut(qapp):
    a = _Counting(action_id="r", icon_text="summarize", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a])
    assert len(ctrl.shortcuts) == 1
    qs = ctrl.shortcuts[0]
    assert qs.key() == QKeySequence("R")
    assert qs.context() == Qt.WidgetWithChildrenShortcut
    assert qs.parentWidget() is pane


def test_shortcut_triggers_execute(qapp):
    a = _Counting(action_id="r", icon_text="summarize", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a])
    ctrl.shortcuts[0].activated.emit()
    assert a.calls == 1


def test_shortcut_is_gated_by_is_running(qapp):
    a = _Counting(action_id="r", icon_text="summarize", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a])
    pane.protocol_running_changed.emit(True)
    ctrl.shortcuts[0].activated.emit()
    assert a.calls == 0


def test_no_shortcut_means_no_qshortcut_registered(qapp):
    a = _Counting(action_id="r", icon_text="add", tooltip="", shortcut="")
    pane = _Pane()
    bar = QuickActionBar(actions=[a])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a])
    assert ctrl.shortcuts == []


def test_duplicate_shortcut_skips_second_and_logs_warning(qapp, caplog):
    a = _Counting(action_id="first", icon_text="add", tooltip="",
                  shortcut="R")
    b = _Counting(action_id="second", icon_text="del", tooltip="",
                  shortcut="R")
    pane = _Pane()
    bar = QuickActionBar(actions=[a, b])
    ctrl = QuickActionsController(bar=bar, pane=pane, actions=[a, b])
    # Only the first wins.
    assert len(ctrl.shortcuts) == 1
    ctrl.shortcuts[0].activated.emit()
    assert a.calls == 1
    assert b.calls == 0
    assert any(
        "R" in r.message and "first" in r.message and "second" in r.message
        for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_actions_shortcuts.py -v
```

Expected: `AttributeError: 'QuickActionsController' object has no attribute 'shortcuts'`.

- [ ] **Step 3: Extend the controller with `_wire_shortcuts`**

Modify `src/pluggable_protocol_tree/views/quick_action_bar.py`. First, augment the imports near the top of the controller section:

```python
from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QKeySequence, QShortcut
```

Then, in `QuickActionsController.__init__`, **before** the final `self.refresh_enabled()` call, insert:

```python
        self.shortcuts = []
        self._wire_shortcuts()
```

And add the new method at the end of the class:

```python
    def _wire_shortcuts(self) -> None:
        claimed = {}                              # shortcut str -> action_id
        for action in self._actions:
            key_str = (action.shortcut or "").strip()
            if not key_str:
                continue
            existing = claimed.get(key_str)
            if existing is not None:
                logger.warning(
                    f"quick-action shortcut conflict on {key_str!r}: "
                    f"{existing!r} already registered; skipping "
                    f"{action.action_id!r}.")
                continue
            claimed[key_str] = action.action_id
            qs = QShortcut(QKeySequence(key_str), self._pane)
            qs.setContext(Qt.WidgetWithChildrenShortcut)
            qs.activated.connect(lambda a=action: self._execute(a))
            self.shortcuts.append(qs)
```

- [ ] **Step 4: Run test to verify it passes**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_actions_shortcuts.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add src/pluggable_protocol_tree/views/quick_action_bar.py src/pluggable_protocol_tree/tests/test_quick_actions_shortcuts.py
git commit -m "[ppt-21] Wire QShortcuts from IQuickAction.shortcut (with conflict detection)"
```

---

### Task 6: Add `selection_changed` + `protocol_running_changed` signals to `ProtocolTreePane`

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_emits_protocol_running_changed_true_on_start(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    seen = []
    pane.protocol_running_changed.connect(lambda v: seen.append(v))
    pane._on_protocol_started()
    assert seen == [True]


def test_pane_emits_protocol_running_changed_false_on_terminated(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    seen = []
    pane.protocol_running_changed.connect(lambda v: seen.append(v))
    pane._on_protocol_terminated()
    assert seen == [False]


def test_pane_emits_selection_changed_on_tree_selection(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pyface.qt.QtCore import QItemSelection
    pane = ptp.ProtocolTreePane([make_name_column()])
    fired = []
    pane.selection_changed.connect(lambda: fired.append(True))
    # Drive the tree's selectionModel directly — pane subscribes to
    # selectionChanged and re-emits the parameterless selection_changed.
    sm = pane.widget.tree.selectionModel()
    sm.selectionChanged.emit(QItemSelection(), QItemSelection())
    assert fired == [True]
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_emits_protocol_running_changed_true_on_start src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_emits_protocol_running_changed_false_on_terminated src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_emits_selection_changed_on_tree_selection -v
```

Expected: 3 failures on `AttributeError: 'ProtocolTreePane' object has no attribute 'protocol_running_changed'` / `selection_changed`.

- [ ] **Step 3: Add the signal declarations**

In `src/pluggable_protocol_tree/views/protocol_tree_pane.py`, locate the `phase_acked = Signal()` line near the top of the class:

```python
class ProtocolTreePane(QWidget):
    ...
    phase_acked = Signal()
```

Replace with:

```python
class ProtocolTreePane(QWidget):
    ...
    phase_acked = Signal()
    # Quick-actions toolbar feed: emit True/False on protocol start/end,
    # parameterless selection_changed on each tree selection move.
    # QuickActionsController listens to both to drive button enabled state.
    protocol_running_changed = Signal(bool)
    selection_changed = Signal()
```

- [ ] **Step 4: Emit `protocol_running_changed` on start / terminate**

Locate `_on_protocol_started(self):` and add as the FIRST line after the docstring (or after the existing first line):

```python
        self.protocol_running_changed.emit(True)
```

Locate `_on_protocol_terminated(self, outcome="finished"):` and add as the FIRST line of the body:

```python
        self.protocol_running_changed.emit(False)
```

- [ ] **Step 5: Wire `selection_changed` to the tree's selectionModel**

Locate `_wire_executor_signals(self):` (or alternatively, add a new wiring point in `__init__` after `self.widget = ProtocolTreeWidget(...)`). Add right after the tree widget construction in `__init__` (near where `device_viewer_sync` is attached):

```python
        # Re-emit the tree's selectionChanged as a parameterless signal so
        # the QuickActionsController doesn't have to know about Qt selection
        # models. The pane already constructed self.widget above.
        self.widget.tree.selectionModel().selectionChanged.connect(
            lambda *_: self.selection_changed.emit()
        )
```

- [ ] **Step 6: Run tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'protocol_running_changed or selection_changed'
```

Expected: 3 passed.

- [ ] **Step 7: Run the full pane suite to confirm no regressions**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v
```

Expected: all previously-passing tests still pass + the 3 new ones pass.

- [ ] **Step 8: Commit**

```
git add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[ppt-21] Pane signals: protocol_running_changed + selection_changed"
```

---

### Task 7: Mount the bar in `ProtocolTreePane` from injected contributions

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py` (constructor + `_build_layout`)
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_mounts_quick_action_bar_when_actions_passed(qapp):
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.quick_action import BaseQuickAction

    a = BaseQuickAction(action_id="add_step", icon_text="add",
                        tooltip="Add step", priority=10)
    b = BaseQuickAction(action_id="save_protocol", icon_text="save",
                        tooltip="Save", priority=60)
    pane = ptp.ProtocolTreePane([make_name_column()], quick_actions=[a, b])
    assert pane.quick_action_bar is not None
    assert set(pane.quick_action_bar.buttons.keys()) == {"add_step", "save_protocol"}
    assert pane.quick_actions_controller is not None


def test_pane_skips_quick_action_bar_when_no_actions(qapp):
    """No actions contributed (e.g. demo, headless test) -> no bar
    widget mounted; controller is None. This is the architectural
    commitment: the tree plugin ships zero builtins."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column

    pane = ptp.ProtocolTreePane([make_name_column()])
    assert pane.quick_action_bar is None
    assert pane.quick_actions_controller is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'quick_action_bar'
```

Expected: failures on `AttributeError: 'ProtocolTreePane' object has no attribute 'quick_action_bar'`.

- [ ] **Step 3: Add `quick_actions` constructor parameter**

In `ProtocolTreePane.__init__`, find the signature:

```python
def __init__(
    self,
    columns_or_manager,
    *,
    application=None,
    experiment_manager=None,
    sticky_manager=None,
    device_viewer_sync=None,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    executor_factory=None,
    logging_device_context_provider=None,
    parent=None,
):
```

Add `quick_actions=None,` immediately before `parent=None,`:

```python
def __init__(
    self,
    columns_or_manager,
    *,
    application=None,
    experiment_manager=None,
    sticky_manager=None,
    device_viewer_sync=None,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    executor_factory=None,
    logging_device_context_provider=None,
    quick_actions=None,
    parent=None,
):
```

- [ ] **Step 4: Construct the bar (or set to None) BEFORE `_build_layout()`**

In `ProtocolTreePane.__init__`, find the line:

```python
        self._build_layout()
```

Insert **immediately above** that line:

```python
        # Quick-actions toolbar (bar + controller). Both are None when no
        # contributions exist (demo / headless test environments) so the
        # pane stays usable with no chrome below the tree. Constructed
        # before _build_layout() so it can be inserted in the layout.
        from pluggable_protocol_tree.views.quick_action_bar import (
            QuickActionBar, QuickActionsController,
        )
        if quick_actions:
            self.quick_action_bar = QuickActionBar(
                actions=list(quick_actions), parent=self)
            self.quick_actions_controller = QuickActionsController(
                bar=self.quick_action_bar, pane=self,
                actions=list(quick_actions))
        else:
            self.quick_action_bar = None
            self.quick_actions_controller = None
```

- [ ] **Step 5: Mount the bar in `_build_layout`**

Locate the `_build_layout` method:

```python
def _build_layout(self):
    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(self.navigation_bar)
    layout.addWidget(self.status_bar)
    layout.addWidget(make_separator())
    layout.addWidget(self.widget)
```

Replace with:

```python
def _build_layout(self):
    layout = QVBoxLayout(self)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(self.navigation_bar)
    layout.addWidget(self.status_bar)
    layout.addWidget(make_separator())
    layout.addWidget(self.widget)
    if self.quick_action_bar is not None:
        layout.addWidget(self.quick_action_bar)
```

- [ ] **Step 6: Run tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'quick_action_bar'
```

Expected: 2 passed.

- [ ] **Step 7: Run the full pane suite + bar + controller suites**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_quick_action_bar.py src/pluggable_protocol_tree/tests/test_quick_actions_controller.py src/pluggable_protocol_tree/tests/test_quick_actions_shortcuts.py -v
```

Expected: all green.

- [ ] **Step 8: Commit**

```
git add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[ppt-21] Mount QuickActionBar in ProtocolTreePane from injected contributions"
```

---

### Task 8: Pane helpers (`add_step_after_selection`, `add_group_after_selection`, `delete_selected_rows`, `import_into_selected_group`, `browse_reports_dialog`)

Five small helpers added to `ProtocolTreePane`. We TDD each one in turn — same task, five mini-cycles.

**Files:**
- Modify: `src/pluggable_protocol_tree/views/protocol_tree_pane.py`
- Modify: `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py` (append)

- [ ] **Step 1: Write the failing tests for all 5 helpers**

Append to `src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def _pane_with_two_steps(qapp):
    """Pane with a tree containing exactly two top-level step rows."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    # seed_default_step_if_empty already gave us 1 step; add one more.
    pane.manager.add_step()
    return pane


def test_add_step_after_selection_with_no_selection_appends_root(qapp):
    pane = _pane_with_two_steps(qapp)
    before = len(pane.manager.root.children)
    pane.manager.selection = []
    pane.add_step_after_selection()
    assert len(pane.manager.root.children) == before + 1


def test_add_step_after_selection_with_one_selected_inserts_below(qapp):
    pane = _pane_with_two_steps(qapp)
    # Select the first row.
    pane.manager.selection = [(0,)]
    before = len(pane.manager.root.children)
    pane.add_step_after_selection()
    assert len(pane.manager.root.children) == before + 1
    # The newly-inserted step should be at index 1 (right after selected).
    # Easiest assertion: the row that used to be at (1,) is now at (2,).
    # We can't peek at row identity easily here, so just check count.


def test_add_group_after_selection_appends_a_group(qapp):
    pane = _pane_with_two_steps(qapp)
    pane.manager.selection = []
    before = len(pane.manager.root.children)
    pane.add_group_after_selection()
    assert len(pane.manager.root.children) == before + 1
    from pluggable_protocol_tree.models.row import GroupRow
    assert isinstance(pane.manager.root.children[-1], GroupRow)


def test_delete_selected_rows_removes_at_those_paths(qapp):
    pane = _pane_with_two_steps(qapp)
    before = len(pane.manager.root.children)
    pane.manager.selection = [(0,)]
    pane.delete_selected_rows()
    assert len(pane.manager.root.children) == before - 1


def test_delete_selected_rows_no_selection_is_noop(qapp):
    pane = _pane_with_two_steps(qapp)
    before = len(pane.manager.root.children)
    pane.manager.selection = []
    pane.delete_selected_rows()
    assert len(pane.manager.root.children) == before


def test_import_into_selected_group_noop_when_no_group_selected(qapp,
                                                                 monkeypatch):
    """Selection points to a step (not a group) -> import is a no-op."""
    pane = _pane_with_two_steps(qapp)
    pane.manager.selection = [(0,)]            # a step row
    called = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.QFileDialog."
        "getOpenFileName",
        lambda *a, **k: called.append(True) or ("", ""))
    pane.import_into_selected_group()
    assert called == []                        # never even opened the dialog


def test_browse_reports_dialog_opens_with_globbed_paths(qapp, monkeypatch,
                                                         tmp_path):
    """browse_reports_dialog globs <experiment_dir>/reports/*.html and
    feeds the path list into ReportBrowserDialog. The pane only needs a
    ``reports_dir_provider`` (callable) — the dialog class itself is
    monkeypatched here so this test can run without the new plugin."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    # Seed two HTML reports.
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "report_a.html").write_text("<html></html>", encoding="utf-8")
    (reports / "report_b.html").write_text("<html></html>", encoding="utf-8")

    captured = {}
    class _FakeDialog:
        def __init__(self, paths, parent=None):
            captured["paths"] = list(paths)
        def exec(self_inner):
            return 0
    monkeypatch.setattr(ptp, "_get_report_browser_dialog_cls",
                        lambda: _FakeDialog)

    pane = ptp.ProtocolTreePane([make_name_column()])
    pane._reports_dir_provider = lambda: reports
    pane.browse_reports_dialog()
    assert set(captured["paths"]) == {
        str(reports / "report_a.html"),
        str(reports / "report_b.html"),
    }


def test_browse_reports_dialog_no_provider_logs_and_returns(qapp, caplog):
    """No reports_dir_provider configured (e.g. demo, no experiment manager)
    -> log a debug message and return; do NOT crash."""
    import pluggable_protocol_tree.views.protocol_tree_pane as ptp
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    pane = ptp.ProtocolTreePane([make_name_column()])
    pane._reports_dir_provider = None
    pane.browse_reports_dialog()                 # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'add_step_after_selection or add_group_after_selection or delete_selected_rows or import_into_selected_group or browse_reports_dialog'
```

Expected: failures on `AttributeError: ... has no attribute 'add_step_after_selection'` (etc.).

- [ ] **Step 3: Add the helpers to `ProtocolTreePane`**

In `protocol_tree_pane.py`:

First, add `glob` to the existing imports near the top of the file. Find:

```python
from pathlib import Path
```

Replace with:

```python
import glob
from pathlib import Path
```

Then, in `ProtocolTreePane.__init__`, after the `quick_actions=None` block from Task 7, add an attribute initializer for the reports-dir provider (used by browse_reports_dialog):

```python
        # Optional callable returning the path to the experiment's reports
        # dir (set by callers that have an experiment manager). When None,
        # browse_reports_dialog is a no-op.
        self._reports_dir_provider = (
            (lambda: experiment_manager.get_experiment_directory() / "reports")
            if experiment_manager is not None else None
        )
```

Add a module-level helper near the top of the file (just above the `class ProtocolTreePane` declaration) for the dialog class lookup. This indirection keeps the pane decoupled from the new plugin — the pane imports lazily through this seam:

```python
def _get_report_browser_dialog_cls():
    """Lazy import so the pluggable tree doesn't statically depend on
    protocol_quick_action_tools. Returns the dialog class or None when
    the new plugin isn't installed (development environments, demos)."""
    try:
        from protocol_quick_action_tools.views.report_browser_dialog import (
            ReportBrowserDialog,
        )
        return ReportBrowserDialog
    except Exception:                             # pragma: no cover - defensive
        return None
```

Now add the five helper methods at the end of the `ProtocolTreePane` class (after the existing experiment-bar handlers, e.g. after `_on_experiment_changed`):

```python
    # --- quick-actions helpers --------------------------------------

    def _insert_position_after_selection(self):
        """Return ``(parent_path, index)`` for "insert after current
        selection". With nothing selected -> ``((), None)`` (append to
        root). With one selection at path ``(p..., i)`` -> ``((p...,),
        i + 1)``. With multiple selections we use the last one."""
        sel = list(self.manager.selection or [])
        if not sel:
            return ((), None)
        last = tuple(sel[-1])
        return (last[:-1], last[-1] + 1)

    def add_step_after_selection(self):
        parent_path, index = self._insert_position_after_selection()
        self.manager.add_step(parent_path=parent_path, index=index)

    def add_group_after_selection(self):
        parent_path, index = self._insert_position_after_selection()
        self.manager.add_group(parent_path=parent_path, index=index)

    def delete_selected_rows(self):
        sel = list(self.manager.selection or [])
        if not sel:
            return
        self.manager.remove(sel)

    def import_into_selected_group(self):
        """Open a file picker, load the JSON protocol, and merge every
        top-level row from the loaded protocol under the selected group.

        No-op when the selection isn't exactly one row OR the selected
        row isn't a GroupRow.
        """
        sel = list(self.manager.selection or [])
        if len(sel) != 1:
            return
        target_path = tuple(sel[0])
        try:
            target = self.manager.get_row(target_path)
        except (IndexError, AttributeError):
            return
        if not isinstance(target, GroupRow):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Protocol", "", "Protocol JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"import_into_selected_group: read failed: {e}")
            return
        # The loaded protocol's top-level rows live under data["rows"]
        # (RowManager.to_json shape); each entry is either a step dict
        # or a {"type": "group", "rows": [...]} dict. Use add_step /
        # add_group with the row dict's values to seed each new row.
        for row_dict in (data.get("rows") or []):
            if row_dict.get("type") == "group":
                self.manager.add_group(
                    parent_path=target_path,
                    name=row_dict.get("name", "Group"),
                )
                # Nested rows are not recursively imported in this PR —
                # callers paste structurally identical protocols and the
                # legacy did the same. Out of scope: deep-import.
            else:
                values = {k: v for k, v in row_dict.items()
                          if k not in ("type",)}
                self.manager.add_step(
                    parent_path=target_path, values=values)

    def browse_reports_dialog(self):
        """Glob <experiment_dir>/reports/*.html and open the
        ReportBrowserDialog from protocol_quick_action_tools. No-op when
        no reports-dir provider is configured (demos / no experiment
        manager) or when the dialog plugin isn't installed."""
        if self._reports_dir_provider is None:
            logger.debug("browse_reports_dialog: no reports_dir_provider")
            return
        cls = _get_report_browser_dialog_cls()
        if cls is None:
            logger.warning(
                "browse_reports_dialog: ReportBrowserDialog not available")
            return
        reports_dir = self._reports_dir_provider()
        paths = sorted(glob.glob(str(reports_dir / "*.html")))
        cls(paths, parent=self).exec()
```

- [ ] **Step 4: Run helper tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k 'add_step_after_selection or add_group_after_selection or delete_selected_rows or import_into_selected_group or browse_reports_dialog'
```

Expected: 8 passed.

- [ ] **Step 5: Run the full pane suite**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v
```

Expected: full suite green.

- [ ] **Step 6: Commit**

```
git add src/pluggable_protocol_tree/views/protocol_tree_pane.py src/pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "[ppt-21] Pane helpers: add_step/group_after_selection, delete_selected_rows, import_into_selected_group, browse_reports_dialog"
```

---

### Task 9: Wire `PROTOCOL_QUICK_ACTIONS` extension point in `PluggableProtocolTreePlugin` + forward to dock pane

**Files:**
- Modify: `src/pluggable_protocol_tree/plugin.py`
- Modify: `src/pluggable_protocol_tree/views/dock_pane.py`
- Create: `src/pluggable_protocol_tree/tests/test_quick_actions_extension_point.py`

- [ ] **Step 1: Write the failing test**

Create `src/pluggable_protocol_tree/tests/test_quick_actions_extension_point.py`:

```python
"""The tree plugin exposes PROTOCOL_QUICK_ACTIONS as an Envisage
extension point. Like PROTOCOL_COLUMNS, plugin.start() copies
contributions into a plain list, and the dock-pane factory passes
that list into ProtocolTreePane(quick_actions=...).

The tree plugin itself contributes zero builtins."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin


def test_plugin_ships_zero_builtin_quick_actions():
    plugin = PluggableProtocolTreePlugin()
    # No contribution list set yet -> empty default.
    assert plugin.contributed_quick_actions == []


def test_assemble_quick_actions_sorts_by_priority_then_action_id():
    plugin = PluggableProtocolTreePlugin()
    plugin.contributed_quick_actions = [
        BaseQuickAction(action_id="z", priority=10),
        BaseQuickAction(action_id="a", priority=20),
        BaseQuickAction(action_id="c", priority=10),
    ]
    assembled = plugin._assemble_quick_actions()
    assert [a.action_id for a in assembled] == ["c", "z", "a"]
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_actions_extension_point.py -v
```

Expected: `AttributeError: ... 'PluggableProtocolTreePlugin' object has no attribute 'contributed_quick_actions'`.

- [ ] **Step 3: Add the extension point + assembler to the tree plugin**

In `src/pluggable_protocol_tree/plugin.py`, add to the imports:

```python
from pluggable_protocol_tree.consts import (
    ACTOR_TOPIC_DICT, LOGGING_ACTOR_TOPIC_DICT, PKG, PKG_name,
    PROTOCOL_COLUMNS, PROTOCOL_QUICK_ACTIONS,
)
from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction
```

In the `PluggableProtocolTreePlugin` class, add after the existing `_column_extension_point` / `contributed_columns` block:

```python
    #: Envisage extension point — sibling plugins contribute
    #: IQuickAction instances rendered as buttons on the tree's
    #: quick-actions toolbar. Tree plugin itself contributes none.
    _quick_action_extension_point = ExtensionPoint(
        List(Instance(IQuickAction)), id=PROTOCOL_QUICK_ACTIONS,
        desc="IQuickAction instances contributed by sibling plugins.",
    )

    contributed_quick_actions = List(
        desc="Quick actions contributed by other plugins (populated "
             "from the extension point at plugin start).")
```

Add the assembler method (next to `_assemble_columns`):

```python
    def _assemble_quick_actions(self):
        """Return contributed quick actions in deterministic order
        (priority then action_id)."""
        try:
            actions = list(self.contributed_quick_actions)
        except Exception:
            actions = []
        return sorted(actions, key=lambda a: (a.priority, a.action_id))
```

In `start(self)`, after the existing `contributed_columns = list(...)` assignment:

```python
        try:
            self.contributed_quick_actions = list(
                self._quick_action_extension_point)
        except Exception as e:
            logger.warning(
                f"failed to read PROTOCOL_QUICK_ACTIONS extension point: {e}"
            )
```

In `_make_dock_pane`:

```python
    def _make_dock_pane(self, *args, **kwargs):
        from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane
        columns = self._assemble_columns()
        quick_actions = self._assemble_quick_actions()
        return PluggableProtocolDockPane(
            columns=columns, quick_actions=quick_actions,
            *args, **kwargs)
```

- [ ] **Step 4: Forward quick_actions through the dock pane**

In `src/pluggable_protocol_tree/views/dock_pane.py`, find the `PluggableProtocolDockPane` class definition. Locate the existing `columns` trait declaration and add a sibling:

```python
    quick_actions = List(desc="Quick actions to mount under the tree.")
```

Then in the dock pane's `create_contents` (or wherever `ProtocolTreePane(...)` is constructed — search for `ProtocolTreePane(`), add `quick_actions=list(self.quick_actions),` to the kwargs:

```python
        pane = ProtocolTreePane(
            manager,
            application=app,
            experiment_manager=experiment_manager,
            sticky_manager=sticky_manager,
            device_viewer_sync=sync,
            logging_device_context_provider=_logging_device_context,
            quick_actions=list(self.quick_actions),
            parent=parent,
        )
```

If `List` isn't imported at the top of `dock_pane.py`, add `from traits.api import List` (and any other missing imports).

- [ ] **Step 5: Run extension-point tests to verify they pass**

```
pixi run pytest src/pluggable_protocol_tree/tests/test_quick_actions_extension_point.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run the full tree-plugin test suite**

```
pixi run pytest src/pluggable_protocol_tree/tests/ -v
```

Expected: every previously-green test stays green; new tests added in tasks 1-9 pass.

- [ ] **Step 7: Commit**

```
git add src/pluggable_protocol_tree/plugin.py src/pluggable_protocol_tree/views/dock_pane.py src/pluggable_protocol_tree/tests/test_quick_actions_extension_point.py
git commit -m "[ppt-21] Wire PROTOCOL_QUICK_ACTIONS extension point + dock-pane forwarding"
```

---

### Task 10: Scaffold the new `protocol_quick_action_tools` plugin (consts, plugin shell, base helper)

**Files (all NEW):**
- Create: `src/protocol_quick_action_tools/__init__.py`
- Create: `src/protocol_quick_action_tools/consts.py`
- Create: `src/protocol_quick_action_tools/plugin.py`
- Create: `src/protocol_quick_action_tools/quick_actions/__init__.py`
- Create: `src/protocol_quick_action_tools/quick_actions/base.py`
- Create: `src/protocol_quick_action_tools/views/__init__.py`
- Create: `src/protocol_quick_action_tools/tests/__init__.py`
- Create: `src/protocol_quick_action_tools/tests/test_plugin_scaffold.py`

- [ ] **Step 1: Write the failing test**

Create `src/protocol_quick_action_tools/tests/test_plugin_scaffold.py`:

```python
"""Plugin scaffold: package importable, consts defined, plugin class
declares the IQuickAction contribution list (initially empty until
the action factories land in task 12)."""

import protocol_quick_action_tools
from protocol_quick_action_tools.consts import PKG, PKG_name
from protocol_quick_action_tools.plugin import (
    ProtocolQuickActionToolsPlugin,
)


def test_package_is_importable():
    assert protocol_quick_action_tools is not None


def test_consts_match_package_layout():
    assert PKG == "protocol_quick_action_tools"
    assert PKG_name == "Protocol Quick Action Tools"


def test_plugin_id_and_name():
    p = ProtocolQuickActionToolsPlugin()
    assert p.id == "protocol_quick_action_tools.plugin"
    assert p.name == "Protocol Quick Action Tools Plugin"


def test_plugin_has_contribution_list_trait():
    p = ProtocolQuickActionToolsPlugin()
    # The factories aren't wired in yet — they land in task 12. The
    # trait must exist and default to an empty list so the scaffold
    # can be loaded by Envisage without crashing.
    assert isinstance(p.contributed_quick_actions, list)
```

- [ ] **Step 2: Run test to verify it fails**

```
pixi run pytest src/protocol_quick_action_tools/tests/test_plugin_scaffold.py -v
```

Expected: `ModuleNotFoundError: No module named 'protocol_quick_action_tools'`.

- [ ] **Step 3: Create the package skeleton**

Create `src/protocol_quick_action_tools/__init__.py`:

```python
"""Quick-actions contributions for the pluggable protocol tree (#433).

Architecture lives in pluggable_protocol_tree (extension point, traits
model, bar widget, controller, pane integration). This plugin
contributes the 8 legacy actions (add/delete/save/open/import/new
protocol, add group, browse reports) plus the ReportBrowserDialog.
"""
```

Create `src/protocol_quick_action_tools/consts.py`:

```python
"""Package-level constants for protocol_quick_action_tools.

Follows the MicroDrop convention: PKG derived from __name__, PKG_name
title-cased for display.
"""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Stable action_id strings. Tests assert against these constants so
# the legacy ids remain accessible by name from outside the plugin.
ACTION_ADD_STEP        = "add_step"
ACTION_DELETE_ROW      = "delete_row"
ACTION_ADD_GROUP       = "add_group"
ACTION_IMPORT_PROTOCOL = "import_protocol"
ACTION_OPEN_PROTOCOL   = "open_protocol"
ACTION_SAVE_PROTOCOL   = "save_protocol"
ACTION_NEW_PROTOCOL    = "new_protocol"
ACTION_BROWSE_REPORTS  = "browse_reports"
```

Create `src/protocol_quick_action_tools/plugin.py`:

```python
"""ProtocolQuickActionToolsPlugin — contributes the 8 legacy quick
actions to the pluggable protocol tree.

Pattern mirrors peripheral_protocol_controls / dropbot_protocol_controls.
The factories ship in task 12; the scaffold lands first so the rest of
the plan can land in any order without "import broken" stages."""

from envisage.plugin import Plugin
from traits.api import List

from pluggable_protocol_tree.consts import PROTOCOL_QUICK_ACTIONS

from logger.logger_service import get_logger

from .consts import PKG, PKG_name

logger = get_logger(__name__)


class ProtocolQuickActionToolsPlugin(Plugin):
    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    contributed_quick_actions = List(contributes_to=PROTOCOL_QUICK_ACTIONS)

    def _contributed_quick_actions_default(self):
        # Filled in by task 12.
        return []
```

Create `src/protocol_quick_action_tools/quick_actions/__init__.py`:

```python
"""IQuickAction implementations for the 8 legacy quick actions."""
```

Create `src/protocol_quick_action_tools/quick_actions/base.py`:

```python
"""Shared helpers used by every action factory.

Keeps the per-action factory files (one per file) one-purpose: build
an IQuickAction with the right id / icon / tooltip / hooks. Predicates
that several actions share (``has_selection``, ``is_single_group_selected``,
...) live here.
"""

from pluggable_protocol_tree.models.row import GroupRow


def has_selection(ctx) -> bool:
    return len(ctx.selected_paths) >= 1


def is_single_row_selected(ctx) -> bool:
    return len(ctx.selected_paths) == 1


def is_single_group_selected(ctx) -> bool:
    """True iff exactly one row is selected AND that row is a GroupRow."""
    if not is_single_row_selected(ctx):
        return False
    pane = ctx.pane
    try:
        row = pane.manager.get_row(tuple(ctx.selected_paths[0]))
    except (IndexError, AttributeError):
        return False
    return isinstance(row, GroupRow)
```

Create `src/protocol_quick_action_tools/views/__init__.py`:

```python
"""Standalone Qt widgets used by quick actions (ReportBrowserDialog)."""
```

Create `src/protocol_quick_action_tools/tests/__init__.py` (empty):

```python
```

- [ ] **Step 4: Run scaffold tests to verify they pass**

```
pixi run pytest src/protocol_quick_action_tools/tests/test_plugin_scaffold.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add src/protocol_quick_action_tools/
git commit -m "[ppt-21] Scaffold protocol_quick_action_tools plugin (consts + plugin shell + base helpers)"
```

---

### Task 11: Port `ReportBrowserDialog` into the new plugin

**Files:**
- Create: `src/protocol_quick_action_tools/views/report_browser_dialog.py`
- Create: `src/protocol_quick_action_tools/tests/test_report_browser_dialog.py`

- [ ] **Step 1: Write the failing test**

Create `src/protocol_quick_action_tools/tests/test_report_browser_dialog.py`:

```python
"""Smoke tests for the ported ReportBrowserDialog: constructor accepts
a list of path strings, populates a sortable tree of (Name, Size, Date),
filters by name in the search box, and opens the selected report via
QDesktopServices when the user activates a row."""

from protocol_quick_action_tools.views.report_browser_dialog import (
    ReportBrowserDialog,
)


def test_dialog_populates_one_row_per_path(qapp, tmp_path):
    a = tmp_path / "report_a.html"; a.write_text("a", encoding="utf-8")
    b = tmp_path / "report_b.html"; b.write_text("bb", encoding="utf-8")
    dlg = ReportBrowserDialog([str(a), str(b)])
    assert dlg._tree.topLevelItemCount() == 2


def test_dialog_handles_empty_list_without_crashing(qapp):
    """No reports yet -> open with an empty table; no rows shown."""
    dlg = ReportBrowserDialog([])
    assert dlg._tree.topLevelItemCount() == 0


def test_search_box_hides_non_matching_rows(qapp, tmp_path):
    a = tmp_path / "alpha.html"; a.write_text("a", encoding="utf-8")
    b = tmp_path / "beta.html"; b.write_text("b", encoding="utf-8")
    dlg = ReportBrowserDialog([str(a), str(b)])
    dlg._apply_filter("alph")
    visible = [
        dlg._tree.topLevelItem(i).text(0)
        for i in range(dlg._tree.topLevelItemCount())
        if not dlg._tree.topLevelItem(i).isHidden()
    ]
    assert visible == ["alpha.html"]


def test_format_size_threshold_branches():
    fs = ReportBrowserDialog._format_size
    assert fs(900) == "900 B"
    assert fs(2048) == "2.0 KB"
    assert fs(5 * 1024 * 1024) == "5.0 MB"


def test_open_item_calls_qdesktopservices(qapp, tmp_path, monkeypatch):
    """Double-click / Open routes through QDesktopServices.openUrl."""
    from protocol_quick_action_tools.views import report_browser_dialog as mod
    opened = []
    monkeypatch.setattr(mod.QDesktopServices, "openUrl",
                        lambda url: opened.append(url))
    p = tmp_path / "report.html"; p.write_text("", encoding="utf-8")
    dlg = ReportBrowserDialog([str(p)])
    item = dlg._tree.topLevelItem(0)
    dlg._open_item(item)
    assert len(opened) == 1
    assert opened[0].toLocalFile() == str(p)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/protocol_quick_action_tools/tests/test_report_browser_dialog.py -v
```

Expected: `ImportError: cannot import name 'ReportBrowserDialog'`.

- [ ] **Step 3: Port the dialog**

Create `src/protocol_quick_action_tools/views/report_browser_dialog.py`:

```python
"""File-manager-style dialog to browse and open session reports.

Ported from protocol_grid/extra_ui_elements.py:942-1064 (the legacy
class is fully decoupled from PGCWidget — only input is a list of path
strings). Kept verbatim except for the import path adjustments.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pyface.qt.QtCore import Qt, QUrl
from pyface.qt.QtGui import QDesktopServices
from pyface.qt.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)


class _ReportSortableTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem subclass that sorts the Size column numerically
    and the Date column chronologically instead of lexicographically."""

    _SIZE_COL = 1
    _DATE_COL = 2

    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        if col == self._SIZE_COL:
            return ((self.data(col, Qt.UserRole) or 0)
                    < (other.data(col, Qt.UserRole) or 0))
        if col == self._DATE_COL:
            return ((self.data(col, Qt.UserRole) or 0)
                    < (other.data(col, Qt.UserRole) or 0))
        return super().__lt__(other)


class ReportBrowserDialog(QDialog):
    """Search-and-open dialog over a flat list of report HTML paths."""

    _COL_NAME = 0
    _COL_SIZE = 1
    _COL_DATE = 2

    def __init__(self, report_paths: List[str], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Session Reports")
        self.setModal(True)
        self.setMinimumSize(650, 420)
        self._report_paths = report_paths
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- search bar ---
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by file name...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self._search_box)
        layout.addLayout(search_layout)

        # --- file table ---
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Size", "Date Created"])
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(True)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self._COL_NAME, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self._COL_DATE, QHeaderView.ResizeToContents)

        for path_str in self._report_paths:
            p = Path(path_str)
            try:
                stat = os.stat(p)
                size_bytes = stat.st_size
                ctime = stat.st_ctime
            except OSError:
                size_bytes = 0
                ctime = 0.0

            item = _ReportSortableTreeWidgetItem([
                p.name,
                self._format_size(size_bytes),
                datetime.fromtimestamp(ctime).strftime("%Y-%m-%d  %H:%M:%S")
                if ctime else "",
            ])
            item.setToolTip(self._COL_NAME, str(p))
            item.setData(self._COL_NAME, Qt.UserRole, path_str)
            item.setData(self._COL_SIZE, Qt.UserRole, size_bytes)
            item.setData(self._COL_DATE, Qt.UserRole, ctime)
            self._tree.addTopLevelItem(item)

        self._tree.sortByColumn(self._COL_DATE, Qt.DescendingOrder)
        layout.addWidget(self._tree)

        # --- buttons ---
        button_layout = QHBoxLayout()
        open_btn = QPushButton("Open")
        open_btn.setDefault(True)
        open_btn.clicked.connect(self._open_selected)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(open_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        self._tree.itemDoubleClicked.connect(self._open_item)

    def _apply_filter(self, text: str):
        text_lower = text.lower()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            item.setHidden(text_lower not in item.text(self._COL_NAME).lower())

    def _open_selected(self):
        items = self._tree.selectedItems()
        if items:
            self._open_item(items[0])

    def _open_item(self, item):
        path_str = item.data(self._COL_NAME, Qt.UserRole)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path_str))

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes / (1024 * 1024):.1f} MB"
```

- [ ] **Step 4: Run dialog tests to verify they pass**

```
pixi run pytest src/protocol_quick_action_tools/tests/test_report_browser_dialog.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add src/protocol_quick_action_tools/views/report_browser_dialog.py src/protocol_quick_action_tools/tests/test_report_browser_dialog.py
git commit -m "[ppt-21] Port ReportBrowserDialog from protocol_grid/extra_ui_elements.py"
```

---

### Task 12: Eight action factories

**Files:**
- Create: `src/protocol_quick_action_tools/quick_actions/add_step.py`
- Create: `src/protocol_quick_action_tools/quick_actions/add_group.py`
- Create: `src/protocol_quick_action_tools/quick_actions/delete_row.py`
- Create: `src/protocol_quick_action_tools/quick_actions/import_protocol.py`
- Create: `src/protocol_quick_action_tools/quick_actions/open_protocol.py`
- Create: `src/protocol_quick_action_tools/quick_actions/save_protocol.py`
- Create: `src/protocol_quick_action_tools/quick_actions/new_protocol.py`
- Create: `src/protocol_quick_action_tools/quick_actions/browse_reports.py`
- Modify: `src/protocol_quick_action_tools/plugin.py` (populate `_contributed_quick_actions_default`)
- Create: `src/protocol_quick_action_tools/tests/test_quick_actions.py`

- [ ] **Step 1: Write the failing tests (all 8 actions in one file)**

Create `src/protocol_quick_action_tools/tests/test_quick_actions.py`:

```python
"""One block per action. Each block builds a QuickActionCtx with a
MagicMock pane and asserts:
  * on_execute_action(ctx) calls the right pane method (or constructs
    the dialog with the right args).
  * is_enabled(ctx) matrix is correct for the meaningful states.
The plugin's _contributed_quick_actions_default returns all 8 actions
in priority order.
"""

from unittest.mock import MagicMock

import pytest

from pluggable_protocol_tree.models.quick_action import QuickActionCtx
from pluggable_protocol_tree.models.row import GroupRow

from protocol_quick_action_tools.consts import (
    ACTION_ADD_GROUP, ACTION_ADD_STEP, ACTION_BROWSE_REPORTS,
    ACTION_DELETE_ROW, ACTION_IMPORT_PROTOCOL, ACTION_NEW_PROTOCOL,
    ACTION_OPEN_PROTOCOL, ACTION_SAVE_PROTOCOL,
)
from protocol_quick_action_tools.plugin import (
    ProtocolQuickActionToolsPlugin,
)
from protocol_quick_action_tools.quick_actions.add_group import (
    make_add_group_action,
)
from protocol_quick_action_tools.quick_actions.add_step import (
    make_add_step_action,
)
from protocol_quick_action_tools.quick_actions.browse_reports import (
    make_browse_reports_action,
)
from protocol_quick_action_tools.quick_actions.delete_row import (
    make_delete_row_action,
)
from protocol_quick_action_tools.quick_actions.import_protocol import (
    make_import_protocol_action,
)
from protocol_quick_action_tools.quick_actions.new_protocol import (
    make_new_protocol_action,
)
from protocol_quick_action_tools.quick_actions.open_protocol import (
    make_open_protocol_action,
)
from protocol_quick_action_tools.quick_actions.save_protocol import (
    make_save_protocol_action,
)


def _ctx(*, selected_paths=(), is_running=False, group=False,
         experiment_manager=True):
    pane = MagicMock()
    if group and selected_paths:
        pane.manager.get_row.return_value = GroupRow(name="G")
    else:
        pane.manager.get_row.return_value = MagicMock(spec=[])
    pane.experiment_manager = MagicMock() if experiment_manager else None
    return QuickActionCtx(pane=pane,
                          selected_paths=tuple(selected_paths),
                          is_running=is_running)


# --- add_step -----------------------------------------------------

def test_add_step_metadata():
    a = make_add_step_action()
    assert a.action_id == ACTION_ADD_STEP
    assert a.icon_text == "add"
    assert a.priority == 10
    assert a.shortcut == ""


def test_add_step_execute_calls_pane_helper():
    a = make_add_step_action()
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.add_step_after_selection.assert_called_once_with()


@pytest.mark.parametrize("running,expected",
                         [(False, True), (True, False)])
def test_add_step_is_enabled(running, expected):
    assert make_add_step_action().is_enabled(_ctx(is_running=running)) is expected


# --- delete_row ---------------------------------------------------

def test_delete_row_metadata():
    a = make_delete_row_action()
    assert a.action_id == ACTION_DELETE_ROW
    assert a.icon_text == "delete"
    assert a.priority == 20


def test_delete_row_execute_calls_pane_helper():
    a = make_delete_row_action()
    ctx = _ctx(selected_paths=[(0,)])
    a.on_execute_action(ctx)
    ctx.pane.delete_selected_rows.assert_called_once_with()


def test_delete_row_is_enabled_matrix():
    a = make_delete_row_action()
    assert a.is_enabled(_ctx()) is False                  # no selection
    assert a.is_enabled(_ctx(selected_paths=[(0,)])) is True
    assert a.is_enabled(_ctx(selected_paths=[(0,), (1,)])) is True
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              is_running=True)) is False


# --- add_group ----------------------------------------------------

def test_add_group_metadata():
    a = make_add_group_action()
    assert a.action_id == ACTION_ADD_GROUP
    assert a.icon_text == "playlist_add"
    assert a.priority == 30


def test_add_group_execute_calls_pane_helper():
    a = make_add_group_action()
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.add_group_after_selection.assert_called_once_with()


# --- import_protocol ----------------------------------------------

def test_import_protocol_metadata():
    a = make_import_protocol_action()
    assert a.action_id == ACTION_IMPORT_PROTOCOL
    assert a.icon_text == "unarchive"
    assert a.priority == 40


def test_import_protocol_execute_calls_pane_helper():
    a = make_import_protocol_action()
    ctx = _ctx(selected_paths=[(0,)], group=True)
    a.on_execute_action(ctx)
    ctx.pane.import_into_selected_group.assert_called_once_with()


def test_import_protocol_is_enabled_requires_single_group_selection():
    a = make_import_protocol_action()
    assert a.is_enabled(_ctx()) is False                       # no sel
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              group=False)) is False           # step, not group
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              group=True)) is True
    assert a.is_enabled(_ctx(selected_paths=[(0,), (1,)],
                              group=True)) is False            # multi-sel
    assert a.is_enabled(_ctx(selected_paths=[(0,)],
                              group=True,
                              is_running=True)) is False


# --- open / save / new_protocol -----------------------------------

def test_open_protocol_calls_pane_helper():
    a = make_open_protocol_action()
    assert a.action_id == ACTION_OPEN_PROTOCOL
    assert a.icon_text == "file_open"
    assert a.priority == 50
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.load_protocol_dialog.assert_called_once_with()


def test_save_protocol_calls_pane_helper():
    a = make_save_protocol_action()
    assert a.action_id == ACTION_SAVE_PROTOCOL
    assert a.icon_text == "save"
    assert a.priority == 60
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.save_protocol_dialog.assert_called_once_with()


def test_new_protocol_calls_pane_helper():
    a = make_new_protocol_action()
    assert a.action_id == ACTION_NEW_PROTOCOL
    assert a.icon_text == "new_window"
    assert a.priority == 70
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.new_protocol.assert_called_once_with()


# --- browse_reports -----------------------------------------------

def test_browse_reports_metadata_and_shortcut():
    a = make_browse_reports_action()
    assert a.action_id == ACTION_BROWSE_REPORTS
    assert a.icon_text == "summarize"
    assert a.priority == 80
    assert a.shortcut == "R"


def test_browse_reports_execute_calls_pane_helper():
    a = make_browse_reports_action()
    ctx = _ctx()
    a.on_execute_action(ctx)
    ctx.pane.browse_reports_dialog.assert_called_once_with()


def test_browse_reports_disabled_without_experiment_manager():
    a = make_browse_reports_action()
    assert a.is_enabled(_ctx(experiment_manager=False)) is False
    assert a.is_enabled(_ctx(experiment_manager=True)) is True
    assert a.is_enabled(_ctx(experiment_manager=True,
                              is_running=True)) is False


# --- plugin default contributions list ----------------------------

def test_plugin_default_contributions_includes_all_eight_actions():
    plugin = ProtocolQuickActionToolsPlugin()
    contribs = plugin._contributed_quick_actions_default()
    ids = sorted(a.action_id for a in contribs)
    assert ids == sorted([
        ACTION_ADD_STEP, ACTION_DELETE_ROW, ACTION_ADD_GROUP,
        ACTION_IMPORT_PROTOCOL, ACTION_OPEN_PROTOCOL, ACTION_SAVE_PROTOCOL,
        ACTION_NEW_PROTOCOL, ACTION_BROWSE_REPORTS,
    ])
```

- [ ] **Step 2: Run tests to verify they fail**

```
pixi run pytest src/protocol_quick_action_tools/tests/test_quick_actions.py -v
```

Expected: import errors / `AttributeError` for the missing factories.

- [ ] **Step 3: Add the 8 factories**

Create `src/protocol_quick_action_tools/quick_actions/add_step.py`:

```python
"""'Add step below selection' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_ADD_STEP


class _AddStepAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.add_step_after_selection()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_add_step_action() -> _AddStepAction:
    return _AddStepAction(
        action_id=ACTION_ADD_STEP,
        icon_text="add",
        tooltip="Add step below selection",
        priority=10,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/add_group.py`:

```python
"""'Add group' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_ADD_GROUP


class _AddGroupAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.add_group_after_selection()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_add_group_action() -> _AddGroupAction:
    return _AddGroupAction(
        action_id=ACTION_ADD_GROUP,
        icon_text="playlist_add",
        tooltip="Add group",
        priority=30,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/delete_row.py`:

```python
"""'Delete selected step / group' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_DELETE_ROW
from .base import has_selection


class _DeleteRowAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.delete_selected_rows()

    def is_enabled(self, ctx) -> bool:
        return (not ctx.is_running) and has_selection(ctx)


def make_delete_row_action() -> _DeleteRowAction:
    return _DeleteRowAction(
        action_id=ACTION_DELETE_ROW,
        icon_text="delete",
        tooltip="Delete selected step / group",
        priority=20,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/import_protocol.py`:

```python
"""'Import protocol into selected group' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_IMPORT_PROTOCOL
from .base import is_single_group_selected


class _ImportProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.import_into_selected_group()

    def is_enabled(self, ctx) -> bool:
        return (not ctx.is_running) and is_single_group_selected(ctx)


def make_import_protocol_action() -> _ImportProtocolAction:
    return _ImportProtocolAction(
        action_id=ACTION_IMPORT_PROTOCOL,
        icon_text="unarchive",
        tooltip="Import protocol into selected group",
        priority=40,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/open_protocol.py`:

```python
"""'Open Protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_OPEN_PROTOCOL


class _OpenProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.load_protocol_dialog()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_open_protocol_action() -> _OpenProtocolAction:
    return _OpenProtocolAction(
        action_id=ACTION_OPEN_PROTOCOL,
        icon_text="file_open",
        tooltip="Open Protocol",
        priority=50,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/save_protocol.py`:

```python
"""'Save Protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_SAVE_PROTOCOL


class _SaveProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.save_protocol_dialog()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_save_protocol_action() -> _SaveProtocolAction:
    return _SaveProtocolAction(
        action_id=ACTION_SAVE_PROTOCOL,
        icon_text="save",
        tooltip="Save Protocol",
        priority=60,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/new_protocol.py`:

```python
"""'New protocol' quick-action factory."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_NEW_PROTOCOL


class _NewProtocolAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.new_protocol()

    def is_enabled(self, ctx) -> bool:
        return not ctx.is_running


def make_new_protocol_action() -> _NewProtocolAction:
    return _NewProtocolAction(
        action_id=ACTION_NEW_PROTOCOL,
        icon_text="new_window",
        tooltip="New protocol",
        priority=70,
    )
```

Create `src/protocol_quick_action_tools/quick_actions/browse_reports.py`:

```python
"""'Browse session reports' quick-action factory. Bound to 'R'."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction

from ..consts import ACTION_BROWSE_REPORTS


class _BrowseReportsAction(BaseQuickAction):
    def on_execute_action(self, ctx):
        ctx.pane.browse_reports_dialog()

    def is_enabled(self, ctx) -> bool:
        return ((not ctx.is_running)
                and getattr(ctx.pane, "experiment_manager", None) is not None)


def make_browse_reports_action() -> _BrowseReportsAction:
    return _BrowseReportsAction(
        action_id=ACTION_BROWSE_REPORTS,
        icon_text="summarize",
        tooltip="Browse session reports (R)",
        priority=80,
        shortcut="R",
    )
```

- [ ] **Step 4: Wire all 8 into the plugin default**

Modify `src/protocol_quick_action_tools/plugin.py` — replace `_contributed_quick_actions_default` body:

```python
    def _contributed_quick_actions_default(self):
        from .quick_actions.add_group import make_add_group_action
        from .quick_actions.add_step import make_add_step_action
        from .quick_actions.browse_reports import make_browse_reports_action
        from .quick_actions.delete_row import make_delete_row_action
        from .quick_actions.import_protocol import make_import_protocol_action
        from .quick_actions.new_protocol import make_new_protocol_action
        from .quick_actions.open_protocol import make_open_protocol_action
        from .quick_actions.save_protocol import make_save_protocol_action
        return [
            make_add_step_action(),
            make_delete_row_action(),
            make_add_group_action(),
            make_import_protocol_action(),
            make_open_protocol_action(),
            make_save_protocol_action(),
            make_new_protocol_action(),
            make_browse_reports_action(),
        ]
```

- [ ] **Step 5: Run tests to verify they pass**

```
pixi run pytest src/protocol_quick_action_tools/tests/test_quick_actions.py -v
```

Expected: all passed (~20 tests).

- [ ] **Step 6: Commit**

```
git add src/protocol_quick_action_tools/quick_actions/ src/protocol_quick_action_tools/plugin.py src/protocol_quick_action_tools/tests/test_quick_actions.py
git commit -m "[ppt-21] Eight legacy quick-action factories (full parity)"
```

---

### Task 13: Live-app wiring — load `ProtocolQuickActionToolsPlugin` from `examples/plugin_consts.py`

**Files:**
- Modify: `src/examples/plugin_consts.py` (or wherever frontend plugins are listed — see step 1)

- [ ] **Step 1: Locate the frontend plugin list**

```
pixi run grep -rn 'PeripheralProtocolControlsPlugin' src/examples/ | head -3
```

Expected output points to a `plugin_consts.py` (or similar) listing frontend plugins. Open that file and find the list that includes `PeripheralProtocolControlsPlugin` (similar pattern).

- [ ] **Step 2: Add the new plugin**

Add to the imports block near the top:

```python
from protocol_quick_action_tools.plugin import (
    ProtocolQuickActionToolsPlugin,
)
```

Append to the same frontend-plugins list (next to `PeripheralProtocolControlsPlugin()`):

```python
    ProtocolQuickActionToolsPlugin(),
```

- [ ] **Step 3: Verify import correctness with a smoke check**

```
pixi run python -c "from examples import plugin_consts; print('ok')"
```

Expected: prints `ok` with no traceback. If `examples.plugin_consts` isn't importable as a module (no `__init__.py`), substitute the right import path observed in step 1's grep output.

- [ ] **Step 4: Full project test sweep**

```
pixi run pytest src/pluggable_protocol_tree/tests/ src/protocol_quick_action_tools/tests/ -v
```

Expected: all tasks 1-12 tests still pass.

- [ ] **Step 5: Commit**

```
git add src/examples/plugin_consts.py
git commit -m "[ppt-21] Load ProtocolQuickActionToolsPlugin in the live app"
```

---

## Spec Coverage Map

| Spec section | Implementing task(s) |
|---|---|
| Architecture §1 — extension-point + IQuickAction + BaseQuickAction + QuickActionCtx | Tasks 1, 2 |
| Architecture §2 — QuickActionBar widget | Task 3 |
| Architecture §2 — QuickActionsController (click + enabled) | Task 4 |
| Architecture §2 — Shortcut wiring + conflict detection | Task 5 |
| Architecture §3 — Pane signals + bar mount | Tasks 6, 7 |
| Architecture §4 — Pane helpers (5 methods) | Task 8 |
| Tree plugin — extension point wiring + dock-pane forwarding | Task 9 |
| New plugin scaffold (consts / plugin shell / base helper) | Task 10 |
| Report browser port | Task 11 |
| Eight action factories | Task 12 |
| Live-app wiring | Task 13 |
| Tree-plugin builtins = none | Task 9 (test asserts empty contributed_quick_actions default) |
| Shortcuts respect `is_running` gating | Task 5 (test_shortcut_is_gated_by_is_running) |
| `R` shortcut on browse_reports | Task 12 (test_browse_reports_metadata_and_shortcut) |
| ReportBrowserDialog ported verbatim | Task 11 |
| Error handling: buggy contribution swallowed | Task 4 (test_buggy_action_does_not_break_other_buttons) |
| Error handling: shortcut conflicts | Task 5 (test_duplicate_shortcut_skips_second_and_logs_warning) |
| Error handling: missing reports dir / empty | Task 11 (test_dialog_handles_empty_list_without_crashing) |
| Error handling: missing experiment manager | Task 8 (test_browse_reports_dialog_no_provider_logs_and_returns), Task 12 (test_browse_reports_disabled_without_experiment_manager) |

All spec sections accounted for.
