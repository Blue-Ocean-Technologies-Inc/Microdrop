# PPT-3 Design — Electrodes + Routes columns + simplified phase math + simple device viewer

Companion to `2026-04-21-pluggable-protocol-tree-design.md` (sections 11–12) and `2026-04-22-ppt-2-executor-design.md`.

## 0. Scope

- Two complex per-row columns: `electrodes: List[Str]` (held active for the step) and `routes: List[List[Str]]` (paths to traverse).
- Six hidden-by-default config columns: `trail_length`, `trail_overlay`, `soft_start`, `soft_end`, `repeat_duration`, `linear_repeats`.
- New `services/phase_math.py` — clean pure-function rewrite of legacy phase generation (~150 lines vs the legacy ~760).
- `RoutesHandler` at priority 30 — walks `iter_phases()`, publishes each phase to `ELECTRODES_STATE_CHANGE`, waits for `ELECTRODES_STATE_APPLIED` before the next.
- `RowManager.protocol_metadata` Dict trait persisted in the JSON header; carries `electrode_to_channel: dict[str, int]` for PPT-3 and is a generic bag for future per-protocol settings.
- `SimpleDeviceViewer` — 5×5 grid widget for the demo. Click-to-toggle static electrodes, click-sequence-then-Finish to draw routes, live green overlay on currently-actuated cells. Embedded alongside the tree in the demo via `QSplitter`.
- In-process electrode responder (Dramatiq actor) for end-to-end demo + integration test.
- Header right-click context menu in the tree to toggle hidden columns visible.

**Out of scope:**
- Touching `device_viewer/` plugin — left alone.
- Touching `protocol_grid/services/path_execution_service.py` (760 lines) — the legacy plugin keeps using it unchanged.
- Touching `protocol_grid/state/device_state.py` — `DeviceState` deletion is PPT-9.
- Replacing `protocol_runner_controller.py` (2354 lines) — also PPT-9.
- Editing `electrodes` / `routes` from production GUI device viewer — only the demo's `SimpleDeviceViewer` supports editing in PPT-3.

## 1. Decisions locked in during brainstorming

| # | Question | Decision |
|---|---|---|
| 1 | Scope split | **A** — one PR, ships all 6 hidden config columns + 2 complex columns + RoutesHandler + phase math + simple device viewer. |
| 2 | Phase math lift | **A** — leave `path_execution_service.py` alone; write fresh simplified `phase_math.py` from scratch. No shared imports. |
| 3 | Data model | Per-row: `electrodes: List(Str)`, `routes: List(List(Str))`. Per-protocol: `electrode_to_channel: dict[str, int]` in JSON header. |
| 4 | Device viewer integration | **A** — none. PPT-3 publishes phase electrode-lists on `ELECTRODES_STATE_CHANGE` and that's it. No subscribing to `DEVICE_VIEWER_STATE_CHANGED`, no publishing `STEP_PARAMS_COMMIT`. The demo's `SimpleDeviceViewer` is the only editing UI in PPT-3. |
| 5 | Cell editing for electrodes/routes | **A** — read-only summary cells. Edited only via the demo's `SimpleDeviceViewer` or programmatic / JSON-load path. |
| 6 | Demo device viewer | **5×5 grid**, two modes (Static / Route), Finish/Clear Route buttons, live green actuation overlay subscribing to `ELECTRODES_STATE_CHANGE`. |

## 2. File layout

```
pluggable_protocol_tree/
├── builtins/
│   ├── electrodes_column.py        # NEW
│   ├── routes_column.py            # NEW (incl. RoutesHandler)
│   ├── trail_length_column.py      # NEW
│   ├── trail_overlay_column.py     # NEW
│   ├── soft_start_column.py        # NEW
│   ├── soft_end_column.py          # NEW
│   ├── repeat_duration_column.py   # NEW
│   └── linear_repeats_column.py    # NEW
├── services/
│   └── phase_math.py               # NEW
├── models/row_manager.py           # +protocol_metadata trait
├── services/persistence.py         # +metadata round-trip
├── execution/executor.py           # +scratch.update(metadata) at run start
├── plugin.py                       # +new builtins; +seed-from-prefs helper
├── views/tree_widget.py            # +hide cols where view.hidden_by_default;
│                                    # +header right-click "Show…" menu
├── consts.py                       # +ELECTRODES_STATE_CHANGE/_APPLIED topics
├── demos/
│   ├── simple_device_viewer.py     # NEW
│   ├── electrode_responder.py      # NEW (in-process actuation responder)
│   └── run_widget.py               # MODIFIED — embeds SimpleDeviceViewer + seeds metadata
└── tests/
    ├── test_phase_math.py          # NEW (~20 tests)
    ├── test_electrodes_routes_columns.py    # NEW
    ├── test_hidden_columns.py      # NEW (one per of the 6)
    ├── test_persistence.py         # +protocol_metadata round-trip + backward-compat
    └── tests_with_redis_server_need/
        └── test_routes_handler_redis.py     # NEW (end-to-end actuation)
```

