# Protocol Timeline Seek Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a video-style timeline seek bar to the pluggable protocol tree — a horizontal track with a tick per step and a draggable playhead, plus a secondary phase track for the current step — that redirects all navigation intent through the existing dock-pane controller.

**Architecture:** A new pure-Qt `TimelineBar` view emits `step_seek_requested(int)` / `phase_seek_requested(int)` intents and exposes `rebuild()` / `set_position()` / `set_running()` push methods. The existing `PluggableProtocolDockPane` (the controller) connects those intents to the already-built `ProtocolStatusController.seek_to(step_path, phase_index)` + `preview_phase(...)` and pushes model state into the bar via its existing `dispatch="ui"` model observers. No new model; no executor changes.

**Tech Stack:** Python, Traits/`@observe`, PySide6 via `pyface.qt`, pytest with the project's `qapp` fixture.

## Global Constraints

- Qt is imported **only** in view code. `TimelineBar` is a view, so Qt imports are allowed there; the controller wiring lives in the existing view file `views/dock_pane.py`. (microdrop-conventions: "never import Qt in service/model layers".)
- Logging: `from logger.logger_service import get_logger; logger = get_logger(__name__)` — never `logging.getLogger`.
- Use f-strings; no `%`/`.format()`.
- Constants are `UPPER_SNAKE_CASE` at the top of the module (below imports).
- Reuse existing names; do not mint parallel constants/helpers. The phase seek reuses the existing `seek_to` 0-based `phase_index` convention.
- Steps-only track; phase sub-ticks appear **only** for the current step (granularity 1C). No group tier.
- Seeking is always interactive; while **actively running (not paused)** a scrub is **preview-only** (B1) — `seek_to`'s executor side is paused-guarded, so it updates the model + DeviceViewer overlay and the executor reasserts at the next boundary. No executor changes.
- View tests need no Redis/hardware → they live in the top-level `pluggable_protocol_tree/tests/` dir and use the `qapp` fixture.
- **Working directory:** run all `git`, `pytest`, and `pixi` commands from the **`microdrop-py/src` submodule** (the inner git repo and Python source root). All paths below are relative to that directory. Python/pytest are invoked through `pixi` per the project's verified invocation (see the `pixi-python-invocation` memory) — if `pixi run python -m pytest <path>` differs in your env, match how the existing `pluggable_protocol_tree/tests` are run.

## File Structure

- **Create** `pluggable_protocol_tree/views/timeline_bar.py` — the `TimelineBar` `QWidget` (view only: paint + intent signals + push API).
- **Create** `pluggable_protocol_tree/tests/test_timeline_bar.py` — unit tests for the widget (`qapp`).
- **Modify** `pluggable_protocol_tree/views/protocol_tree_pane.py` — build `self.timeline_bar` and place it directly under the nav bar in `_build_layout`.
- **Modify** `pluggable_protocol_tree/tests/test_protocol_tree_pane.py` — assert the pane exposes & places `timeline_bar`.
- **Modify** `pluggable_protocol_tree/views/dock_pane.py` — connect the bar's intents to `seek_to`/`preview_phase`, push model state into the bar, refactor `_seek_relative_phase` to reuse a new `_seek_to_phase`.

### Index alignment decision (resolves the spec's open item)

The timeline's tick list is `ProtocolTreePane._navigable_steps()` — the same distinct-step-rows-in-execution-order list the nav buttons walk (repetitions collapsed to one entry per row). The playhead index is `dock_pane._current_step_in(steps)` (the same helper the nav buttons use). This keeps the timeline, the nav buttons, and `_select_step` perfectly aligned and sidesteps the execution-frame-vs-navigable-step mismatch. Phase position comes from the model's `phase_index` (1-based) / `phase_total`, which the controller already maintains for the executing/paused step.

---

### Task 1: `TimelineBar` view widget

**Files:**
- Create: `pluggable_protocol_tree/views/timeline_bar.py`
- Test: `pluggable_protocol_tree/tests/test_timeline_bar.py`

