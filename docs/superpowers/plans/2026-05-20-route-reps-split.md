# Route-Reps Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project test convention:** the implementer does NOT auto-run pytest. Every "Run the test" step is a **manual checkpoint** — pause and let the user run it. Write the test first (TDD), but hand the run to the user.

**Goal:** Decouple the whole-thing "Reps" repeat from route-loop repetition by adding a `route_repetitions` column, rename "Repeat (s)" → "Route Reps Dur" with exact hold-last-phase padding, and turn the duration-mode flag into a plain row trait persisted via a `row_flags` map.

**Architecture:** `repetitions` keeps driving `row_manager._expand_frames` (whole-thing repeat) only; a new `route_repetitions` column feeds `phase_math.iter_phases` `n_repeats`. The duration-mode flag `repeat_duration_controls` moves off the column system onto `BaseRow` as a `Bool` trait, round-tripped through a new top-level `row_flags` uuid-map in persistence. The reps↔duration confirm-dialog handoff is repointed to arbitrate Route Reps ↔ Route Reps Dur.

**Tech Stack:** Python, Traits/TraitsUI, PySide6/Qt (pyface), pytest. Pixi-managed env.

**Spec:** `docs/superpowers/specs/2026-05-20-route-reps-split-design.md`

**Working dir for all paths below:** `microdrop-py/src/` (the Microdrop submodule). Run pytest from there.

---

## File Structure

- **Modify** `pluggable_protocol_tree/models/row.py` — add `repeat_duration_controls` Bool trait to `BaseRow`.
- **Modify** `pluggable_protocol_tree/services/persistence.py` — serialize/deserialize a `row_flags` uuid-map.
- **Create** `pluggable_protocol_tree/builtins/route_repetitions_column.py` — new "Route Reps" column + `RouteRepsHandler`.
- **Modify** `pluggable_protocol_tree/builtins/repetitions_column.py` — drop the dialog; "Reps" becomes a plain spinbox.
- **Modify** `pluggable_protocol_tree/builtins/repeat_duration_column.py` — rename display, make visible, repoint estimate + flag.
- **Modify** `pluggable_protocol_tree/services/phase_math.py` — duration-mode return-phase drop + `pad_seconds_for_duration`.
- **Modify** `pluggable_protocol_tree/builtins/routes_column.py` — feed `route_repetitions`; hold-pad after loop.
- **Delete** `pluggable_protocol_tree/builtins/repeat_duration_controls_column.py`.
- **Modify** `pluggable_protocol_tree/plugin.py` — column list (add route_repetitions, drop controls).
- **Modify** demos: `run_widget.py`, `run_session_demo.py`, `run_headless.py`, `run_widget_auto.py`.
- **Modify/Create** tests alongside each change.

---

### Task 1: Add `repeat_duration_controls` trait to BaseRow

**Files:**
- Modify: `pluggable_protocol_tree/models/row.py:14` (imports) and `:20-26` (BaseRow body)
- Test: `pluggable_protocol_tree/tests/test_row_manager.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- repeat_duration_controls internal flag (route-reps split) ---

def test_base_row_has_repeat_duration_controls_flag_default_false():
    from pluggable_protocol_tree.models.row import BaseRow, GroupRow
    assert BaseRow().repeat_duration_controls is False
    assert GroupRow().repeat_duration_controls is False


def test_repeat_duration_controls_is_settable():
    from pluggable_protocol_tree.models.row import BaseRow
    r = BaseRow()
    r.repeat_duration_controls = True
    assert r.repeat_duration_controls is True
```

- [ ] **Step 2: Run test to verify it fails** *(manual checkpoint — ask the user)*

Run: `pytest pluggable_protocol_tree/tests/test_row_manager.py -k repeat_duration_controls -v`
Expected: FAIL — `AttributeError`/`TraitError` (trait does not exist yet).

- [ ] **Step 3: Add the trait**

In `pluggable_protocol_tree/models/row.py`, add `Bool` to the traits import on line 14:

```python
from traits.api import HasTraits, Str, List, Instance, Tuple, Property, Bool, provides
```

Add the trait inside `BaseRow` (after the `path` Property, around line 26):

```python
    repeat_duration_controls = Bool(
        False,
        desc="Internal mode flag: True when Route Reps Dur is the "
             "authoritative loop knob; False when Route Reps controls. "
             "Not a column — persisted via the row_flags map.")
```

- [ ] **Step 4: Run test to verify it passes** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_row_manager.py -k repeat_duration_controls -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row.py pluggable_protocol_tree/tests/test_row_manager.py
git commit -m "[route-reps] Add repeat_duration_controls Bool trait to BaseRow"
```

---

### Task 2: Persist the flag via a `row_flags` uuid-map

**Files:**
- Modify: `pluggable_protocol_tree/services/persistence.py` (serialize_tree `:35-62`, `_walk_with_depth` `:65-75`, deserialize_tree `:84-151`)
- Test: `pluggable_protocol_tree/tests/test_persistence.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_persistence.py`:

```python
# --- repeat_duration_controls round-trip via row_flags (route-reps split) ---

