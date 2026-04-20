# Device Viewer → Protocol Grid: Step Execution Parameters Commit

**Date:** 2026-04-20
**Branch context:** `feat/346-sandbox-settings` (scope of this spec is independent of the sandbox settings work)

## Problem

The device viewer sidebar (`RouteLayerManager`) owns execution parameters (`duration`, `repetitions`, `repeat_duration`, `trail_length`, `trail_overlay`, `soft_start`, `soft_terminate`) that drive local `RouteExecutionService` playback. These parameters map 1:1 to the protocol grid columns `Duration`, `Repetitions`, `Repeat Duration`, `Trail Length`, `Trail Overlay`, `Ramp Up`, `Ramp Dn`.

Today, the cross-plugin state sync (`DEVICE_VIEWER_STATE_CHANGED` for DV → grid; `PROTOCOL_GRID_DISPLAY_STATE` for grid → DV — both carrying `DeviceViewerMessageModel`) carries only route geometry and activated electrodes. If a user tunes execution parameters in the device viewer sidebar, those tweaks stay local; they never reach the protocol step. Conversely, when a user selects a step in the grid, the sidebar sliders are not reconciled against the step's stored values.

## Goals

1. When a protocol step is selected, the device viewer sidebar sliders reflect that step's stored execution parameters (one-shot pull).
2. The user can modify sidebar sliders freely, then push them back to the selected step with an explicit commit action.
3. Direct edits of execution-parameter cells in the protocol grid after a step has been selected are *not* mirrored back into the sidebar.
4. The "insert free-mode state as a new step" dialog bundles the sidebar's current parameter values into the new step.
5. Route geometry continues to live-sync from sidebar to step (unchanged).

## Non-goals

- Syncing Voltage / Frequency / Force (these live in `manual_controls`, not the device viewer sidebar).
- Syncing grid-only fields: `Message`, `Video`, `Capture`, `Record`, `Volume Threshold`, `Magnet`, `Magnet Height (mm)`, `Max. Path Length`, `Run Time`.
- Live-syncing sidebar parameter changes back to the grid on every trait tick.
- Changing the device viewer's local execution playback (`RouteExecutionService`) semantics.

## Behavior summary

| Direction | Trigger | Frequency |
| --- | --- | --- |
| Grid → sidebar (params) | Selected-step change | One-shot, on `step_id` transition |
| Sidebar → grid (params) | User clicks "Commit to step" button | Explicit, user-initiated |
| Grid cell edit (user) → sidebar | — | Never |
| Sidebar → grid (routes / electrodes) | Trait observer on `model.routes.layers.items.route.route.items` | Live, unchanged |
| Free-mode "insert as new step" dialog | User accepts prompt | One-shot, bundles sidebar params into new step |

## Data model changes

### Extend `DeviceViewerMessageModel`

File: `device_viewer/models/messages.py`

Add one optional field:

```python
execution_params: Optional[dict] = None
# expected keys (all required when field is non-None):
#   duration: float
#   repetitions: int
#   repeat_duration: float
#   trail_length: int
#   trail_overlay: int
#   soft_start: bool
#   soft_terminate: bool
```

Only populated on grid → device viewer publications. Left `None` on device viewer → grid publications (the existing live-route-sync flow). Serialization is automatic via Pydantic.

### New `StepParamsCommitMessage`

New file: `protocol_grid/models/step_params_commit.py` (new `protocol_grid/models/` package if needed).

```python
from pydantic import BaseModel

class StepParamsCommitMessage(BaseModel):
    step_id: str
    duration: float
    repetitions: int
    repeat_duration: float
    trail_length: int
    trail_overlay: int
    soft_start: bool
    soft_terminate: bool

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "StepParamsCommitMessage":
        return cls.model_validate_json(json_str)
```

### New topic constant

File: `protocol_grid/consts.py`

```python
STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"
```

Add the topic to `ACTOR_TOPIC_DICT[PROTOCOL_GRID_LISTENER_NAME]` in the same file, alongside the existing `DEVICE_VIEWER_STATE_CHANGED` entry.

## Data flow

### Pull: grid → sidebar (on step-selection change)

1. When a step becomes selected in the grid, `device_state_to_device_viewer_message()` in `protocol_grid/state/device_state.py` is called (existing flow). Extend its signature to accept an `execution_params: dict | None = None` kwarg and populate the new field on the returned `DeviceViewerMessageModel`.
2. The protocol grid caller (same selection code path that invokes `device_state_to_device_viewer_message`) reads the 7 execution-parameter cells from the selected row and passes them in.
3. In the device viewer, extend `device_view_dock_pane.on_device_viewer_message` (or the equivalent inbound handler) to:
   - detect that `dv_msg.step_id != self._last_applied_step_id` (new attribute on the dock pane, initialized to `None`);
   - on transition, if `dv_msg.execution_params is not None`, write the 7 values onto `model.routes.*` and capture a baseline snapshot in `_committed_params_baseline`;
   - update `_last_applied_step_id`.

   `_committed_params_baseline` is a new `Dict` trait on `RouteLayerManager` (see Open Item 3 for rationale).
4. If `execution_params` is `None` or `step_id` hasn't changed, skip the pull. Routes / electrodes / colors sync as before.

### Commit: sidebar → grid (on explicit button press)

1. Add `commit_to_step_btn = Button("save")` on `RouteLayerManager` (`device_viewer/models/route.py`), alongside `run_routes`, `pause_btn`, `stop_btn`.
2. Add a `commit_enabled = Property(observe="...")` that recomputes on changes to the 7 parameter traits **and** on `_committed_params_baseline`. It is `True` iff (baseline is non-empty — i.e., a step is currently selected) AND (any of the 7 current values ≠ baseline).
3. The view places the button in the existing execution-controls row, bound to `enabled_when="commit_enabled"`.
4. Click handler (on `RouteLayerManager` or a dedicated service):
   - reads current param values;
   - builds `StepParamsCommitMessage(step_id=<current selected step_id>, ...)`;
   - publishes via `publish_message(topic=STEP_PARAMS_COMMIT, message=msg.serialize())`;
   - updates `_committed_params_baseline` to the just-published values (which disables the button).