## 3. Data model

### `electrodes` column

```python
# pluggable_protocol_tree/builtins/electrodes_column.py

from traits.api import List, Str

class ElectrodesColumnModel(BaseColumnModel):
    """Static electrodes held active for the entire step."""
    def trait_for_row(self):
        return List(Str, value=list(self.default_value or []))


class ElectrodesSummaryView(BaseColumnView):
    """Read-only cell. '0 electrodes' / '1 electrode' / '12 electrodes'.
    Mutated only via the demo's SimpleDeviceViewer or programmatic API."""
    def format_display(self, value, row):
        n = len(value or [])
        return f"{n} electrode" + ("" if n == 1 else "s")
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable     # NOT editable
    def create_editor(self, parent, ctx):
        return None


def make_electrodes_column():
    return Column(
        model=ElectrodesColumnModel(
            col_id="electrodes", col_name="Electrodes", default_value=[],
        ),
        view=ElectrodesSummaryView(),
    )
```

### `routes` column + RoutesHandler

```python
# pluggable_protocol_tree/builtins/routes_column.py

from traits.api import List, Str

class RoutesColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return List(List(Str), value=list(self.default_value or []))


class RoutesSummaryView(BaseColumnView):
    def format_display(self, value, row):
        n = len(value or [])
        return f"{n} route" + ("" if n == 1 else "s")
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    def create_editor(self, parent, ctx):
        return None


class RoutesHandler(BaseColumnHandler):
    """Drives electrode actuation for the step.

    Walks iter_phases() over the row's electrodes/routes/trail config,
    publishes each phase as a JSON envelope on ELECTRODES_STATE_CHANGE,
    waits for an ELECTRODES_STATE_APPLIED ack before the next phase.
    Priority 30 keeps it earlier than DurationColumnHandler's 90 — the
    duration sleep only starts after all phases have completed.
    """
    priority = 30
    wait_for_topics = [ELECTRODES_STATE_APPLIED]

    def on_step(self, row, ctx):
        mapping = ctx.protocol.scratch.get("electrode_to_channel", {})
        for phase in iter_phases(
            static_electrodes=row.electrodes,
            routes=row.routes,
            trail_length=row.trail_length,
            trail_overlay=row.trail_overlay,
            soft_start=row.soft_start,
            soft_end=row.soft_end,
            repeat_duration_s=row.repeat_duration,
            linear_repeats=row.linear_repeats,
            step_duration_s=row.duration_s,
        ):
            channels = sorted(mapping[e] for e in phase if e in mapping)
            unmapped = sorted(e for e in phase if e not in mapping)
            for e in unmapped:
                logger.warning("electrode %r has no channel mapping; skipping", e)
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps({
                    "electrodes": sorted(phase),
                    "channels": channels,
                }),
            )
            ctx.wait_for(ELECTRODES_STATE_APPLIED, timeout=2.0)


def make_routes_column():
    return Column(
        model=RoutesColumnModel(
            col_id="routes", col_name="Routes", default_value=[],
        ),
        view=RoutesSummaryView(),
        handler=RoutesHandler(),
    )
```

### Six hidden config columns

Each in its own file, factory pattern. All set `view.hidden_by_default = True`.

| col_id | type | view | low/high | default |
|---|---|---|---|---|
| `trail_length` | Int | hidden IntSpinBox | 1 / 64 | 1 |
| `trail_overlay` | Int | hidden IntSpinBox | 0 / 63 | 0 |
| `soft_start` | Bool | hidden Checkbox | — | False |
| `soft_end` | Bool | hidden Checkbox | — | False |
| `repeat_duration` | Float | hidden DoubleSpinBox | 0.0 / 3600 | 0.0 |
| `linear_repeats` | Bool | hidden Checkbox | — | False |

`_HiddenIntSpinBoxView`, `_HiddenCheckboxColumnView`, `_HiddenDoubleSpinBoxView` are tiny subclasses of the existing PPT-1 views that override the class attribute `hidden_by_default = True`.

### Plugin `_assemble_columns` becomes:

```python
return [
    make_type_column(), make_id_column(), make_name_column(),
    make_repetitions_column(), make_duration_column(),
    make_electrodes_column(), make_routes_column(),
    make_trail_length_column(), make_trail_overlay_column(),
    make_soft_start_column(), make_soft_end_column(),
    make_repeat_duration_column(), make_linear_repeats_column(),
] + list(self.contributed_columns)
```

A `_seed_from_preferences()` helper in `plugin.py` looks up `ProtocolPreferences` via `try/except ImportError` and overrides each factory's defaults before construction. Production honors user prefs; tests / standalone demo use the literal defaults from the table above.

### Topics

```python
# consts.py additions
ELECTRODES_STATE_CHANGE  = f"{PROTOCOL_TOPIC_PREFIX}/electrodes_state_change"
ELECTRODES_STATE_APPLIED = f"{PROTOCOL_TOPIC_PREFIX}/electrodes_state_applied"
```

## 4. Phase math

`pluggable_protocol_tree/services/phase_math.py` — pure functions. No Traits, no Qt, no global state.

```python
def iter_phases(
    static_electrodes: list[str],
    routes: list[list[str]],
    *,
    trail_length: int = 1,
    trail_overlay: int = 0,
    soft_start: bool = False,
    soft_end: bool = False,
    repeat_duration_s: float = 0.0,
    linear_repeats: bool = False,
    step_duration_s: float = 1.0,
) -> Iterator[set[str]]:
    """Yield each phase as the set of electrode IDs to actuate.

    Each yield is one snapshot in time: static electrodes are always
    included; per-route trail windows are unioned in. The caller (a
    RoutesHandler) publishes the set, waits for the device's apply
    confirmation, then asks for the next phase.
    """
```

Composed of small one-job helpers:

```python
def _is_loop_route(route): return len(route) >= 2 and route[0] == route[-1]

def _route_windows(route, trail_length, trail_overlay):
    """Sliding-window iterator over one route. Yields sets.
    Open route: ceil((len-trail_length)/step + 1) windows.
    Loop route (first==last): one full cycle of windows wrapping
    around the dropped-last electrode."""

def _route_with_repeats(route, trail_length, trail_overlay, *,
                        linear_repeats, repeat_duration_s, step_duration_s):
    """Wraps _route_windows with linear_repeats / loop-cycle counting /
    repeat_duration_s budget logic. Yields a finite sequence of windows."""

def _zip_with_static(per_route_iters, static):
    """At each tick, union the static set with each route's current
    window. Routes shorter than the longest hold at their last window
    so phases aren't ragged. Stops when all routes exhausted."""

def _ramp_up(phases, trail_length):
    """Prepend phases that grow from 1 electrode to trail_length."""

def _ramp_down(phases, trail_length):
    """Append phases that shrink from trail_length back to 1."""
```

`iter_phases` composes them:

```python
def iter_phases(static_electrodes, routes, *, trail_length, trail_overlay,
                soft_start, soft_end, repeat_duration_s,
                linear_repeats, step_duration_s):
    static = set(static_electrodes or [])
    if not routes:
        # No paths to traverse; the static set is the only phase.
        yield static
        return
    per_route = [_route_with_repeats(
                     r, trail_length, trail_overlay,
                     linear_repeats=linear_repeats,
                     repeat_duration_s=repeat_duration_s,
                     step_duration_s=step_duration_s)
                 for r in routes]
    base = _zip_with_static(per_route, static)
    if soft_start:
        base = _ramp_up(base, trail_length)
    if soft_end:
        base = _ramp_down(base, trail_length)
    yield from base
```

### Semantic decisions (each documented in docstrings)

1. **Empty routes + non-empty static** → exactly one phase emitted (the static set). Step holds for `duration_s`.
2. **trail_length > len(route)** → window is the whole route every tick.
3. **trail_overlay ≥ trail_length** → effective `step_size = max(1, trail_length - trail_overlay)` (clamp to 1 to guarantee progress).
4. **Loop route** → one cycle of windows. `repetitions` (existing PPT-2 column) controls how many cycles the row runs total. `repeat_duration_s` overrides: cycles = `floor(repeat_duration_s / (cycle_phases × step_duration_s))`, padded with idle phases to fill remaining time.
5. **Open route + linear_repeats=True** → replay the windows N times where N = `repetitions`. False → one pass.
6. **Multiple routes** → all advance in parallel each tick. Each tick's phase = static ∪ each_route_window.
7. **Soft start ramp** → if first phase has K electrodes, prepend K-1 ramp phases ([first[0]], [first[0],first[1]], ...).
8. **Soft end ramp** → if last phase has K electrodes, append K-1 ramp phases shrinking from the trailing edge.

## 5. Persistence + protocol metadata

