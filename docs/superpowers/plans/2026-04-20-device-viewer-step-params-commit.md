# Device Viewer → Protocol Grid Step Execution Params Commit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the device viewer sidebar pull execution parameters (duration, repetitions, repeat_duration, trail_length, trail_overlay, soft_start, soft_terminate) from the currently-selected protocol step on selection change, and push them back to that step on an explicit commit button press.

**Architecture:** Extend `DeviceViewerMessageModel` with an optional `execution_params` dict carried only on the grid → DV direction (`PROTOCOL_GRID_DISPLAY_STATE`). A new dedicated topic `STEP_PARAMS_COMMIT` carries a `StepParamsCommitMessage` from DV → grid only when the user clicks the commit button. The sidebar maintains a `_committed_params_baseline` so a `commit_enabled` property can drive button enablement and the dirty-switch dialog.

**Tech Stack:** Python, Envisage plugins, Traits/TraitsUI, PySide6, Pydantic, Dramatiq + Redis.

**Spec:** `docs/superpowers/specs/2026-04-20-device-viewer-step-params-commit-design.md`

---

## File map

**Create:**
- `protocol_grid/models/__init__.py` (new package)
- `protocol_grid/models/step_params_commit.py` — `StepParamsCommitMessage`
- `device_viewer/tests/__init__.py`, `device_viewer/tests/test_messages.py` — unit tests for extended `DeviceViewerMessageModel`
- `device_viewer/tests/test_route_layer_manager_commit.py` — unit tests for `commit_enabled` property
- `protocol_grid/tests/test_step_params_commit.py` — unit tests for the new message + `device_state_to_device_viewer_message` pass-through + `extract_execution_params`
- `protocol_grid/tests/test_message_listener_step_params.py` — unit test for the listener branch
- `examples/tests/tests_with_redis_server_need/test_step_params_roundtrip.py` — end-to-end integration

**Modify:**
- `device_viewer/models/messages.py` — add `execution_params` field
- `device_viewer/models/route.py` — add commit-state traits and button
- `device_viewer/utils/message_utils.py` — attach `execution_params` in free mode
- `device_viewer/views/device_view_dock_pane.py` — pull handler + dirty-switch dialog + commit publisher
- `device_viewer/views/route_selection_view/route_selection_view.py` — add commit button to `run_controls`
- `device_viewer/consts.py` — subscribe device viewer listener to `STEP_PARAMS_COMMIT`? (No — DV publishes, grid subscribes. Leave alone.)
- `protocol_grid/consts.py` — add `STEP_PARAMS_COMMIT` constant + subscribe
- `protocol_grid/state/device_state.py` — add `execution_params` kwarg on `device_state_to_device_viewer_message`
- `protocol_grid/protocol_grid_helpers.py` — add `extract_execution_params(parameters: dict) -> dict`
- `protocol_grid/services/message_listener.py` — handle `STEP_PARAMS_COMMIT`
- `protocol_grid/widget.py` — pass `execution_params` on publish; connect commit signal; seed from free-mode message
- `MESSAGES.md` — document new topic and flow

---

## Task 1: Add `execution_params` field to `DeviceViewerMessageModel`

**Files:**
- Modify: `device_viewer/models/messages.py:5-61`
- Create: `device_viewer/tests/__init__.py` (empty)
- Create: `device_viewer/tests/test_messages.py`

- [ ] **Step 1: Create the test file**

Create `device_viewer/tests/__init__.py` as an empty file.

Create `device_viewer/tests/test_messages.py`:

```python
from device_viewer.models.messages import DeviceViewerMessageModel


def _base_kwargs():
    return dict(
        channels_activated=set(),
        routes=[],
        id_to_channel={},
    )


def test_execution_params_defaults_to_none():
    msg = DeviceViewerMessageModel(**_base_kwargs())
    assert msg.execution_params is None


def test_execution_params_roundtrip():
    params = {
        "duration": 1.5,
        "repetitions": 3,
        "repeat_duration": 0.0,
        "trail_length": 2,
        "trail_overlay": 1,
        "soft_start": True,
        "soft_terminate": False,
    }
    msg = DeviceViewerMessageModel(**_base_kwargs(), execution_params=params)

    rebuilt = DeviceViewerMessageModel.deserialize(msg.serialize())
    assert rebuilt.execution_params == params


def test_execution_params_none_roundtrip():
    msg = DeviceViewerMessageModel(**_base_kwargs())
    rebuilt = DeviceViewerMessageModel.deserialize(msg.serialize())
    assert rebuilt.execution_params is None
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest device_viewer/tests/test_messages.py -v`

Expected: FAIL — `ValidationError` or `AttributeError` because `execution_params` doesn't exist.

- [ ] **Step 3: Add the field**

In `device_viewer/models/messages.py`, after the `svg_file` field (around line 25), add:

```python
    execution_params: Optional[dict] = None
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest device_viewer/tests/test_messages.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add device_viewer/models/messages.py device_viewer/tests/__init__.py device_viewer/tests/test_messages.py
git commit -m "[Feat] Add execution_params field to DeviceViewerMessageModel"
```

---

## Task 2: Create `StepParamsCommitMessage`

**Files:**
- Create: `protocol_grid/models/__init__.py` (empty)
- Create: `protocol_grid/models/step_params_commit.py`
- Create: `protocol_grid/tests/test_step_params_commit.py`

- [ ] **Step 1: Write the failing test**

Create `protocol_grid/tests/test_step_params_commit.py`:

```python
import pytest
from pydantic import ValidationError

from protocol_grid.models.step_params_commit import StepParamsCommitMessage


def _valid_kwargs():
    return dict(
        step_id="abc123",
        duration=1.5,
        repetitions=3,
        repeat_duration=0.0,
        trail_length=2,
        trail_overlay=1,
        soft_start=True,
        soft_terminate=False,
    )


def test_step_params_commit_roundtrip():
    msg = StepParamsCommitMessage(**_valid_kwargs())
    rebuilt = StepParamsCommitMessage.deserialize(msg.serialize())
    assert rebuilt == msg


def test_step_params_commit_rejects_missing_field():
    kwargs = _valid_kwargs()
    del kwargs["duration"]
    with pytest.raises(ValidationError):
        StepParamsCommitMessage(**kwargs)
```

- [ ] **Step 2: Run tests — expect import failure**

Run: `pytest protocol_grid/tests/test_step_params_commit.py -v`

Expected: `ModuleNotFoundError: protocol_grid.models.step_params_commit`.

- [ ] **Step 3: Create the module**

Create empty `protocol_grid/models/__init__.py`.

Create `protocol_grid/models/step_params_commit.py`:

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

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest protocol_grid/tests/test_step_params_commit.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add protocol_grid/models/__init__.py protocol_grid/models/step_params_commit.py protocol_grid/tests/test_step_params_commit.py
git commit -m "[Feat] Add StepParamsCommitMessage for sidebar → step commit payload"
```

---

## Task 3: Add `STEP_PARAMS_COMMIT` topic and subscribe the protocol grid listener

**Files:**
- Modify: `protocol_grid/consts.py:25-53`

- [ ] **Step 1: Add the topic constant**

In `protocol_grid/consts.py`, after the existing `DEVICE_VIEWER_STATE_CHANGED` line (~25), add:

```python
STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"
```

- [ ] **Step 2: Subscribe the listener**

In `protocol_grid/consts.py`, inside `ACTOR_TOPIC_DICT[PROTOCOL_GRID_LISTENER_NAME]` list (around line 38-52), add `STEP_PARAMS_COMMIT` to the list (place it right after `DEVICE_VIEWER_STATE_CHANGED`):

```python
ACTOR_TOPIC_DICT = {
    PROTOCOL_GRID_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        STEP_PARAMS_COMMIT,
        DROPBOT_DISCONNECTED,
        # ... rest unchanged
    ]
}
```

- [ ] **Step 3: Quick sanity check**

Run: `python -c "from protocol_grid.consts import STEP_PARAMS_COMMIT, ACTOR_TOPIC_DICT, PROTOCOL_GRID_LISTENER_NAME; assert STEP_PARAMS_COMMIT in ACTOR_TOPIC_DICT[PROTOCOL_GRID_LISTENER_NAME]; print('ok')"`

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add protocol_grid/consts.py
git commit -m "[Feat] Register STEP_PARAMS_COMMIT topic for protocol grid listener"
```

---

## Task 4: Add `extract_execution_params` helper

Purely functional conversion of a step's `parameters` dict (string-valued) into the typed dict used by `DeviceViewerMessageModel.execution_params`. Keeps conversion logic testable in isolation.

**Files:**
- Modify: `protocol_grid/protocol_grid_helpers.py`
- Modify: `protocol_grid/tests/test_step_params_commit.py` (append test)

- [ ] **Step 1: Add the failing test**

Append to `protocol_grid/tests/test_step_params_commit.py`:

```python
from protocol_grid.protocol_grid_helpers import extract_execution_params


def test_extract_execution_params_happy_path():
    parameters = {
        "Duration": "1.5",
        "Repetitions": "3",
        "Repeat Duration": "0.0",
        "Trail Length": "2",
        "Trail Overlay": "1",
        "Ramp Up": "1",
        "Ramp Dn": "0",
        "Voltage": "100",  # should be ignored
    }
    result = extract_execution_params(parameters)
    assert result == {
        "duration": 1.5,
        "repetitions": 3,
        "repeat_duration": 0.0,
        "trail_length": 2,
        "trail_overlay": 1,
        "soft_start": True,
        "soft_terminate": False,
    }


def test_extract_execution_params_missing_keys_use_defaults():
    # If a key is absent, fall back to step_defaults string, then cast.
    result = extract_execution_params({})
    assert result["duration"] == 1.0
    assert result["repetitions"] == 1
    assert result["repeat_duration"] == 1.0
    assert result["trail_length"] == 1
    assert result["trail_overlay"] == 0
    assert result["soft_start"] is False
    assert result["soft_terminate"] is False
```

- [ ] **Step 2: Run tests — expect import failure**

Run: `pytest protocol_grid/tests/test_step_params_commit.py -v`

Expected: `ImportError: cannot import name 'extract_execution_params'`.

- [ ] **Step 3: Add the helper**

At the bottom of `protocol_grid/protocol_grid_helpers.py` (after existing functions), add:

```python
from protocol_grid.consts import step_defaults


_EXEC_PARAM_FIELD_MAP = {
    # device-viewer key: (grid cell key, cast)
    "duration":        ("Duration",        float),
    "repetitions":     ("Repetitions",     int),
    "repeat_duration": ("Repeat Duration", float),
    "trail_length":    ("Trail Length",    int),
    "trail_overlay":   ("Trail Overlay",   int),
    "soft_start":      ("Ramp Up",         lambda s: str(s).strip() in ("1", "true", "True")),
    "soft_terminate":  ("Ramp Dn",         lambda s: str(s).strip() in ("1", "true", "True")),
}


def extract_execution_params(parameters: dict) -> dict:
    """Read the 7 execution params out of a step's `parameters` dict.

    Falls back to `step_defaults` when a key is missing. Returns a dict keyed
    by the device-viewer trait names (lowercase snake_case), typed correctly.
    """
    out = {}
    for dv_key, (cell_key, cast) in _EXEC_PARAM_FIELD_MAP.items():
        raw = parameters.get(cell_key, step_defaults.get(cell_key, ""))
        try:
            out[dv_key] = cast(raw)
        except (ValueError, TypeError):
            out[dv_key] = cast(step_defaults[cell_key])
    return out
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest protocol_grid/tests/test_step_params_commit.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add protocol_grid/protocol_grid_helpers.py protocol_grid/tests/test_step_params_commit.py
git commit -m "[Feat] Add extract_execution_params helper for step → DV conversion"
```