def test_row_flags_serialized_only_for_true_rows(manager):
    p = manager.add_step(values={"name": "A"})
    row = manager.get_row(p)
    row.repeat_duration_controls = True
    manager.add_step(values={"name": "B"})  # stays False
    data = manager.to_json()
    flags = data["row_flags"]
    assert row.uuid in flags
    assert flags[row.uuid]["repeat_duration_controls"] is True
    # The False row is omitted to keep saves compact.
    assert len(flags) == 1


def test_row_flags_round_trip(manager):
    p = manager.add_step(values={"name": "A"})
    manager.get_row(p).repeat_duration_controls = True
    data = manager.to_json()
    new_mgr = RowManager.from_json(data, columns=list(manager.columns))
    assert new_mgr.root.children[0].repeat_duration_controls is True


def test_load_old_payload_without_row_flags_defaults_false(manager):
    manager.add_step(values={"name": "A"})
    data = manager.to_json()
    del data["row_flags"]            # simulate a pre-split save
    new_mgr = RowManager.from_json(data, columns=list(manager.columns))
    assert new_mgr.root.children[0].repeat_duration_controls is False
```

- [ ] **Step 2: Run test to verify it fails** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_persistence.py -k row_flags -v`
Expected: FAIL — `KeyError: 'row_flags'`.

- [ ] **Step 3: Implement serialize side**

In `pluggable_protocol_tree/services/persistence.py`, add a row-flags collector and include it in the output dict. Replace the `serialize_tree` return block (lines ~54-62) so it also walks flags:

```python
    rows_out = list(_walk_with_depth(root, columns, depth=0, skip_root=True))
    row_flags = {}
    _collect_row_flags(root, row_flags, skip_root=True)

    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "protocol_metadata": dict(protocol_metadata or {}),
        "row_flags": row_flags,
        "columns": col_specs,
        "fields": fields,
        "rows": rows_out,
    }
```

Add this helper just below `_walk_with_depth` (after line ~75):

```python
def _collect_row_flags(node, out: dict, skip_root: bool) -> None:
    """Populate ``out`` with {uuid: {"repeat_duration_controls": True}} for
    every row whose flag is True. False rows are omitted to keep saves
    compact (load defaults missing entries to False)."""
    if not skip_root and bool(getattr(node, "repeat_duration_controls", False)):
        out[node.uuid] = {"repeat_duration_controls": True}
    if isinstance(node, GroupRow):
        for child in node.children:
            _collect_row_flags(child, out, skip_root=False)
```

- [ ] **Step 4: Implement deserialize side**

In `deserialize_tree`, read the map once before the row loop. Add after `fields: list = data["fields"]` (line ~98):

```python
    row_flags: dict = data.get("row_flags") or {}
```

Inside the row loop, right after `row = row_cls(name=name, uuid=uuid_)` (line ~138), apply the flag:

```python
        row.repeat_duration_controls = bool(
            row_flags.get(uuid_, {}).get("repeat_duration_controls", False)
        )
```

- [ ] **Step 5: Run tests to verify they pass** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_persistence.py -v`
Expected: PASS (new row_flags tests + existing persistence tests still green — `fields`/`rows` positions are untouched).

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/persistence.py pluggable_protocol_tree/tests/test_persistence.py
git commit -m "[route-reps] Round-trip repeat_duration_controls via row_flags map"
```

---

### Task 3: New `route_repetitions` column + RouteRepsHandler

**Files:**
- Create: `pluggable_protocol_tree/builtins/route_repetitions_column.py`
- Test: `pluggable_protocol_tree/tests/test_builtins.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_builtins.py`:

```python
# --- route_repetitions column (route-reps split) ---

def test_route_repetitions_column_metadata():
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    col = make_route_repetitions_column()
    assert col.model.col_id == "route_repetitions"
    assert col.model.col_name == "Route Reps"
    assert col.model.default_value == 1
    assert col.view.hidden_by_default is False
    assert col.view.low == 1 and col.view.high == 1000


def test_route_repetitions_editable_on_step_not_group():
    from pyface.qt.QtCore import Qt
    from pluggable_protocol_tree.models.row import BaseRow, GroupRow
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    col = make_route_repetitions_column()
    assert col.view.get_flags(BaseRow()) & Qt.ItemIsEditable
    assert not (col.view.get_flags(GroupRow()) & Qt.ItemIsEditable)


def test_route_reps_handler_plain_write_when_not_in_duration_mode():
    from pluggable_protocol_tree.models.row import BaseRow
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    col = make_route_repetitions_column()
    row = BaseRow()
    row.repeat_duration_controls = False
    assert col.handler.on_interact(row, col.model, 5) is True
    assert row.route_repetitions == 5


def test_route_reps_handler_switch_back_from_duration_on_confirm(monkeypatch):
    import pluggable_protocol_tree.builtins.route_repetitions_column as mod
    from pluggable_protocol_tree.models.row import BaseRow
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: mod.YES)
    col = mod.make_route_repetitions_column()
    row = BaseRow()
    row.repeat_duration_controls = True
    assert col.handler.on_interact(row, col.model, 3) is True
    assert row.repeat_duration_controls is False     # handed back to count mode
    assert row.route_repetitions == 3


def test_route_reps_handler_cancel_rejects_edit(monkeypatch):
    import pluggable_protocol_tree.builtins.route_repetitions_column as mod
    from pluggable_protocol_tree.models.row import BaseRow
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: 0)   # not YES
    col = mod.make_route_repetitions_column()
    row = BaseRow()
    row.repeat_duration_controls = True
    row.route_repetitions = 1
    assert col.handler.on_interact(row, col.model, 9) is False
    assert row.repeat_duration_controls is True          # unchanged
    assert row.route_repetitions == 1                    # edit rejected
```

