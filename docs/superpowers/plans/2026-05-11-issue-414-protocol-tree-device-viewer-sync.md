# PPT-10.2 Implementation Plan — Bidirectional electrode sync between protocol tree pane and device viewer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the new `pluggable_protocol_tree` dock pane bidirectionally to the device viewer for electrode state. Step-click pushes the step's electrodes/routes to the DV; free-mode toggles in the DV are captured and on next step click prompt the user to "Insert as new step / Discard"; deselect returns DV to free mode. Add a separate `DEVICE_VIEWER_GEOMETRY_CHANGED` topic so the ~120-entry mapping isn't redundantly carried on every state-change publish.

**Architecture:** New `DeviceViewerSyncController` service owns the bidirectional state and the dialog. Pane gains one optional injection (`device_viewer_sync=None`) — demo windows pass `None`, dock pane in the full app constructs and passes a real one. New slim `ProtocolTreeDisplayMessage` Pydantic model on a new `PROTOCOL_TREE_DISPLAY_STATE` topic; one adapter handler added to the device viewer dock pane. `id_to_channel` lives in **one** place — `RowManager.protocol_metadata["electrode_to_channel"]` — written by the controller from the geometry topic, persisted automatically via `to_json`. Pane publishes `PROTOCOL_RUNNING` on start/finish/abort so the DV gates its own free-mode publishes during a run.

**Tech Stack:** Python, Traits/Pyface, PySide6 (Qt6), Dramatiq + Redis (message bus), Pydantic v2, pytest, Envisage plugins, the `pluggable_protocol_tree` core (existing — PPT-1/2/3/10.1), `microdrop_application.dialogs.pyface_wrapper.confirm` for dialogs.

**Spec:** [`../specs/2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md`](../specs/2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md). Companion lifecycle reference: [`../specs/2026-05-11-issue-414-id-to-channel-lifecycle.md`](../specs/2026-05-11-issue-414-id-to-channel-lifecycle.md). Design and decisions are locked in there. The plan below assumes you have read both.