---

## Task 5: Extend `device_state_to_device_viewer_message` with `execution_params` kwarg

**Files:**
- Modify: `protocol_grid/state/device_state.py:194-233`
- Modify: `protocol_grid/tests/test_step_params_commit.py` (append test)

- [ ] **Step 1: Add the failing test**

Append to `protocol_grid/tests/test_step_params_commit.py`:

```python
from protocol_grid.state.device_state import (
    DeviceState,
    device_state_to_device_viewer_message,
)


def test_device_state_message_carries_execution_params():
    params = {
        "duration": 2.0,
        "repetitions": 5,
        "repeat_duration": 0.0,
        "trail_length": 3,
        "trail_overlay": 2,
        "soft_start": True,
        "soft_terminate": False,
    }
    state = DeviceState()
    msg = device_state_to_device_viewer_message(
        state, step_uid="u1", step_description="Step", step_id="1",
        execution_params=params,
    )
    assert msg.execution_params == params


def test_device_state_message_execution_params_defaults_none():
    state = DeviceState()
    msg = device_state_to_device_viewer_message(state, step_uid="u1")
    assert msg.execution_params is None
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest protocol_grid/tests/test_step_params_commit.py::test_device_state_message_carries_execution_params -v`

Expected: FAIL — `got an unexpected keyword argument 'execution_params'`.

- [ ] **Step 3: Extend the function**

In `protocol_grid/state/device_state.py`, change the signature and body of `device_state_to_device_viewer_message`:

```python
def device_state_to_device_viewer_message(device_state: DeviceState, step_uid: str=None,
                                          step_description: str=None, step_id: str=None,
                                          editable: bool=True,
                                          execution_params: dict=None) -> DeviceViewerMessageModel:
    # ...existing body unchanged...

    return DeviceViewerMessageModel(
        channels_activated=channels_activated,
        routes=routes,
        id_to_channel=id_to_channel,
        step_info=step_info,
        editable=editable,
        execution_params=execution_params,
    )
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest protocol_grid/tests/test_step_params_commit.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add protocol_grid/state/device_state.py protocol_grid/tests/test_step_params_commit.py
git commit -m "[Feat] Accept execution_params kwarg in device_state_to_device_viewer_message"
```

---

## Task 6: `_publish_step_message` passes the selected step's execution params

**Files:**
- Modify: `protocol_grid/widget.py:1762-1800` (`_publish_step_message`)

- [ ] **Step 1: Update the call site**

In `protocol_grid/widget.py`, at the top add (if not already present):

```python
from protocol_grid.protocol_grid_helpers import extract_execution_params
```

Then in `_publish_step_message` (around line 1781), replace:

```python
        msg_model = device_state_to_device_viewer_message(
            device_state, step_uid, step_description, step_id, editable
        )
```

with:

```python
        step_data = self.state.get_element_by_path(step_path)
        execution_params = extract_execution_params(step_data.parameters) if step_data else None

        msg_model = device_state_to_device_viewer_message(
            device_state, step_uid, step_description, step_id, editable,
            execution_params=execution_params,
        )
```

Note: `step_data` was already fetched a few lines later for voltage/frequency. Move that fetch up (or reuse) to avoid fetching twice. The surrounding `voltage = step_data.parameters["Voltage"]` lines can be kept as-is after the new code.

- [ ] **Step 2: Smoke check the module loads**

Run: `python -c "from protocol_grid.widget import Widget; print('ok')"`

Expected: `ok` (no import/syntax errors).

- [ ] **Step 3: Commit**

```bash
git add protocol_grid/widget.py
git commit -m "[Feat] _publish_step_message now carries step execution params to DV"
```

---

## Task 7: Add commit-state traits to `RouteLayerManager`

Adds the button, baseline trait, and `commit_enabled` property. No wiring yet — purely the model.

**Files:**
- Modify: `device_viewer/models/route.py:184-230`
- Create: `device_viewer/tests/test_route_layer_manager_commit.py`

- [ ] **Step 1: Write the failing test**

Create `device_viewer/tests/test_route_layer_manager_commit.py`:

```python
from device_viewer.models.route import RouteLayerManager


EXEC_PARAMS = {
    "duration": 1.5,
    "repetitions": 3,
    "repeat_duration": 0.0,
    "trail_length": 2,
    "trail_overlay": 1,
    "soft_start": True,
    "soft_terminate": False,
}


def _apply(mgr, params):
    mgr.apply_execution_params(params)


def test_commit_disabled_when_no_baseline():
    mgr = RouteLayerManager()
    assert mgr.commit_enabled is False


def test_commit_disabled_when_equal_to_baseline():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    assert mgr.commit_enabled is False


def test_commit_enabled_when_any_param_diverges():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    mgr.duration = 5.0
    assert mgr.commit_enabled is True


def test_commit_enabled_resets_after_rebaseline():
    mgr = RouteLayerManager()
    _apply(mgr, EXEC_PARAMS)
    mgr.duration = 5.0
    assert mgr.commit_enabled is True

    # Re-baseline to current values (what commit handler does)
    mgr.mark_params_committed()
    assert mgr.commit_enabled is False
```

- [ ] **Step 2: Run — expect attribute errors**

Run: `pytest device_viewer/tests/test_route_layer_manager_commit.py -v`

Expected: FAIL — `apply_execution_params`, `mark_params_committed`, `commit_enabled` don't exist.

- [ ] **Step 3: Add the traits, methods, and property**