> Note: `route_repetitions` is set on `BaseRow` in these tests via the handler/model; `BaseRow` itself has no such trait. Add a permissive trait so plain `BaseRow` instances accept it in unit tests **and** so `model.set_value` works without a built row-type. Do this by giving the column model a typed `trait_for_row` (used by `build_row_type` in real runs) — for the bare-`BaseRow` unit tests we set the attribute dynamically, which Traits' `HasTraits` permits as a shadow attribute. If a test fails because `BaseRow` rejects the attribute, build the row type instead: `build_row_type([col], base=BaseRow)()`.

- [ ] **Step 2: Run test to verify it fails** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_builtins.py -k route_rep -v`
Expected: FAIL — `ModuleNotFoundError: route_repetitions_column`.

- [ ] **Step 3: Create the column module**

Create `pluggable_protocol_tree/builtins/route_repetitions_column.py`:

```python
"""Route Reps column — number of times a step's ROUTES loop.

Feeds ``n_repeats`` into phase_math.iter_phases (loop-route cycles, and
open-route passes when Lin Reps is on). Distinct from the "Reps" column,
which repeats the whole step/group via row_manager._expand_frames. On a
step, total route plays = Reps x Route Reps. Inert on groups.

Edits prompt the user to hand control back from Route Reps Dur when the
row is in duration-controlled mode (``repeat_duration_controls`` True).
Confirming flips the flag back to False; cancelling rejects the edit.
This is the count-side of the same mode handoff the legacy protocol_grid
used between Repetitions and Repeat Duration.
"""

from pyface.qt.QtCore import Qt
from traits.api import Int

from microdrop_application.dialogs.pyface_wrapper import YES, confirm

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RouteRepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this step's routes loop "
                           "(loop-route cycles / open-route passes).")


class RouteRepsHandler(BaseColumnHandler):
    """Count-side of the Route Reps <-> Route Reps Dur mode handoff."""

    def on_interact(self, row, model, value):
        if not bool(getattr(row, "repeat_duration_controls", False)):
            return model.set_value(row, value)
        choice = confirm(
            None,
            title="Switch to Route Reps Control",
            message=(
                "Switching back to Route Reps control will loop until the "
                "largest loop has completed all repetitions.<br><br>"
                "Route Reps Dur will be recalculated to match exactly "
                "(no idle time)."
            ),
            yes_label="Switch",
            no_label="Cancel",
        )
        if choice != YES:
            return False
        row.repeat_duration_controls = False
        return model.set_value(row, value)


def make_route_repetitions_column():
    return Column(
        model=RouteRepetitionsColumnModel(
            col_id="route_repetitions", col_name="Route Reps",
            default_value=1,
        ),
        view=IntSpinBoxColumnView(low=1, high=1000),
        handler=RouteRepsHandler(),
    )
```

- [ ] **Step 4: Run tests to verify they pass** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_builtins.py -k route_rep -v`
Expected: PASS. If a bare-`BaseRow` test errors on attribute assignment, switch that test to `row = build_row_type([col], base=BaseRow)()` per the note in Step 1.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/builtins/route_repetitions_column.py pluggable_protocol_tree/tests/test_builtins.py
git commit -m "[route-reps] Add Route Reps column + RouteRepsHandler"
```

---

### Task 4: Strip the dialog from "Reps" (`repetitions`)

**Files:**
- Modify: `pluggable_protocol_tree/builtins/repetitions_column.py` (remove handler import/class, drop handler from factory)
- Test: `pluggable_protocol_tree/tests/test_builtins.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_builtins.py`:

```python
# --- Reps column no longer arbitrates duration mode (route-reps split) ---

def test_reps_handler_is_plain_write_through_even_in_duration_mode():
    """Reps now means 'repeat the whole thing' only; it must NOT prompt or
    touch repeat_duration_controls. A bare BaseColumnHandler write-through."""
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    col = make_repetitions_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = True
    assert col.handler.on_interact(row, col.model, 4) is True
    assert row.repetitions == 4
    assert row.repeat_duration_controls is True   # untouched by Reps edits