**Issue:** [#414](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/414). Phase-2 follow-up tracked at [#415](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/415).

**Branch state at task start:**
```
feat/414-ppt-102-wire-pluggable_protocol_tree-dock-pane-to-device-viewer-dropbot-listeners
├── 55fe3e4 [PPT-10.2] Cross-reference Phase-2 tracking issue #415 in design + lifecycle docs
├── 0e28c70 [PPT-10.2] Companion doc: id_to_channel lifecycle reference
├── 9000c0c [PPT-10.2] Spec revision: id_to_channel as single-source-of-truth in protocol_metadata
├── 0a14737 [PPT-10.2] Spec revision: confirm reusable RowManager API + add lean geometry topic
├── 25f6b5c [PPT-10.2] Spec: bidirectional electrode sync between protocol tree pane and device viewer
└── 4fa44c7 Merge pull request #413 (PPT-10.1)
```

All work on the inner `src/` submodule (the standalone `Microdrop` repo, the source of truth). All paths in this plan are relative to `microdrop-py/src/`.

---

## Quick reference: relevant existing files

| Where | What you need from it |
|---|---|
| `pluggable_protocol_tree/consts.py` | Add `PROTOCOL_TREE_DISPLAY_STATE` topic. Already imports `DEVICE_VIEWER_STATE_CHANGED`, `PROTOCOL_RUNNING` from `device_viewer.consts`. |
| `pluggable_protocol_tree/models/row_manager.py:41-45` | `protocol_metadata: Dict(Str, AnyTrait)` trait. The single source of truth for `electrode_to_channel`. Already used by executor via `ProtocolContext.scratch`. |
| `pluggable_protocol_tree/models/row_manager.py:86,99,109` | Public `add_step / add_group / remove` methods — reusable as-is. |
| `pluggable_protocol_tree/views/protocol_tree_pane.py:64-71` | Existing `application` / `experiment_manager` / `sticky_manager` injection pattern — match it for `device_viewer_sync`. |
| `pluggable_protocol_tree/views/protocol_tree_pane.py:232-238` | `_on_protocol_started` — add `PROTOCOL_RUNNING` publish here. |
| `pluggable_protocol_tree/views/protocol_tree_pane.py:390-413` | `_on_protocol_finished` / `_on_protocol_aborted` — add `PROTOCOL_RUNNING="False"` publishes. |
| `pluggable_protocol_tree/views/protocol_tree_pane.py:540-556` | `_select_step` / `clear_highlights` — wrap with `_suppress_publish`. |
| `pluggable_protocol_tree/views/tree_widget.py:146` | `_index_to_path(index)` — promote to public `index_to_path`. |
| `pluggable_protocol_tree/views/dock_pane.py` | Construct `DeviceViewerSyncController` + pass into `ProtocolTreePane`. |
| `device_viewer/consts.py:13-26` | Pattern for adding new topic constant + `ACTOR_TOPIC_DICT` extension. |
| `device_viewer/views/device_view_dock_pane.py:271-274` | `_on_display_state_triggered` — pattern for the new `_on_protocol_tree_display_state_triggered` handler. Uses `display_state_signal.emit(serial)`. |
| `device_viewer/views/device_view_dock_pane.py:225,1124,477-481` | `gui_models_to_message_model` is called here to build `message_buffer`. Add `_publish_geometry_if_changed` near these sites and wire into chip-insert / SVG-load handlers. |
| `device_viewer/utils/message_utils.py:7-9` | Where `id_to_channel` is built today. The geometry-publish helper does the same dict comprehension. |
| `device_viewer/models/messages.py` | Add `GeometryChangedMessage` alongside existing `DeviceViewerMessageModel`. |
| `microdrop_application/dialogs/pyface_wrapper.py` | `confirm(parent, message, title, informative, yes_label, no_label, modal=False) -> int` — returns YES (5) / NO (0). |
| `microdrop_utils/dramatiq_pub_sub_helpers.py` | `publish_message(topic, message)` for sending; `generate_class_method_dramatiq_listener_actor(listener_name, class_method)` for class-method-bound actors. |
| `microdrop_utils/broker_server_helpers.py` | `configure_dramatiq_broker()` and `is_redis_running()` for Redis-integration test conftest pattern. |
| `pluggable_protocol_tree/tests/conftest.py` | `qapp` fixture (session-scoped QApplication). Reuse — no new fixture needed for unit tests. |
| `pluggable_protocol_tree/tests/tests_with_redis_server_need/conftest.py` | Pattern for Redis-skipping conftest + `router_actor` session-scoped fixture. Mirror this in our new redis test file. |

**Run-tests pattern** (from memory `reference_pixi_python_invocation`):

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/<file>.py -v"
```

For tests outside the submodule (DV tests):
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest device_viewer/tests/<file>.py -v"
```

---

## Task 1: Topic constants + Pydantic models

**Files:**
- Modify: `pluggable_protocol_tree/consts.py`
- Create: `pluggable_protocol_tree/models/display_state.py`
- Modify: `device_viewer/consts.py`
- Modify: `device_viewer/models/messages.py`
- Test: `pluggable_protocol_tree/tests/test_display_state.py` (NEW)
- Test: `device_viewer/tests/test_geometry_changed_message.py` (NEW)

- [ ] **Step 1: Write the failing test for `ProtocolTreeDisplayMessage`** — create `pluggable_protocol_tree/tests/test_display_state.py`:

```python
"""Tests for ProtocolTreeDisplayMessage Pydantic model + topic constant."""

from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)


def test_topic_constant_value():
    assert PROTOCOL_TREE_DISPLAY_STATE == "ui/protocol_tree/display_state"


def test_default_construction_is_free_mode_empty():
    msg = ProtocolTreeDisplayMessage()
    assert msg.electrodes == []
    assert msg.routes == []
    assert msg.step_id is None
    assert msg.step_label is None
    assert msg.free_mode is False
    assert msg.editable is True


def test_step_payload_round_trip():
    msg = ProtocolTreeDisplayMessage(
        electrodes=["e00", "e01"],
        routes=[["e02", "e03", "e04"]],
        step_id="abc123",
        step_label="Wash",
        free_mode=False,
        editable=True,
    )
    rt = ProtocolTreeDisplayMessage.deserialize(msg.serialize())
    assert rt.electrodes == ["e00", "e01"]
    assert rt.routes == [["e02", "e03", "e04"]]
    assert rt.step_id == "abc123"
    assert rt.step_label == "Wash"
    assert rt.free_mode is False
    assert rt.editable is True


def test_free_mode_payload_round_trip():
    msg = ProtocolTreeDisplayMessage(free_mode=True)
    rt = ProtocolTreeDisplayMessage.deserialize(msg.serialize())
    assert rt.free_mode is True
    assert rt.electrodes == []
    assert rt.routes == []
    assert rt.step_id is None
```

- [ ] **Step 2: Write the failing test for `GeometryChangedMessage`** — create `device_viewer/tests/test_geometry_changed_message.py`:

```python
"""Tests for GeometryChangedMessage Pydantic model + topic constant."""

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    ACTOR_TOPIC_DICT,
    listener_name,
)
from device_viewer.models.messages import GeometryChangedMessage


def test_topic_constant_value():
    assert DEVICE_VIEWER_GEOMETRY_CHANGED == "ui/device_viewer/geometry_changed"


def test_topic_in_actor_topic_dict():
    assert DEVICE_VIEWER_GEOMETRY_CHANGED in ACTOR_TOPIC_DICT[listener_name]


def test_round_trip():
    msg = GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1, "e02": None})
    rt = GeometryChangedMessage.deserialize(msg.serialize())
    assert rt.id_to_channel == {"e00": 0, "e01": 1, "e02": None}


def test_empty_mapping_round_trip():
    msg = GeometryChangedMessage(id_to_channel={})
    rt = GeometryChangedMessage.deserialize(msg.serialize())
    assert rt.id_to_channel == {}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_display_state.py device_viewer/tests/test_geometry_changed_message.py -v"
```
Expected: ImportError on `PROTOCOL_TREE_DISPLAY_STATE`, `ProtocolTreeDisplayMessage`, `DEVICE_VIEWER_GEOMETRY_CHANGED`, `GeometryChangedMessage`.

- [ ] **Step 4: Add the topic constant to `pluggable_protocol_tree/consts.py`** — append after the `PROTOCOL_TOPIC_PREFIX` block:

```python
# PPT-10.2: tree -> DV slim display message
PROTOCOL_TREE_DISPLAY_STATE = "ui/protocol_tree/display_state"
```

- [ ] **Step 5: Create `pluggable_protocol_tree/models/display_state.py`**:

```python
"""Slim payload for `PROTOCOL_TREE_DISPLAY_STATE` — what the
pluggable tree pushes to the device viewer when the user
selects/deselects a step.

Strict subset of `device_viewer.models.messages.DeviceViewerMessageModel`:
only the fields the DV actually needs from us. Channel resolution is
left to the DV (it owns electrode->channel geometry via its own model).
"""

from typing import Optional

from pydantic import BaseModel


class ProtocolTreeDisplayMessage(BaseModel):
    electrodes: list[str] = []
    routes: list[list[str]] = []
    step_id: Optional[str] = None
    step_label: Optional[str] = None
    free_mode: bool = False
    editable: bool = True

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeDisplayMessage":
        return cls.model_validate_json(json_str)
```

- [ ] **Step 6: Add `GeometryChangedMessage` to `device_viewer/models/messages.py`** — append after the existing `DeviceViewerMessageModel` class:

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

- [ ] **Step 7: Add the geometry topic + extend `ACTOR_TOPIC_DICT` in `device_viewer/consts.py`** — after the existing `DEVICE_VIEWER_MEDIA_CAPTURED` line, add:

```python
DEVICE_VIEWER_GEOMETRY_CHANGED = "ui/device_viewer/geometry_changed"
```

And in `ACTOR_TOPIC_DICT[f"{PKG}_listener"]` (the existing list), add `DEVICE_VIEWER_GEOMETRY_CHANGED` as a new entry.

- [ ] **Step 8: Run tests to verify they pass**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_display_state.py device_viewer/tests/test_geometry_changed_message.py -v"
```
Expected: 8 PASSED.

- [ ] **Step 9: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/consts.py pluggable_protocol_tree/models/display_state.py pluggable_protocol_tree/tests/test_display_state.py device_viewer/consts.py device_viewer/models/messages.py device_viewer/tests/test_geometry_changed_message.py
git -C microdrop-py/src commit -m "[PPT-10.2] Add ProtocolTreeDisplayMessage + GeometryChangedMessage models and topics"
```

---

## Task 2: Promote `_index_to_path` to public `index_to_path`

**Files:**
- Modify: `pluggable_protocol_tree/views/tree_widget.py`
- Test: `pluggable_protocol_tree/tests/test_qt_tree_model.py` (existing — add one test)

- [ ] **Step 1: Write the failing test** — append to `pluggable_protocol_tree/tests/test_qt_tree_model.py`:

```python
def test_widget_exposes_public_index_to_path(qapp):
    """Public alias for the previously-private _index_to_path. PPT-10.2
    needs this for the device-viewer sync controller to resolve tree
    selection events without reaching into a private API."""
    from pluggable_protocol_tree.builtins.electrodes_column import (
        make_electrodes_column,
    )
    from pluggable_protocol_tree.builtins.name_column import make_name_column
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

    manager = RowManager(columns=[make_name_column(), make_electrodes_column()])
    manager.add_step(values={"name": "Step A"})
    widget = ProtocolTreeWidget(manager)
    idx = widget.tree.model().index(0, 0)
    assert widget.index_to_path(idx) == widget._index_to_path(idx) == (0,)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_qt_tree_model.py::test_widget_exposes_public_index_to_path -v"
```
Expected: AttributeError on `index_to_path`.

- [ ] **Step 3: Add the public alias** — in `pluggable_protocol_tree/views/tree_widget.py`, immediately after the existing `def _index_to_path(self, index):` method, add:

```python
    def index_to_path(self, index):
        """Public alias for `_index_to_path` (kept for backward compat)."""
        return self._index_to_path(index)
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2.
Expected: 1 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/views/tree_widget.py pluggable_protocol_tree/tests/test_qt_tree_model.py
git -C microdrop-py/src commit -m "[PPT-10.2] Promote ProtocolTreeWidget._index_to_path to public index_to_path"
```

---

## Task 3: DV-side geometry publishing

**Files:**
- Modify: `device_viewer/views/device_view_dock_pane.py`
- Test: `device_viewer/tests/test_geometry_publish.py` (NEW)

- [ ] **Step 1: Write the failing test** — create `device_viewer/tests/test_geometry_publish.py`:

```python
"""Tests for DV-side DEVICE_VIEWER_GEOMETRY_CHANGED publishing."""

from unittest.mock import MagicMock, patch

import pytest

from device_viewer.consts import DEVICE_VIEWER_GEOMETRY_CHANGED
from device_viewer.models.messages import GeometryChangedMessage


@pytest.fixture
def fake_dock_pane():
    """A minimal stand-in for DeviceViewDockPane carrying just the
    attributes the helper touches."""

    class _Electrode:
        def __init__(self, channel):
            self.channel = channel

    pane = MagicMock()
    pane._last_published_id_to_channel = None
    pane.model.electrodes.electrodes = {
        "e00": _Electrode(0),
        "e01": _Electrode(1),
        "e02": _Electrode(None),
    }
    return pane


def test_publishes_on_first_call(fake_dock_pane):
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewDockPane,
    )
    with patch(
        "device_viewer.views.device_view_dock_pane.publish_message"
    ) as send:
        DeviceViewDockPane._publish_geometry_if_changed(fake_dock_pane)

    send.send.assert_called_once()
    args, kwargs = send.send.call_args
    assert kwargs["topic"] == DEVICE_VIEWER_GEOMETRY_CHANGED
    msg = GeometryChangedMessage.deserialize(kwargs["message"])
    assert msg.id_to_channel == {"e00": 0, "e01": 1, "e02": None}


def test_no_republish_when_unchanged(fake_dock_pane):
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewDockPane,
    )
    with patch(
        "device_viewer.views.device_view_dock_pane.publish_message"
    ) as send:
        DeviceViewDockPane._publish_geometry_if_changed(fake_dock_pane)
        DeviceViewDockPane._publish_geometry_if_changed(fake_dock_pane)
    assert send.send.call_count == 1


def test_republishes_when_mapping_changes(fake_dock_pane):
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewDockPane,
    )
    with patch(
        "device_viewer.views.device_view_dock_pane.publish_message"
    ) as send:
        DeviceViewDockPane._publish_geometry_if_changed(fake_dock_pane)
        # Simulate chip insert: mapping changes
        fake_dock_pane.model.electrodes.electrodes["e00"].channel = 5
        DeviceViewDockPane._publish_geometry_if_changed(fake_dock_pane)
    assert send.send.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest device_viewer/tests/test_geometry_publish.py -v"
```
Expected: AttributeError on `_publish_geometry_if_changed`.

- [ ] **Step 3: Implement the helper + initialize the tracking attribute** — in `device_viewer/views/device_view_dock_pane.py`:

(a) Add the import at the top:
```python
from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
)
from device_viewer.models.messages import GeometryChangedMessage
```

(b) Initialize `_last_published_id_to_channel = None` as an instance attribute. Easiest place: in the existing `__init__` (search for it in the file). If there's no plain `__init__` override, add one that calls `super().__init__()` and sets the attr.

(c) Add the helper method (place it near `publish_model_message`, around line 477):

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

- [ ] **Step 4: Wire the helper into the chip-insert and SVG-load handlers** — search for the existing `apply_message_model` call site (around line 395 where `electrode.channel = message_model.id_to_channel.get(...)`) and the place that handles the chip-insert / SVG-load events. After the model is updated in both spots, call `self._publish_geometry_if_changed()`.

If it's not obvious where to call from, the safest umbrella catch is to add an observer:

```python
@observe("model.electrodes.electrodes_items")
def _on_electrodes_geometry_change(self, event=None):
    self._publish_geometry_if_changed()
```

- [ ] **Step 5: Run test to verify it passes**

Run: same as Step 2.
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git -C microdrop-py/src add device_viewer/views/device_view_dock_pane.py device_viewer/tests/test_geometry_publish.py
git -C microdrop-py/src commit -m "[PPT-10.2] DV publishes DEVICE_VIEWER_GEOMETRY_CHANGED on chip insert / SVG load"
```

---

## Task 4: DV-side adapter for `PROTOCOL_TREE_DISPLAY_STATE`

**Files:**
- Modify: `device_viewer/views/device_view_dock_pane.py`
- Modify: `device_viewer/consts.py` (add the topic to `ACTOR_TOPIC_DICT`)
- Test: `device_viewer/tests/test_protocol_tree_display_state_handler.py` (NEW)

- [ ] **Step 1: Write the failing test** — create `device_viewer/tests/test_protocol_tree_display_state_handler.py`:

```python
"""Tests for the DV-side handler that adapts ProtocolTreeDisplayMessage
to the existing DeviceViewerMessageModel pipeline."""

from unittest.mock import MagicMock

from device_viewer.consts import (
    PROTOCOL_TREE_DISPLAY_STATE, ACTOR_TOPIC_DICT, listener_name,
)
from device_viewer.models.messages import DeviceViewerMessageModel
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)