PPT-1's persistence format already handles columns + rows. PPT-3 adds **per-protocol metadata** stored alongside `schema_version` and `columns`.

### New JSON header shape

```json
{
  "schema_version": 1,
  "protocol_metadata": {
    "electrode_to_channel": {
      "e00": 0, "e01": 1, "e02": 2, "...": "..."
    }
  },
  "columns": [...],
  "fields": [...],
  "rows": [...]
}
```

`protocol_metadata` is optional. Loading a PPT-1/PPT-2 protocol without it → `manager.protocol_metadata = {}`.

### `RowManager` change

```python
protocol_metadata = Dict(Str, Any,
    desc="Per-protocol scratch (electrode→channel mapping, etc.). "
         "Persisted in the JSON header. Keys are namespaced by feature "
         "(e.g. 'electrode_to_channel') to avoid collisions.")
```

### `services/persistence.py` change

```python
def serialize_tree(root, columns, protocol_metadata=None):
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "protocol_metadata": dict(protocol_metadata or {}),
        "columns": col_specs,
        "fields": fields,
        "rows": rows_out,
    }


def deserialize_tree(data, columns, step_type, group_type):
    # ... existing logic ...
    return root, dict(data.get("protocol_metadata") or {})
```

`RowManager.to_json` passes `self.protocol_metadata` through; `RowManager.from_json` populates it from the loaded data.

### Executor wires metadata into ProtocolContext

```python
# pluggable_protocol_tree/execution/executor.py — addition in run()
proto_ctx = ProtocolContext(
    columns=cols,
    stop_event=self.stop_event,
)
proto_ctx.scratch.update(self.row_manager.protocol_metadata)
```

So `RoutesHandler.on_step` reads `ctx.protocol.scratch["electrode_to_channel"]`.

Missing electrode IDs (in `row.electrodes` but not in mapping) get logged at WARNING level and skipped.

## 6. Hide-by-default + header context menu

PPT-1 added `BaseColumnView.hidden_by_default = Bool(False)` but the model never consumed it.

PPT-3 wires the QTreeView in `ProtocolTreeWidget.__init__`:

```python
# After self.tree.setModel(self.model):
for i, col in enumerate(self._manager.columns):
    if getattr(col.view, "hidden_by_default", False):
        self.tree.setColumnHidden(i, True)
```

A header right-click menu is added (`self.tree.header().setContextMenuPolicy(Qt.CustomContextMenu)` + handler) listing every column with toggleable "Show" checkmarks. Selecting the checkmark hides/shows the column at runtime — does not modify the row data.

## 7. Demo `SimpleDeviceViewer`

5×5 grid widget for the demo. Lives in `demos/`. NOT the production device viewer.

```python
class SimpleDeviceViewer(QWidget):
    GRID_W = 5
    GRID_H = 5
    # 25 cells → IDs "e00".."e24"

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._active_row = None
        self._actuated: set[str] = set()
        self._mode = "static"             # 'static' or 'route'
        self._in_progress_route: list[str] = []
        # ... grid layout, mode toolbar (radio), Finish/Clear Route buttons

    def set_active_row(self, row):
        """Called by the demo on tree-selection-change AND by the
        executor's step_started signal."""

    def set_actuated(self, electrode_ids: set[str]):
        """Called by the actuation listener. Paints those cells bright
        green on top of the static/route layers."""

    def _on_cell_clicked(self, electrode_id):
        if self._mode == "static":
            electrodes = list(self._active_row.electrodes)
            if electrode_id in electrodes:
                electrodes.remove(electrode_id)
            else:
                electrodes.append(electrode_id)
            self._active_row.electrodes = electrodes
        else:                              # route mode
            self._in_progress_route.append(electrode_id)
        self.update()

    def _finish_route(self):
        if self._in_progress_route:
            self._active_row.routes = list(self._active_row.routes) + [
                list(self._in_progress_route),
            ]
        self._in_progress_route = []
        self.update()

    def _clear_route(self):
        self._in_progress_route = []
        self.update()
```

### Cell painting Z-order (back to front)

1. Base color (light gray).
2. **Yellow** if `id in row.electrodes`.
3. **Solid line segment** between consecutive electrodes in any `row.routes` entry.
4. **Dashed outline + line** if part of in-progress route (route mode).
5. **Bright green fill** if `id in self._actuated`.

Lines are drawn via the parent `paintEvent` overlay so they don't get clipped at cell boundaries.

### `electrode_responder.py`