In `device_viewer/models/route.py`, in the imports at the top, add `Dict`, `Property`, `cached_property` if not already imported (Property is already imported per line 1).

Inside `RouteLayerManager`, after the existing `soft_terminate = Bool(False)` line (around line 227), add:

```python
    # -------- Step-params commit state --------
    # Empty dict means no step is currently selected — commit button disabled.
    _committed_params_baseline = Dict()

    # Button for pushing current sidebar params to the selected protocol step.
    commit_to_step_btn = Button("save")

    # True iff a baseline is set AND current values diverge from it.
    commit_enabled = Property(
        observe=(
            "_committed_params_baseline.items,"
            "duration,repetitions,repeat_duration,"
            "trail_length,trail_overlay,soft_start,soft_terminate"
        )
    )

    def _get_commit_enabled(self):
        baseline = self._committed_params_baseline
        if not baseline:
            return False
        return self._current_params() != baseline

    def _current_params(self) -> dict:
        return {
            "duration": float(self.duration),
            "repetitions": int(self.repetitions),
            "repeat_duration": float(self.repeat_duration),
            "trail_length": int(self.trail_length),
            "trail_overlay": int(self.trail_overlay),
            "soft_start": bool(self.soft_start),
            "soft_terminate": bool(self.soft_terminate),
        }

    def apply_execution_params(self, params: dict) -> None:
        """Apply params from the grid to the sidebar, then baseline them.

        The existing observers on `repetitions` / `repeat_duration` reset each
        other — we suppress them for the duration of the bulk write so the
        pulled values stick.
        """
        with self._suppress_repeat_exclusion():
            self.trait_set(
                duration=params["duration"],
                repetitions=params["repetitions"],
                repeat_duration=params["repeat_duration"],
                trail_length=params["trail_length"],
                trail_overlay=params["trail_overlay"],
                soft_start=params["soft_start"],
                soft_terminate=params["soft_terminate"],
            )
        self.mark_params_committed()

    def mark_params_committed(self) -> None:
        """Snapshot current values as the committed baseline → disables button."""
        self._committed_params_baseline = self._current_params()

    def clear_committed_baseline(self) -> None:
        """Clear baseline — e.g. when transitioning to free mode."""
        self._committed_params_baseline = {}

    def _suppress_repeat_exclusion(self):
        """Context manager that pauses the repetitions ↔ repeat_duration reset.

        `_route_repeats_changed` / `_route_repeat_duration_changed` observers
        use this flag to bail out.
        """
        mgr = self
        class _Ctx:
            def __enter__(self_inner):
                mgr._suspend_repeat_exclusion = True
                return self_inner
            def __exit__(self_inner, *exc):
                mgr._suspend_repeat_exclusion = False
                return False
        return _Ctx()
```

Also add the `_suspend_repeat_exclusion` trait near the execution-state traits:

```python
    _suspend_repeat_exclusion = Bool(False)
```

Then guard the two existing observers. Change:

```python
    @observe("repetitions")
    def _route_repeats_changed(self, event):
        self.repeat_duration = 0

    @observe("repeat_duration")
    def _route_repeat_duration_changed(self, event):
        self.repetitions = 1
```

to:

```python
    @observe("repetitions")
    def _route_repeats_changed(self, event):
        if self._suspend_repeat_exclusion:
            return
        self.repeat_duration = 0

    @observe("repeat_duration")
    def _route_repeat_duration_changed(self, event):
        if self._suspend_repeat_exclusion:
            return
        self.repetitions = 1
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest device_viewer/tests/test_route_layer_manager_commit.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add device_viewer/models/route.py device_viewer/tests/test_route_layer_manager_commit.py
git commit -m "[Feat] Add commit-to-step state to RouteLayerManager"
```

---

## Task 8: Device viewer inbound handler pulls params on step-id change

Wire the grid → DV pull into `device_view_dock_pane`. The handler compares `dv_msg.step_id` against a new `_last_applied_step_id` attribute and only pulls on transition. On the transition it calls `model.routes.apply_execution_params(...)` which also baselines.

**Files:**
- Modify: `device_viewer/views/device_view_dock_pane.py`

The inbound handler is `apply_message_model` (`device_viewer/views/device_view_dock_pane.py:357`). It already deserializes the `DeviceViewerMessageModel` and applies electrode/route state; we hook into it right after the deserialize.

- [ ] **Step 1: Add `_last_applied_step_id` attribute**

At the top of the dock pane class (wherever other traits/attributes are declared), add:

```python
    _last_applied_step_id = Any()  # Optional[str]; None means no step applied yet
```