**Interfaces:**
- Consumes: nothing (leaf view).
- Produces:
  - Signals: `step_seek_requested = Signal(int)` (0-based step index), `phase_seek_requested = Signal(int)` (0-based phase index).
  - `rebuild(step_labels: list[str]) -> None` — set the major-tick count (`len(step_labels)`) and per-tick hover labels.
  - `set_position(step_index: int, step_total: int, phase_index: int, phase_total: int) -> None` — move the step playhead (`step_index`, use `-1` for "none") and draw the phase track for the current step (`phase_index` 0-based, `phase_total`; phase track shown only when `phase_total > 1`).
  - `set_running(running: bool) -> None` — toggle the preview-mode accent; the bar stays interactive.
  - Pure helpers (for tests): `_step_index_at_x(x: int) -> int`, `_phase_index_at_x(x: int) -> int`, `_seek_at_point(point) -> None` (dispatches to the correct signal by which track row contains `point`).

- [ ] **Step 1: Write the failing test**

Create `pluggable_protocol_tree/tests/test_timeline_bar.py`:

```python
"""TimelineBar is a pure rendering/intent widget: it paints a step track
(one tick per step) plus a phase track for the current step, and emits
step_seek_requested / phase_seek_requested when the user clicks a track.
It holds no engine references and performs no seeking itself."""

from pyface.qt.QtCore import QPoint
from pluggable_protocol_tree.views.timeline_bar import TimelineBar

WIDTH = 400


def _bar(qapp, labels=("S0", "S1", "S2", "S3")):
    bar = TimelineBar()
    bar.rebuild(list(labels))
    bar.resize(WIDTH, bar.height())
    return bar


def test_rebuild_sets_step_count(qapp):
    bar = _bar(qapp)
    assert bar.step_count == 4


def test_step_index_at_x_maps_across_width(qapp):
    bar = _bar(qapp)
    # 4 steps across the usable width -> first quarter is step 0, last is 3.
    assert bar._step_index_at_x(bar._step_track_rect().left() + 1) == 0
    assert bar._step_index_at_x(bar._step_track_rect().right() - 1) == 3


def test_step_index_at_x_is_clamped(qapp):
    bar = _bar(qapp)
    assert bar._step_index_at_x(-50) == 0
    assert bar._step_index_at_x(WIDTH + 50) == 3


def test_click_on_step_track_emits_step_seek(qapp):
    bar = _bar(qapp)
    bar.set_position(0, 4, 0, 0)
    captured = []
    bar.step_seek_requested.connect(captured.append)
    r = bar._step_track_rect()
    bar._seek_at_point(QPoint(r.right() - 1, r.center().y()))
    assert captured == [3]


def test_phase_track_hidden_without_multiple_phases(qapp):
    bar = _bar(qapp)
    bar.set_position(1, 4, 0, 1)  # phase_total == 1 -> no phase track
    assert bar._phase_track_visible() is False


def test_click_on_phase_track_emits_phase_seek(qapp):
    bar = _bar(qapp)
    bar.set_position(1, 4, 0, 5)  # current step has 5 phases
    captured = []
    bar.phase_seek_requested.connect(captured.append)
    r = bar._phase_track_rect()
    bar._seek_at_point(QPoint(r.right() - 1, r.center().y()))
    assert captured == [4]


def test_set_running_does_not_break_interaction(qapp):
    bar = _bar(qapp)
    bar.set_position(0, 4, 0, 0)
    bar.set_running(True)
    captured = []
    bar.step_seek_requested.connect(captured.append)
    r = bar._step_track_rect()
    bar._seek_at_point(QPoint(r.left() + 1, r.center().y()))
    assert captured == [0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run python -m pytest pluggable_protocol_tree/tests/test_timeline_bar.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.views.timeline_bar'`.

- [ ] **Step 3: Write minimal implementation**

Create `pluggable_protocol_tree/views/timeline_bar.py`:

```python
"""TimelineBar — a video-style seek strip for the pluggable protocol tree.

Pure view: it paints a step track (one tick per navigable step) with a
playhead, and — only when the current step has more than one phase — a
secondary phase track beneath it. Clicking either track emits an intent
signal; the dock-pane controller translates that into a status-controller
seek. The widget holds no engine references and never seeks itself.

Mirrors NavigationBar's conventions: hugs its height (Expanding/Fixed),
re-applies theme colours on colorSchemeChanged (deferred one event-loop
tick, since is_dark_mode() can be briefly stale at signal time).
"""

from pyface.qt.QtCore import Qt, QRect, QTimer, Signal
from pyface.qt.QtGui import QColor, QPainter, QPen
from pyface.qt.QtWidgets import QApplication, QSizePolicy, QWidget

from microdrop_style.colors import BLACK, GREY, SECONDARY_SHADE, WHITE
from microdrop_style.helpers import is_dark_mode

# Layout geometry (px). The widget is a fixed-height strip; the step track
# sits on top, the phase track (shown only for multi-phase current steps)
# directly below it.
SIDE_MARGIN = 8
BAR_HEIGHT = 34
STEP_TRACK_TOP = 6
STEP_TRACK_BOTTOM = 18
PHASE_TRACK_TOP = 21
PHASE_TRACK_BOTTOM = 29


class TimelineBar(QWidget):
    step_seek_requested = Signal(int)
    phase_seek_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(BAR_HEIGHT)
        self.setMouseTracking(True)

        self.step_count = 0
        self._step_labels = []
        self._step_index = -1
        self._phase_index = 0
        self._phase_total = 0
        self._running = False

        QApplication.styleHints().colorSchemeChanged.connect(
            self._on_color_scheme_changed,
        )

    # --- push API (driven by the dock-pane controller) ---------------

    def rebuild(self, step_labels):
        self._step_labels = list(step_labels)
        self.step_count = len(self._step_labels)
        self.update()

    def set_position(self, step_index, step_total, phase_index, phase_total):
        # step_total is accepted for API symmetry with the status bar, but the
        # tick count comes from rebuild()'s label list; trust step_count.
        self._step_index = step_index
        self._phase_index = phase_index
        self._phase_total = phase_total
        self.setToolTip(self._current_label())
        self.update()

    def set_running(self, running):
        self._running = bool(running)
        self.update()

    # --- geometry / hit testing --------------------------------------

    def _usable_width(self):
        return max(1, self.width() - 2 * SIDE_MARGIN)

    def _step_track_rect(self):
        return QRect(SIDE_MARGIN, STEP_TRACK_TOP,
                     self._usable_width(), STEP_TRACK_BOTTOM - STEP_TRACK_TOP)

    def _phase_track_rect(self):
        return QRect(SIDE_MARGIN, PHASE_TRACK_TOP,
                     self._usable_width(), PHASE_TRACK_BOTTOM - PHASE_TRACK_TOP)

    def _phase_track_visible(self):
        return self._phase_total > 1

    def _index_at_x(self, x, count):
        if count <= 0:
            return 0
        seg = self._usable_width() / count
        idx = int((x - SIDE_MARGIN) / seg)
        return max(0, min(count - 1, idx))

    def _step_index_at_x(self, x):
        return self._index_at_x(x, self.step_count)

    def _phase_index_at_x(self, x):
        return self._index_at_x(x, self._phase_total)

    def _seek_at_point(self, point):
        if self._phase_track_visible() and self._phase_track_rect().contains(point):
            self.phase_seek_requested.emit(self._phase_index_at_x(point.x()))
        elif self._step_track_rect().contains(point):
            self.step_seek_requested.emit(self._step_index_at_x(point.x()))

    # --- mouse ------------------------------------------------------

    def _event_point(self, event):
        # PySide6: QMouseEvent.position() returns QPointF; older shims use pos().
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._seek_at_point(self._event_point(event))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Scrub: while the left button is held, keep emitting as the pointer
        # crosses ticks. Qt coalesces move events, so this is not per-pixel.
        if event.buttons() & Qt.LeftButton:
            self._seek_at_point(self._event_point(event))
        super().mouseMoveEvent(event)

    # --- labels / theme ---------------------------------------------

    def _current_label(self):
        if 0 <= self._step_index < len(self._step_labels):
            return self._step_labels[self._step_index]
        return ""

    def _on_color_scheme_changed(self, *_):
        QTimer.singleShot(0, self.update)

    def _colors(self):
        if is_dark_mode():
            return dict(track=GREY["dark"], tick=GREY["lighter"], text=WHITE,
                        head=SECONDARY_SHADE[300])
        return dict(track=GREY["light"], tick=GREY["dark"], text=BLACK,
                    head=SECONDARY_SHADE[700])

    # --- paint ------------------------------------------------------

    def _tick_center_x(self, index, count):
        seg = self._usable_width() / max(1, count)
        return int(SIDE_MARGIN + (index + 0.5) * seg)

    def _paint_track(self, painter, rect, count, position, colors):
        painter.setPen(QPen(QColor(colors["track"]), 2))
        mid_y = rect.center().y()
        painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)
        painter.setPen(QPen(QColor(colors["tick"]), 1))
        for i in range(count):
            x = self._tick_center_x(i, count)
            painter.drawLine(x, rect.top(), x, rect.bottom())
        if 0 <= position < count:
            head_x = self._tick_center_x(position, count)
            head_color = SECONDARY_SHADE[300] if self._running else colors["head"]
            painter.setPen(QPen(QColor(head_color), 3))
            painter.drawLine(head_x, rect.top() - 2, head_x, rect.bottom() + 2)

    def paintEvent(self, event):
        if self.step_count <= 0:
            return
        colors = self._colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_track(painter, self._step_track_rect(),
                          self.step_count, self._step_index, colors)
        if self._phase_track_visible():
            self._paint_track(painter, self._phase_track_rect(),
                              self._phase_total, self._phase_index, colors)
        painter.end()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run python -m pytest pluggable_protocol_tree/tests/test_timeline_bar.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/views/timeline_bar.py \
        pluggable_protocol_tree/tests/test_timeline_bar.py
git commit -m "feat(protocol-tree): add TimelineBar seek widget (view)"
```