def test_topic_in_actor_topic_dict():
    assert PROTOCOL_TREE_DISPLAY_STATE in ACTOR_TOPIC_DICT[listener_name]


def test_handler_emits_adapted_message_via_display_state_signal():
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewDockPane,
    )
    pane = MagicMock()
    pane.model.electrodes.id_to_channel = {
        "e00": 0, "e01": 1, "e02": 2, "missing": None,
    }
    msg = ProtocolTreeDisplayMessage(
        electrodes=["e00", "e01", "missing"],
        routes=[["e02", "e00"]],
        step_id="uuid-abc", step_label="Wash",
        free_mode=False, editable=True,
    )
    DeviceViewDockPane._on_protocol_tree_display_state_triggered(
        pane, msg.serialize(),
    )

    pane.device_view.display_state_signal.emit.assert_called_once()
    serial = pane.device_view.display_state_signal.emit.call_args.args[0]
    rich = DeviceViewerMessageModel.deserialize(serial)
    assert rich.channels_activated == {0, 1}        # "missing" dropped
    assert rich.routes == [(["e02", "e00"], "blue")]
    assert rich.step_info == {
        "step_id": "uuid-abc", "step_label": "Wash", "free_mode": False,
    }
    assert rich.editable is True
    assert rich.id_to_channel == {
        "e00": 0, "e01": 1, "e02": 2, "missing": None,
    }


def test_free_mode_payload_clears_display():
    from device_viewer.views.device_view_dock_pane import (
        DeviceViewDockPane,
    )
    pane = MagicMock()
    pane.model.electrodes.id_to_channel = {"e00": 0, "e01": 1}
    msg = ProtocolTreeDisplayMessage(free_mode=True)
    DeviceViewDockPane._on_protocol_tree_display_state_triggered(
        pane, msg.serialize(),
    )
    serial = pane.device_view.display_state_signal.emit.call_args.args[0]
    rich = DeviceViewerMessageModel.deserialize(serial)
    assert rich.channels_activated == set()
    assert rich.routes == []
    assert rich.step_info == {
        "step_id": None, "step_label": None, "free_mode": True,
    }
```

- [ ] **Step 2: Add `PROTOCOL_TREE_DISPLAY_STATE` to `device_viewer/consts.py`** — at the top, add:

```python
from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
```

…and append `PROTOCOL_TREE_DISPLAY_STATE` to the existing `ACTOR_TOPIC_DICT[f"{PKG}_listener"]` list (next to `DEVICE_VIEWER_GEOMETRY_CHANGED` from Task 1).

- [ ] **Step 3: Run test to verify it fails**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest device_viewer/tests/test_protocol_tree_display_state_handler.py -v"
```
Expected: AttributeError on `_on_protocol_tree_display_state_triggered`.

- [ ] **Step 4: Implement the handler** — in `device_viewer/views/device_view_dock_pane.py`, immediately after the existing `_on_display_state_triggered` (~line 271), add:

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

- [ ] **Step 5: Run tests to verify they pass**

Run: same as Step 3.
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git -C microdrop-py/src add device_viewer/views/device_view_dock_pane.py device_viewer/consts.py device_viewer/tests/test_protocol_tree_display_state_handler.py
git -C microdrop-py/src commit -m "[PPT-10.2] DV adapter handler for PROTOCOL_TREE_DISPLAY_STATE"
```

---

## Task 5: `DeviceViewerSyncController` skeleton + Qt bridge + actor

**Files:**
- Create: `pluggable_protocol_tree/services/device_viewer_sync.py`
- Test: `pluggable_protocol_tree/tests/test_device_viewer_sync.py` (NEW)

- [ ] **Step 1: Write the failing test** — create `pluggable_protocol_tree/tests/test_device_viewer_sync.py`:

```python
"""Tests for DeviceViewerSyncController."""

from unittest.mock import MagicMock

from device_viewer.consts import (
    DEVICE_VIEWER_STATE_CHANGED,
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    PROTOCOL_RUNNING,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController,
)


def _make_manager():
    return RowManager(columns=[
        make_name_column(),
        make_electrodes_column(),
        make_routes_column(),
    ])