(If `Any` isn't already imported from `traits.api`, add it.)

- [ ] **Step 2: Extend `apply_message_model`**

In `apply_message_model` (line 357), after `message_model = DeviceViewerMessageModel.deserialize(message_model_serial)` (line 360) and before the `if message_model.uuid == self.model.uuid:` early-return (line 362), add:

```python
        if message_model.step_id != self._last_applied_step_id:
            self._apply_step_transition(message_model)
            self._last_applied_step_id = message_model.step_id
```

Then add the helper method on the dock pane:

```python
    def _apply_step_transition(self, dv_msg):
        """Pull execution params from the newly-selected step into the sidebar.

        Called only when step_id changes. If the inbound message has no
        execution_params (free mode or legacy), clear the baseline instead so
        the commit button becomes disabled.
        """
        if dv_msg.execution_params:
            self.model.routes.apply_execution_params(dv_msg.execution_params)
        else:
            self.model.routes.clear_committed_baseline()
```

- [ ] **Step 3: Manual smoke test**

Start Redis, backend, and frontend (see `CLAUDE.md` Running section). In the GUI:

1. Select step 1 in the protocol grid.
2. Verify the device viewer sidebar's Duration/Repetitions/Trail Length sliders now reflect that step's cell values.
3. Select step 2 (with different values). Verify the sidebar updates.
4. The commit button (added in Task 10) will not exist yet — don't look for it.

Note any observed deviations; if the sliders don't update, add debug logging to `_apply_step_transition` and re-run.

- [ ] **Step 4: Commit**

```bash
git add device_viewer/views/device_view_dock_pane.py
git commit -m "[Feat] DV sidebar pulls execution params on step-selection change"
```

---

## Task 9: Commit button publisher — DV → grid

Adds the click handler on the dock pane (or on a service observer) that builds `StepParamsCommitMessage`, publishes on `STEP_PARAMS_COMMIT`, and re-baselines the sidebar.

**Files:**
- Modify: `device_viewer/views/device_view_dock_pane.py`

- [ ] **Step 1: Add the observer**

In `device_view_dock_pane.py`, add this observer method on the dock pane class (next to other observers):

```python
    @observe("model:routes:commit_to_step_btn")
    def _on_commit_to_step_btn_fired(self, event):
        step_id = self._last_applied_step_id
        if not step_id:
            # No step selected — shouldn't happen because the button is disabled,
            # but guard anyway.
            return

        params = self.model.routes._current_params()
        msg = StepParamsCommitMessage(step_id=step_id, **params)
        publish_message.send(topic=STEP_PARAMS_COMMIT, message=msg.serialize())

        # Re-baseline so the button goes back to disabled.
        self.model.routes.mark_params_committed()
```

Add imports at the top of the file:

```python
from traits.api import observe  # if not already imported
from protocol_grid.consts import STEP_PARAMS_COMMIT
from protocol_grid.models.step_params_commit import StepParamsCommitMessage
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message  # if not already imported
```

- [ ] **Step 2: Write an integration-shaped unit test**

This is easier to verify end-to-end in Task 15; skip a dedicated unit test here.

- [ ] **Step 3: Commit**

```bash
git add device_viewer/views/device_view_dock_pane.py
git commit -m "[Feat] DV publishes STEP_PARAMS_COMMIT when sidebar commit button fires"
```

---

## Task 10: Wire the commit button into the sidebar view

Adds the button to `run_controls` alongside play/pause/stop, enabled by `commit_enabled`.

**Files:**
- Modify: `device_viewer/views/route_selection_view/route_selection_view.py:154-192`

- [ ] **Step 1: Add the `UItem` inside `run_controls`**

In `route_selection_view.py`, inside `run_controls = HGroup(...)`, after the final `UItem("object.routes.stop_btn", ...)` entry and before `enabled_when="not object.protocol_running"`, add:

```python
    UItem(
        "object.routes.commit_to_step_btn",
        tooltip="Commit execution parameters to selected step",
        enabled_when="object.routes.commit_enabled",
        visible_when=f"not {executing}",
        springy=True,
    ),  # commit to step
```

- [ ] **Step 2: Manual smoke test**

Run the app. With a step selected:

1. Sidebar params should reflect the step's values; commit button disabled.
2. Change Duration → commit button enables.
3. Click commit → button disables. Re-select the step — values match what you committed.
4. Select a different step → sidebar pulls that step's values; button disabled again.
5. Free mode (no step selected) → button disabled.

- [ ] **Step 3: Commit**

```bash
git add device_viewer/views/route_selection_view/route_selection_view.py
git commit -m "[Feat] Add commit-to-step button to sidebar execution controls"
```

---

## Task 11: Protocol grid listener handles `STEP_PARAMS_COMMIT`

**Files:**
- Modify: `protocol_grid/services/message_listener.py:15-121`
- Create: `protocol_grid/tests/test_message_listener_step_params.py`

- [ ] **Step 1: Write the failing test**

Create `protocol_grid/tests/test_message_listener_step_params.py`:

```python
from unittest.mock import patch
import pytest

from protocol_grid.services.message_listener import MessageListener
from protocol_grid.models.step_params_commit import StepParamsCommitMessage
from protocol_grid.consts import STEP_PARAMS_COMMIT


@pytest.fixture
def listener():
    with patch(
        "protocol_grid.services.message_listener.generate_class_method_dramatiq_listener_actor"
    ):
        yield MessageListener()


def test_listener_emits_step_params_commit_received(listener):
    msg = StepParamsCommitMessage(
        step_id="uid-1",
        duration=2.0, repetitions=3, repeat_duration=0.0,
        trail_length=2, trail_overlay=1,
        soft_start=True, soft_terminate=False,
    )

    received = []
    listener.signal_emitter.step_params_commit_received.connect(
        lambda m: received.append(m)
    )

    listener.listener_actor_routine(msg.serialize(), STEP_PARAMS_COMMIT)

    assert len(received) == 1
    assert received[0] == msg
```

- [ ] **Step 2: Run — expect failure**

Run: `pytest protocol_grid/tests/test_message_listener_step_params.py -v`

Expected: FAIL — `step_params_commit_received` attribute does not exist.

- [ ] **Step 3: Add the signal**

In `protocol_grid/services/message_listener.py`, extend `MessageListenerSignalEmitter`:

```python
class MessageListenerSignalEmitter(QObject):
    # ...existing signals unchanged...
    step_params_commit_received = Signal(object)  # StepParamsCommitMessage
```

- [ ] **Step 4: Add the topic branch**

In the same file, add `STEP_PARAMS_COMMIT` to the imports from `protocol_grid.consts`, and import the new model:

```python
from protocol_grid.consts import (... STEP_PARAMS_COMMIT ...)
from protocol_grid.models.step_params_commit import StepParamsCommitMessage
```

Inside `listener_actor_routine`, add a branch — place it right after the `DEVICE_VIEWER_STATE_CHANGED` branch:

```python
            elif topic == STEP_PARAMS_COMMIT:
                try:
                    commit_msg = StepParamsCommitMessage.deserialize(message)
                except Exception as e:
                    logger.error(f"Failed to parse STEP_PARAMS_COMMIT: {e}", exc_info=True)
                    return
                logger.info(f"Received step params commit for step_id={commit_msg.step_id}")
                self.signal_emitter.step_params_commit_received.emit(commit_msg)
```

- [ ] **Step 5: Run tests — expect pass**

Run: `pytest protocol_grid/tests/test_message_listener_step_params.py -v`

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add protocol_grid/services/message_listener.py protocol_grid/tests/test_message_listener_step_params.py
git commit -m "[Feat] Protocol grid listener emits step_params_commit_received"
```

---

## Task 12: Protocol grid widget writes committed params to the step row

**Files:**
- Modify: `protocol_grid/widget.py`

- [ ] **Step 1: Connect the signal in `connect_listener`**

In `protocol_grid/widget.py`, inside `connect_listener` (near line 604), after the existing device-viewer connection (`sig.device_viewer_message_received.connect(...)` at ~610), add:

```python
        # Sidebar commit of execution params to a step
        sig.step_params_commit_received.connect(self._on_step_params_commit)
```

- [ ] **Step 2: Add the handler**

Add a new method to the widget class (place it near `on_device_viewer_message`):

```python
    def _on_step_params_commit(self, commit_msg):
        """Write the 7 execution-param cells of the step identified by step_id."""
        target_item, target_path = self._find_step_by_uid(commit_msg.step_id)
        if not target_item:
            logger.warning(
                f"Commit received for unknown step_id={commit_msg.step_id}; ignoring"
            )
            return

        parent = target_item.parent() or self.model.invisibleRootItem()
        row = target_item.row()

        updates = {
            "Duration":        f"{commit_msg.duration:g}",
            "Repetitions":     str(commit_msg.repetitions),
            "Repeat Duration": f"{commit_msg.repeat_duration:g}",
            "Trail Length":    str(commit_msg.trail_length),
            "Trail Overlay":   str(commit_msg.trail_overlay),
            "Ramp Up":         "1" if commit_msg.soft_start else "0",
            "Ramp Dn":         "1" if commit_msg.soft_terminate else "0",
        }

        self._programmatic_change = True
        try:
            for field, text in updates.items():
                col = protocol_grid_fields.index(field)
                cell = parent.child(row, col)
                if cell is not None:
                    cell.setText(text)

            # Mirror into the ProtocolStep.parameters dict so persistence is up to date.
            step_data = self.state.get_element_by_path(target_path)
            if step_data is not None:
                step_data.parameters.update(updates)

            self._mark_protocol_modified()
        finally:
            self._programmatic_change = False
```

- [ ] **Step 3: Import check**

`protocol_grid_fields` is already imported in widget.py per earlier tasks — verify with grep if unsure.

- [ ] **Step 4: Manual smoke test**

Run the app. Select a step. Change Duration in the sidebar → click commit. Inspect the Duration column of that step — it should reflect the new value. Undo (Ctrl+Z) should roll it back since `_mark_protocol_modified` runs.

- [ ] **Step 5: Commit**

```bash
git add protocol_grid/widget.py
git commit -m "[Feat] Widget writes committed execution params to step row"
```

---

## Task 13: Step-switch dialog for uncommitted sidebar changes

Option B from the brainstorm: Commit / Discard / Cancel modal when a new `step_id` arrives while sidebar is dirty.

**Files:**
- Modify: `device_viewer/views/device_view_dock_pane.py`

- [ ] **Step 1: Locate the existing `confirm` dialog pattern**

Run: `grep -n "from.*confirm import\|def confirm\|confirm(" device_viewer/ -r | head -20`

Find the project's existing yes/no dialog helper. If the project's helper supports only 2 buttons, we may need a Qt `QMessageBox` directly. Inspect and decide. If using `QMessageBox`, add: `from PySide6.QtWidgets import QMessageBox`.

- [ ] **Step 2: Gate the transition on the dirty check**

In `device_view_dock_pane.py`, modify `_apply_step_transition` to first handle the dirty case:

```python
    def _apply_step_transition(self, dv_msg):
        if self.model.routes.commit_enabled and self._last_applied_step_id:
            choice = self._prompt_uncommitted_changes()
            if choice == "cancel":
                # Undo the step_id update by reverting _last_applied_step_id.
                # The caller just assigned dv_msg.step_id — we need to signal
                # "don't apply", so we return False.
                return False
            if choice == "commit":
                # Commit to the old step first.
                prev_id = self._last_applied_step_id
                params = self.model.routes._current_params()
                msg = StepParamsCommitMessage(step_id=prev_id, **params)
                publish_message.send(topic=STEP_PARAMS_COMMIT, message=msg.serialize())
            # "discard" falls through to apply the new step.

        if dv_msg.execution_params:
            self.model.routes.apply_execution_params(dv_msg.execution_params)
        else:
            self.model.routes.clear_committed_baseline()
        return True

    def _prompt_uncommitted_changes(self) -> str:
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox()
        box.setWindowTitle("Uncommitted execution parameters")
        box.setText(
            f"You have uncommitted execution parameter changes for step "
            f"{self._last_applied_step_id}."
        )
        box.setInformativeText("Commit the changes to that step, discard them, or cancel?")
        commit_btn = box.addButton("Commit", QMessageBox.AcceptRole)
        discard_btn = box.addButton("Discard", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is commit_btn:
            return "commit"
        if clicked is discard_btn:
            return "discard"
        return "cancel"
```

- [ ] **Step 3: Update `apply_message_model` to honor cancel**

Back in `apply_message_model` where we added the step-transition block (Task 8, Step 2), change it to:

```python
        if message_model.step_id != self._last_applied_step_id:
            if self._apply_step_transition(message_model):
                self._last_applied_step_id = message_model.step_id
            # On cancel we do NOT update _last_applied_step_id.
            # The grid's selection remains visually on the new row, but the
            # sidebar stays on the old values — see Open Item 1 in the spec
            # for the follow-up on forcing the grid to revert selection.
```

- [ ] **Step 4: Manual smoke test**

1. Select step A, change Duration → dirty.
2. Click step B in the grid.
3. Dialog appears. Choose **Commit** → step A's Duration column updates; sidebar shows step B's values.
4. Repeat — this time choose **Discard** → step A untouched; sidebar shows step B's values.
5. Repeat — choose **Cancel** → sidebar keeps dirty values. (Grid row selection may visually sit on step B; this is the known follow-up.)

- [ ] **Step 5: Commit**

```bash
git add device_viewer/views/device_view_dock_pane.py
git commit -m "[Feat] Prompt Commit/Discard/Cancel on step-switch with dirty sidebar"
```

---

## Task 14: Free-mode — attach execution params on outbound DV message, seed new step

**Files:**
- Modify: `device_viewer/utils/message_utils.py`
- Modify: `protocol_grid/widget.py:1939-1955` (`_insert_free_mode_state_as_new_step`)

- [ ] **Step 1: Attach params to outbound message when in free mode**

In `device_viewer/utils/message_utils.py`, modify `gui_models_to_message_model`:

```python
def gui_models_to_message_model(model: DeviceViewMainModel) -> DeviceViewerMessageModel:
    id_to_channel = {}
    for electrode_id, electrode in model.electrodes.electrodes.items():
        id_to_channel[electrode_id] = electrode.channel

    # In free mode, carry the sidebar's current execution params so the grid
    # can seed them into a newly-created step. With a step selected, the grid
    # already owns those values — don't round-trip them.
    exec_params = None
    if not model.step_id:
        exec_params = model.routes._current_params()

    return DeviceViewerMessageModel(
        channels_activated=model.electrodes.actuated_channels,
        routes=[(layer.route.route, layer.color) for layer in model.routes.layers],
        id_to_channel=id_to_channel,
        step_info={"step_id": model.step_id, "step_label": model.step_label},
        uuid=model.uuid,
        editable=model.editable,
        activated_electrodes_area_mm2=model.electrodes.get_activated_electrode_area_mm2(),
        svg_file=model.electrodes.svg_model.filename,
        execution_params=exec_params,
    )
```

- [ ] **Step 2: Seed new step from free-mode message params**

In `protocol_grid/widget.py`, modify `_insert_free_mode_state_as_new_step`:

```python
    def _insert_free_mode_state_as_new_step(self):
        dv_msg = self.last_device_view_free_mode_msg_with_unsaved_changes
        device_state = device_state_from_device_viewer_message(dv_msg)

        scroll_pos = self.save_scroll_positions()
        self.state.snapshot_for_undo()
        new_step = ProtocolStep(parameters=dict(step_defaults), name="Step")

        # Seed the new step's execution params from the DV sidebar if provided.
        if dv_msg.execution_params:
            new_step.parameters["Duration"]        = f"{dv_msg.execution_params['duration']:g}"
            new_step.parameters["Repetitions"]     = str(dv_msg.execution_params["repetitions"])
            new_step.parameters["Repeat Duration"] = f"{dv_msg.execution_params['repeat_duration']:g}"
            new_step.parameters["Trail Length"]    = str(dv_msg.execution_params["trail_length"])
            new_step.parameters["Trail Overlay"]   = str(dv_msg.execution_params["trail_overlay"])
            new_step.parameters["Ramp Up"]         = "1" if dv_msg.execution_params["soft_start"] else "0"
            new_step.parameters["Ramp Dn"]         = "1" if dv_msg.execution_params["soft_terminate"] else "0"

        new_step.device_state.from_dict(device_state.to_dict())

        self.state.assign_uid_to_step(new_step)
        self.state.sequence.append(new_step)
        self.reassign_ids()
        self.load_from_state()

        self.restore_scroll_positions(scroll_pos)
        self._mark_protocol_modified()
```

- [ ] **Step 3: Manual smoke test**

1. In free mode (no step selected), draw a route, set Duration=3.0 in sidebar.
2. Click into the grid area or trigger the unsaved-changes dialog; accept "Insert as New Step".
3. New step appears. Its Duration column should show `3` (not the default `1.0`).
4. Click the new step; sidebar Duration should now read `3` and commit button should be disabled.

- [ ] **Step 4: Commit**

```bash
git add device_viewer/utils/message_utils.py protocol_grid/widget.py
git commit -m "[Feat] Free-mode sidebar params flow into newly-inserted step"
```

---

## Task 15: End-to-end integration test

Requires Redis. Covers: grid publish with params → sidebar updates → mutate → commit → grid cells update.

**Files:**
- Create: `examples/tests/tests_with_redis_server_need/test_step_params_roundtrip.py`

- [ ] **Step 1: Scaffold the test**

Look at an existing test under `examples/tests/tests_with_redis_server_need/` for the conventional setup pattern (Redis fixture, plugin bootstrap). Mirror it.

Create `test_step_params_roundtrip.py`:

```python
"""Integration: sidebar execution-params pull + commit flow."""
import json

import pytest

from device_viewer.models.messages import DeviceViewerMessageModel
from protocol_grid.models.step_params_commit import StepParamsCommitMessage
from protocol_grid.consts import (
    PROTOCOL_GRID_DISPLAY_STATE, STEP_PARAMS_COMMIT,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message


@pytest.mark.usefixtures("redis_server")  # adapt fixture name to this suite's convention
def test_grid_publishes_params_and_dv_echoes_on_commit(device_viewer_fixture, protocol_grid_fixture):
    """Publish PROTOCOL_GRID_DISPLAY_STATE with execution_params for a new
    step_id. The device viewer applies them. A sidebar edit + commit round-
    trips a STEP_PARAMS_COMMIT back that the grid applies to that step."""

    params = {
        "duration": 2.5,
        "repetitions": 4,
        "repeat_duration": 0.0,
        "trail_length": 3,
        "trail_overlay": 1,
        "soft_start": True,
        "soft_terminate": False,
    }

    msg = DeviceViewerMessageModel(
        channels_activated=set(),
        routes=[],
        id_to_channel={},
        step_info={"step_id": "step-uid-1", "step_label": "Step 1"},
        execution_params=params,
    )
    publish_message.send(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg.serialize())

    # Assert sidebar picked it up (fixture should expose .routes for inspection)
    routes = device_viewer_fixture.wait_for_params(step_id="step-uid-1", timeout=5)
    assert float(routes.duration) == pytest.approx(2.5)
    assert int(routes.repetitions) == 4

    # Mutate + commit
    routes.duration = 9.0
    assert routes.commit_enabled is True
    routes.commit_to_step_btn = True  # fire the Traits Button

    # Assert the grid received the commit and wrote the cell
    committed = protocol_grid_fixture.wait_for_cell_update("step-uid-1", "Duration", timeout=5)
    assert committed == "9"
```

Note: the exact fixture names and helpers (`device_viewer_fixture`, `protocol_grid_fixture`, `wait_for_params`, `wait_for_cell_update`) likely don't exist yet — adapt to what's present in the suite or stub them minimally. If the existing redis suite doesn't have a device-viewer fixture, mark the test `@pytest.mark.skip(reason="requires fixture infra TBD")` and leave a TODO comment referring to this plan's Open Item.

- [ ] **Step 2: Run the test**

Start Redis (`python examples/start_redis_server.py`), then:

Run: `pytest examples/tests/tests_with_redis_server_need/test_step_params_roundtrip.py -v`

Expected: PASS, or SKIP if fixtures are stubbed.

- [ ] **Step 3: Commit**

```bash
git add examples/tests/tests_with_redis_server_need/test_step_params_roundtrip.py
git commit -m "[Test] Integration: sidebar params pull + commit round-trip"
```

---

## Task 16: Update `MESSAGES.md`

**Files:**
- Modify: `MESSAGES.md`

- [ ] **Step 1: Update the topic lists**

In the `device_viewer` "Sending (Via publish_method)" section, add:

```
- STEP_PARAMS_COMMIT "ui/device_viewer/step_params_commit"
```

Under `protocol_grid` (add the section if the file doesn't have one yet — it does not currently appear), or in the Detailed Flows, note the receiving handler.

- [ ] **Step 2: Add a Detailed Flows subsection**

After the existing "Device Viewer → Protocol Grid: routes / state sync" subsection, append:

```markdown
### Device Viewer → Protocol Grid: step execution params commit

Separate topic used only when the user explicitly commits the sidebar
execution parameters back to the selected protocol step. Distinct from the
live route sync so grid cells only mutate on deliberate user action.

**Topic**
- `STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"` — defined in `protocol_grid/consts.py`.

**Publisher side (device_viewer)**
- `device_viewer/views/device_view_dock_pane.py` — `_on_commit_to_step_btn_fired` builds a `StepParamsCommitMessage` and publishes via `publish_message.send(topic=STEP_PARAMS_COMMIT, ...)`.
- Triggered by the Traits Button `commit_to_step_btn` on `RouteLayerManager`.

**Payload schema**
- Pydantic `StepParamsCommitMessage` at `protocol_grid/models/step_params_commit.py`.
- Fields: `step_id, duration, repetitions, repeat_duration, trail_length, trail_overlay, soft_start, soft_terminate`.

**Subscriber side (protocol_grid)**
- `protocol_grid/services/message_listener.py` — `listener_actor_routine` branches on `STEP_PARAMS_COMMIT`, deserializes, emits `step_params_commit_received`.
- `protocol_grid/widget.py` — `_on_step_params_commit` finds the step by UID and writes the 7 cell values.

**Companion addition (pull direction)**
- The grid → DV publish on `PROTOCOL_GRID_DISPLAY_STATE` now carries the target step's params in `DeviceViewerMessageModel.execution_params`. The DV only applies them on `step_id` transition (`device_view_dock_pane._apply_step_transition`), then baselines the sidebar for dirty tracking.
```

- [ ] **Step 3: Commit**

```bash
git add MESSAGES.md
git commit -m "[Docs] Document STEP_PARAMS_COMMIT flow in MESSAGES.md"
```

---

## Final verification

- [ ] **Step 1: Run the full unit test suite for the touched packages**

```bash
pytest device_viewer/tests/ protocol_grid/tests/ -v
```

Expected: all pass.

- [ ] **Step 2: Full manual exercise**

Start Redis + backend + frontend. Walk through every behavior in the spec's "Behavior summary" table:

1. Select step → sidebar pulls params, commit disabled.
2. Edit sidebar field → commit enables.
3. Commit → step row cells update; commit disables.
4. Edit grid cell directly → sidebar does NOT echo.
5. Switch step while dirty → dialog (Commit / Discard / Cancel) works as designed.
6. Free mode: draw + set Duration + accept "insert as new step" dialog → new step has the sidebar's Duration.

Record any deviations and address them before merging.

---

## Open items referenced from the spec

- **Cancel-on-step-switch visual revert.** Task 13 leaves the grid selection on the new row when the user cancels; the sidebar correctly stays on the old step. Forcing the grid to visually re-select the old row is a follow-up (requires a Qt selection signal emit from DV → grid, or a grid-side pre-selection veto hook).
- **Baseline storage location.** Landed on `RouteLayerManager` — keeps the dirty-state logic co-located with the param traits it compares against.