def test_reps_column_metadata_unchanged():
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    col = make_repetitions_column()
    assert col.model.col_id == "repetitions"
    assert col.model.col_name == "Reps"
    assert col.model.default_value == 1
```

- [ ] **Step 2: Run test to verify it fails** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_builtins.py -k reps_handler -v`
Expected: FAIL — current `RepetitionsHandler` prompts/flips the flag, so `repeat_duration_controls` becomes False (or `on_interact` returns False under the default no-op confirm).

- [ ] **Step 3: Rewrite the module without the handler**

Replace the entire contents of `pluggable_protocol_tree/builtins/repetitions_column.py` with:

```python
"""Repetitions column — number of times each row executes as a whole.

Steps re-run their on_step N times; groups expand their child subtree N
times. Default 1. Consumed only by row_manager._expand_frames.

NOTE: Reps no longer affects route looping — that is the separate
``route_repetitions`` ("Route Reps") column. A plain spinbox: editing
Reps never prompts and never touches repeat_duration_controls.

``iter_execution_frames`` in RowManager reads ``getattr(row,
"repetitions", 1)``; this column populates the trait. The getattr
fallback is kept for safety against persisted protocols predating the
column.
"""

from pyface.qt.QtCore import Qt
from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this row executes as a whole "
                            "(groups expand subtree Nx)")


class RepsSpinBoxColumnView(IntSpinBoxColumnView):
    """IntSpinBoxColumnView variant that stays editable on group rows.

    Repetitions IS meaningful on groups — it multiplies the child
    subtree — so groups must be editable here too.
    """

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable


def make_repetitions_column():
    return Column(
        model=RepetitionsColumnModel(
            col_id="repetitions", col_name="Reps", default_value=1,
        ),
        view=RepsSpinBoxColumnView(low=1, high=1000),
    )
```

- [ ] **Step 4: Run tests to verify they pass** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_builtins.py -k "reps_handler or reps_column_metadata" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/builtins/repetitions_column.py pluggable_protocol_tree/tests/test_builtins.py
git commit -m "[route-reps] Reps becomes plain whole-thing repeat (drop mode dialog)"
```

---

### Task 5: Rename + unhide `repeat_duration` → "Route Reps Dur", repoint estimate + flag

**Files:**
- Modify: `pluggable_protocol_tree/builtins/repeat_duration_column.py`
- Test: `pluggable_protocol_tree/tests/test_hidden_columns.py` (edit existing) + `test_builtins.py` (append)

- [ ] **Step 1: Update the existing visibility test + add behavior tests**

In `pluggable_protocol_tree/tests/test_hidden_columns.py`, replace `test_repeat_duration_column_metadata_and_hidden` (lines ~55-60) with:

```python
def test_repeat_duration_column_metadata_and_visible():
    col = make_repeat_duration_column()
    assert col.model.col_id == "repeat_duration"
    assert col.model.col_name == "Route Reps Dur"
    assert col.model.default_value == 0.0
    assert col.view.hidden_by_default is False
    assert col.view.low == 0.0 and col.view.high == 3600.0
```

Append to `pluggable_protocol_tree/tests/test_builtins.py`:

```python
# --- Route Reps Dur handler repoints to route_repetitions + flag trait ---

def test_repeat_duration_handler_uses_route_repetitions_for_estimate(monkeypatch):
    """When the typed value matches the auto-estimate computed from
    route_repetitions, the write goes through without a dialog and the
    flag stays False."""
    import pluggable_protocol_tree.builtins.repeat_duration_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column

    cols = [make_repeat_duration_column(), make_route_repetitions_column(),
            make_routes_column(), make_duration_column()]
    Row = build_row_type(cols, base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]   # one loop route
    row.route_repetitions = 2
    row.duration_s = 1.0
    row.repeat_duration_controls = False

    from pluggable_protocol_tree.services.phase_math import estimate_repeat_duration_s
    est = estimate_repeat_duration_s(
        routes=row.routes, trail_length=1, trail_overlay=0,
        n_repeats=2, step_duration_s=1.0, linear_repeats=False,
        soft_start=False, soft_end=False,
    )
    # Sentinel so we'd notice an unexpected dialog.
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("dialog should not appear when value matches estimate")))
    col = make_repeat_duration_column()
    assert col.handler.on_interact(row, col.model, round(est, 2)) is True
    assert row.repeat_duration_controls is False


def test_repeat_duration_handler_switch_to_duration_on_confirm(monkeypatch):
    import pluggable_protocol_tree.builtins.repeat_duration_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column

    cols = [make_repeat_duration_column(), make_route_repetitions_column(),
            make_routes_column()]
    Row = build_row_type(cols, base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]
    row.route_repetitions = 2
    row.repeat_duration_controls = False
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: mod.YES)
    col = make_repeat_duration_column()
    assert col.handler.on_interact(row, col.model, 99.0) is True
    assert row.repeat_duration_controls is True
    assert row.repeat_duration == 99.0
