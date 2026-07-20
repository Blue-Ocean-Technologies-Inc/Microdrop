# PPT Generic Add-Step Topic + Group Selection + Load Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three small, generic `pluggable_protocol_tree` extensions that the fluorescence capture-chain rework (fluorescence-microdrop-plugin-py#6) needs: a `PROTOCOL_TREE_ADD_STEP` request topic (insert a step after a given step, or as a group's last child, with seeded cells), a `group_id` field on `PROTOCOL_TREE_ROW_SELECTED` (today a group click is indistinguishable from deselection), and an `on_row_loaded` column-model hook fired by persistence load (so columns with derived runtime state — e.g. #541 locks — can rebuild it).

**Architecture:** All three ride existing seams: the message models in `models/cell_sync.py`, the `DeviceViewerSyncController`'s worker-thread topic dispatch → `Event(Str)` trait → `@observe(dispatch="ui")` handler pattern (`services/device_viewer_sync.py`), and the per-row build loop in `services/persistence.py`. No new services, no new listeners.

**Tech Stack:** Python 3.13 (pixi), Traits, Pydantic message models, pytest offscreen.

## Global Constraints

- **Working copy:** the Microdrop submodule `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src`. Branch `feat/ppt-fluorescence-support-topics` from **`integration/541-542`** (c0d09b0e) — NOT from origin/main: the `on_row_loaded` hook's consumer test uses #541's lock API, and the fluorescence work builds on the merged state. Note this in the PR body (it must land after #541).
- Conventional Commits; commit per task on the branch; NEVER push, NEVER open a PR without user approval.
- pytest: targeted files only, `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/<file> -q`.
- f-strings only; match surrounding comment density; new topics follow the `"ui/protocol_tree/<verb>"` naming of their siblings.
- `ProtocolTreeAddStepMessage` is ignored while a protocol runs — same rule the set_cell docstring states ("the executor owns the rows then").

---

### Task 1: Message models + topic constants

**Files:**
- Modify: `pluggable_protocol_tree/models/cell_sync.py`
- Modify: `pluggable_protocol_tree/consts.py` (~lines 96-127: topic block + publishers + `ACTOR_TOPIC_DICT`)
- Test: `pluggable_protocol_tree/tests/test_cell_sync_messages.py` (new)

**Interfaces:**
- Produces: `PROTOCOL_TREE_ADD_STEP = "ui/protocol_tree/add_step"`, `protocol_tree_add_step_publisher.publish(*, after_step_id=None, group_id=None, cells, name=None)`, `ProtocolTreeAddStepMessage {after_step_id: str|None, group_id: str|None, cells: dict[str, Any], name: str|None}`; `ProtocolTreeRowSelectedMessage` gains `group_id: str | None = None` and its publisher gains the keyword (default None — every existing caller stays valid).

- [ ] **Step 1: Write the failing tests**

`pluggable_protocol_tree/tests/test_cell_sync_messages.py`:

```python
"""Round-trip tests for the tree's generic sync message models."""

from pluggable_protocol_tree.models.cell_sync import (
    ProtocolTreeAddStepMessage,
    ProtocolTreeRowSelectedMessage,
)


def test_add_step_message_round_trip():
    msg = ProtocolTreeAddStepMessage(
        after_step_id="abc123", cells={"fluorescence_chain": [{"label": "GFP"}]},
        name="Step (capture chain)")
    back = ProtocolTreeAddStepMessage.deserialize(msg.serialize())
    assert back.after_step_id == "abc123"
    assert back.group_id is None
    assert back.cells == {"fluorescence_chain": [{"label": "GFP"}]}
    assert back.name == "Step (capture chain)"


def test_add_step_message_defaults():
    msg = ProtocolTreeAddStepMessage.deserialize(
        ProtocolTreeAddStepMessage(cells={}).serialize())
    assert msg.after_step_id is None and msg.group_id is None
    assert msg.cells == {} and msg.name is None


def test_row_selected_message_gains_group_id():
    msg = ProtocolTreeRowSelectedMessage(step_id=None, group_id="grp1", cells={})
    back = ProtocolTreeRowSelectedMessage.deserialize(msg.serialize())
    assert back.group_id == "grp1" and back.step_id is None


def test_row_selected_message_back_compat_without_group_id():
    # Payloads serialized by older senders must still parse.
    back = ProtocolTreeRowSelectedMessage.deserialize(
        '{"step_id": "s1", "cells": {}}')
    assert back.step_id == "s1" and back.group_id is None
```

- [ ] **Step 2: Run to verify failure**

Run: `... -m pytest src/pluggable_protocol_tree/tests/test_cell_sync_messages.py -q`
Expected: FAIL — `ImportError: cannot import name 'ProtocolTreeAddStepMessage'`.

- [ ] **Step 3: Implement**

In `models/cell_sync.py`:
1. Extend the module docstring with one paragraph:

```
``PROTOCOL_TREE_ADD_STEP`` — request handled by the sync controller:
insert a new step carrying ``cells`` (columns' serialized forms) either
immediately after the step ``after_step_id``, or as the last child of
the group ``group_id``, or appended at the root when neither is given.
Ignored while a protocol runs — the executor owns the rows then.
```

2. Add `group_id: str | None = None` to `ProtocolTreeRowSelectedMessage` (after `step_id`), and thread it through the publisher:

```python
    def publish(self, *, step_id, cells, group_id=None, **kw):
        super().publish(
            {"step_id": step_id, "group_id": group_id, "cells": cells}, **kw)
```

3. Append the new model + publisher (after `ProtocolTreeSetCellPublisher`):

```python
class ProtocolTreeAddStepMessage(BaseModel):
    after_step_id: str | None = None
    group_id: str | None = None
    cells: dict[str, Any] = {}
    name: str | None = None

    def serialize(self) -> str:
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, json_str: str) -> "ProtocolTreeAddStepMessage":
        return cls.model_validate_json(json_str)


class ProtocolTreeAddStepPublisher(ValidatedTopicPublisher):
    """Validated publisher for ``PROTOCOL_TREE_ADD_STEP``."""
    validator_class = ProtocolTreeAddStepMessage

    def publish(self, *, after_step_id=None, group_id=None, cells,
                name=None, **kw):
        super().publish({
            "after_step_id": after_step_id,
            "group_id": group_id,
            "cells": cells,
            "name": name,
        }, **kw)
```

4. In `consts.py`, next to the sibling topics (line ~98) add `PROTOCOL_TREE_ADD_STEP = "ui/protocol_tree/add_step"`; next to the sibling publishers add:

```python
protocol_tree_add_step_publisher = ProtocolTreeAddStepPublisher(
    topic=PROTOCOL_TREE_ADD_STEP)
```

(import `ProtocolTreeAddStepPublisher` alongside the existing cell_sync imports), and append `PROTOCOL_TREE_ADD_STEP,` to the `SYNC_LISTENER_NAME` topic list in `ACTOR_TOPIC_DICT` (after `PROTOCOL_TREE_SET_CELL`).

- [ ] **Step 4: Run to verify pass** — same command; also `src/pluggable_protocol_tree/tests/test_qt_tree_model.py -q` as an import-health canary. Expected: all PASS.

- [ ] **Step 5: Commit (per policy)**

```
feat(pluggable_protocol_tree): add-step topic + group id on row_selected

PROTOCOL_TREE_SET_CELL lets a column-owning plugin write a cell, but
nothing lets it create a step (the fluorescence attach flow inserts a
new step carrying a capture chain), and a group click publishes the
same row_selected payload as a deselection. Add the ADD_STEP message/
publisher/topic and an optional group_id on row_selected.

Part of fluorescence-microdrop-plugin-py#6 groundwork
```

---

### Task 2: Sync-controller handler + group publish

**Files:**
- Modify: `pluggable_protocol_tree/services/device_viewer_sync.py` (imports ~line 50-58; Event traits ~line 171; `_listener_routine` ~line 288; `_publish_row_selected` ~line 488; new module-level helper + handler)
- Test: `pluggable_protocol_tree/tests/test_add_step_request.py` (new)

**Interfaces:**
- Consumes: Task 1's message/topic; `RowManager.get_row_by_uuid`, `RowManager.add_step(parent_path, index, values)`, `col.model.deserialize`.
- Produces: module-level `_insert_step_from_message(row_manager, msg) -> None` (pure, unit-testable — the dramatiq/Qt plumbing wraps it); `_publish_row_selected` publishes `group_id=row.uuid` with `step_id=None` for group rows.

- [ ] **Step 1: Write the failing tests**

`pluggable_protocol_tree/tests/test_add_step_request.py`:

```python
"""PROTOCOL_TREE_ADD_STEP insertion logic (module-level helper — the
dramatiq/Qt plumbing around it is the same Event->observe pattern as
set_cell and is not re-tested here)."""

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.cell_sync import ProtocolTreeAddStepMessage
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    _insert_step_from_message,
)


def _manager():
    m = RowManager(columns=[make_type_column(), make_name_column(),
                            make_duration_column()])
    m.add_step(values={"name": "A"})
    m.add_step(values={"name": "B"})
    return m


def test_insert_after_step_lands_between():
    m = _manager()
    a_uuid = m.root.children[0].uuid
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        after_step_id=a_uuid, cells={"duration_s": 7.5}, name="Chain step"))
    names = [r.name for r in m.root.children]
    assert names == ["A", "Chain step", "B"]
    assert m.root.children[1].duration_s == 7.5


def test_insert_into_group_appends_as_last_child():
    m = _manager()
    m.add_group()
    grp = m.root.children[2]
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        group_id=grp.uuid, cells={}, name="In group"))
    assert [r.name for r in grp.children] == ["In group"]


def test_unknown_ids_append_at_root_end():
    m = _manager()
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        after_step_id="nope", cells={}, name="Tail"))
    assert [r.name for r in m.root.children][-1] == "Tail"


def test_unknown_columns_in_cells_are_skipped():
    m = _manager()
    _insert_step_from_message(m, ProtocolTreeAddStepMessage(
        cells={"duration_s": 2.0, "not_a_column": 1}, name="Partial"))
    assert m.root.children[-1].duration_s == 2.0
```

(If `RowManager` has no `add_group()` matching this call shape, mirror how `pluggable_protocol_tree/views/protocol_tree_pane.py:812-814` adds groups instead — read it before writing the test.)

- [ ] **Step 2: Run to verify failure** — `... test_add_step_request.py -q`. Expected: ImportError on `_insert_step_from_message`.

- [ ] **Step 3: Implement**

In `services/device_viewer_sync.py`:

1. Extend the `pluggable_protocol_tree.consts` import with `PROTOCOL_TREE_ADD_STEP` and the `models.cell_sync` import with `ProtocolTreeAddStepMessage`.
2. Module-level helper (place near `_col_values_from_execution_params`):

```python
def _insert_step_from_message(row_manager, msg) -> None:
    """Insert the step a PROTOCOL_TREE_ADD_STEP message describes.

    Placement: after the step ``after_step_id``; as the last child of
    the group ``group_id``; appended at the root when neither resolves.
    ``cells`` values arrive in each column's serialized form and are
    deserialized through the live column set — unknown col_ids are
    skipped (plugin not loaded), matching persistence's behavior.
    """
    values = {}
    by_id = {c.model.col_id: c for c in row_manager.columns}
    for col_id, raw in (msg.cells or {}).items():
        col = by_id.get(col_id)
        if col is None:
            logger.warning(f"add_step: skipping unknown column {col_id!r}")
            continue
        values[col_id] = col.model.deserialize(raw)
    if msg.name:
        values["name"] = msg.name

    parent_path, index = (), None
    if msg.after_step_id:
        row = row_manager.get_row_by_uuid(msg.after_step_id)
        if row is not None and not isinstance(row, GroupRow):
            path = tuple(row.path)
            parent_path, index = path[:-1], path[-1] + 1
    elif msg.group_id:
        group = row_manager.get_row_by_uuid(msg.group_id)
        if isinstance(group, GroupRow):
            parent_path = tuple(group.path)
    row_manager.add_step(parent_path=parent_path, index=index, values=values)
```

3. Event trait next to `_set_cell_request_event` (line ~171): `_add_step_request_event = Event(Str)`.
4. `_listener_routine` branch (after the `PROTOCOL_TREE_SET_CELL` elif):

```python
        elif topic == PROTOCOL_TREE_ADD_STEP:
            self._add_step_request_event = message
```

5. Handler (next to the set_cell observer, same style):

```python
    @observe("_add_step_request_event", dispatch="ui")
    def _on_add_step_request(self, event) -> None:
        """PROTOCOL_TREE_ADD_STEP: insert a plugin-authored step. Runs on
        the GUI thread (row mutation); refused mid-run like set_cell."""
        if self._protocol_running:
            logger.warning("add_step request ignored: protocol running")
            return
        try:
            msg = ProtocolTreeAddStepMessage.deserialize(event.new)
        except Exception as e:
            logger.warning(f"bad add_step payload {event.new!r}: {e}")
            return
        self._suppress_publish = True
        try:
            _insert_step_from_message(self.row_manager, msg)
        finally:
            self._suppress_publish = False
```

6. `_publish_row_selected` (line ~488): give groups an identity instead of collapsing to the free-mode payload. Change the callers at `_publish_for_row`'s tail from `self._publish_row_selected(None if row is None or isinstance(row, GroupRow) else row)` to `self._publish_row_selected(row)`, and inside `_publish_row_selected` add, before the existing `row is None` branch's publish:

```python
        if isinstance(row, GroupRow):
            protocol_tree_row_selected_publisher.publish(
                step_id=None, group_id=row.uuid, cells={})
            return
```

(Keep the existing `None` branch exactly as is — deselection still publishes `step_id=None` with no group_id. Check every other `_publish_row_selected` call site — grep within the file — and pass the row through unchanged.)

- [ ] **Step 4: Run to verify pass** — `... test_add_step_request.py src/pluggable_protocol_tree/tests/test_cell_sync_messages.py -q`. Expected: all PASS.

- [ ] **Step 5: Commit**

```
feat(pluggable_protocol_tree): handle add-step requests, identify groups

_insert_step_from_message resolves after-step/into-group placement and
deserializes cells through the live column set; the sync controller
consumes the topic on the GUI thread and refuses it mid-run, exactly
like set_cell. Group selections now publish their uuid on row_selected
instead of masquerading as free mode.

Part of fluorescence-microdrop-plugin-py#6 groundwork
```

---

### Task 3: `on_row_loaded` column hook in persistence load

**Files:**
- Modify: `pluggable_protocol_tree/services/persistence.py` (row-build loop, ~lines 160-176)
- Test: `pluggable_protocol_tree/tests/test_persistence.py` (append)

**Interfaces:**
- Produces: after a loaded row's cell values are set, persistence calls `col.model.on_row_loaded(row)` for every resolved live column that defines the hook. Columns use it to rebuild runtime-derived state (the fluorescence chain column rebuilds its #541 capture lock here).

- [ ] **Step 1: Write the failing test** (append to `test_persistence.py`; reuse the module's existing serialize/load helpers exactly as the neighbouring tests do — read that section first):

```python
def test_on_row_loaded_hook_fires_per_loaded_row():
    """Columns with runtime-derived state (e.g. #541 locks) rebuild it
    on load via an optional on_row_loaded(row) model hook."""
    seen = []

    class _HookedModel(BaseColumnModel):
        def trait_for_row(self):
            return Int(0)

        def on_row_loaded(self, row):
            seen.append(row.uuid)

    hooked = Column(model=_HookedModel(col_id="hooked", col_name="Hooked",
                                       default_value=0),
                    view=ReadOnlyLabelColumnView())
    # Build a manager with [type, name, hooked], two steps; serialize;
    # load back through this module's load path (same helpers as the
    # tests above); then:
    assert sorted(seen) == sorted(r.uuid for r in loaded_root.children)
```

(Flesh out the construction lines from the neighbouring round-trip tests — same imports, same helpers. The assertion lines are the contract.)

- [ ] **Step 2: Run to verify failure** — `... test_persistence.py -q`. Expected: the new test fails (`seen == []`).

- [ ] **Step 3: Implement** — in the load loop of `services/persistence.py`, immediately after the per-row `for (col_id, live_col), raw in zip(resolved, values): ... setattr(...)` loop (line ~171-174), add:

```python
        # Runtime-derived column state (issue #541 locks and the like)
        # is never persisted; give each column a chance to rebuild it
        # now that every cell value is in place.
        for _col_id, live_col in resolved:
            if live_col is None:
                continue
            hook = getattr(live_col.model, "on_row_loaded", None)
            if hook is not None:
                hook(row)
```

- [ ] **Step 4: Run to verify pass** — `... test_persistence.py -q`. Expected: all PASS (pre-existing tests unaffected — no builtin column defines the hook).

- [ ] **Step 5: Commit**

```
feat(pluggable_protocol_tree): on_row_loaded column hook after load

Persistence writes cell values with setattr, bypassing set_value, so a
column deriving runtime state from its value (capture locks rebuilt
from a fluorescence chain) had no load-path hook. Call an optional
model.on_row_loaded(row) once per row after its cells are populated.

Part of fluorescence-microdrop-plugin-py#6 groundwork
```

## Self-Review Notes

- Coverage: fluorescence#6 needs (a) create-step-after-uuid with seeded cells ✔ T1+T2, (b) group-click identity ✔ T2, (c) lock rebuild on load ✔ T3. Nothing else was added (YAGNI: no delete/move topics).
- Back-compat: `group_id` optional-with-default on both message and publisher; old payloads parse (tested); deselection payload unchanged.
- Consistency: handler mirrors set_cell (Event(Str), dispatch="ui", mid-run refusal, `_suppress_publish` guard around the mutation like `_insert_free_mode_as_new_step`).
- Known judgment points for the executor: `add_group()` call shape in T2's test (verify against `protocol_tree_pane.py:812-814`), and T3's fixture lines adapted from the neighbouring persistence tests.
