# PPT-10.2 (subset) Design — Bidirectional electrode sync between protocol tree and device viewer

**Date:** 2026-05-11
**Status:** Draft, pre-implementation
**Issue:** [#414 — PPT-10.2 wire pluggable_protocol_tree dock pane to device viewer + DropBot listeners](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/414)
**Parent:** [#361 — Pluggable Protocol Tree umbrella](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/361)
**Closest precedent:** PPT-10.1 (PR #411) — same pane, same dock-pane mounting, same Trait-injection pattern.

## 0. Scope

Wire the pluggable protocol tree's dock pane bidirectionally to the device viewer for **electrode state only**. Specifically:

- **Tree → DV:** when the user selects a step in the tree, the device viewer displays that step's static electrodes and route overlay.
- **DV → tree:** when the user toggles electrodes in the device viewer with no step selected (free mode), the toggles are captured. On the next step click, a `confirm` dialog asks "Insert as new step / Discard". Insert appends a new step at the end of the root with the captured electrodes + routes.
- **Deselect / group click:** clears the device viewer back to free mode (editable, no electrodes lit).
- **Protocol-running gate:** the pane publishes `PROTOCOL_RUNNING` on start/finish/abort so the DV (and the new sync controller itself) suppresses sync activity during a run.

This is the `device_viewer_state_changed` row of issue #414's listener table — a self-contained subset that lets the new pane own the device-viewer relationship the same way the legacy `protocol_grid` does today.

**Out of scope** (deferred to follow-up specs against the same issue):

- DropBot connection-state gating (`DROPBOT_CONNECTED` / `DISCONNECTED` / `CHIP_INSERTED`) and the "Disconnected Before Run" dialog.
- Capacitance overlay during execution.
- Droplet-detection failure dialog (already covered by PPT-8 separately).
- `routes_executing` / `device_viewer_recording_state` UI gating.
- `voltage_frequency_range_changed`, `calibration_data`, `step_params_commit`, `advanced_mode_change`, `zstage_position_updated`, `device_viewer_media_captured`.

## 1. Decisions locked in during brainstorming

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Scope of this spec | Just bidirectional electrode sync + free-mode prompt | Smallest blast radius; ships fastest; the rest of #414 is independently addressable. |
| 2 | Topic strategy for tree → DV | New tree-specific topic + new slim Pydantic model | Cleaner separation than reusing `PROTOCOL_GRID_DISPLAY_STATE`; legacy stays untouched while migration finishes; new model owns its own contract. Trade-off: one new handler on DV side. |
| 3 | What to push on step selection | Static electrodes + routes overlay | Matches legacy display semantics; routes column entries are part of "what's on this step." |
| 4 | Insert location for free-mode capture | Append at end of root | Matches legacy (`state.sequence.append`); predictable; avoids ambiguity inside groups. |
| 5 | Dialog buttons | YES (Insert as New Step) / NO (Discard); no Cancel | Matches legacy `confirm` usage; Cancel would create an in-between state where the click happened but selection didn't move. |
| 6 | Architectural shape | Dedicated `DeviceViewerSyncController` service | Matches existing `application` / `experiment_manager` / `sticky_manager` injection pattern; pane stays focused; controller is independently testable; natural place to grow when remaining #414 listeners land. |
| 7 | Tree-mutation API for free-mode capture | Use existing `RowManager.add_step / add_group / remove / move` | These are already public, already cover what we need (and more). No new RowManager API is added by this spec. Free-mode capture calls `add_step(parent_path=(), index=None, values={...})`. |
| 8 | Lean `id_to_channel` publishing | Two-phase: introduce `DEVICE_VIEWER_GEOMETRY_CHANGED` now, lean the state payload later (PPT-9 timing) | DV publishes the ~120-entry mapping on every state message today. Splitting it onto its own topic published only on geometry change (chip insert / SVG load) is the right shape. But `protocol_grid` consumes `id_to_channel` from the state topic in 30+ places, so removing the field from state messages now would require touching code that's about to be deleted. Phase 1 (this spec): add the new topic, our controller caches from it. Phase 2 (PPT-9 / [#415](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/415)): flip the state publisher to omit the mapping. |
| 9 | Where the mapping lives in the protocol | Single source of truth: `RowManager.protocol_metadata["electrode_to_channel"]` | This trait already exists for exactly this purpose ("Per-protocol scratch persisted in the JSON header. Keys are namespaced by feature ('electrode_to_channel', etc.)"). The executor already hydrates it into `ProtocolContext.scratch`. NO per-step or per-row storage — that was a legacy quirk in `protocol_grid.state.device_state.id_to_channel` that this spec deliberately does not reproduce. Controller writes to `protocol_metadata["electrode_to_channel"]` on geometry-changed; persistence is automatic via `to_json()`. **Full lifecycle traced in the [companion doc](./2026-05-11-issue-414-id-to-channel-lifecycle.md)**. |

## 2. File layout

```
microdrop-py/src/pluggable_protocol_tree/
├── consts.py                                            # MODIFIED — add PROTOCOL_TREE_DISPLAY_STATE
├── models/
│   └── display_state.py                                 # NEW — ProtocolTreeDisplayMessage Pydantic model
├── services/
│   └── device_viewer_sync.py                            # NEW — DeviceViewerSyncController + Qt signal bridge
├── views/
│   ├── protocol_tree_pane.py                            # MODIFIED — accept device_viewer_sync kwarg;
│   │                                                    #            wire suppress_publish into _select_step /
│   │                                                    #            clear_highlights / executor highlight signal;
│   │                                                    #            publish PROTOCOL_RUNNING on start/finish/abort
│   ├── dock_pane.py                                     # MODIFIED — instantiate controller and pass it in
│   └── tree_widget.py                                   # MODIFIED — promote _index_to_path to public index_to_path
└── tests/
    ├── test_device_viewer_sync.py                       # NEW
    └── tests_with_redis_server_need/
        └── test_device_viewer_sync_redis.py             # NEW

microdrop-py/src/device_viewer/
├── consts.py                                            # MODIFIED — add PROTOCOL_TREE_DISPLAY_STATE
│                                                        #            and DEVICE_VIEWER_GEOMETRY_CHANGED;
│                                                        #            add the latter to ACTOR_TOPIC_DICT
├── models/
│   └── messages.py                                      # NEW model: GeometryChangedMessage (small Pydantic)
└── views/
    └── device_view_dock_pane.py                         # MODIFIED — add _on_protocol_tree_display_state_triggered;
                                                         #            publish DEVICE_VIEWER_GEOMETRY_CHANGED on
                                                         #            chip insert / SVG load

docs/superpowers/specs/
└── 2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md   # this file
```

## 3. Architecture

```
                          ┌────────────────────────────┐
                          │      ProtocolTreePane      │
                          └─────────────┬──────────────┘
                                        │ optional injection
                                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │  DeviceViewerSyncController                              │
        │                                                          │
        │  in:   DEVICE_VIEWER_STATE_CHANGED       (actor)         │
        │  in:   DEVICE_VIEWER_GEOMETRY_CHANGED    (actor) ── caches
        │  in:   PROTOCOL_RUNNING                  (actor)         │
        │  in:   tree.selectionModel().currentChanged   (Qt)       │
        │                                                          │
        │  out:  PROTOCOL_TREE_DISPLAY_STATE  (publish_message)    │
        │  out:  RowManager.add_step(...)     (insert-as-new-step) │
        │  side: pyface_wrapper.confirm dialog for unsaved free    │
        │        mode                                              │
        └──────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                          ┌────────────────────────────┐
                          │   DeviceViewDockPane       │
                          │  _on_protocol_tree_        │
                          │   display_state_triggered  │
                          │                            │
                          │  publishes                 │
                          │  DEVICE_VIEWER_GEOMETRY_   │
                          │  CHANGED on chip insert /  │
                          │  SVG load                  │
                          └────────────────────────────┘

                ProtocolTreePane (separately, not via the controller)
                        │
                        ▼
                publish PROTOCOL_RUNNING True/False on
                _on_protocol_started / _finished / _aborted
```

The controller is the **only** module that knows about both the tree and the DV. The pane gains one optional injection (`device_viewer_sync=None`); the dock pane in the full app constructs the controller and passes it. Demo windows pass `None` and the tree → DV / DV → tree wiring becomes a no-op (matches the existing `application` / `experiment_manager` / `sticky_manager` defaults).

## 4. Data flow

### A) Tree → Device Viewer (step click)

1. User clicks step row in `QTreeView`.
2. `tree.selectionModel().currentChanged` fires → `controller._on_current_changed(QModelIndex)`.
3. Resolve index → row via `widget.index_to_path` then `RowManager.get_row(path)`.
4. Guard: `_suppress_publish` set (programmatic move) → return.
5. Guard: `_protocol_running` true → return.
6. Guard: `_free_mode_stash` non-empty AND `row.uuid != _last_selected_uuid` → branch to (C).
7. Build `ProtocolTreeDisplayMessage(electrodes=row.electrodes, routes=row.routes, step_id=row.uuid, step_label=row.name, free_mode=False, editable=True)`.
8. `publish_message(topic=PROTOCOL_TREE_DISPLAY_STATE, message=msg.serialize())`.
9. Update `_last_selected_uuid = row.uuid`.

### B) Device Viewer → Tree (free-mode capture)

1. User toggles electrodes on the DV with no step selected.
2. DV's existing publisher fires `DEVICE_VIEWER_STATE_CHANGED` with full `DeviceViewerMessageModel` payload.
3. Controller's dramatiq actor receives → emits `bridge.dv_state_received` Qt signal (signal bridge — same pattern as legacy `MessageListenerSignalEmitter`, scoped to one topic).
4. `_on_dv_state_qt(payload)` runs on Qt thread:
   - Parse with `DeviceViewerMessageModel.deserialize`.
   - If `dv_msg.step_id` is set → `_free_mode_stash = None` (DV thinks it's editing a specific step).
   - If neither channels nor routes → `_free_mode_stash = None`.
   - Otherwise: reverse-lookup channels → electrode IDs using `_channel_to_id_cache` (built from `protocol_metadata["electrode_to_channel"]`). If the metadata is empty (cold start, no geometry message seen yet), seed it from `dv_msg.id_to_channel` and continue. Store `{"electrodes": sorted([...]), "routes": [list(ids) for ids, _color in dv_msg.routes]}` as `_free_mode_stash`.

### B') Device Viewer → Tree (geometry as protocol metadata)

1. DV publishes `DEVICE_VIEWER_GEOMETRY_CHANGED` on chip insert / SVG load with a small payload: `{"id_to_channel": {...}}`.
2. Controller's dramatiq actor receives → emits `bridge.geometry_changed` Qt signal.
3. `_on_geometry_qt(payload)` parses and writes the mapping to `row_manager.protocol_metadata["electrode_to_channel"]` — the single source of truth for the entire protocol. The reverse-lookup cache (`_channel_to_id_cache`) is rebuilt as an inverted view.

The metadata dict is also seeded on the first `DEVICE_VIEWER_STATE_CHANGED` we see (whose payload still carries the mapping in Phase 1). That covers the cold-start case where the DV had already initialized before our controller subscribed.

**Persistence:** because the mapping lives in `protocol_metadata`, it's automatically included in `RowManager.to_json()` and restored by `from_json` / `set_state_from_json`. No per-step duplication, no separate serialization path.

**Sharing:** the executor already reads from the same dict (via `ProtocolContext.scratch["electrode_to_channel"]`) for `routes_column.py:122`'s electrode→channel resolution during phase publishing. Both consumers (executor + controller) see the same up-to-date mapping with no synchronization code.

### C) The free-mode prompt (resolution of B's stash on next selection)

```python
result = confirm(
    parent=self.parent_widget,
    "You have unsaved changes from free mode.",
    title="Unsaved Free Mode Changes",
    informative=("There are electrode actuations or routes from free mode "
                 "that have not been saved to a protocol step.<br><br>"
                 "Would you like to insert them as a new step?"),
    yes_label="Insert as New Step",
    no_label="Discard Changes",
)

if result == YES:
    self.row_manager.add_step(
        parent_path=(),
        index=None,                       # append at end of root
        values={
            "name": "Step (free-mode capture)",
            "electrodes": stash["electrodes"],
            "routes": stash["routes"],
        },
    )
self._free_mode_stash = None
# Fall through to publish (A.7+)
```

Dialog uses `microdrop_application.dialogs.pyface_wrapper.confirm` (per project rule against raw `QMessageBox` / raw `pyface.api`). NO and X-close both behave as Discard — matches legacy.

### D) Deselect / group click (back to free mode)

1. Selection cleared, or user clicked a group node.
2. Resolve any pending free-mode stash (branch C, same prompt rules).
3. Publish `ProtocolTreeDisplayMessage(electrodes=[], routes=[], step_id=None, step_label=None, free_mode=True, editable=True)`.
4. `_last_selected_uuid = None`.

### E) Protocol-running gate

`ProtocolTreePane._on_protocol_started` publishes `PROTOCOL_RUNNING="True"`; `_on_protocol_finished` and `_on_protocol_aborted` publish `"False"`. The DV already subscribes to this and gates its own free-mode publishes (`device_view_dock_pane.py:489`). Without this addition, free-mode toggles would leak through during a run and create false stashes. The controller also subscribes (via the same dramatiq actor) so its own `_on_current_changed` can bail out at A.5.

## 5. Topic + message schema

### New constants

`pluggable_protocol_tree/consts.py`:

```python
PROTOCOL_TREE_DISPLAY_STATE = "ui/protocol_tree/display_state"
```

Naming mirrors legacy `PROTOCOL_GRID_DISPLAY_STATE = "ui/protocol_grid/display_state"` — same namespace, only the middle segment changes. Self-explanatory once `protocol_grid` is deleted in PPT-9.

`device_viewer/consts.py`:

```python
DEVICE_VIEWER_GEOMETRY_CHANGED = "ui/device_viewer/geometry_changed"
```

Published only when `id_to_channel` actually changes (chip insert, SVG file load). Listeners cache and reuse — saves a ~120-entry dict on every state-change publish.

### New model

`pluggable_protocol_tree/models/display_state.py`:

```python
from typing import Optional
from pydantic import BaseModel


class ProtocolTreeDisplayMessage(BaseModel):
    """Slim payload for `PROTOCOL_TREE_DISPLAY_STATE` — what the
    pluggable tree pushes to the device viewer when the user
    selects/deselects a step.

    Strict subset of `device_viewer.models.messages.DeviceViewerMessageModel`:
    only the fields the DV actually needs from us. Channel resolution is
    left to the DV (it owns electrode->channel geometry via its own model)."""

    electrodes: list[str] = []          # static electrodes from the step
    routes: list[list[str]] = []        # per-route electrode-id sequences
    step_id: Optional[str] = None       # row.uuid; None = free mode
    step_label: Optional[str] = None    # row.name
    free_mode: bool = False
    editable: bool = True

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeDisplayMessage":
        return cls.model_validate_json(json_str)
```

### Geometry-changed model

`device_viewer/models/messages.py` (new class added alongside `DeviceViewerMessageModel`):

```python
class GeometryChangedMessage(BaseModel):
    """Payload for `DEVICE_VIEWER_GEOMETRY_CHANGED`. Published whenever
    the electrode-to-channel mapping changes (chip insert, SVG load) so
    listeners can cache it once instead of receiving it on every state
    update."""

    id_to_channel: dict[str, int | None]

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "GeometryChangedMessage":
        return cls.model_validate_json(json_str)
```

### Field rationale (vs. legacy `DeviceViewerMessageModel`)

| Field | Kept? | Why |
|---|---|---|
| `electrodes` (list[str]) | ✓ | Static electrodes column — primary "what's on this step" payload |
| `routes` (list[list[str]]) | ✓ | Route overlay (decision #3) |
| `step_id` / `step_label` | ✓ | DV uses these to label its sidebar / suppress redundant updates |
| `free_mode` / `editable` | ✓ | DV gates its own publish behavior on these |
| `channels_activated` | ✗ | Derivable from `electrodes` via DV's existing geometry |
| `id_to_channel` | ✗ | DV already owns this mapping |
| `routes` color tuple `(ids, color)` | ✗ → flat list[list[str]] | Color is purely a DV display concern; let DV pick |
| `activated_electrodes_area_mm2` | ✗ | DV computes from its own model |
| `uuid`, `svg_file`, `execution_params` | ✗ | Not used by anything in this scope |

### DV-side handler (one new method)

`device_viewer/views/device_view_dock_pane.py`:

```python
def _on_protocol_tree_display_state_triggered(self, message_serial: str):
    """Adapter for ProtocolTreeDisplayMessage -> DeviceViewerMessageModel.
    The downstream display_state_signal pipeline reuses what already
    works for the legacy widget."""
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    msg = ProtocolTreeDisplayMessage.deserialize(message_serial)
    id_to_channel = self.model.electrodes.id_to_channel
    channels_activated = {
        id_to_channel[eid]
        for eid in msg.electrodes
        if id_to_channel.get(eid) is not None
    }
    rich = DeviceViewerMessageModel(
        channels_activated=channels_activated,
        routes=[(route, "blue") for route in msg.routes],
        id_to_channel=id_to_channel,
        step_info={
            "step_id": msg.step_id,
            "step_label": msg.step_label,
            "free_mode": msg.free_mode,
        },
        editable=msg.editable,
    )
    self.device_view.display_state_signal.emit(rich.serialize())
```

`device_viewer/consts.py:ACTOR_TOPIC_DICT[listener_name]` gains one entry: `PROTOCOL_TREE_DISPLAY_STATE`.

### DV-side geometry publishing

`device_view_dock_pane.py` gets a small helper:

```python
def _publish_geometry_if_changed(self):
    """Publish DEVICE_VIEWER_GEOMETRY_CHANGED if id_to_channel differs
    from the last-published mapping. No-op otherwise. Called from chip-
    insert and SVG-load handlers."""
    current = {
        eid: e.channel
        for eid, e in self.model.electrodes.electrodes.items()
    }
    if current == self._last_published_id_to_channel:
        return
    self._last_published_id_to_channel = dict(current)
    msg = GeometryChangedMessage(id_to_channel=current)
    publish_message.send(
        topic=DEVICE_VIEWER_GEOMETRY_CHANGED, message=msg.serialize(),
    )
```

Called from the existing chip-insert handler and from `apply_message_model` (which loads SVG geometry). One-time publish on first model initialization too. The `_last_published_id_to_channel` instance attribute starts as `None`.

**Phase 1 explicitly does NOT** strip `id_to_channel` from `DEVICE_VIEWER_STATE_CHANGED` — legacy `protocol_grid` still consumes it from there. Phase 2 (PPT-9 / its own spec) does the strip-down once legacy is deleted.

### Why a new model instead of reusing `DeviceViewerMessageModel`

Direct reuse couples the new tree to a legacy schema that lives in `device_viewer.models.messages` but encodes legacy assumptions (color tuples, `execution_params` dict). Slim model gives us:

- Stable contract owned by the new pane; legacy stays free to evolve / be deleted.
- Field-by-field trade-offs become explicit (the table above).
- DV owns its own geometry — no `id_to_channel` round-trips.

Trade-off: one adapter method on the DV side. Acceptable.

## 6. Controller internals

### Class shape

```python
class _Bridge(QObject):
    """Qt signal bridge — Dramatiq actor runs on a worker thread,
    Qt mutations must happen on the GUI thread."""
    dv_state_received        = Signal(str)
    geometry_changed         = Signal(str)
    protocol_running_changed = Signal(bool)


class DeviceViewerSyncController(HasTraits):
    row_manager              = Instance(RowManager)
    parent_widget            = Instance(QWidget)
    bridge                   = Instance(_Bridge)
    dramatiq_actor           = Instance(dramatiq.Actor)
    listener_name            = "protocol_tree_dv_sync_listener"

    _free_mode_stash         = Instance(dict, allow_none=True)
    _last_selected_uuid      = Str(allow_none=True)
    _protocol_running        = Bool(False)
    _suppress_publish        = Bool(False)
    # Reverse-lookup cache (channel -> electrode_id), invalidated on
    # geometry change. The forward mapping itself lives ONLY in
    # row_manager.protocol_metadata["electrode_to_channel"] — this
    # cache is just an inverted view for fast free-mode resolution.
    _channel_to_id_cache     = Dict(Int, Str)

    def attach(self, tree_widget): ...
    def detach(self): ...

    @property
    def id_to_channel(self) -> dict[str, int | None]:
        """Single source of truth — read from protocol metadata."""
        return self.row_manager.protocol_metadata.get(
            "electrode_to_channel", {}
        )
```

### Lifecycle

```python
# in ProtocolTreePane.__init__, after self.widget is built:
if self.device_viewer_sync is not None:
    self.device_viewer_sync.attach(self.widget)

# in ProtocolTreePane.closeEvent:
if self.device_viewer_sync is not None:
    self.device_viewer_sync.detach()
```

`attach(tree_widget)`:

1. Stash refs to `tree_widget.tree.selectionModel()` for later disconnect.
2. Connect `selectionModel.currentChanged` → `_on_current_changed`.
3. Connect bridge signals → handlers (`_on_dv_state_qt`, `_on_protocol_running_qt`).
4. Register dramatiq actor (single actor, two-topic subscription map):

```python
ACTOR_TOPIC_DICT[self.listener_name] = [
    DEVICE_VIEWER_STATE_CHANGED,
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    PROTOCOL_RUNNING,
]
self.dramatiq_actor = generate_class_method_dramatiq_listener_actor(
    listener_name=self.listener_name,
    class_method=self._listener_routine,
)
```

`detach()`: disconnect signal/slot bindings, drop actor reference (Dramatiq broker shutdown handles teardown).

### Threading

- **Dramatiq actor** runs on a worker thread. `_listener_routine` does only dispatch — never touches Qt or the RowManager directly:

```python
def _listener_routine(self, message: str, topic: str) -> None:
    if topic == DEVICE_VIEWER_STATE_CHANGED:
        self.bridge.dv_state_received.emit(message)
    elif topic == DEVICE_VIEWER_GEOMETRY_CHANGED:
        self.bridge.geometry_changed.emit(message)
    elif topic == PROTOCOL_RUNNING:
        self.bridge.protocol_running_changed.emit(
            message.casefold() == "true"
        )
```

- **Qt signals** (auto-connected with `Qt.AutoConnection`) marshal to the GUI thread, where `_on_dv_state_qt` parses and mutates state.
- **Tree selection signal** (`currentChanged`) already fires on the Qt thread — handler runs there directly.
- **`add_step` mutation + `publish_message`** both happen on the Qt thread inside the slot. `publish_message` is thread-safe (it just enqueues to Dramatiq).

Same bridge pattern as legacy `MessageListenerSignalEmitter` — proven working, no new threading risk.

### `_suppress_publish` flag

Set during programmatic selection changes (executor highlighting the active row, step-cursor nav buttons, `clear_highlights`). Without this, those programmatic moves would each fire a publish. The pane's existing methods get small wraps:

```python
# in ProtocolTreePane._select_step / clear_highlights, and around
# executor.qsignals.step_started -> widget.highlight_active_row
if self.device_viewer_sync is not None:
    self.device_viewer_sync._suppress_publish = True
try:
    # existing setCurrentIndex / clearSelection logic
finally:
    if self.device_viewer_sync is not None:
        self.device_viewer_sync._suppress_publish = False
```

Programmatic-move call sites: `_select_step`, `clear_highlights`, the executor-driven `highlight_active_row` wiring (six total). Small surface.

### Subtleties

- **Reentrancy on `add_step`:** RowManager mutation may fire trait observers that the Qt model relays as selection changes. `_suppress_publish` is set around the add too — defensive. Covered by a regression test.
- **Row resolution:** `widget.index_to_path(index)` → `RowManager.get_row(path)`. If `row.type == "group"` → return `None`. Promote `_index_to_path` to public `index_to_path` (delegate; private alias retained for any external callers).
- **No ack:** `PROTOCOL_TREE_DISPLAY_STATE` is fire-and-forget; DV updates its own state. No `_APPLIED` topic needed.

## 7. Testing strategy

### Unit (no Redis, no Qt event loop) — `tests/test_device_viewer_sync.py`

| Test | Setup | Assertion |
|---|---|---|
| `test_step_click_publishes_display_state` | Controller + RowManager with 2 steps | `_on_current_changed` on step 2 → mock `publish_message` called with `topic=PROTOCOL_TREE_DISPLAY_STATE`, payload contains `step_id=row.uuid`, `electrodes=row.electrodes`, `free_mode=False` |
| `test_group_click_emits_free_mode_payload` | Manager with one group | Group click → publish with `free_mode=True`, `electrodes=[]` |
| `test_protocol_running_blocks_publish` | Set `_protocol_running=True` | Step click → no publish |
| `test_dv_free_mode_message_stashes_electrodes` | Synthetic `DeviceViewerMessageModel` (no `step_id`, channels=[1,2], `id_to_channel` mapping) | `_on_dv_state_qt` → `_free_mode_stash == {"electrodes": ["e01","e02"], "routes": []}` |
| `test_dv_step_scoped_message_clears_stash` | Stash non-empty + incoming msg with `step_id="abc"` | Stash → None |
| `test_dv_empty_message_clears_stash` | Stash non-empty + incoming msg with empty channels/routes | Stash → None |
| `test_step_click_with_stash_prompts_yes_inserts_step` | Stash set + step click + dialog mock returns YES | `RowManager.add_step` called with stashed values; publish still happens |
| `test_step_click_with_stash_prompts_no_discards` | Stash set + dialog mock returns NO | No `add_step`; stash cleared; publish happens |
| `test_suppress_publish_during_programmatic_select` | `_suppress_publish=True` + `_on_current_changed` | No publish |
| `test_listener_routine_emits_correct_bridge_signal` | Call `_listener_routine("True", PROTOCOL_RUNNING)` | Bridge `protocol_running_changed` emitted with True |
| `test_insert_new_step_does_not_publish_twice` | Stash set + step click → YES | Exactly one `publish_message` call (regression for the `add_step` reentrancy concern) |
| `test_geometry_message_writes_to_protocol_metadata` | `_listener_routine` with `DEVICE_VIEWER_GEOMETRY_CHANGED` payload | `row_manager.protocol_metadata["electrode_to_channel"] == {"e00": 0, "e01": 1, ...}`; `_channel_to_id_cache` is the inverted view |
| `test_dv_state_uses_metadata_for_reverse_lookup` | Pre-seed `protocol_metadata["electrode_to_channel"]` + state msg with channels=[1,2] but empty id_to_channel | Stash uses metadata mapping → electrodes=["e01","e02"] |
| `test_dv_state_seeds_metadata_when_empty` | Empty metadata + state msg with id_to_channel populated | Stash resolves correctly; `protocol_metadata["electrode_to_channel"]` is now populated (cold-start seed) |
| `test_no_per_step_id_to_channel_storage` | Add several steps; trigger geometry change | Each row has no `id_to_channel` attribute / value; mapping exists ONLY in `protocol_metadata` |
| `test_protocol_metadata_persists_round_trip` | Set `protocol_metadata["electrode_to_channel"]` → `to_json` → `from_json` | Reconstructed manager has the same mapping under the same key |

Dialog mocking: monkeypatch `pyface_wrapper.confirm` to return YES/NO. Same pattern as existing `tests/test_protocol_tree_pane.py`.

### Integration (Redis-dependent) — `tests/tests_with_redis_server_need/test_device_viewer_sync_redis.py`

| Test | Flow |
|---|---|
| `test_dv_state_to_stash_roundtrip` | Publish synthetic `DEVICE_VIEWER_STATE_CHANGED` JSON → wait briefly → assert controller's stash populated |
| `test_step_click_to_publish_roundtrip` | Subscribe a spy actor to `PROTOCOL_TREE_DISPLAY_STATE` → drive a selection change → assert spy receives correct payload |
| `test_protocol_running_publish_on_executor_start` | Spy on `PROTOCOL_RUNNING` → run minimal protocol on pane → assert "True" published on start, "False" on finish |
| `test_geometry_publish_on_chip_insert` | Spy on `DEVICE_VIEWER_GEOMETRY_CHANGED` → trigger chip-insert flow on DV → assert one publish with the expected mapping; trigger again with same mapping → assert no second publish |

Pattern matches existing `test_executor_redis_integration.py` (uses `tests_with_redis_server_need/conftest.py` fixtures).

### Manual smoke

1. Launch `examples/run_device_viewer_pluggable.py` with `MockDropbotControllerPlugin`.
2. Toggle electrodes in DV with no step selected → no immediate stash visible, but logged.
3. Click step 1 → free-mode prompt appears → "Insert as New Step" → new step at end of tree, original click selects step 1, DV shows step 1's electrodes.
4. Click a group → DV clears (free-mode visual).
5. Start protocol → executor drives DV; clicking other steps mid-run does nothing.
6. After protocol ends, selection-driven sync resumes.

## 8. Acceptance criteria

- [ ] `pluggable_protocol_tree.services.device_viewer_sync.DeviceViewerSyncController` exists, with `attach` / `detach` plus the handlers above.
- [ ] `pluggable_protocol_tree.models.display_state.ProtocolTreeDisplayMessage` exists with the schema in §5.
- [ ] `PROTOCOL_TREE_DISPLAY_STATE = "ui/protocol_tree/display_state"` exported from `pluggable_protocol_tree.consts`.
- [ ] `DEVICE_VIEWER_GEOMETRY_CHANGED = "ui/device_viewer/geometry_changed"` exported from `device_viewer.consts`; included in DV's `ACTOR_TOPIC_DICT[listener_name]`.
- [ ] `device_viewer.models.messages.GeometryChangedMessage` exists with the schema in §5.
- [ ] `device_view_dock_pane.py` publishes `DEVICE_VIEWER_GEOMETRY_CHANGED` on chip insert / SVG load / first model init, gated on actual change vs `_last_published_id_to_channel`.
- [ ] `ProtocolTreePane` accepts `device_viewer_sync=None`, attaches in `__init__`, detaches in `closeEvent`, publishes `PROTOCOL_RUNNING` on start/finish/abort, and wraps programmatic selection moves with `_suppress_publish`.
- [ ] `PluggableProtocolDockPane` constructs the controller and passes it to the pane.
- [ ] `device_view_dock_pane.py` has `_on_protocol_tree_display_state_triggered`; `device_viewer.consts.ACTOR_TOPIC_DICT` includes `PROTOCOL_TREE_DISPLAY_STATE`.
- [ ] `DeviceViewerSyncController` writes `id_to_channel` from geometry-changed messages to `row_manager.protocol_metadata["electrode_to_channel"]` (single source of truth); maintains an inverted `_channel_to_id_cache` for reverse-lookup; cold-starts by seeding the metadata from `DEVICE_VIEWER_STATE_CHANGED` if no geometry message has arrived yet.
- [ ] No per-step / per-row storage of `id_to_channel` anywhere — the mapping lives ONLY in `RowManager.protocol_metadata["electrode_to_channel"]`. `to_json` / `from_json` round-trip preserves it. The executor (`routes_column.py`) continues to read it via `ProtocolContext.scratch["electrode_to_channel"]`.
- [ ] `widget.index_to_path` is public (private `_index_to_path` retained as a one-line alias).
- [ ] No new RowManager API is added (existing `add_step` / `add_group` / `remove` / `move` are sufficient and used directly by the controller).
- [ ] Legacy `protocol_grid` widget continues to work unchanged — `DEVICE_VIEWER_STATE_CHANGED` payload still includes `id_to_channel` in Phase 1.
- [ ] All unit tests in §7 pass.
- [ ] All Redis-dependent tests in §7 pass against a running Redis.
- [ ] Manual smoke checklist (§7) passes against `examples/run_device_viewer_pluggable.py` with `MockDropbotControllerPlugin`.

## 9. Open questions / known limitations

- **Routes overlay color:** the DV-side adapter uses a fixed `"blue"` placeholder. Legacy used a route-specific palette. Phase 1 ships with single color; a follow-up spec can wire the palette.
- **Channel-mapping mismatches:** if an electrode in the step has no `id_to_channel` entry (chip schema mismatch), it's silently dropped from `channels_activated`. Same lenient policy as legacy.
- **New step naming:** `"Step (free-mode capture)"` — distinguishable, sortable. Open to a different convention; user can rename in the tree after insertion.
- **`PROTOCOL_RUNNING` publish coupling:** the pane was previously silent on this topic. Adding it is necessary for correctness here, but other listeners (DV, future panes) may react to the new publishes. Acceptable — this matches the contract the legacy widget already provided.

## 10. Out of scope reminder

This spec deliberately does NOT cover:

- DropBot connection-state gating (`DROPBOT_CONNECTED` / `DISCONNECTED` / `CHIP_INSERTED`).
- "Disconnected Before Run" dialog.
- Capacitance overlay, droplet-detection failure dialog (PPT-8 separate), `routes_executing` / `device_viewer_recording_state` UI gating.
- Voltage/frequency-range preferences, calibration data, step-params commit, advanced-mode, z-stage position, media-captured logging.

These remain in issue #414 and will be addressed in follow-up specs/PRs.

## 11. Phase-2 follow-up: lean state payload (deferred)

Phase 1 (this spec) introduces `DEVICE_VIEWER_GEOMETRY_CHANGED` and our controller caches from it, but `DEVICE_VIEWER_STATE_CHANGED` still carries the full `id_to_channel` mapping for legacy compatibility.

Phase 2 is tracked at [#415](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/415), blocked on PPT-9 ([#371](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/371)) deleting `protocol_grid`. The actual byte-saving step:

1. Make `DeviceViewerMessageModel.id_to_channel` `Optional[dict[str, int | None]] = None`.
2. `gui_models_to_message_model` stops populating it (or sets it to `None`).
3. Any remaining listener that reads `dv_msg.id_to_channel` is updated to subscribe to `DEVICE_VIEWER_GEOMETRY_CHANGED` and cache, or read from a shared registry.
4. Legacy `protocol_grid` is the largest blocker today — Phase 2 lands cleanly once it's deleted in PPT-9 (#371).

Estimated payload reduction: a 90-pin chip's `id_to_channel` is ~90 entries × ~15 bytes serialized = ~1.4 KB per state-change publish. With state-change publishes happening per-electrode-toggle during free-mode interaction, this measurably reduces broker traffic and listener parse time.