5. In `protocol_grid/services/message_listener.py`, add a branch for `STEP_PARAMS_COMMIT`:
   - deserialize to `StepParamsCommitMessage`;
   - emit a new Qt signal `step_params_commit_received = Signal(StepParamsCommitMessage)` on `MessageListenerSignalEmitter`.
6. In `protocol_grid/widget.py`, `connect_listener` subscribes the widget to that signal. The handler:
   - finds the step by `step_id` (via existing `_find_step_by_uid` helper);
   - writes the 7 cell values for that row;
   - updates the persisted `parameters` dict on the `ProtocolStep`;
   - triggers whatever downstream recalculation already happens on manual cell edits (duration aggregation, etc. — reuse existing code paths).

### Step-switch with uncommitted sidebar changes

When the device viewer receives a grid → DV `PROTOCOL_GRID_DISPLAY_STATE` whose `step_id` differs from `_last_applied_step_id`, and `commit_enabled` is `True` (sidebar is dirty):

- Show a modal: "You have uncommitted execution parameter changes for step *X*. Commit, Discard, or Cancel?"
  - **Commit** → publish `STEP_PARAMS_COMMIT` for the *old* `step_id`, update baseline, then apply the incoming message's params to the sidebar for the new step.
  - **Discard** → apply the incoming message's params directly; update baseline.
  - **Cancel** → do not apply the new message. See open item on veto mechanism below.

### Free mode and "insert as new step"

- In free mode, `step_id` is `None` and the sidebar keeps whatever values the user has set; `_committed_params_baseline` is empty so the commit button is disabled.
- To make free-mode state → new-step inherit the current sidebar params, extend the device viewer's outbound `DEVICE_VIEWER_STATE_CHANGED` publication (via `gui_models_to_message_model` in `device_viewer/utils/message_utils.py`) to attach `execution_params` when in free mode only. This gives the grid's `_insert_free_mode_state_as_new_step` handler the values it needs.
- `widget._insert_free_mode_state_as_new_step` reads those params out of the latest inbound DV message and seeds the new step's `parameters` dict before adding it to the sequence.
- Once that new step is selected, the normal pull path fires: baseline is set from the committed values; commit button stays disabled until further edits.

## UI

- Button label/icon: existing `save` icon (used elsewhere in the project — verify in `microdrop_style/icons`).
- Placement: `RouteLayerManager` view's existing execution-controls row in the device viewer sidebar, next to `run_routes`, `pause_btn`, `stop_btn`.
- Enabled rule: truthy `commit_enabled` property only (option 2a from brainstorming — no per-field dirty indicators).
- Tooltip: "Commit execution parameters to selected step".

## Testing

- Unit, `DeviceViewerMessageModel`: round-trip serialization with `execution_params` populated and with `None`; `get_routes_with_channels` still works in both cases.
- Unit, `StepParamsCommitMessage`: round-trip serialization; rejects missing fields.
- Unit, `device_state_to_device_viewer_message`: carries `execution_params` when provided, returns `None` otherwise.
- Unit, `RouteLayerManager.commit_enabled`: transitions correctly across (no baseline) → (baseline set, equal) → (baseline set, divergent) → (committed, equal).
- Integration (place under `examples/tests/tests_with_redis_server_need/` since it exercises the message router): publish a grid-side `DEVICE_VIEWER_STATE_CHANGED` with `execution_params` and a new `step_id`; assert sidebar values update and `commit_enabled` is `False`. Mutate a sidebar value; assert `commit_enabled` is `True`. Trigger commit; assert the step's cells are updated and `commit_enabled` returns to `False`.
- UI smoke (manual, to be verified in a dev run): select step → edit field → commit → switch steps → verify params pull; dirty + switch → verify dialog; accept new-step-from-free-mode → verify params bundled.

## `MESSAGES.md` updates

- Add `STEP_PARAMS_COMMIT` to the device viewer "Sending" list and the protocol grid "Receiving" list.
- Add a "Device Viewer → Protocol Grid: step execution params commit" subsection under "Detailed Flows", mirroring the format of the existing routes subsection: topic name, publisher file/line, payload schema, subscriber file/line.

## Open items for the implementation plan

1. **Cancel-on-step-switch veto mechanism.** Two viable options:
   - Block the grid selection by emitting a Qt signal back to the grid to restore the prior selection (risk: transient visual flicker).
   - Intercept the selection *before* it propagates (cleaner UX; requires hooking the grid's selection logic, not the DV side).
   Decide during implementation; prefer the second if feasible.
2. **Exact placement in the view.** Verify the existing button layout in `device_view_dock_pane.py` / relevant `.View()` definition and pick the least-intrusive slot.
3. **Baseline storage location.** `_committed_params_baseline` can live on `RouteLayerManager` (keeps state with the data) or on the dock pane (keeps it out of the serializable model). Implementation plan should pick one and justify it.
4. **Does commit close the dirty state immediately or await a round-trip acknowledgement?** The design assumes immediate local baseline update; if the grid write can fail, we may want an ack. Low priority — the grid side cannot meaningfully reject a valid `step_id` it just published.

## Out-of-scope follow-ups (not part of this spec)

- Adding Voltage/Frequency/Force to the sidebar and to this commit flow.
- Bidirectional live sync of params (rejected by the design in favor of explicit commit).
- A sidebar history / undo of uncommitted edits.
