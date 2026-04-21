# Pluggable Protocol Tree — Design Spec

**Date:** 2026-04-21
**Status:** Draft, pre-implementation
**Related work:** `origin/pluggable_protocol_tree` (reference, not authoritative)

## 1. Goal

Replace the monolithic `protocol_grid` plugin with a pluggable version in which columns — their model, view, and runtime behaviour — are contributed by any plugin. The core plugin owns the tree structure, selection, clipboard, persistence, and execution loop; it knows nothing about what columns exist. Plugins contribute columns through an Envisage extension point; their runtime logic runs inside a shared priority-bucketed executor coordinated with dramatiq via a simple `ctx.wait_for(topic, timeout)` API.

Migration is incremental. The existing `protocol_grid` plugin keeps running in parallel. Features are ported column-by-column into their owning plugin. Old code is deleted only when its replacement is proven.

## 2. Locked-in decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Migration scope | Core skeleton first, then migrate features incrementally into their owning plugins |
| Async control flow for hooks | Sync-looking helper: `ctx.wait_for(topic, timeout)` |
| Hook fan-out across columns | Priority buckets (default 50), buckets sequential, columns within bucket parallel |
| Row data storage | Per-protocol dynamic `HasTraits` subclass built from active column set |
| Step duration | Default contributed column, not a hard-coded trait |
| Group semantics | Groups render all columns (column decides); executor flattens groups + expands repetitions |
| Column contribution mechanism | Custom Envisage extension point `PROTOCOL_COLUMNS` |
| Row manager API | Single `RowManager` (HasTraits) service with structure/selection/clipboard/slicing/persistence |
| Clipboard | System `QClipboard` with MIME `application/x-microdrop-rows+json` |
| Selection shape | `List[Tuple[int, ...]]` (paths, not row refs) |
| Slicing | Pandas DataFrame facade (read); imperative API (write) |
| Persistence | Compact JSON: metadata columns + depth-encoded row tuples + plugin class paths |
| Backward compat with legacy file format | No |
| UUIDs on rows | Yes (for future merge/diff; regenerated on copy/paste) |
| Electrode + Routes columns | Built into core plugin (not separable) |
| Trail/loop/ramp knobs | Hidden-by-default per-step columns, defaults from `ProtocolPreferences` |
| First migration target | Voltage + Electrodes/Routes (exercises the hard parts first) |
| Pause / resume / stop | Stop + pause between steps; no mid-hook interruption |
| Convention | All new classes are `HasTraits` with typed traits, defaults, `desc`, observers |

## 3. Architecture overview

Three layers:

1. **Data layer** — `BaseRow`, `GroupRow`, dynamic per-protocol row subclass, `RowManager`.
2. **View layer** — Qt tree widget, tree model adapter, per-column editors, dock pane.
3. **Execution layer** — `ProtocolExecutor`, `StepContext` with `wait_for`, dramatiq listener.

Everything is wired together by the core `PluggableProtocolTreePlugin`. Contributed columns (`IColumn` instances, each bundling `IColumnModel` + `IColumnView` + `IColumnHandler`) enter through the `PROTOCOL_COLUMNS` extension point.

### Three-way concern split for columns

- **`IColumnModel`** — semantics: `col_id`, `col_name`, `default_value`, `trait_for_row()`, `serialize()`, `deserialize()`.
- **`IColumnView`** — presentation: `format_display()`, `create_editor()`, `get_flags()`, hints (`decimals`, `single_step`, `hidden_by_default`, `renders_on_group`).
- **`IColumnHandler`** — behaviour: priority bucket, `on_interact()`, five execution hooks (`on_protocol_start`, `on_pre_step`, `on_step`, `on_post_step`, `on_protocol_end`).

Reuse: two plugins can use the same model with different views, or the same view with different handlers.

## 4. Package layout