```python
@dramatiq.actor(actor_name="ppt_demo_electrode_responder", queue_name="default")
def _responder(message: str, topic: str, timestamp: float = None):
    """Stand-in for a hardware electrode controller. ~50ms apply delay,
    publishes ELECTRODES_STATE_APPLIED."""
    time.sleep(0.05)
    publish_message(message="ok", topic=ELECTRODES_STATE_APPLIED)
```

### Demo wiring (`demos/run_widget.py` changes)

- Embeds `ProtocolTreeWidget` + `SimpleDeviceViewer` in a `QSplitter(Qt.Horizontal)` (sizes 600/400).
- Seeds `manager.protocol_metadata["electrode_to_channel"] = {f"e{i:02d}": i for i in range(25)}`.
- Wires tree's `currentRowChanged` → `device_view.set_active_row(...)`.
- Wires executor's `step_started` → `device_view.set_active_row(...)` (so during a run, the viewer follows the active step).
- Adds a Dramatiq subscription for `ELECTRODES_STATE_CHANGE` → `device_view.set_actuated(payload["electrodes"])` (live overlay).
- Adds the responder's subscription so the round-trip works.

## 8. Testing

### `tests/test_phase_math.py` (~20 tests, pure unit)
- `_is_loop_route` — true cases, false cases, len-1 edge case.
- `_route_windows` — open route trail_length=1, trail_length>len, trail_length=2 with overlay=0 and 1, loop route one cycle.
- `_route_with_repeats` — linear_repeats False (one pass), linear_repeats True with repetitions=3, loop route reps=2, repeat_duration_s caps loop reps, idle pad fills tail.
- `_zip_with_static` — single route + static merges, two routes of different length zip with shorter holding, static-only no routes.
- `_ramp_up` / `_ramp_down` — K=1 no-op, K=3 prepends 2 phases growing.
- `iter_phases` end-to-end — empty routes static-only, single open route, single loop route, two parallel routes, soft_start+soft_end on a 5-electrode line, repeat_duration_s budget exhaustion.

### `tests/test_electrodes_routes_columns.py`
- Factories return columns with right metadata.
- `format_display` text — 0/1/N electrodes; 0/1/N routes.
- Read-only flags (no `ItemIsEditable`).
- Trait-on-row defaults (empty list).

### `tests/test_hidden_columns.py`
- One test per hidden column: factory metadata, `view.hidden_by_default is True`, default value matches the table.

### `tests/test_persistence.py` (extension)
- Round-trip with `protocol_metadata` populated → comes back identical.
- Backward-compat: load JSON without `protocol_metadata` → `manager.protocol_metadata == {}`.

### `tests/tests_with_redis_server_need/test_routes_handler_redis.py`
- One step with `electrodes=["e00","e01"]`, `routes=[["e02","e03","e04"]]`, `trail_length=1`, default config.
- Subscribes the demo electrode_responder to `ELECTRODES_STATE_CHANGE`.
- Subscribes the executor listener to `ELECTRODES_STATE_APPLIED`.
- Runs one step; collects all published phase payloads from a spy actor on `ELECTRODES_STATE_CHANGE`.
- Asserts: 3 phases (one per route position), each phase's `electrodes` list is `static ∪ {e02|e03|e04}`, channels match the seeded mapping, total step duration ≈ 3 × ack_delay + duration_s.

### Acceptance bar for PPT-3 merge
- All `pluggable_protocol_tree/tests/` pass without Redis.
- Redis-backed test passes with `redis-server` running.
- Demo: open `run_widget`, click squares to add static electrodes, switch to Route mode + click sequence + Finish, click Run; live green overlay walks along the route as `RoutesHandler` publishes each phase.

## 9. Issue tracking

- Sub-issue: `#365 [PPT-3] Electrodes + Routes columns + device-viewer binding + phase math lift`. PR closes via `Closes #365`.
- The "device-viewer binding" half of the issue title is intentionally deferred per design decision #4. The sub-issue title is kept as-is for historical continuity.

## 10. What's deferred to later sub-issues

- Production device-viewer integration (binding service that publishes `STEP_PARAMS_COMMIT` on row-select and subscribes to `DEVICE_VIEWER_STATE_CHANGED` on user clicks). Either a small follow-up sub-issue or absorbed into PPT-9's legacy-deletion PR.
- Editing electrodes/routes in the production device viewer.
- Deleting `protocol_grid/state/device_state.py` and the legacy `protocol_runner_controller.py` actuation loop. PPT-9.
- Cross-device `electrode_to_channel` mapping reconciliation (warn on mismatch, remap by ID where possible). For now the persisted mapping is trusted as-is.
- Multiple concurrent waiters on the same topic (PPT-2 left this out; nothing in PPT-3 changes it).