---

### Task 2: Mount `TimelineBar` under the nav bar in `ProtocolTreePane`

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py` (`__init__` build section near line 163-164; `_build_layout` at lines 249-258)
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

**Interfaces:**
- Consumes: `TimelineBar` from Task 1.
- Produces: `pane.timeline_bar: TimelineBar`, laid out directly under `pane.navigation_bar` and above `pane.status_bar`.

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_has_timeline_bar_under_nav_bar(qapp):
    from pluggable_protocol_tree.builtins.type_column import make_type_column
    from pluggable_protocol_tree.views.protocol_tree_pane import ProtocolTreePane
    from pluggable_protocol_tree.views.timeline_bar import TimelineBar

    pane = ProtocolTreePane([make_type_column()])
    assert isinstance(pane.timeline_bar, TimelineBar)

    layout = pane.layout()
    nav_idx = layout.indexOf(pane.navigation_bar)
    timeline_idx = layout.indexOf(pane.timeline_bar)
    status_idx = layout.indexOf(pane.status_bar)
    assert nav_idx < timeline_idx < status_idx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py::test_pane_has_timeline_bar_under_nav_bar -v`
Expected: FAIL with `AttributeError: 'ProtocolTreePane' object has no attribute 'timeline_bar'`.

- [ ] **Step 3: Write minimal implementation**

In `protocol_tree_pane.py`, add the import near the other view imports (around line 55-58):

```python
from pluggable_protocol_tree.views.timeline_bar import TimelineBar
```

In `__init__`, right after the `self._build_navigation_bar()` call (line 164), add:

```python
        self.timeline_bar = TimelineBar()
```

In `_build_layout` (lines 249-258), insert the timeline between the nav bar and the status bar:

```python
    def _build_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation_bar)
        layout.addWidget(self.timeline_bar)
        layout.addWidget(self.status_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self.widget)
        if self.quick_action_bar is not None:
            layout.addWidget(self.quick_action_bar)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v`
Expected: PASS (the new test plus all existing pane tests).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/views/protocol_tree_pane.py \
        pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git commit -m "feat(protocol-tree): mount TimelineBar under the nav bar"