```

- [ ] **Step 2: Run tests to verify they fail** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_hidden_columns.py::test_repeat_duration_column_metadata_and_visible pluggable_protocol_tree/tests/test_builtins.py -k repeat_duration_handler -v`
Expected: FAIL — col_name is still "Repeat (s)", view is hidden, and the handler still reads `repetitions`.

- [ ] **Step 3: Edit the column module**

In `pluggable_protocol_tree/builtins/repeat_duration_column.py`:

(a) Swap the view import (line ~22-24) from the hidden mixin to the plain view:

```python
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)
```

(b) In `RepeatDurationHandler.on_interact`, change the `n_repeats` source from `repetitions` to `route_repetitions` (line ~58):

```python
            n_repeats=int(getattr(row, "route_repetitions", 1) or 1),
```

(c) Replace the factory (lines ~89-97) so the name is "Route Reps Dur" and the view is the visible double spinbox:

```python
def make_repeat_duration_column():
    return Column(
        model=RepeatDurationColumnModel(
            col_id="repeat_duration", col_name="Route Reps Dur",
            default_value=0.0,
        ),
        view=DoubleSpinBoxColumnView(low=0.0, high=3600.0,
                                     decimals=2, single_step=0.1),
        handler=RepeatDurationHandler(),
    )
```

(d) The handler already reads/sets `row.repeat_duration_controls` via `getattr`/`row.repeat_duration_controls = True` — those now hit the BaseRow trait. No further change. Update the module docstring's "Reps" references to "Route Reps" for accuracy.

- [ ] **Step 4: Run tests to verify they pass** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_hidden_columns.py pluggable_protocol_tree/tests/test_builtins.py -k "repeat_duration" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/builtins/repeat_duration_column.py pluggable_protocol_tree/tests/test_hidden_columns.py pluggable_protocol_tree/tests/test_builtins.py
git commit -m "[route-reps] Route Reps Dur: visible column, estimate from route_repetitions"
```

---

### Task 6: phase_math — drop return phase in duration mode + `pad_seconds_for_duration`

**Files:**
- Modify: `pluggable_protocol_tree/services/phase_math.py` (`_route_with_repeats` `:79-126`; add helper near `effective_repetitions_for_duration` `:204-231`)
- Test: `pluggable_protocol_tree/tests/test_phase_math.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `pluggable_protocol_tree/tests/test_phase_math.py`:

```python
# --- duration-mode return-phase drop + pad_seconds_for_duration ---

from pluggable_protocol_tree.services.phase_math import (
    _route_with_repeats, pad_seconds_for_duration,
)


def test_duration_mode_omits_trailing_return_phase():
    """Loop route, 4-window cycle, T fits exactly 2 cycles at dwell=1.0.
    Count mode yields N*C + 1 (return) phases; duration mode yields N*C
    (no return) so emitted dwell == cycles*cycle_time exactly."""
    route = ["a", "b", "c", "d", "a"]   # loop, effective len 4, trail 1 => 4 windows
    count_mode = list(_route_with_repeats(
        route, trail_length=1, trail_overlay=0,
        n_repeats=2, repeat_duration_s=0.0, step_duration_s=1.0))
    dur_mode = list(_route_with_repeats(
        route, trail_length=1, trail_overlay=0,
        n_repeats=2, repeat_duration_s=8.0, step_duration_s=1.0))
    assert len(count_mode) == 2 * 4 + 1     # cycles + return phase
    assert len(dur_mode) == 2 * 4           # no return phase


def test_pad_seconds_exact_leftover():
    """T=10s, cycle=4 windows @1.0s => cycle_time=4. floor(10/4)=2 cycles
    => 8s used, pad = 2.0s held on the last phase."""
    routes = [["a", "b", "c", "d", "a"]]
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=1.0)
    assert pad == 2.0


def test_pad_seconds_zero_when_t_below_one_cycle():
    """T < cycle_time => max(1, floor)=1 cycle (overshoot), pad clamps to 0."""
    routes = [["a", "b", "c", "d", "a"]]
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=2.0, step_duration_s=1.0)
    assert pad == 0.0


def test_pad_seconds_zero_without_loop_routes():
    routes = [["a", "b", "c"]]   # open route, no loop
    pad = pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=1.0)
    assert pad == 0.0


def test_pad_seconds_zero_when_step_duration_nonpositive():
    routes = [["a", "b", "c", "d", "a"]]
    assert pad_seconds_for_duration(
        routes, trail_length=1, trail_overlay=0,
        repeat_duration_s=10.0, step_duration_s=0.0) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_phase_math.py -k "duration_mode_omits or pad_seconds" -v`
Expected: FAIL — `pad_seconds_for_duration` undefined; duration mode currently appends the return phase.

- [ ] **Step 3: Drop the return phase in duration mode**

In `pluggable_protocol_tree/services/phase_math.py`, in `_route_with_repeats`, change the loop-route branch (lines ~112-122) so the return phase is only appended in count mode:

```python
    is_loop = _is_loop_route(route)
    if is_loop:
        if repeat_duration_s > 0 and step_duration_s > 0:
            cycle_phases = len(cycle)
            cycles = max(1, int(repeat_duration_s
                                / (cycle_phases * step_duration_s)))
            for _ in range(cycles):
                yield from cycle
            # Duration mode: NO trailing return phase. Total emitted dwell
            # equals cycles*cycle_time exactly; the RoutesHandler holds the
            # last phase for the leftover (pad_seconds_for_duration).
        else:
            cycles = max(1, int(n_repeats))
            for _ in range(cycles):
                yield from cycle
            yield cycle[0]
    else:
        passes = max(1, int(n_repeats)) if linear_repeats else 1
        for _ in range(passes):
            yield from cycle
```

- [ ] **Step 4: Add the pad helper**

Add after `effective_repetitions_for_duration` (after line ~231):

```python
def pad_seconds_for_duration(
    routes: List[List[str]],
    trail_length: int = 1,
    trail_overlay: int = 0,
    *,
    repeat_duration_s: float = 0.0,
    step_duration_s: float = 1.0,
) -> float:
    """Leftover hold time for Route Reps Dur mode: the seconds remaining
    after the maximum number of FULL loop cycles fit inside
    ``repeat_duration_s``. The RoutesHandler holds the last phase's
    electrodes for this long so total step time lands on
    ``repeat_duration_s`` exactly.

    cycle_time = cycle_length * step_duration_s (dominant loop route).
    cycles = max(1, floor(repeat_duration_s / cycle_time)).
    pad = max(0.0, repeat_duration_s - cycles * cycle_time).

    Returns 0.0 when there are no loop routes, or either budget is
    non-positive (matches the max(1,...) overshoot case where T is below
    one cycle).
    """
    loop_lengths = []
    for r in routes or []:
        if not _is_loop_route(r):
            continue
        cycle = list(_route_windows(r, trail_length, trail_overlay))
        if cycle:
            loop_lengths.append(len(cycle))
    if not loop_lengths or step_duration_s <= 0 or repeat_duration_s <= 0:
        return 0.0
    cycle_time = max(loop_lengths) * float(step_duration_s)
    cycles = max(1, int(repeat_duration_s / cycle_time))
    return max(0.0, float(repeat_duration_s) - cycles * cycle_time)
```

- [ ] **Step 5: Run tests to verify they pass** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_phase_math.py -v`
Expected: PASS (new tests + existing phase_math tests; note any existing count-mode loop test still expects the `+1` return phase — it should, since count mode is unchanged).

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/phase_math.py pluggable_protocol_tree/tests/test_phase_math.py
git commit -m "[route-reps] Duration mode drops return phase; add pad_seconds_for_duration"
```

---

### Task 7: RoutesHandler — feed route_repetitions + hold-pad

**Files:**
- Modify: `pluggable_protocol_tree/builtins/routes_column.py` (import `:49`; `on_step` `:101-193`)
- Test: `pluggable_protocol_tree/tests/test_phase_math.py` is pure; the handler dwell is exercised in `tests/tests_with_redis_server_need/test_routes_handler_redis.py`. Add a focused unit assert on the n_repeats wiring via a fake ctx in `tests/test_electrodes_routes_columns.py`.

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_electrodes_routes_columns.py` (a non-redis unit that drives `on_step` with a fake ctx and asserts the pad sleep + n_repeats source). First inspect the file's existing fake-ctx helpers and reuse them; if none exist, use this self-contained version:

```python
# --- RoutesHandler uses route_repetitions + holds last phase for pad ---

def test_routes_handler_uses_route_repetitions_for_loop_count(monkeypatch):
    """The phase count must reflect route_repetitions (not repetitions)."""
    import pluggable_protocol_tree.builtins.routes_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.routes_column import make_routes_column
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    from pluggable_protocol_tree.builtins.duration_column import make_duration_column

    captured = {}
    real_iter = mod.iter_phases
    def spy(*args, **kwargs):
        captured["n_repeats"] = kwargs.get("n_repeats")
        return real_iter(*args, **kwargs)
    monkeypatch.setattr(mod, "iter_phases", spy)
    # No hardware: stub publish + make preview True so no ack wait.
    monkeypatch.setattr(mod, "publish_message", lambda *a, **k: None)

    cols = [make_routes_column(), make_route_repetitions_column(),
            make_duration_column()]
    Row = build_row_type(cols, base=BaseRow)
    row = Row()
    row.routes = [["a", "b", "c", "a"]]
    row.route_repetitions = 3
    row.repetitions = 7          # must be IGNORED by phase generation
    row.duration_s = 0.0         # zero dwell so the test is instant

    ctx = _make_fake_ctx(preview_mode=True)   # see helper below
    col = make_routes_column()
    col.handler.on_step(row, ctx)
    assert captured["n_repeats"] == 3