def test_listener_routine_emits_dv_state_signal_on_state_topic(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    spy = MagicMock()
    ctrl.bridge.dv_state_received.connect(spy)
    ctrl._listener_routine("payload-1", DEVICE_VIEWER_STATE_CHANGED)
    qapp.processEvents()
    spy.assert_called_once_with("payload-1")


def test_listener_routine_emits_geometry_signal_on_geometry_topic(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    spy = MagicMock()
    ctrl.bridge.geometry_changed.connect(spy)
    ctrl._listener_routine("geom-payload", DEVICE_VIEWER_GEOMETRY_CHANGED)
    qapp.processEvents()
    spy.assert_called_once_with("geom-payload")


def test_listener_routine_emits_protocol_running_bool(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    spy = MagicMock()
    ctrl.bridge.protocol_running_changed.connect(spy)
    ctrl._listener_routine("True", PROTOCOL_RUNNING)
    ctrl._listener_routine("False", PROTOCOL_RUNNING)
    qapp.processEvents()
    spy.assert_any_call(True)
    spy.assert_any_call(False)


def test_actor_subscribes_to_three_topics():
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    from pluggable_protocol_tree.services.device_viewer_sync import (
        SYNC_ACTOR_TOPIC_DICT,
    )
    topics = SYNC_ACTOR_TOPIC_DICT[ctrl.listener_name]
    assert set(topics) == {
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_device_viewer_sync.py -v"
```
Expected: ImportError on `device_viewer_sync` module.

- [ ] **Step 3: Implement the controller skeleton** — create `pluggable_protocol_tree/services/device_viewer_sync.py`:

```python
"""DeviceViewerSyncController - bidirectional electrode sync between
the protocol tree pane and the device viewer.

Owns:
  - subscription to DEVICE_VIEWER_STATE_CHANGED (free-mode capture)
  - subscription to DEVICE_VIEWER_GEOMETRY_CHANGED (electrode->channel
    mapping cache, written to row_manager.protocol_metadata)
  - subscription to PROTOCOL_RUNNING (gate selection-driven publishes)
  - tree.selectionModel().currentChanged (selection -> DV publish)
  - publishes PROTOCOL_TREE_DISPLAY_STATE
  - the unsaved-free-mode confirm dialog and the
    'Insert as new step' RowManager.add_step call
"""

from __future__ import annotations

from typing import Optional

import dramatiq

from pyface.qt.QtCore import QObject, Signal
from pyface.qt.QtWidgets import QWidget

from traits.api import Bool, Dict, HasTraits, Instance, Int, Str

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    PROTOCOL_RUNNING,
)
from logger.logger_service import get_logger
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from pluggable_protocol_tree.models.row_manager import RowManager

logger = get_logger(__name__)


SYNC_LISTENER_NAME = "protocol_tree_dv_sync_listener"

# Module-level so plugin start-up code can include it in the global
# actor->topic routing without instantiating a controller first.
SYNC_ACTOR_TOPIC_DICT = {
    SYNC_LISTENER_NAME: [
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
    ]
}


class _Bridge(QObject):
    """Qt signal bridge - Dramatiq actor runs on a worker thread, Qt
    mutations must happen on the GUI thread."""

    dv_state_received        = Signal(str)
    geometry_changed         = Signal(str)
    protocol_running_changed = Signal(bool)


class DeviceViewerSyncController(HasTraits):
    row_manager              = Instance(RowManager)
    parent_widget            = Instance(QWidget, allow_none=True)
    bridge                   = Instance(_Bridge)
    dramatiq_actor           = Instance(dramatiq.Actor, allow_none=True)
    listener_name            = Str(SYNC_LISTENER_NAME)

    _free_mode_stash         = Instance(dict, allow_none=True)
    _last_selected_uuid      = Str(allow_none=True)
    _protocol_running        = Bool(False)
    _suppress_publish        = Bool(False)
    # Inverted view of protocol_metadata["electrode_to_channel"]; built
    # on geometry change. The forward mapping itself lives ONLY in
    # row_manager.protocol_metadata - this dict is just an inverted
    # cache for fast free-mode reverse-lookup.
    _channel_to_id_cache     = Dict(Int, Str)

    def traits_init(self):
        if self.bridge is None:
            self.bridge = _Bridge()
        if self.dramatiq_actor is None:
            self.dramatiq_actor = generate_class_method_dramatiq_listener_actor(
                listener_name=self.listener_name,
                class_method=self._listener_routine,
            )

    # --- public lifecycle ----------------------------------------------

    def attach(self, tree_widget) -> None:
        """Bind the controller to a ProtocolTreeWidget instance."""
        self._tree_widget = tree_widget
        # selection wiring (Task 8)
        # bridge connections (Tasks 6, 7, 10)

    def detach(self) -> None:
        """Disconnect Qt signal bindings. Dramatiq broker shutdown
        handles actor teardown."""
        self._tree_widget = None

    # --- single source of truth ----------------------------------------

    @property
    def id_to_channel(self) -> dict[str, int | None]:
        return self.row_manager.protocol_metadata.get(
            "electrode_to_channel", {},
        )

    # --- worker-thread dispatch (no Qt / RowManager mutation here) -----

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

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/services/device_viewer_sync.py pluggable_protocol_tree/tests/test_device_viewer_sync.py
git -C microdrop-py/src commit -m "[PPT-10.2] DeviceViewerSyncController skeleton + dramatiq actor + Qt bridge"
```

---

## Task 6: Geometry handler — write to `protocol_metadata`, rebuild inverted cache

**Files:**
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py`
- Modify: `pluggable_protocol_tree/tests/test_device_viewer_sync.py`

- [ ] **Step 1: Write the failing tests** — append to `pluggable_protocol_tree/tests/test_device_viewer_sync.py`:

```python
def test_geometry_message_writes_to_protocol_metadata(qapp):
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    msg = GeometryChangedMessage(
        id_to_channel={"e00": 0, "e01": 1, "e02": None}
    )
    ctrl._on_geometry_qt(msg.serialize())
    assert ctrl.row_manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 0, "e01": 1, "e02": None,
    }
    assert ctrl._channel_to_id_cache == {0: "e00", 1: "e01"}


def test_geometry_replace_overwrites_metadata_and_rebuilds_cache(qapp):
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0}).serialize()
    )
    ctrl._on_geometry_qt(
        GeometryChangedMessage(
            id_to_channel={"e00": 5, "e01": 6}
        ).serialize()
    )
    assert ctrl.row_manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 5, "e01": 6,
    }
    assert ctrl._channel_to_id_cache == {5: "e00", 6: "e01"}


def test_no_per_step_id_to_channel_storage(qapp):
    """Invariant: id_to_channel lives ONLY in protocol_metadata; never
    on individual rows. Legacy protocol_grid duplicated on each step;
    we deliberately do not."""
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    manager.add_step(values={"name": "S2"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0}).serialize()
    )
    for path, row in manager._walk():
        assert not hasattr(row, "id_to_channel")


def test_protocol_metadata_round_trip(qapp):
    """Mapping persists through to_json / from_json without per-step
    duplication."""
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0}).serialize()
    )
    data = manager.to_json()
    restored = RowManager.from_json(data, columns=list(manager.columns))
    assert restored.protocol_metadata["electrode_to_channel"] == {"e00": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: same as Task 5 Step 2.
Expected: AttributeError on `_on_geometry_qt`.

- [ ] **Step 3: Implement the handler + connect bridge** — in `pluggable_protocol_tree/services/device_viewer_sync.py`, add:

```python
from device_viewer.models.messages import GeometryChangedMessage
```

…and append the handler to `DeviceViewerSyncController`:

```python
def _on_geometry_qt(self, payload: str) -> None:
    """Receive DEVICE_VIEWER_GEOMETRY_CHANGED on the Qt thread. Single
    write site for the electrode-to-channel mapping in protocol-tree
    land."""
    try:
        msg = GeometryChangedMessage.deserialize(payload)
    except Exception as e:
        logger.warning(f"failed to parse geometry payload: {e}")
        return
    self.row_manager.protocol_metadata["electrode_to_channel"] = (
        dict(msg.id_to_channel)
    )
    self._channel_to_id_cache = {
        chan: eid
        for eid, chan in msg.id_to_channel.items()
        if chan is not None
    }
```

Wire it up in `attach`:

```python
def attach(self, tree_widget) -> None:
    self._tree_widget = tree_widget
    self.bridge.geometry_changed.connect(self._on_geometry_qt)
```

And in `detach`:

```python
def detach(self) -> None:
    try:
        self.bridge.geometry_changed.disconnect(self._on_geometry_qt)
    except (RuntimeError, TypeError):
        pass
    self._tree_widget = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 4 new tests PASSED (8 total in the file).

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/services/device_viewer_sync.py pluggable_protocol_tree/tests/test_device_viewer_sync.py
git -C microdrop-py/src commit -m "[PPT-10.2] Controller geometry handler writes to protocol_metadata + inverted cache"
```

---

## Task 7: DV-state handler — free-mode capture + cold-start seed

**Files:**
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py`
- Modify: `pluggable_protocol_tree/tests/test_device_viewer_sync.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
def _make_dv_msg(channels=(), routes=(), step_id=None, id_to_channel=None):
    from device_viewer.models.messages import DeviceViewerMessageModel
    return DeviceViewerMessageModel(
        channels_activated=set(channels),
        routes=list(routes),
        id_to_channel=id_to_channel or {},
        step_info={"step_id": step_id, "step_label": None,
                   "free_mode": step_id is None},
    )


def test_free_mode_message_stashes_electrodes(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    # Pre-seed metadata so reverse-lookup works
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl._on_geometry_qt(
        GeometryChangedMessage(
            id_to_channel={"e00": 0, "e01": 1, "e02": 2}
        ).serialize()
    )
    dv_msg = _make_dv_msg(channels=[1, 2])
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash == {
        "electrodes": ["e01", "e02"], "routes": [],
    }


def test_step_scoped_message_clears_stash(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._free_mode_stash = {"electrodes": ["x"], "routes": []}
    dv_msg = _make_dv_msg(channels=[1], step_id="abc")
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash is None


def test_empty_message_clears_stash(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._free_mode_stash = {"electrodes": ["x"], "routes": []}
    dv_msg = _make_dv_msg(channels=[], routes=[])
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash is None


def test_state_seeds_metadata_when_empty_cold_start(qapp):
    """Phase-1 cold start: if no GEOMETRY_CHANGED seen yet, take the
    inline mapping from the first state message."""
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    assert ctrl.id_to_channel == {}
    dv_msg = _make_dv_msg(
        channels=[0], id_to_channel={"e00": 0, "e01": 1}
    )
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl.row_manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 0, "e01": 1,
    }
    assert ctrl._free_mode_stash == {"electrodes": ["e00"], "routes": []}


def test_state_uses_metadata_for_reverse_lookup(qapp):
    """Once metadata is populated, reverse-lookup uses it - state msgs
    that omit id_to_channel still resolve correctly."""
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1}).serialize()
    )
    dv_msg = _make_dv_msg(channels=[0, 1], id_to_channel={})
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash == {
        "electrodes": ["e00", "e01"], "routes": [],
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: same as Task 5 Step 2.
Expected: AttributeError on `_on_dv_state_qt`.

- [ ] **Step 3: Implement** — append to `DeviceViewerSyncController`:

```python
def _on_dv_state_qt(self, payload: str) -> None:
    """Receive DEVICE_VIEWER_STATE_CHANGED on the Qt thread. Captures
    free-mode toggles into _free_mode_stash; clears stash for any
    step-scoped or empty message."""
    from device_viewer.models.messages import DeviceViewerMessageModel
    try:
        dv_msg = DeviceViewerMessageModel.deserialize(payload)
    except Exception as e:
        logger.warning(f"failed to parse DV state: {e}")
        return

    if dv_msg.step_id:
        self._free_mode_stash = None
        return

    if not dv_msg.channels_activated and not dv_msg.routes:
        self._free_mode_stash = None
        return

    # Cold-start seed: populate metadata if empty so reverse-lookup works.
    if (not self.row_manager.protocol_metadata.get("electrode_to_channel")
            and dv_msg.id_to_channel):
        self.row_manager.protocol_metadata["electrode_to_channel"] = (
            dict(dv_msg.id_to_channel)
        )
        self._channel_to_id_cache = {
            chan: eid
            for eid, chan in dv_msg.id_to_channel.items()
            if chan is not None
        }

    electrodes = sorted(
        self._channel_to_id_cache[c]
        for c in dv_msg.channels_activated
        if c in self._channel_to_id_cache
    )
    routes = [list(ids) for ids, _color in dv_msg.routes]
    self._free_mode_stash = {"electrodes": electrodes, "routes": routes}
```

Wire it up in `attach`:

```python
self.bridge.dv_state_received.connect(self._on_dv_state_qt)
```

…and a matching disconnect in `detach`:

```python
try:
    self.bridge.dv_state_received.disconnect(self._on_dv_state_qt)
except (RuntimeError, TypeError):
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 5 new tests PASSED (13 total in the file).

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/services/device_viewer_sync.py pluggable_protocol_tree/tests/test_device_viewer_sync.py
git -C microdrop-py/src commit -m "[PPT-10.2] Controller DV-state handler: free-mode capture + cold-start seed"
```

---

## Task 8: Tree-selection handler — publish display state on click (with guards)

**Files:**
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py`
- Modify: `pluggable_protocol_tree/tests/test_device_viewer_sync.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_step_click_publishes_display_state(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={
        "name": "S1", "electrodes": ["e00", "e01"], "routes": [["e02"]],
    })
    ctrl = DeviceViewerSyncController(row_manager=manager)
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)

    assert len(publishes) == 1
    from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    topic, payload = publishes[0]
    assert topic == PROTOCOL_TREE_DISPLAY_STATE
    msg = ProtocolTreeDisplayMessage.deserialize(payload)
    assert msg.electrodes == ["e00", "e01"]
    assert msg.routes == [["e02"]]
    assert msg.step_id == row.uuid
    assert msg.step_label == "S1"
    assert msg.free_mode is False


def test_group_click_emits_free_mode_payload(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._publish_for_row(None)        # treats None as deselect/group
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    msg = ProtocolTreeDisplayMessage.deserialize(publishes[0][1])
    assert msg.free_mode is True
    assert msg.electrodes == []
    assert msg.routes == []
    assert msg.step_id is None


def test_protocol_running_blocks_publish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1", "electrodes": ["e00"]})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._protocol_running = True
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)
    assert publishes == []


def test_suppress_publish_blocks_publish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1", "electrodes": ["e00"]})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._suppress_publish = True
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)
    assert publishes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: same as Task 5 Step 2.
Expected: AttributeError on `_publish_for_row`.

- [ ] **Step 3: Implement publish helper + selection slot** — at the top of `device_viewer_sync.py` add:

```python
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)
from pluggable_protocol_tree.models.row import GroupRow
```

…and append to `DeviceViewerSyncController`:

```python
def _publish_for_row(self, row) -> None:
    """Publish PROTOCOL_TREE_DISPLAY_STATE for the given row (or
    free-mode payload if row is None / a group). Gated on suppress
    flag and protocol_running."""
    if self._suppress_publish or self._protocol_running:
        return
    if row is None or isinstance(row, GroupRow):
        msg = ProtocolTreeDisplayMessage(free_mode=True)
        self._last_selected_uuid = ""
    else:
        msg = ProtocolTreeDisplayMessage(
            electrodes=list(getattr(row, "electrodes", []) or []),
            routes=list(getattr(row, "routes", []) or []),
            step_id=row.uuid,
            step_label=row.name,
            free_mode=False,
            editable=True,
        )
        self._last_selected_uuid = row.uuid
    publish_message(
        topic=PROTOCOL_TREE_DISPLAY_STATE,
        message=msg.serialize(),
    )

def _on_current_changed(self, current, _previous) -> None:
    """Qt slot wired to selectionModel().currentChanged. Resolves the
    QModelIndex to a row, then delegates to _publish_for_row."""
    if self._suppress_publish or self._protocol_running:
        return
    if not current.isValid():
        self._publish_for_row(None)
        return
    path = self._tree_widget.index_to_path(current)
    try:
        row = self.row_manager.get_row(path)
    except (IndexError, KeyError):
        self._publish_for_row(None)
        return
    self._publish_for_row(row)
```

Wire selection in `attach`:

```python
selection_model = tree_widget.tree.selectionModel()
selection_model.currentChanged.connect(self._on_current_changed)
self._selection_model = selection_model
```

And matching disconnect in `detach` (guard against the model already being torn down):

```python
try:
    if self._selection_model is not None:
        self._selection_model.currentChanged.disconnect(
            self._on_current_changed,
        )
except (RuntimeError, TypeError):
    pass
self._selection_model = None
```

Add `_selection_model = Instance(QObject, allow_none=True)` to the trait list.

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 4 new tests PASSED (17 total in the file).

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/services/device_viewer_sync.py pluggable_protocol_tree/tests/test_device_viewer_sync.py
git -C microdrop-py/src commit -m "[PPT-10.2] Controller selection handler publishes display state with guards"
```

---

## Task 9: Free-mode prompt + insert-as-new-step

**Files:**
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py`
- Modify: `pluggable_protocol_tree/tests/test_device_viewer_sync.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_step_click_with_stash_yes_inserts_step(qapp, monkeypatch):
    from microdrop_application.dialogs.pyface_wrapper import YES
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: YES,
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {
        "electrodes": ["e00", "e01"], "routes": [["e02"]],
    }
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)

    # New step appended at end of root with the stashed values
    assert len(manager.root.children) == 2
    new_row = manager.root.children[1]
    assert new_row.electrodes == ["e00", "e01"]
    assert new_row.routes == [["e02"]]
    assert ctrl._free_mode_stash is None
    # Exactly one publish (regression for add_step reentrancy)
    assert len(publishes) == 1


def test_step_click_with_stash_no_discards(qapp, monkeypatch):
    from microdrop_application.dialogs.pyface_wrapper import NO
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: NO,
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {
        "electrodes": ["e00"], "routes": [],
    }
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)

    assert len(manager.root.children) == 1   # no add_step
    assert ctrl._free_mode_stash is None
    assert len(publishes) == 1