```

---

### Task 3: Wire `TimelineBar` into the dock-pane controller

**Files:**
- Modify: `pluggable_protocol_tree/views/dock_pane.py` — `create_contents` (signal connections + initial build, near line 245-259); `_seek_relative_phase` (lines 335-343); add `_seek_to_phase`, `_on_timeline_step_seek`, `_on_timeline_phase_seek`, `_refresh_timeline_position`, `_rebuild_timeline`; extend the model observers (`_on_counts_changed` line 793, `_on_current_step_path_changed` line 780, `_on_protocol_running_changed` line 807) and add a `manager:rows_changed` observer.
- Test: manual GUI checklist + an import/structure smoke test (full dock-pane construction needs the Envisage task/window, so the seek path itself is covered by the already-passing `ProtocolStatusController` tests; the wiring is verified manually).

**Interfaces:**
- Consumes: `TimelineBar` signals + push API (Task 1), `pane.timeline_bar` (Task 2), existing `self.status_controller` (`ProtocolStatusController`) with `seek_to(step_path, phase_index)` and `preview_phase(step_path, phase_index, preview_mode)`, `self._pane._navigable_steps()`, `self._current_step_in(steps)`, `self._select_step(row)`, `self._current_run_preview_mode`, `self._current_row`.
- Produces: a fully wired timeline — clicks seek, model changes move the playhead.

- [ ] **Step 1: Refactor `_seek_relative_phase` to expose a reusable absolute-phase seek**

Replace the existing `_seek_relative_phase` (lines 335-343) with:

```python
    def _seek_to_phase(self, target0):
        """Seek the current step to absolute 0-based phase ``target0`` and
        preview it. Shared by the nav-bar prev/next-phase buttons and the
        timeline's phase track."""
        sc = self.status_controller
        if sc is None or self._current_row is None:
            return
        path = tuple(self._current_row.path)
        sc.seek_to(path, target0)
        sc.preview_phase(path, target0, self._current_run_preview_mode)
        self._update_phase_nav_buttons()

    def _seek_relative_phase(self, delta):
        sc = self.status_controller
        if sc is None:
            return
        # model phase_index is 1-based; convert to a 0-based absolute target.
        self._seek_to_phase((sc.model.phase_index - 1) + delta)
```

- [ ] **Step 2: Add the timeline seek handlers + refresh helpers**

Add these methods to the dock-pane class (next to the navigation helpers, after `_seek_relative_phase`):

```python
    # --- timeline seek bar (view -> controller) ----------------------

    def _on_timeline_step_seek(self, step_index):
        steps = self._pane._navigable_steps()
        if not (0 <= step_index < len(steps)):
            return
        row = steps[step_index]
        sc = self.status_controller
        if sc is not None and sc.model.running and not sc.model.paused:
            # B1: preview-only while actively running. Move the selection and
            # preview the target; the executor reasserts at the next boundary.
            self._pane.select_row(row)
            self._current_row = row
            path = tuple(row.path)
            sc.seek_to(path, 0)
            sc.preview_phase(path, 0, self._current_run_preview_mode)
        else:
            # Paused -> real seek; idle -> selection only (matches nav buttons).
            self._select_step(row)

    def _on_timeline_phase_seek(self, phase_index):
        # The bar emits a 0-based phase index, exactly what _seek_to_phase wants.
        self._seek_to_phase(phase_index)

    # --- timeline seek bar (model -> view) ---------------------------

    def _refresh_timeline_position(self):
        tb = getattr(self._pane, "timeline_bar", None)
        if tb is None:
            return
        steps = self._pane._navigable_steps()
        cur = self._current_step_in(steps)
        model = self.status_controller.model if self.status_controller else None
        phase_index0 = (model.phase_index - 1) if (model and model.phase_index > 0) else 0
        phase_total = model.phase_total if model else 0
        tb.set_position(cur if cur is not None else -1, len(steps),
                        phase_index0, phase_total)

    def _rebuild_timeline(self, event=None):
        tb = getattr(self._pane, "timeline_bar", None)
        if tb is None:
            return
        steps = self._pane._navigable_steps()
        tb.rebuild([(row.name or row.dotted_path()) for row in steps])
        self._refresh_timeline_position()
```

- [ ] **Step 3: Connect the bar's intent signals + seed it in `create_contents`**

In `create_contents`, right after the navigation-bar wiring block (after line 252, `nb.btn_last.clicked.connect(...)`), add:

```python
        # Timeline seek bar: clicks redirect through the status controller; the
        # model observers below push the playhead position back.
        tb = pane.timeline_bar
        tb.step_seek_requested.connect(self._on_timeline_step_seek)
        tb.phase_seek_requested.connect(self._on_timeline_phase_seek)