```

If `_make_fake_ctx` does not already exist in the file, add this minimal helper near the top of the test module (mirror the real `ctx`/`ctx.protocol` shape used by `RoutesHandler.on_step`: `ctx.protocol.scratch`, `ctx.protocol.stop_event`, `ctx.protocol.pause_event`, `ctx.protocol.preview_mode`, `ctx.protocol.qsignals`, `ctx.scratch`, `ctx.wait_for`):

```python
class _Event:
    def __init__(self): self._set = False
    def is_set(self): return self._set
    def wait_cleared(self): pass

class _Protocol:
    def __init__(self, preview_mode):
        self.scratch = {"electrode_to_channel": {"a": 0, "b": 1, "c": 2}}
        self.stop_event = _Event()
        self.pause_event = _Event()
        self.preview_mode = preview_mode
        self.qsignals = None

class _Ctx:
    def __init__(self, preview_mode):
        self.protocol = _Protocol(preview_mode)
        self.scratch = {}
    def wait_for(self, *a, **k): pass

def _make_fake_ctx(preview_mode=True):
    return _Ctx(preview_mode)
```

- [ ] **Step 2: Run test to verify it fails** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -k route_repetitions_for_loop_count -v`
Expected: FAIL — handler still passes `n_repeats=repetitions` (would capture 7).

- [ ] **Step 3: Wire route_repetitions + add the hold-pad**

In `pluggable_protocol_tree/builtins/routes_column.py`:

(a) Add `pad_seconds_for_duration` to the phase_math import (line ~49):

```python
from pluggable_protocol_tree.services.phase_math import (
    iter_phases, pad_seconds_for_duration,
)
```

(b) In `on_step`, change the `iter_phases(...)` call's `n_repeats` (line ~129) from `repetitions` to `route_repetitions`:

```python
            n_repeats=int(getattr(row, "route_repetitions", 1)),
```

(c) After the phase loop, before `ctx.scratch[DURATION_CONSUMED_KEY] = True` (line ~192-193), add the hold-pad:

```python
        # Route Reps Dur mode: after the full cycles, hold the last
        # phase's electrodes (no new publish) for the exact leftover so
        # total step time lands on the budget precisely.
        if (bool(getattr(row, "repeat_duration_controls", False))
                and float(getattr(row, "repeat_duration", 0.0) or 0.0) > 0
                and not stop_event.is_set()):
            pad = pad_seconds_for_duration(
                list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                repeat_duration_s=float(getattr(row, "repeat_duration", 0.0)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            )
            if pad > 0:
                _cooperative_sleep(pad, stop_event, pause_event)
        # Tell DurationColumnHandler we already covered the dwell.
        ctx.scratch[DURATION_CONSUMED_KEY] = True
```

- [ ] **Step 4: Run test to verify it passes** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_electrodes_routes_columns.py -k route_repetitions_for_loop_count -v`
Expected: PASS (`captured["n_repeats"] == 3`).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/builtins/routes_column.py pluggable_protocol_tree/tests/test_electrodes_routes_columns.py
git commit -m "[route-reps] RoutesHandler feeds route_repetitions + holds last phase for pad"
```

---

### Task 8: Delete controls column; wire route_repetitions into plugin + demos

**Files:**
- Delete: `pluggable_protocol_tree/builtins/repeat_duration_controls_column.py`
- Modify: `pluggable_protocol_tree/plugin.py:22-25, 102-118`
- Modify: `pluggable_protocol_tree/demos/run_widget.py`, `run_session_demo.py`, `run_headless.py`, `run_widget_auto.py`
- Test: `pluggable_protocol_tree/tests/test_plugin.py` (edit column-set expectations)

- [ ] **Step 1: Add the plugin column-set test**

The existing `test_plugin.py` order tests filter to fixed id-sets that don't include the new column, and none reference `repeat_duration_controls`, so they stay green as-is — no edits needed there. Just **add** this test (the plugin class is `PluggableProtocolTreePlugin`, instantiated as `PluggableProtocolTreePlugin()` like the existing tests):

```python
def test_assembled_columns_have_route_reps_and_no_controls_column():
    p = PluggableProtocolTreePlugin()
    ids = [c.model.col_id for c in p._assemble_columns()]
    assert "route_repetitions" in ids
    assert "repeat_duration_controls" not in ids
    # Reps still present and distinct from Route Reps.
    assert "repetitions" in ids
    # Route Reps lands right after Reps.
    assert ids.index("route_repetitions") == ids.index("repetitions") + 1
```

> `PluggableProtocolTreePlugin` is already imported at the top of `test_plugin.py` — reuse that import.