```
pluggable_protocol_tree/              # new core package
├── __init__.py
├── plugin.py                         # PluggableProtocolTreePlugin, PROTOCOL_COLUMNS extension point
├── consts.py                         # PKG, topic constants, ACTOR_TOPIC_DICT
│
├── interfaces/
│   ├── i_column.py                   # IColumn, IColumnModel, IColumnView, IColumnHandler
│   └── i_row.py                      # IRow, IGroupRow
│
├── models/
│   ├── row.py                        # BaseRow, GroupRow, build_row_type()
│   ├── column.py                     # BaseColumnModel and typed variants
│   └── row_manager.py                # RowManager (HasTraits)
│
├── views/
│   ├── tree_widget.py                # Qt widget (QTreeView + delegate + context menu)
│   ├── qt_tree_model.py              # QAbstractItemModel adapter over RowManager
│   ├── dock_pane.py                  # Envisage DockPane factory
│   └── columns/                      # built-in column views
│       ├── base.py                   # BaseColumnView
│       ├── spinbox.py                # IntSpinBoxColumnView, DoubleSpinBoxColumnView
│       ├── checkbox.py               # CheckboxColumnView
│       ├── string_edit.py            # StringEditColumnView
│       └── readonly_label.py         # label-only view (for id/type)
│
├── execution/
│   ├── executor.py                   # ProtocolExecutor (HasTraits, QThread-hosted)
│   ├── step_context.py               # StepContext, ProtocolContext, wait_for machinery
│   ├── listener.py                   # dramatiq listener feeding StepContext mailboxes
│   └── signals.py                    # ExecutorSignals (QObject) for UI updates
│
├── builtins/                         # columns shipped by core plugin
│   ├── type_column.py                # read-only step/group label
│   ├── id_column.py                  # read-only dotted-path id (derived)
│   ├── name_column.py                # free text
│   ├── duration_column.py            # float seconds
│   ├── repetitions_column.py         # int, renders on groups + steps
│   ├── electrode_activation_column.py # List[ElectrodeID]
│   ├── routes_column.py              # List[List[ElectrodeID]]; handler publishes phase messages
│   └── trail_config_columns.py       # trail_length, trail_overlay, soft_start, soft_end,
│                                     # repeat_duration, linear_repeats (hidden by default)
│
├── services/
│   ├── device_viewer_binding.py      # Two-way binding for electrode/routes columns
│   ├── persistence.py                # Save/load to compact JSON
│   └── phase_math.py                 # Pure helpers lifted from path_execution_service.py
│
├── tests/
│   ├── test_row_manager.py
│   ├── test_executor.py
│   ├── test_persistence.py
│   ├── test_device_viewer_binding.py
│   └── tests_with_redis_server_need/
│       └── test_wait_for_integration.py
│
└── demos/
    └── run_protocol_tree_pluggable.py
```

## 5. Plugin contribution

```python
# pluggable_protocol_tree/plugin.py
PROTOCOL_COLUMNS = "pluggable_protocol_tree.protocol_columns"

class PluggableProtocolTreePlugin(Plugin):
    id = PKG + ".plugin"
    name = PKG_name

    # Extension point: other plugins contribute IColumn instances here
    columns = ExtensionPoint(List(Instance(IColumn)), id=PROTOCOL_COLUMNS)

    # Standard plumbing
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
```

A contributing plugin:

```python
class DropbotControllerPlugin(Plugin):
    protocol_columns = List(contributes_to=PROTOCOL_COLUMNS)

    def _protocol_columns_default(self):
        return [
            Column(
                model=BaseColumnModel(col_id="voltage", col_name="Voltage",
                                      default_value=100.0),
                view=DoubleSpinBoxColumnView(low=0, high=200, decimals=1, single_step=1.0),
                handler=VoltageHandler(priority=20),   # runs before default 50 bucket
            ),
        ]
```

Display column order is extension-contribution order. Column **priority** only governs execution fan-out, not display. Plugin load order (from `plugin_consts.py`) determines contribution order: the core plugin loads first so the extension point exists; contributors load in the order listed.

## 6. Column contract