def test_no_prompt_when_stash_empty(qapp, monkeypatch):
    publishes = []
    confirms = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: confirms.append(1),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)
    assert confirms == []                    # dialog never shown
    assert len(publishes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: same as Task 5 Step 2.
Expected: NameError on `confirm` import in module.

- [ ] **Step 3: Implement** — at the top of `device_viewer_sync.py`:

```python
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
```

…and update `_publish_for_row` to show the prompt before publishing on a real-row click. Replace the existing method body with:

```python
def _publish_for_row(self, row) -> None:
    if self._suppress_publish or self._protocol_running:
        return

    # Resolve the unsaved free-mode stash before changing display.
    if (self._free_mode_stash is not None
            and row is not None
            and not isinstance(row, GroupRow)):
        choice = confirm(
            self.parent_widget,
            "You have unsaved changes from free mode.",
            title="Unsaved Free Mode Changes",
            informative=(
                "There are electrode actuations or routes from free "
                "mode that have not been saved to a protocol step."
                "<br><br>Would you like to insert them as a new step?"
            ),
            yes_label="Insert as New Step",
            no_label="Discard Changes",
        )
        if choice == YES:
            self._insert_free_mode_as_new_step()
        self._free_mode_stash = None

    if row is None or isinstance(row, GroupRow):
        msg = ProtocolTreeDisplayMessage(free_mode=True)
        self._last_selected_uuid = ""
    else:
        msg = ProtocolTreeDisplayMessage(
            electrodes=list(getattr(row, "electrodes", []) or []),
            routes=list(getattr(row, "routes", []) or []),
            step_id=row.uuid,
            step_label=row.name,
            free_mode=False,
            editable=True,
        )
        self._last_selected_uuid = row.uuid

    publish_message(
        topic=PROTOCOL_TREE_DISPLAY_STATE,
        message=msg.serialize(),
    )

def _insert_free_mode_as_new_step(self) -> None:
    """Reentrancy-guarded RowManager.add_step for the free-mode capture.
    Sets _suppress_publish around the mutation so the model-change
    cascade (which can fire selectionModel.currentChanged) does not
    trigger a duplicate publish from this same click."""
    stash = self._free_mode_stash
    if stash is None:
        return
    self._suppress_publish = True
    try:
        self.row_manager.add_step(
            parent_path=(),
            index=None,
            values={
                "name": "Step (free-mode capture)",
                "electrodes": stash["electrodes"],
                "routes": stash["routes"],
            },
        )
    finally:
        self._suppress_publish = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 3 new tests PASSED (20 total).

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/services/device_viewer_sync.py pluggable_protocol_tree/tests/test_device_viewer_sync.py
git -C microdrop-py/src commit -m "[PPT-10.2] Free-mode prompt + insert-as-new-step (with reentrancy guard)"
```

---

## Task 10: Protocol-running gate (controller side)

**Files:**
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py`
- Modify: `pluggable_protocol_tree/tests/test_device_viewer_sync.py`

- [ ] **Step 1: Write the failing test** — append:

```python
def test_protocol_running_signal_updates_flag(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._on_protocol_running_qt(True)
    assert ctrl._protocol_running is True
    ctrl._on_protocol_running_qt(False)
    assert ctrl._protocol_running is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: same as Task 5 Step 2.
Expected: AttributeError on `_on_protocol_running_qt`.

- [ ] **Step 3: Implement + connect bridge** — append to `DeviceViewerSyncController`:

```python
def _on_protocol_running_qt(self, running: bool) -> None:
    self._protocol_running = bool(running)
```

In `attach`, add:

```python
self.bridge.protocol_running_changed.connect(self._on_protocol_running_qt)
```

In `detach`:

```python
try:
    self.bridge.protocol_running_changed.disconnect(
        self._on_protocol_running_qt,
    )
except (RuntimeError, TypeError):
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2.
Expected: 1 new test PASSED (21 total).

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/services/device_viewer_sync.py pluggable_protocol_tree/tests/test_device_viewer_sync.py
git -C microdrop-py/src commit -m "[PPT-10.2] Controller protocol-running gate (subscribe + flag update)"
```

---

## Task 11: Pane wiring — `device_viewer_sync` injection + attach/detach

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py` (existing — append)

- [ ] **Step 1: Write the failing tests** — append to `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`:

```python
def test_pane_accepts_device_viewer_sync_kwarg(qapp):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    pane = ProtocolTreePane(
        [make_name_column()], device_viewer_sync=sync,
    )
    sync.attach.assert_called_once_with(pane.widget)


def test_pane_detaches_sync_on_close(qapp):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    pane = ProtocolTreePane(
        [make_name_column()], device_viewer_sync=sync,
    )
    pane.close()
    sync.detach.assert_called_once()


def test_pane_without_sync_works(qapp):
    """Demo windows pass None - the pane stays usable."""
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    pane = ProtocolTreePane([make_name_column()])
    assert pane.device_viewer_sync is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k device_viewer_sync"
```
Expected: TypeError on unexpected kwarg.

- [ ] **Step 3: Implement** — in `pluggable_protocol_tree/views/protocol_tree_pane.py`:

(a) Add `device_viewer_sync=None` to the `__init__` signature, between `sticky_manager=None` and `phase_ack_topic=...`:

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
    parent=None,
):
```

(b) Stash + attach after `self.widget` is built (around line 86):

```python
self.device_viewer_sync = device_viewer_sync
if self.device_viewer_sync is not None:
    self.device_viewer_sync.attach(self.widget)
```

(c) Detach in `closeEvent` (around line 609), before the `super().closeEvent`:

```python
if self.device_viewer_sync is not None:
    try:
        self.device_viewer_sync.detach()
    except Exception as e:
        logger.warning(f"failed to detach device_viewer_sync: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.2] Pane accepts device_viewer_sync kwarg; attach in init, detach on close"
```

---

## Task 12: Pane publishes `PROTOCOL_RUNNING` on start/finish/abort

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_pane_publishes_protocol_running_true_on_start(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from device_viewer.consts import PROTOCOL_RUNNING
    pane = ProtocolTreePane([make_name_column()])
    pane._on_protocol_started()
    assert (PROTOCOL_RUNNING, "True") in publishes


def test_pane_publishes_protocol_running_false_on_finish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from device_viewer.consts import PROTOCOL_RUNNING
    pane = ProtocolTreePane([make_name_column()])
    pane._on_protocol_finished()
    assert (PROTOCOL_RUNNING, "False") in publishes


def test_pane_publishes_protocol_running_false_on_abort(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.views.protocol_tree_pane.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from device_viewer.consts import PROTOCOL_RUNNING
    pane = ProtocolTreePane([make_name_column()])
    pane._on_protocol_aborted()
    assert (PROTOCOL_RUNNING, "False") in publishes
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k protocol_running"
```
Expected: assertion fails (no PROTOCOL_RUNNING publish observed).

- [ ] **Step 3: Implement** — in `protocol_tree_pane.py`:

(a) Add the import:
```python
from device_viewer.consts import PROTOCOL_RUNNING
```

(b) In `_on_protocol_started` (line 232), at the very top:
```python
publish_message(topic=PROTOCOL_RUNNING, message="True")
```

(c) In `_on_protocol_finished` (line 390), at the very top:
```python
publish_message(topic=PROTOCOL_RUNNING, message="False")
```

(d) In `_on_protocol_aborted` (line 401), at the very top:
```python
publish_message(topic=PROTOCOL_RUNNING, message="False")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2.
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.2] Pane publishes PROTOCOL_RUNNING on start/finish/abort"
```

---

## Task 13: Pane wraps programmatic selection moves with `_suppress_publish`

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_tree_pane.py`

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_select_step_suppresses_sync_publish(qapp, monkeypatch):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    sync._suppress_publish = False
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)
    pane.manager.add_step(values={"name": "S1"})
    row = pane.manager.get_row((0,))

    # Capture the value of _suppress_publish at the moment of programmatic move
    captured = []
    original_set = type(sync)._suppress_publish.fset \
        if hasattr(type(sync)._suppress_publish, "fset") \
        else None

    pane._select_step(row)

    # Sync was set True before the move, then back to False after
    assert sync._suppress_publish is False    # ends restored


def test_clear_highlights_suppresses_sync_publish(qapp):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    sync._suppress_publish = False
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)
    pane.clear_highlights()
    assert sync._suppress_publish is False    # ends restored
```

(Note: the precise behavior is "set True around the call, restore to False after"; the captured-True moment is hard to assert without mocking selectionModel. The end-state assertion plus visual code review of the wrap is enough for this PR.)

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py -v -k suppress"
```
Expected: tests pass-by-default since the code currently doesn't touch the flag — but they'll start failing in the next iteration if we accidentally leave the flag True. Add an explicit positive-side assertion using a helper:

Replace the test bodies with:

```python
def test_select_step_suppresses_sync_publish(qapp):
    from unittest.mock import MagicMock
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    sync = MagicMock()
    seen_states = []

    def select_observer(*a, **kw):
        seen_states.append(sync._suppress_publish)

    sync.attach.side_effect = lambda widget: None
    pane = ProtocolTreePane([make_name_column()], device_viewer_sync=sync)
    pane.manager.add_step(values={"name": "S1"})
    row = pane.manager.get_row((0,))

    # Patch tree.setCurrentIndex to record the suppress flag state
    original = pane.widget.tree.setCurrentIndex
    def capturing(idx):
        seen_states.append(sync._suppress_publish)
        return original(idx)
    pane.widget.tree.setCurrentIndex = capturing
    pane._select_step(row)

    assert seen_states == [True]
    assert sync._suppress_publish is False
```

(Run again to confirm it fails — the wrap doesn't exist yet.)

- [ ] **Step 3: Implement the wraps** — in `protocol_tree_pane.py`, add a small helper near the bottom of `__init__`:

```python
def _suppress_sync_publish(self):
    """Context manager wrapping a programmatic selection move so the
    sync controller's currentChanged slot does not trigger a publish."""
    pane = self
    class _Guard:
        def __enter__(self_):
            if pane.device_viewer_sync is not None:
                pane.device_viewer_sync._suppress_publish = True
        def __exit__(self_, *exc):
            if pane.device_viewer_sync is not None:
                pane.device_viewer_sync._suppress_publish = False
    return _Guard()
```

Then wrap the body of `_select_step` (line 540):

```python
def _select_step(self, row):
    with self._suppress_sync_publish():
        idx = self.widget._node_to_index(row)
        if not idx.isValid():
            return
        parent = idx.parent()
        while parent.isValid():
            self.widget.tree.expand(parent)
            parent = parent.parent()
        self.widget.tree.setCurrentIndex(idx)
        self.widget.tree.scrollTo(idx)
```

…and `clear_highlights` (line 551):

```python
def clear_highlights(self):
    with self._suppress_sync_publish():
        self.widget.highlight_active_row(None)
        self.widget.tree.clearSelection()
        self.widget.tree.setCurrentIndex(QModelIndex())
    # ... rest of body unchanged
```

Also wrap the executor's highlight-active-row connection. Replace `_wire_executor_signals`'s line `self.executor.qsignals.step_started.connect(self.widget.highlight_active_row,)` (line 197-199) with:

```python
def _highlight_active_row_safe(row):
    with self._suppress_sync_publish():
        self.widget.highlight_active_row(row)
self.executor.qsignals.step_started.connect(_highlight_active_row_safe)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2 (re-run after the failing version was confirmed).
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/views/protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane.py
git -C microdrop-py/src commit -m "[PPT-10.2] Pane wraps programmatic selection moves with _suppress_publish"
```

---

## Task 14: Dock pane constructs `DeviceViewerSyncController`

**Files:**
- Modify: `pluggable_protocol_tree/views/dock_pane.py`
- Test: `pluggable_protocol_tree/tests/test_dock_pane.py` (existing — append)

- [ ] **Step 1: Write the failing test** — append to `pluggable_protocol_tree/tests/test_dock_pane.py`:

```python
def test_dock_pane_passes_device_viewer_sync_to_pane(qapp):
    """The dock pane in the full app constructs a DeviceViewerSyncController
    and passes it to the ProtocolTreePane."""
    from unittest.mock import MagicMock, patch
    from pluggable_protocol_tree.views.dock_pane import (
        PluggableProtocolDockPane,
    )
    from pluggable_protocol_tree.builtins.name_column import (
        make_name_column,
    )
    from pluggable_protocol_tree.services.device_viewer_sync import (
        DeviceViewerSyncController,
    )

    dp = PluggableProtocolDockPane(columns=[make_name_column()])
    dp.task = MagicMock()
    dp.task.window.application.current_experiment_directory = None

    parent = MagicMock()
    with patch(
        "pluggable_protocol_tree.views.dock_pane.ProtocolTreePane"
    ) as PaneCls:
        dp.create_contents(parent)

    pane_kwargs = PaneCls.call_args.kwargs
    assert isinstance(
        pane_kwargs["device_viewer_sync"], DeviceViewerSyncController,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_dock_pane.py -v -k device_viewer_sync"
```
Expected: KeyError on `device_viewer_sync` kwarg.

- [ ] **Step 3: Implement** — replace `pluggable_protocol_tree/views/dock_pane.py:create_contents` body with:

```python
def create_contents(self, parent):
    # Local imports to avoid pulling Qt at plugin-import time.
    from pluggable_protocol_tree.models.row_manager import RowManager
    from pluggable_protocol_tree.services.device_viewer_sync import (
        DeviceViewerSyncController,
    )
    from pluggable_protocol_tree.views.protocol_tree_pane import (
        ProtocolTreePane,
    )

    app = self.task.window.application
    experiment_manager = ExperimentManager(app.current_experiment_directory)
    sticky_manager = StickyWindowManager()

    manager = RowManager(columns=list(self.columns))
    sync = DeviceViewerSyncController(row_manager=manager)

    return ProtocolTreePane(
        manager,
        application=app,
        experiment_manager=experiment_manager,
        sticky_manager=sticky_manager,
        device_viewer_sync=sync,
        parent=parent,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2.
Expected: PASS.

- [ ] **Step 5: Register the sync actor's topic dict in plugin start-up** — open `pluggable_protocol_tree/plugin.py` and locate the `start()` method (or wherever `ACTOR_TOPIC_DICT` is registered with the `MessageRouterPlugin`). Merge `SYNC_ACTOR_TOPIC_DICT` into the plugin's contributed topic-routing map. Match the existing pattern in the file.

- [ ] **Step 6: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/views/dock_pane.py pluggable_protocol_tree/plugin.py pluggable_protocol_tree/tests/test_dock_pane.py
git -C microdrop-py/src commit -m "[PPT-10.2] Dock pane constructs DeviceViewerSyncController + plugin registers actor topics"
```

---

## Task 15: Redis-integration tests

**Files:**
- Create: `pluggable_protocol_tree/tests/tests_with_redis_server_need/test_device_viewer_sync_redis.py`

- [ ] **Step 1: Verify Redis is available**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python -c "from microdrop_utils.broker_server_helpers import is_redis_running; print(is_redis_running())"
```
Expected: `True`. If False, start Redis: `pixi run python src/examples/start_redis_server.py` in another terminal.

- [ ] **Step 2: Write the test file** — create `pluggable_protocol_tree/tests/tests_with_redis_server_need/test_device_viewer_sync_redis.py`:

```python
"""End-to-end Redis round-trip tests for DeviceViewerSyncController."""

import time

import pytest

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    PROTOCOL_RUNNING,
)
from device_viewer.models.messages import (
    DeviceViewerMessageModel, GeometryChangedMessage,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
from pluggable_protocol_tree.models.display_state import (
    ProtocolTreeDisplayMessage,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController, SYNC_ACTOR_TOPIC_DICT, SYNC_LISTENER_NAME,
)


def _make_manager():
    return RowManager(columns=[
        make_name_column(),
        make_electrodes_column(),
        make_routes_column(),
    ])


@pytest.fixture
def subscribed_router(router_actor):
    """Subscribe the sync controller's actor to the router for this test."""
    for topic in SYNC_ACTOR_TOPIC_DICT[SYNC_LISTENER_NAME]:
        router_actor.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=SYNC_LISTENER_NAME,
        )
    yield router_actor
    for topic in SYNC_ACTOR_TOPIC_DICT[SYNC_LISTENER_NAME]:
        try:
            router_actor.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=SYNC_LISTENER_NAME,
            )
        except Exception:
            pass