```

Then, just before `return pane` (line 265, after `pane._seed_default_step_if_empty()`), add:

```python
        # Initial timeline render (structure + position).
        self._rebuild_timeline()
```

- [ ] **Step 4: Push model/structure changes into the bar**

Extend the existing observers. In `_on_counts_changed` (line 793-796), append a call after the status-bar refresh:

```python
    @observe("status_controller:model:[step_index, step_total, phase_index, phase_total]", dispatch="ui", post_init=True)
    def _on_counts_changed(self, event=None):
        model = self.status_controller.model
        self._pane.status_bar._refresh_counts(current=model.step_index, total=model.step_total)
        self._refresh_timeline_position()
```

In `_on_current_step_path_changed` (line 780-790), append after `self._pane.widget.highlight_active_row(row)`:

```python
        self._refresh_timeline_position()
```

In `_on_protocol_running_changed` (line 807-823), append after the existing body (so the bar gets the preview accent):

```python
        tb = getattr(self._pane, "timeline_bar", None)
        if tb is not None:
            tb.set_running(bool(event.new))
```

Add a new observer for structural changes (place it next to the other model observers, after `_on_current_step_path_changed`):

```python
    @observe("manager:rows_changed", dispatch="ui", post_init=True)
    def _on_rows_changed_rebuild_timeline(self, event=None):
        self._rebuild_timeline()
```

> Verify while implementing: `manager` must be a Traits trait on the dock pane for `@observe("manager:rows_changed", ...)` to fire. If `manager` is a plain attribute, instead call `self._rebuild_timeline()` from wherever the pane already handles `rows_changed` (search `rows_changed` in `dock_pane.py` / `protocol_tree_pane.py`) — do **not** add a second source of truth.

- [ ] **Step 5: Smoke-test that the module imports and the wiring methods exist**

Run:

```bash
pixi run python -c "import pluggable_protocol_tree.views.dock_pane as d; \
print(all(hasattr(d.PluggableProtocolDockPane, m) for m in \
['_seek_to_phase','_on_timeline_step_seek','_on_timeline_phase_seek', \
'_refresh_timeline_position','_rebuild_timeline']))"
```

Expected output: `True`.

- [ ] **Step 6: Run the affected automated tests**

Run: `pixi run python -m pytest pluggable_protocol_tree/tests/test_protocol_status_controller.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py pluggable_protocol_tree/tests/test_timeline_bar.py -v`
Expected: PASS (the seek/refactor reuses already-tested controller methods; the view + pane tests still pass).

- [ ] **Step 7: Manual GUI verification (ask the user to run)**

Start Redis, then `pixi run python examples/run_device_viewer_pluggable.py`. Confirm:
1. A timeline strip appears directly under the nav buttons, with one tick per step.
2. Clicking a tick (idle) selects that step in the tree.
3. Start a protocol, **pause**, click a tick → the tree highlight, the DeviceViewer overlay, and the status bar's "Step n/N" all move to that step; the phase track appears for a multi-phase step and clicking it moves the phase.
4. While **actively running**, clicking a tick previews the target step on the DeviceViewer momentarily; the executor continues and the playhead snaps back to the executing step at the next boundary (B1).
5. Toggle OS dark/light mode → the bar restyles.

- [ ] **Step 8: Commit**

```bash
git add pluggable_protocol_tree/views/dock_pane.py
git commit -m "feat(protocol-tree): wire TimelineBar seeks through the controller"
```

---

## Notes / out of scope (follow-ups)

- Idle-selected steps don't show phase sub-ticks (the model only tracks `phase_total` for the executing/paused step). Showing them would call `ProtocolStatusController._phase_total_for(row)` — deferred.
- The phase track spans the full width representing the current step's phases (bigger hit area), rather than literally subdividing the current step's segment — a deliberate usability choice within the approved "phases on demand" scope.
- Group bands, mid-run execution redirection (B2), and drag-throttling beyond Qt's event coalescing are out of scope.