```python
# interfaces/i_column.py

class IColumnModel(Interface):
    col_id        = Str
    col_name      = Str
    default_value = Any

    def trait_for_row(self) -> TraitType: ...
    def get_value(self, row) -> Any: ...
    def set_value(self, row, value) -> bool: ...
    def serialize(self, value) -> Any: ...
    def deserialize(self, raw) -> Any: ...


class IColumnView(Interface):
    hidden_by_default = Bool(False)
    renders_on_group  = Bool(True)

    def format_display(self, value, row) -> str: ...
    def get_flags(self, row) -> int: ...
    def get_check_state(self, value, row) -> Any: ...
    def create_editor(self, parent, context) -> QWidget: ...
    def set_editor_data(self, editor, value): ...
    def get_editor_data(self, editor) -> Any: ...


class IColumnHandler(Interface):
    priority        = Int(50)
    wait_for_topics = List(Str, desc="Topics this handler may call ctx.wait_for() on; "
                                     "aggregated by core plugin to configure the executor's listener")

    def on_interact(self, row, model, value) -> bool: ...

    def on_protocol_start(self, ctx): ...
    def on_pre_step(self, row, ctx): ...
    def on_step(self, row, ctx): ...
    def on_post_step(self, row, ctx): ...
    def on_protocol_end(self, ctx): ...


class IColumn(Interface):
    model   = Instance(IColumnModel)
    view    = Instance(IColumnView)
    handler = Instance(IColumnHandler)
```

Base implementations (`models/column.py`, `views/columns/base.py`) cover the 80% case: plugin authors subclass only what they need. `BaseColumnHandler` implements all five execution hooks as no-ops; `on_interact` defaults to `model.set_value(row, value)`, which is enough for most columns.

## 7. Row model

```python
# models/row.py
class BaseRow(HasTraits):
    uuid     = Str(desc="Stable identity for merges/diffs and device-viewer routing")
    name     = Str("Step", desc="User-visible row name")
    parent   = Instance("BaseRow", desc="Owning GroupRow (None for root children)")
    row_type = Str("step", desc="'step' or 'group' — drives per-column visibility")
    path     = Property(Tuple, observe="parent, parent.children.items",
                        desc="0-indexed tuple of positions from root")

    def _uuid_default(self):
        return uuid.uuid4().hex


class GroupRow(BaseRow):
    row_type = "group"
    children = List(BaseRow)

    def add_row(self, row): row.parent = self; self.children.append(row)
    def insert_row(self, idx, row): row.parent = self; self.children.insert(idx, row)
    def remove_row(self, row): self.children.remove(row); row.parent = None


def build_row_type(columns, base=BaseRow, name="ProtocolStepRow") -> type:
    class_dict = {col.model.col_id: col.model.trait_for_row() for col in columns}
    return type(name, (base,), class_dict)
```

Every protocol-open builds a fresh `StepRowType` (from `BaseRow`) and `GroupRowType` (from `GroupRow`). Closing garbage-collects the subclasses. No runtime mutation of shared classes.

Columns with `renders_on_group=False` still contribute their trait to the group's subclass (so serialization is symmetric), but the view returns `None` for display — the executor stays ignorant of which columns "apply" to which row.

## 8. RowManager

Single `HasTraits` service for every tree operation:

```python
# models/row_manager.py
class RowManager(HasTraits):
    # Structure
    root       = Instance(GroupRow)
    columns    = List(Instance(IColumn))
    step_type  = Instance(type)   # dynamic StepRow subclass
    group_type = Instance(type)   # dynamic GroupRow subclass

    # Selection
    selection = List(Tuple(Int), desc="List of 0-indexed path tuples")

    # Clipboard
    clipboard_mime = Str("application/x-microdrop-rows+json")

    # Events
    rows_changed = Event(desc="Fires on structure/value change; batch-coalesced")

    # --- Structure ---
    def add_step(self, parent_path=(), index=None, values=None) -> Tuple[int, ...]: ...
    def add_group(self, parent_path=(), index=None, name="Group") -> Tuple[int, ...]: ...
    def remove(self, paths: List[Tuple[int, ...]]): ...
    def move(self, paths, target_parent_path, target_index): ...

    # --- Selection ---
    def select(self, paths, mode: Literal["set","add","range"] = "set"): ...
    def selected_rows(self) -> List[BaseRow]: ...
    def get_row(self, path) -> BaseRow: ...
    def get_row_by_uuid(self, uuid: str) -> Optional[BaseRow]: ...

    # --- Clipboard ---
    def copy(self): ...
    def cut(self):  ...
    def paste(self, target_path=None): ...   # fresh UUIDs on insertion

    # --- Slicing (read-only, pandas-backed) ---
    @property
    def table(self) -> pd.DataFrame:
        """Snapshot. Index = path tuple. Columns = col_id. Rebuilt on call."""
    def rows(self, selector) -> pd.DataFrame: ...
    def cols(self, col_ids: List[str]) -> pd.DataFrame: ...
    def slice(self, rows=None, cols=None) -> pd.DataFrame: ...

    # --- Imperative write ---
    def set_value(self, path, col_id, value): ...
    def set_values(self, paths, col_id, value): ...
    def apply(self, paths, fn): ...

    # --- Execution view ---
    def iter_execution_steps(self) -> Iterator[BaseRow]:
        """Flatten groups; expand repetitions; yield step rows only."""

    # --- Persistence ---
    def to_json(self) -> dict: ...
    @classmethod
    def from_json(cls, data: dict, columns: List[IColumn]) -> "RowManager": ...
```

Design notes:

- **Selection is paths**, not row refs — paths survive mutations during paste; row refs become invalid after remove-then-paste.
- **Read via DataFrame, write via imperative API.** Mutating a DataFrame snapshot would introduce two sources of truth. `set_value`/`set_values`/`apply` emit trait-change events the UI observes.
- **`iter_execution_steps` flattens and expands repetitions in one place** — the executor stays ignorant of groups. Nested groups compose: outer rep N × inner rep M = N×M innermost iterations.
- **Copy generates fresh UUIDs on paste** — otherwise pasting a step creates two rows with the same uuid, breaking device-viewer routing and any future merge semantics.

## 9. Executor

```python
# execution/executor.py
class ProtocolExecutor(HasTraits):
    row_manager = Instance(RowManager)
    columns     = List(Instance(IColumn))

    # Control
    pause_event = Instance(Event)
    stop_event  = Instance(Event)

    # Progress
    qsignals = Instance(ExecutorSignals)   # QObject with Qt signals

    def run(self):
        """Main loop. Runs on a QThread."""
        try:
            proto_ctx = ProtocolContext(columns=self.columns)
            self._run_hooks("on_protocol_start", proto_ctx)
            self.qsignals.protocol_started.emit()

            for row in self.row_manager.iter_execution_steps():
                if self.stop_event.is_set():
                    break
                if self.pause_event.is_set():
                    self.pause_event.wait_cleared()

                step_ctx = StepContext(row=row, protocol=proto_ctx)
                self.qsignals.step_started.emit(row)

                self._run_hooks("on_pre_step",  step_ctx, row)
                self._run_hooks("on_step",      step_ctx, row)
                self._run_hooks("on_post_step", step_ctx, row)

                self.qsignals.step_finished.emit(row)

            self._run_hooks("on_protocol_end", proto_ctx)
            (self.qsignals.protocol_finished
             if not self.stop_event.is_set()
             else self.qsignals.protocol_aborted).emit()
        except Exception as e:
            logger.exception("Protocol error")
            self.qsignals.protocol_error.emit(str(e))

    def _run_hooks(self, hook_name, ctx, row=None):
        """Priority-bucket fan-out. Lower priority first. Same priority → parallel."""
        buckets = group_by_priority(self.columns)
        for priority, cols in sorted(buckets.items()):
            with ThreadPoolExecutor(max_workers=len(cols)) as pool:
                futures = [pool.submit(self._invoke_hook, col, hook_name, ctx, row)
                           for col in cols]
                for f in as_completed(futures):
                    if f.exception():
                        raise f.exception()   # first failure aborts the step
```