- [ ] **Step 2: Run test to verify it fails** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_plugin.py -k "route_reps or assembled_columns or column" -v`
Expected: FAIL — `route_repetitions` missing, `repeat_duration_controls` still present.

- [ ] **Step 3: Edit `plugin.py`**

Remove the controls-column import (lines ~22-24):

```python
# DELETE these lines:
from pluggable_protocol_tree.builtins.repeat_duration_controls_column import (
    make_repeat_duration_controls_column,
)
```

Add the route_repetitions import next to the repetitions import (line ~25):

```python
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.route_repetitions_column import (
    make_route_repetitions_column,
)
```

Edit `_assemble_columns` builtins list (lines ~103-118): add `make_route_repetitions_column()` right after `make_repetitions_column()`, and delete the `make_repeat_duration_controls_column()` entry:

```python
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_repetitions_column(),
            make_route_repetitions_column(),
            make_duration_column(),
            make_electrodes_column(),
            make_routes_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
            make_soft_start_column(),
            make_soft_end_column(),
            make_repeat_duration_column(),
            make_linear_repeats_column(),
        ]
```

- [ ] **Step 4: Delete the controls column file**

```bash
git rm pluggable_protocol_tree/builtins/repeat_duration_controls_column.py
```

- [ ] **Step 5: Update demos**

For each of `run_widget.py`, `run_session_demo.py`, `run_widget_auto.py`, `run_headless.py`: add `make_route_repetitions_column` to the imports from the builtins and insert `make_route_repetitions_column()` into the column list right after `make_repetitions_column()`. Concretely:

- `run_widget.py:22` — after `from ...repetitions_column import make_repetitions_column`, add:
  ```python
  from pluggable_protocol_tree.builtins.route_repetitions_column import (
      make_route_repetitions_column,
  )
  ```
  and at line ~73 change `make_repetitions_column(), make_duration_column(),` to `make_repetitions_column(), make_route_repetitions_column(), make_duration_column(),`.

- `run_session_demo.py:55` — add `make_route_repetitions_column,` to the builtins import block; at line ~100 change `make_repetitions_column(), make_duration_column(),` → `make_repetitions_column(), make_route_repetitions_column(), make_duration_column(),`.

- `run_widget_auto.py:42` — add `make_route_repetitions_column,` to the import block; at line ~150 insert `make_route_repetitions_column(),` after `make_repetitions_column(),`.

- `run_headless.py:63` — after `from ...repetitions_column import make_repetitions_column` add the `make_route_repetitions_column` import; at line ~182 insert `make_route_repetitions_column(),` after `make_repetitions_column(),`.

> These demos already omit the controls column, so no deletion is needed there.

- [ ] **Step 6: Run the plugin test + the broader suite to verify it passes** *(manual checkpoint)*

Run: `pytest pluggable_protocol_tree/tests/test_plugin.py -v`
Then a non-redis sweep: `pytest pluggable_protocol_tree/tests/ -v` (skip the `tests_with_redis_server_need/` and `tests_with_dropbot_connection_need/` subdirs unless Redis/hardware are available).
Expected: PASS. Watch specifically for `test_compound_persistence.py`, `test_session.py`, `test_dock_pane.py`, `test_protocol_tree_pane*.py` referencing the old column set — update any hard-coded column-id/index expectations to include `route_repetitions` and drop `repeat_duration_controls`.

- [ ] **Step 7: Commit**

```bash
git add pluggable_protocol_tree/plugin.py pluggable_protocol_tree/demos/ pluggable_protocol_tree/tests/test_plugin.py
git commit -m "[route-reps] Wire Route Reps column into plugin + demos; remove controls column"
```

---

### Task 9: Redis-tier integration verification (optional, requires Redis)

**Files:**
- Modify: `pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py` if it hard-codes `repetitions` for loop counts.

- [ ] **Step 1: Inspect the redis routes-handler test**

Read `test_routes_handler_redis.py`. Any test that set `repetitions` expecting route looping must instead set `route_repetitions`. Any duration-mode test must set `repeat_duration_controls = True` on the row (now a trait) and assert the hold-pad timing (total ≈ `repeat_duration`).

- [ ] **Step 2: Update assertions to the new contract**

Change route-loop expectations to source from `route_repetitions`; for duration mode, assert the run holds the last phase so total wall time ≈ `repeat_duration` (within a tolerance for ack latency).

- [ ] **Step 3: Run with Redis** *(manual checkpoint — requires `redis-server`)*

Run: `pytest pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/tests/tests_with_redis_server_need/test_routes_handler_redis.py
git commit -m "[route-reps] Update redis routes-handler tests to route_repetitions + hold-pad"
```

---

## Self-Review notes (already reconciled)

- **Spec coverage:** §1 decoupling → Tasks 4,6,7; §2 columns → Tasks 3,5,8; §3 arbitration → Tasks 3,5; §4 padding → Tasks 6,7; §5 flag-as-trait → Tasks 1,2,8; migration (none) → default in Task 3.
- **Type consistency:** new symbols `route_repetitions` (col_id + trait), `make_route_repetitions_column`, `RouteRepsHandler`, `pad_seconds_for_duration`, `row_flags` are used identically across tasks.
- **Behavior change (documented in spec):** old protocols load with `route_repetitions=1`; routes that previously looped via `repetitions` will need Route Reps set. Clipboard copy/paste does not carry the flag (count mode on paste).
```