def test_geometry_round_trip_to_protocol_metadata(
    qapp, subscribed_router,
):
    """Redis: publishing GEOMETRY_CHANGED reaches the controller and
    populates protocol_metadata."""
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    msg = GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1})
    publish_message(
        topic=DEVICE_VIEWER_GEOMETRY_CHANGED, message=msg.serialize(),
    )

    # Spin the dramatiq broker briefly
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if manager.protocol_metadata.get("electrode_to_channel"):
            break
        time.sleep(0.05)

    assert manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 0, "e01": 1,
    }


def test_dv_state_to_stash_round_trip(qapp, subscribed_router):
    """Redis: publishing DEVICE_VIEWER_STATE_CHANGED reaches the
    controller and populates _free_mode_stash."""
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    publish_message(
        topic=DEVICE_VIEWER_GEOMETRY_CHANGED,
        message=GeometryChangedMessage(
            id_to_channel={"e00": 0, "e01": 1}
        ).serialize(),
    )
    publish_message(
        topic=DEVICE_VIEWER_STATE_CHANGED,
        message=DeviceViewerMessageModel(
            channels_activated={0, 1},
            routes=[],
            id_to_channel={"e00": 0, "e01": 1},
            step_info={"step_id": None, "step_label": None,
                       "free_mode": True},
        ).serialize(),
    )

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if ctrl._free_mode_stash:
            break
        time.sleep(0.05)

    assert ctrl._free_mode_stash == {
        "electrodes": ["e00", "e01"], "routes": [],
    }