**Qt signals** (on `ExecutorSignals`, a `QObject`): `protocol_started`, `step_started(row)`, `step_finished(row)`, `protocol_finished`, `protocol_aborted`, `protocol_error(str)`.

**Stop semantics.** Checked at every step boundary. Mid-step `ctx.wait_for()` calls also accept the stop event and return immediately if it fires — a long timeout doesn't delay abort.

**Error semantics.** When a hook raises inside a bucket, the executor sets `stop_event` so any other running hooks' `wait_for` calls return promptly, then waits for the bucket's thread pool to drain (threads can't be forcibly interrupted, but `wait_for` and inter-phase loops cooperatively check `stop_event`). Once drained, the original exception propagates: `on_protocol_end` runs as best-effort cleanup, and `protocol_error` is emitted. No retry. Hook authors handle their own resilience if they want it.

**Pause semantics.** Checked between steps only. No mid-hook interruption — simpler state machine, hook authors don't need to think about interruption.

## 10. StepContext and `wait_for`

```python
# execution/step_context.py
class StepContext(HasTraits):
    row      = Instance(BaseRow)
    protocol = Instance(ProtocolContext)
    scratch  = Dict(Str, Any, desc="Per-step hook-to-hook handoff")

    def wait_for(self, topic: str, timeout: float = 5.0,
                 predicate: Callable = None) -> Any:
        """Block until a message on `topic` arrives (optionally satisfying
        predicate). Returns the payload. Raises TimeoutError on timeout.
        Raises AbortError if the executor's stop_event fires."""
```

**Mechanism.** The executor owns a single dramatiq listener (one actor, one queue — `pluggable_protocol_tree_executor_listener`). When a hook calls `ctx.wait_for("topic")`, the context registers a `threading.Event` + mailbox entry in a shared table keyed by `(step_uuid, topic)`. The listener consumes every incoming message; for any topic with a registered waiter, it enqueues the payload and sets the event. `wait_for` is `event.wait(timeout)` then drains the mailbox.

**Topic routing.** The executor's listener is a separate subscriber from any contributing plugin's listener, so it needs its own subscription list. Each `IColumnHandler` declares the topics it might wait on:

```python
class IColumnHandler(Interface):
    priority = Int(50)
    wait_for_topics = List(Str, desc="Topics this handler may call ctx.wait_for() on")
    ...
```

At plugin start, the core `PluggableProtocolTreePlugin` aggregates `wait_for_topics` from every contributed handler and registers them with the message router under the executor listener's name. This keeps the contributor plugin's own `ACTOR_TOPIC_DICT` untouched (it only governs that plugin's own listeners, if any) and makes the executor's subscription list discoverable at runtime rather than hand-maintained.

Usage inside a handler:

```python
class VoltageHandler(BaseColumnHandler):
    priority        = 20
    wait_for_topics = ["dropbot/voltage_set_ack"]

    def on_step(self, row, ctx):
        publish_message(topic=SET_VOLTAGE, message={"v": row.voltage})
        ack = ctx.wait_for("dropbot/voltage_set_ack", timeout=5.0)
        return ack["ok"]
```

## 11. Complex columns: Electrodes and Routes

Built into the core plugin (not a separate plugin — core enough that decoupling brings only cost).

**`ElectrodeActivationColumn`** — value is `List[ElectrodeID]` (strings), the electrodes held active for the step. View: read-only cell summary (`"3 electrodes"`). Editing happens via the device viewer.

**`RoutesColumn`** — value is `List[List[ElectrodeID]]`, list of ordered paths. View: read-only cell summary (`"2 routes"`). Editing via the device viewer.

### Routes handler (replaces protocol_runner_controller's actuation loop)

```python
class RoutesHandler(BaseColumnHandler):
    priority        = 30   # after voltage-set (20), before settle hooks (50)
    wait_for_topics = ["electrodes/state_applied"]

    def on_step(self, row, ctx):
        if not row.routes:
            return
        phases = calculate_phases_for_step(row)   # reads trail_length, trail_overlay,
                                                  # soft_start, soft_end, loop/repeat
                                                  # flags from the row
        for phase_electrodes in phases:
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message={"active": phase_electrodes},
            )
            ctx.wait_for("electrodes/state_applied", timeout=1.0)
```

`calculate_phases_for_step` is a pure function in `services/phase_math.py`, which is where the reusable helpers from `path_execution_service.py` go: `calculate_trail_phases_for_path`, `calculate_loop_cycle_phases`, `calculate_effective_repetitions_for_path`, `calculate_loop_balance_idle_phases`, ramp helpers. The 638-line `path_execution_service.py` shrinks to those helpers plus the handler above; the rest (stateful step-time calculation reaching into string-parsed `ProtocolStep.parameters`, the lazy-import preference hack, the phase-execution sequencing in `protocol_runner_controller.py`) is deleted.

### Trail / loop / ramp knobs

Implemented as hidden-by-default per-step columns shipped by the core plugin:

| col_id | type | default source |
|---|---|---|
| `trail_length` | Int | `ProtocolPreferences.trail_length` |
| `trail_overlay` | Int | `ProtocolPreferences.trail_overlay` |
| `soft_start` | Bool | `ProtocolPreferences.soft_start` |
| `soft_end` | Bool | `ProtocolPreferences.soft_end` |
| `repeat_duration` | Float | `ProtocolPreferences.repeat_duration` |
| `linear_repeats` | Bool | `ProtocolPreferences.linear_repeats` |

Column header right-click menu toggles visibility. Seeded from preferences on new-step insertion.

## 12. Device-viewer binding

```python
# services/device_viewer_binding.py
class DeviceViewerBinding(HasTraits):
    row_manager = Instance(RowManager)
    editing_uuid = Str(desc="UUID of the row currently bound to the device viewer")

    @observe("editing_uuid")
    def _push_editing_state(self, event):
        row = self.row_manager.get_row_by_uuid(self.editing_uuid)
        if row is None:
            return
        publish_message(
            topic=PROTOCOL_EDITING_STEP,
            message={
                "uuid": row.uuid,
                "activated_electrodes": row.activated_electrodes,
                "routes": row.routes,
            },
        )

    def on_device_viewer_step_update(self, message, topic):
        row = self.row_manager.get_row_by_uuid(message["uuid"])
        if row is None:
            return   # stale uuid, row was deleted
        row.activated_electrodes = message["activated_electrodes"]
        row.routes               = message["routes"]
```

Device viewer plugin changes:
- Subscribe to `PROTOCOL_EDITING_STEP` (replaces `STEP_PARAMS_COMMIT` + `DeviceViewerMessageModel`).
- Publish `DEVICE_VIEWER_STEP_UPDATE` on user electrode clicks / route draws.

The existing `DeviceState` class and `device_state_from/to_device_viewer_message` bridges are deleted. Row traits become the single source of truth.

## 13. Persistence format

Compact JSON with column class paths for plugin identification:

```json
{
  "schema_version": 1,
  "columns": [
    {"id": "type",                  "cls": "pluggable_protocol_tree.builtins.type_column.RowTypeColumn"},
    {"id": "name",                  "cls": "pluggable_protocol_tree.builtins.name_column.NameColumn"},
    {"id": "duration_s",            "cls": "pluggable_protocol_tree.builtins.duration_column.DurationColumn"},
    {"id": "activated_electrodes",  "cls": "pluggable_protocol_tree.builtins.electrode_activation_column.ElectrodeActivationColumn"},
    {"id": "routes",                "cls": "pluggable_protocol_tree.builtins.routes_column.RoutesColumn"},
    {"id": "voltage",               "cls": "dropbot_controller.columns.VoltageColumn"}
  ],
  "fields": ["depth", "uuid", "type", "name", "duration_s",
             "activated_electrodes", "routes", "voltage"],
  "rows": [
    [0, "a3f7...", "group", "Wash",      null, null,          null,                   null],
    [1, "b1e9...", "step",  "Drop on",   2.0,  ["e1","e2"],   [["e1","e2","e3"]],    100.0],
    [1, "b2a0...", "step",  "Drop off",  1.0,  [],            [],                     50.0],
    [0, "c4d5...", "step",  "Settle",    5.0,  [],            [],                      0.0]
  ]
}
```

### Format rules

- **`depth`** (first tuple element) encodes nesting: 0 = top-level, 1 = inside a group, etc. When loading, each row becomes a child of the most recent open row at `depth - 1`. Group membership is sequence-derived.
- **`uuid`** is the stable row identity. Round-tripped. Regenerated on copy/paste.
- **`cls`** for each column is `module.ClassName` for the column's *model* class. On load, `importlib.import_module` resolves it and matches against the live column set by class identity.
- **`fields`** is the tuple schema for `rows`; always `["depth", "uuid", "type", "name", ...col_ids]`.

### Load resolution

For each column spec, three cases:

1. **Class imports, plugin contributed it** — use the live column (its config is current), load values in.
2. **Class imports, plugin did not contribute it** — warn once; values stored in a `_orphan_values` dict on each row. Re-saving round-trips them.
3. **Class does not import** (plugin uninstalled) — warn once; raw spec + values preserved in `_orphan_values`. Re-saving round-trips.

Orphan preservation means sharing a protocol with a teammate who hasn't installed the magnet plugin doesn't destroy their data.

### Clipboard uses the same format

`application/x-microdrop-rows+json` MIME, payload is this structure minus `schema_version` (clipboard is transient). Cross-process paste works; paste into a text editor for inspection works.

## 14. Built-in columns shipped by core

| col_id | View | Hidden by default | Renders on group | Priority |
|---|---|---|---|---|
| `type` | read-only label | no | yes | — |
| `id` | read-only dotted-path (1-indexed) | no | yes | — |
| `name` | line edit | no | yes | — |
| `duration_s` | double spinner | no | no | — |
| `repetitions` | int spinner | no | yes | — |
| `activated_electrodes` | cell summary + device-viewer | no | no | 30 |
| `routes` | cell summary + device-viewer | no | no | 30 |
| `trail_length` | int spinner | yes | no | — |
| `trail_overlay` | int spinner | yes | no | — |
| `soft_start` | checkbox | yes | no | — |
| `soft_end` | checkbox | yes | no | — |
| `repeat_duration` | double spinner | yes | no | — |
| `linear_repeats` | checkbox | yes | no | — |

Priority `—` means the column has no execution hooks (no `on_step` / `on_pre_step` / etc.) — it's purely data/UI, so its priority is irrelevant. The `id` column's view converts the internal 0-indexed `row.path` tuple to a 1-indexed dotted string (`"1.2.3"`) for display.

## 15. Issue tracking workflow

### Umbrella issue

`[Pluggable Protocol Tree] Replace monolithic protocol_grid with pluggable column architecture`

- Body: 3–4 paragraph architecture summary lifted from this spec.
- Links to this design doc.
- Checklist of sub-issues (`- [ ] #N — <title>`).
- Stays open until every sub-issue closes.

### Sub-issues (initial set; more added as scope clarifies)

1. `[PPT-1] Core skeleton: interfaces, BaseRow/GroupRow, RowManager`
2. `[PPT-2] Executor + StepContext.wait_for + pause/stop`
3. `[PPT-3] Electrodes + Routes columns + device-viewer binding + phase math lift`
4. `[PPT-4] Voltage + Frequency columns (dropbot_controller contribution)`
5. `[PPT-5] Migrate magnet column (peripheral_controller contribution)`
6. `[PPT-6] Migrate video / capture / record columns`
7. `[PPT-7] Migrate force calculation`
8. `[PPT-8] Migrate droplet detection`
9. `[PPT-9] Delete legacy protocol_grid plugin`

Each sub-issue:
- Links up with `Part of #<umbrella>`.
- Body summarizes the relevant slice of this spec: files changed, acceptance criteria, tests that must pass. Standalone readable — no need to open the full spec to scope.
- Closed by exactly one PR.

Each PR:
- Title `[PPT-N] <title>`.
- Body has detailed implementation notes: what was added/changed/removed, any deviations from this design with justification, screenshots if UI work.
- Includes `Closes #<sub-issue>` so merge auto-closes the sub-issue and ticks the umbrella's checklist.

Three layers of detail, kept in sync: design doc (full), umbrella (architecture + progress), sub-issue (per-step scope), PR (implementation log).

## 16. Migration plan

Incremental, one PR per sub-issue:

1. **PPT-1 — Skeleton.** New package. Interfaces, `BaseRow`/`GroupRow`, dynamic row subclass builder, `RowManager`. Four built-in columns (`type`, `id`, `name`, `duration_s`). No executor, no hardware. `demos/run_widget.py` opens a grid. Tests: row CRUD, clipboard, slicing, save/load round-trip.
2. **PPT-2 — Executor.** `ProtocolExecutor` with priority buckets, `StepContext.wait_for`, pause/stop. Toy `MessageColumn` (publishes a log line on `on_step`) as exercise. Tests: fan-out ordering, wait_for timeout, stop mid-wait, pause/resume.
3. **PPT-3 — Electrodes, Routes, device-viewer binding.** `ElectrodeActivationColumn`, `RoutesColumn`, lift of phase math from `path_execution_service.py`, `DeviceViewerBinding` service. Small device-viewer PR: publish/subscribe new topics, delete `DeviceState`. Tests: phase generation against real SVG fixtures, binding round-trips.
4. **PPT-4 — Voltage + Frequency.** Contributed by `dropbot_controller` plugin. Uses `ctx.wait_for` for ack. Integration test against mocked dropbot proxy; hardware test against real dropbot.
5. **PPT-5..PPT-8 — Remaining features.** One PR per feature, each adds a contributed column and deletes the corresponding code from `protocol_grid/`.
6. **PPT-9 — Delete legacy plugin.** `protocol_grid/` removed; `plugin_consts.py` updated.

## 17. Testing strategy

- **Unit per column** — model serialize/deserialize round-trip; view `format_display`; handler hooks with a mocked `ctx` (fake `wait_for`).
- **RowManager** — structure mutations, selection invariants across moves, clipboard round-trip, pandas slicing correctness, save/load with missing-plugin simulation.
- **Executor** — priority bucket ordering, parallel fan-out, `wait_for` timeout, stop/pause, error propagation. Dramatiq mocked via stub listener.
- **Integration (`tests_with_redis_server_need/`)** — real dramatiq; assert `ctx.wait_for` receives messages end-to-end.
- **Hardware (`tests_with_dropbot_connection_need/`)** — voltage/frequency columns against real dropbot; flat 3-step protocol.

## 18. Out of scope (deferred)

- Backward compat with legacy `tree_data_save.json` files.
- Real protocol merge/diff algorithm (UUIDs in place; algorithm is future work).
- Schema-version migrations when a column changes its value type.
- DataFrame mutation as a write path (stays snapshot-only).
- Pause mid-hook (pause is between steps only).
- Async / coroutine hooks (sync hooks only; `wait_for` blocks the hook's thread).

## 19. Open questions flagged for implementation phase

- Exact pandas dtype handling for object-typed columns (list-of-lists). Likely `object` dtype with per-column accessors; to validate during PPT-1 testing.
- Whether the `executor` should run on its own `QThread` or re-use existing worker thread infrastructure from `protocol_grid`. Decided during PPT-2 when concrete constraints surface.
- UI treatment of hidden columns (header right-click menu vs. preferences pane vs. view submenu). Decided during PPT-1.