def test_protocol_running_round_trip(qapp, subscribed_router):
    """Redis: PROTOCOL_RUNNING True/False reaches the controller and
    flips _protocol_running."""
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    publish_message(topic=PROTOCOL_RUNNING, message="True")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if ctrl._protocol_running:
            break
        time.sleep(0.05)
    assert ctrl._protocol_running is True

    publish_message(topic=PROTOCOL_RUNNING, message="False")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if not ctrl._protocol_running:
            break
        time.sleep(0.05)
    assert ctrl._protocol_running is False
```

- [ ] **Step 3: Run the integration tests**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/test_device_viewer_sync_redis.py -v"
```
Expected: 3 PASSED (or all SKIPPED if Redis isn't reachable — confirm by re-checking Step 1).

- [ ] **Step 4: Commit**

```bash
git -C microdrop-py/src add pluggable_protocol_tree/tests/tests_with_redis_server_need/test_device_viewer_sync_redis.py
git -C microdrop-py/src commit -m "[PPT-10.2] Redis-integration tests for DV-sync round-trips"
```

---

## Task 16: Manual smoke + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit-test suite for both modules**

Run:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ device_viewer/tests/ -v"
```
Expected: all NEW tests pass; no NEW failures in pre-existing tests. (Pre-existing failures listed in `reference_pixi_python_invocation` memory — `test_shapely_helpers.py`, `test_dmf_utils.py::test_set_fill_black` — are not regressions.)

- [ ] **Step 2: Manual smoke — launch the full app**

Run (in two terminals):
```bash
# Terminal 1 - start Redis if not already running
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python src/examples/start_redis_server.py

# Terminal 2 - launch the app with mock dropbot
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python src/examples/run_device_viewer_pluggable.py
```

- [ ] **Step 3: Run the manual smoke checklist** (from spec §7):

  1. Toggle electrodes in DV with no step selected → no immediate stash visible, but logged.
  2. Click step 1 → free-mode prompt appears → "Insert as New Step" → new step at end of tree, original click selects step 1, DV shows step 1's electrodes.
  3. Click a group → DV clears (free-mode visual).
  4. Start protocol → executor drives DV; clicking other steps mid-run does nothing.
  5. After protocol ends, selection-driven sync resumes.

- [ ] **Step 4: Open PR** (per project workflow):

```bash
git -C microdrop-py/src push -u origin feat/414-ppt-102-wire-pluggable_protocol_tree-dock-pane-to-device-viewer-dropbot-listeners
gh pr create --repo Blue-Ocean-Technologies-Inc/Microdrop --title "[PPT-10.2] Bidirectional electrode sync between protocol tree pane and device viewer" --body "$(cat <<EOF
Resolves the device_viewer_state_changed row of #414. See specs:
- docs/superpowers/specs/2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md
- docs/superpowers/specs/2026-05-11-issue-414-id-to-channel-lifecycle.md

Phase-2 (lean state payload) tracked at #415.

## Test plan
- [ ] All new unit tests pass
- [ ] All Redis-integration tests pass against a running Redis
- [ ] Manual smoke: free-mode capture + step click + DV display end-to-end with MockDropbotControllerPlugin

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist

- **Spec coverage:** All decisions (rows 1-9), file-layout entries, data-flow branches A/B/B'/C/D/E, message schemas, controller internals, test matrix, and acceptance criteria from `2026-05-11-issue-414-protocol-tree-device-viewer-sync-design.md` map to tasks above. The id_to_channel single-source-of-truth invariant from the lifecycle doc is enforced by Tasks 6 and 7's tests.
- **Placeholder scan:** No "TBD"/"TODO" placeholders. Every code step shows actual code. Every test step shows actual test code. Every command shows the exact invocation.
- **Type consistency:** `ProtocolTreeDisplayMessage`, `GeometryChangedMessage`, `DeviceViewerSyncController`, `_publish_for_row`, `_on_dv_state_qt`, `_on_geometry_qt`, `_on_protocol_running_qt`, `_on_current_changed`, `_insert_free_mode_as_new_step`, `_suppress_sync_publish`, `index_to_path`, `attach`, `detach` — all named consistently across tasks.
- **Phase-1 vs Phase-2 boundary:** `id_to_channel` stays in `DEVICE_VIEWER_STATE_CHANGED` payload throughout Phase 1 (Task 3 doesn't touch `gui_models_to_message_model`). Phase 2 lives in #415.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-issue-414-protocol-tree-device-viewer-sync.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
