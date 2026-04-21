# PPT-1 Core Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the headless-and-UI skeleton of the `pluggable_protocol_tree` plugin: interfaces, row model, column abstraction, four built-in columns (type/id/name/duration), RowManager with structure/selection/clipboard/slicing, persistence (save/load), Qt tree widget + dock pane, Envisage plugin with `PROTOCOL_COLUMNS` extension point, and a headless demo. No executor, no hardware — purely data + UI.

**Architecture:** Per-protocol dynamic `HasTraits` row subclass composed from the active column set. Every column is an `IColumn` (model + view + handler); the core plugin ships four built-ins and exposes a `PROTOCOL_COLUMNS` extension point for contributions. `RowManager` is the single public API over the tree (HasTraits, selection via path tuples, pandas-backed slicing). Persistence is compact depth-encoded JSON with plugin class paths for orphan-tolerant loading.

**Tech Stack:** Python 3.11+, PySide6 (6.9.2), Traits (7.x), Envisage (7.x), Pyface (8.x), pandas, pytest. Reference: `src/docs/superpowers/specs/2026-04-21-pluggable-protocol-tree-design.md`.

**Working directory:** `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src`

**Running commands:** All tests run via `pixi run` from the outer `microdrop-py/` directory:
```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ -v"
```

---

## Task 0: Issue tracking setup

**Files:** None (GitHub + git only)

- [ ] **Step 1: Create umbrella issue on GitHub**

Via `gh`:
```bash
gh issue create \
  --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "[Pluggable Protocol Tree] Replace monolithic protocol_grid with pluggable column architecture" \
  --body "$(cat <<'EOF'
Umbrella issue tracking the replacement of `protocol_grid` with a column-contribution architecture. Columns (model + view + handler) are contributed by any plugin through the `PROTOCOL_COLUMNS` extension point; the core owns the row manager, executor, and persistence.

Design doc: `src/docs/superpowers/specs/2026-04-21-pluggable-protocol-tree-design.md`

## Sub-issues

- [ ] PPT-1: Core skeleton — interfaces, BaseRow/GroupRow, RowManager, 4 built-in columns, Qt widget, envisage plugin
- [ ] PPT-2: Executor + StepContext.wait_for + pause/stop
- [ ] PPT-3: Electrodes + Routes columns + device-viewer binding + phase math lift
- [ ] PPT-4: Voltage + Frequency columns (dropbot_controller contribution)
- [ ] PPT-5: Migrate magnet column (peripheral_controller contribution)
- [ ] PPT-6: Migrate video / capture / record columns
- [ ] PPT-7: Migrate force calculation
- [ ] PPT-8: Migrate droplet detection
- [ ] PPT-9: Delete legacy protocol_grid plugin

Closes-when: all sub-issues closed.
EOF
)"
```

Note the umbrella issue number returned (e.g. `#401`). Used in step 2.

- [ ] **Step 2: Create PPT-1 sub-issue**

```bash
gh issue create \
  --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "[PPT-1] Core skeleton: interfaces, BaseRow/GroupRow, RowManager" \
  --body "$(cat <<'EOF'
Part of #<UMBRELLA_NUMBER>

Build the headless-and-UI skeleton of the new pluggable protocol tree plugin: interfaces, row model, column abstraction, four built-in columns, RowManager (structure / selection / clipboard / slicing), persistence, Qt tree widget + dock pane, envisage plugin with `PROTOCOL_COLUMNS` extension point, and a headless demo. No executor, no hardware.

## Files created

- `src/pluggable_protocol_tree/` package (interfaces/, models/, views/, builtins/, services/, tests/, demos/)
- Plan: `src/docs/superpowers/plans/2026-04-21-ppt-1-core-skeleton.md`

## Acceptance criteria

- `pytest pluggable_protocol_tree/tests/ -v` green on `src/`.
- `pixi run python -m pluggable_protocol_tree.demos.run_widget` opens a window; user can add/remove/move steps and groups, edit Name/Duration, copy/cut/paste, save/load JSON.
- Extension point `pluggable_protocol_tree.protocol_columns` is defined and receives zero contributions in the demo (verified via log line).
- No modifications to `protocol_grid/` or any other existing plugin (parallel install).

## Not in scope

Executor, hardware columns, device-viewer binding, electrode/routes columns, trail config columns — see PPT-2..9.
EOF
)" \
  --assignee @me
```

Note the PPT-1 issue number (e.g. `#402`).

- [ ] **Step 3: Create feature branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git checkout -b feat/ppt-1-core-skeleton
```

- [ ] **Step 4: Verify branch and clean state**

```bash
git status
git branch --show-current
```

Expected: branch is `feat/ppt-1-core-skeleton`, working tree clean (only the pre-existing `protocol_grid/preferences.py` modification that was there before — leave it alone).

---

## Task 1: Add pandas dependency and register new package

**Files:**
- Modify: `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/pyproject.toml` (top-level, NOT the src submodule)

- [ ] **Step 1: Add pandas via pixi add**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi add "pandas>=2.0,<3"
```

Expected: `pixi.lock` updates, `pyproject.toml` gets a `pandas = ">=2.0,<3"` line under `[tool.pixi.dependencies]`. DO NOT edit `pixi.lock` by hand.

- [ ] **Step 2: Register new package in hatch build targets**

Edit `C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/pyproject.toml`, find `[tool.hatch.build.targets.wheel]`:

```toml
[tool.hatch.build.targets.wheel]
packages = [
    "src/device_viewer",
    "src/dropbot_controller",
    "src/dropbot_status",
    "src/dropbot_tools_menu",
    "src/electrode_controller",
    "src/manual_controls",
    "src/message_router",
    "src/microdrop_utils",
    "src/microdrop_application",
    "src/pluggable_protocol_tree",
    "src/examples"
]
```

Only line changed is the insertion of `"src/pluggable_protocol_tree",`.

- [ ] **Step 3: Reinstall editable install**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi install
```

Expected: `Successfully installed` or similar; no error.

- [ ] **Step 4: Verify pandas is importable inside pixi env**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python -c "import pandas; print(pandas.__version__)"
```

Expected: a version string `>= 2.0`.

- [ ] **Step 5: Commit**

This is a top-level-repo change (outside the submodule). Commit lives in the outer `pixi-microdrop` repo:

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop" && git add microdrop-py/pyproject.toml microdrop-py/pixi.lock && git commit -m "$(cat <<'EOF'
[PPT-1] Add pandas dep and register pluggable_protocol_tree package

Preparation for the pluggable protocol tree skeleton. Pandas is the
slicing facade used by RowManager; the package listing registers the
new module for editable install.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Package scaffolding and constants

**Files:**
- Create: `src/pluggable_protocol_tree/__init__.py`
- Create: `src/pluggable_protocol_tree/consts.py`
- Create: `src/pluggable_protocol_tree/interfaces/__init__.py`
- Create: `src/pluggable_protocol_tree/models/__init__.py`
- Create: `src/pluggable_protocol_tree/views/__init__.py`
- Create: `src/pluggable_protocol_tree/views/columns/__init__.py`
- Create: `src/pluggable_protocol_tree/builtins/__init__.py`
- Create: `src/pluggable_protocol_tree/services/__init__.py`
- Create: `src/pluggable_protocol_tree/tests/__init__.py`
- Create: `src/pluggable_protocol_tree/demos/__init__.py`

- [ ] **Step 1: Create package skeleton**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  mkdir -p pluggable_protocol_tree/{interfaces,models,views/columns,builtins,services,tests,demos}
```

- [ ] **Step 2: Create empty `__init__.py` files**

Create each of these as empty files (no content):

- `pluggable_protocol_tree/__init__.py`
- `pluggable_protocol_tree/interfaces/__init__.py`
- `pluggable_protocol_tree/models/__init__.py`
- `pluggable_protocol_tree/views/__init__.py`
- `pluggable_protocol_tree/views/columns/__init__.py`
- `pluggable_protocol_tree/builtins/__init__.py`
- `pluggable_protocol_tree/services/__init__.py`
- `pluggable_protocol_tree/tests/__init__.py`
- `pluggable_protocol_tree/demos/__init__.py`

- [ ] **Step 3: Write `consts.py`**

Create `src/pluggable_protocol_tree/consts.py`:

```python
"""Package-level constants for the pluggable protocol tree.

Follows the MicroDrop convention: PKG derived from __name__, topic constants
defined here, ACTOR_TOPIC_DICT aggregating the listener→topic map."""

import os

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

# Envisage extension point id (registered in plugin.py)
PROTOCOL_COLUMNS = f"{PKG}.protocol_columns"

# Clipboard MIME type for copy/cut/paste of protocol rows
PROTOCOL_ROWS_MIME = "application/x-microdrop-rows+json"

# Persistence schema version
PERSISTENCE_SCHEMA_VERSION = 1

# Topic constants (no executor topics yet — added in PPT-2)
# Reserved namespace for future use:
PROTOCOL_TOPIC_PREFIX = "microdrop/pluggable_protocol_tree"

# No ACTOR_TOPIC_DICT entries yet — no listener in PPT-1.
ACTOR_TOPIC_DICT: dict[str, list[str]] = {}
```

- [ ] **Step 4: Smoke-test the package is importable**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree import consts; print(consts.PKG, consts.PROTOCOL_COLUMNS)'"
```

Expected: `pluggable_protocol_tree pluggable_protocol_tree.protocol_columns`

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && \
  git add pluggable_protocol_tree/ && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Package scaffolding + consts

Bare package structure with subpackages (interfaces, models, views,
builtins, services, tests, demos) and consts.py defining PKG, the
PROTOCOL_COLUMNS extension-point id, the clipboard MIME, and the
persistence schema version.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Row interfaces

**Files:**
- Create: `src/pluggable_protocol_tree/interfaces/i_row.py`

- [ ] **Step 1: Write the interface file**

Create `src/pluggable_protocol_tree/interfaces/i_row.py`:

```python
"""Traits interfaces for protocol rows (steps and groups).

BaseRow instances are the leaves of the protocol tree. GroupRow instances
own ordered children. Dynamic subclasses composed from the active column
set hold the per-column trait values — see models/row.py::build_row_type.
"""

from traits.api import Interface, Str, List, Instance, Tuple


class IRow(Interface):
    """A single row in the protocol tree.

    Invariants:
    - `uuid` is stable for the lifetime of the row and survives save/load.
      A fresh uuid is generated on copy/paste.
    - `parent` is None only for rows owned directly by the RowManager.root.
    - `path` is a tuple of 0-indexed positions from the root; derived, not
      stored. Display elsewhere is 1-indexed.
    """
    uuid = Str
    name = Str
    parent = Instance("IRow")
    row_type = Str  # "step" or "group"
    path = Tuple


class IGroupRow(IRow):
    """A row that owns ordered children (other rows or nested groups)."""
    children = List(Instance(IRow))

    def add_row(self, row):
        """Append a row to children; set its parent to self."""

    def insert_row(self, idx, row):
        """Insert a row at idx in children; set its parent to self."""

    def remove_row(self, row):
        """Remove a row from children; clear its parent."""
```

- [ ] **Step 2: Write a sanity test (no behaviour yet, just importable)**

Create `src/pluggable_protocol_tree/tests/test_interfaces.py`:

```python
"""Interface-module smoke tests.

These are lightweight: interfaces don't have behaviour, so we check only
that the interface classes can be imported and subclass the Traits
`Interface` base correctly.
"""

from traits.api import Interface

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


def test_i_row_is_interface():
    assert issubclass(IRow, Interface)


def test_i_group_row_extends_i_row():
    assert issubclass(IGroupRow, IRow)
```

- [ ] **Step 3: Run the test and verify it passes**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_interfaces.py -v"
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/interfaces/i_row.py pluggable_protocol_tree/tests/test_interfaces.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Row interfaces (IRow, IGroupRow)

Traits interfaces for rows in the protocol tree. IRow carries uuid, name,
parent reference, row_type discriminator, and a derived path tuple.
IGroupRow adds ordered children plus add/insert/remove methods.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: BaseRow and GroupRow models

**Files:**
- Create: `src/pluggable_protocol_tree/models/row.py`
- Create: `src/pluggable_protocol_tree/tests/test_row.py`

- [ ] **Step 1: Write failing tests for BaseRow + GroupRow**

Create `src/pluggable_protocol_tree/tests/test_row.py`:

```python
"""Tests for BaseRow and GroupRow structure."""

from pluggable_protocol_tree.models.row import BaseRow, GroupRow


def test_base_row_auto_generates_uuid():
    r = BaseRow()
    assert r.uuid
    assert len(r.uuid) == 32   # hex uuid4


def test_base_row_two_instances_have_different_uuids():
    assert BaseRow().uuid != BaseRow().uuid


def test_base_row_default_type_is_step():
    assert BaseRow().row_type == "step"


def test_group_row_default_type_is_group():
    assert GroupRow().row_type == "group"


def test_group_add_row_sets_parent_and_appends():
    g = GroupRow(name="Group")
    r = BaseRow(name="Step")
    g.add_row(r)
    assert r.parent is g
    assert g.children == [r]


def test_group_insert_row_at_position():
    g = GroupRow(name="Group")
    a, b, c = BaseRow(name="A"), BaseRow(name="B"), BaseRow(name="C")
    g.add_row(a)
    g.add_row(c)
    g.insert_row(1, b)
    assert [r.name for r in g.children] == ["A", "B", "C"]


def test_group_remove_row_clears_parent():
    g = GroupRow(name="Group")
    r = BaseRow(name="Step")
    g.add_row(r)
    g.remove_row(r)
    assert r.parent is None
    assert g.children == []


def test_path_top_level_row_has_empty_path():
    """A row with no parent has an empty path tuple.

    Only rows *under* a parent have positional paths; the root group
    itself is invisible and doesn't count as a parent in path derivation.
    """
    r = BaseRow()
    assert r.path == ()


def test_path_nested_row_has_0_indexed_tuple():
    root = GroupRow(name="Root")
    a = BaseRow(name="A")
    b = BaseRow(name="B")
    root.add_row(a)
    root.add_row(b)
    # a is at position 0 under root, b at position 1
    assert a.path == (0,)
    assert b.path == (1,)


def test_path_doubly_nested():
    root = GroupRow(name="Root")
    g = GroupRow(name="Group")
    s = BaseRow(name="Step")
    root.add_row(g)
    g.add_row(s)
    assert g.path == (0,)
    assert s.path == (0, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row.py -v"
```

Expected: ImportError (`models.row` doesn't exist yet).

- [ ] **Step 3: Implement BaseRow and GroupRow**

Create `src/pluggable_protocol_tree/models/row.py`:

```python
"""Row models for the protocol tree.

BaseRow is the leaf type (steps). GroupRow nests other rows as children.
Path is derived from parent chain + sibling position; it's not stored, so
mutations to the tree automatically invalidate and recompute it via the
Property observe dependency list.

Dynamic per-protocol subclasses (see `build_row_type`) inherit from these
and add one trait per column in the active column set.
"""

import uuid as _uuid

from traits.api import HasTraits, Str, List, Instance, Tuple, Property, provides

from pluggable_protocol_tree.interfaces.i_row import IRow, IGroupRow


@provides(IRow)
class BaseRow(HasTraits):
    uuid = Str(desc="Stable identity for merges/diffs and device-viewer routing")
    name = Str("Step", desc="User-visible row name")
    parent = Instance("BaseRow", desc="Owning GroupRow (None for rows at the top")
    row_type = Str("step", desc="'step' or 'group' — drives per-column visibility")
    path = Property(Tuple, observe="parent, parent.children.items",
                    desc="0-indexed tuple of positions from the root (empty for orphans)")

    def _uuid_default(self):
        return _uuid.uuid4().hex

    def _get_path(self):
        indices: list[int] = []
        current = self
        while current.parent is not None:
            try:
                idx = current.parent.children.index(current)
            except ValueError:
                return ()   # row was detached mid-read; report empty
            indices.insert(0, idx)
            current = current.parent
        return tuple(indices)


@provides(IGroupRow)
class GroupRow(BaseRow):
    row_type = Str("group")
    children = List(Instance(BaseRow))

    def add_row(self, row):
        row.parent = self
        self.children.append(row)

    def insert_row(self, idx, row):
        row.parent = self
        self.children.insert(idx, row)

    def remove_row(self, row):
        if row in self.children:
            self.children.remove(row)
            row.parent = None
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row.py -v"
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row.py pluggable_protocol_tree/tests/test_row.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] BaseRow + GroupRow models

Traits-backed row classes. BaseRow auto-generates a uuid, tracks parent
and row_type, and computes path as a Property observing parent+sibling
order. GroupRow adds a children list with add/insert/remove helpers
that maintain the parent backlink invariant.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Dynamic row subclass builder

**Files:**
- Modify: `src/pluggable_protocol_tree/models/row.py` (add `build_row_type`)
- Modify: `src/pluggable_protocol_tree/tests/test_row.py` (append tests)

- [ ] **Step 1: Write failing tests for `build_row_type`**

Append to `src/pluggable_protocol_tree/tests/test_row.py`:

```python
# --- build_row_type tests ---

from unittest.mock import MagicMock
from traits.api import Float, Int

from pluggable_protocol_tree.models.row import build_row_type, BaseRow, GroupRow


def _mock_column(col_id, trait):
    """Minimal column stand-in for build_row_type tests.

    Only the model.col_id and model.trait_for_row() surface are exercised
    here; real IColumn is introduced in Task 6.
    """
    c = MagicMock()
    c.model.col_id = col_id
    c.model.trait_for_row.return_value = trait
    return c


def test_build_row_type_adds_declared_traits():
    cols = [_mock_column("voltage", Float(100.0)),
            _mock_column("reps", Int(1))]
    RowType = build_row_type(cols, base=BaseRow)
    r = RowType()
    # Declared traits are present with their defaults
    assert r.voltage == 100.0
    assert r.reps == 1


def test_build_row_type_preserves_base_traits():
    cols = [_mock_column("voltage", Float(50.0))]
    RowType = build_row_type(cols, base=BaseRow)
    r = RowType(name="Custom")
    assert r.name == "Custom"
    assert r.row_type == "step"
    assert r.uuid  # still auto-generated


def test_build_row_type_for_group_base():
    cols = [_mock_column("voltage", Float(0.0))]
    GroupType = build_row_type(cols, base=GroupRow, name="ProtocolGroupRow")
    g = GroupType(name="G")
    assert g.row_type == "group"
    assert g.voltage == 0.0
    # children list still works
    child = GroupType(name="Child")
    g.add_row(child)
    assert g.children == [child]


def test_build_row_type_distinct_classes_do_not_share_traits():
    """Fresh type() calls must not leak traits across invocations."""
    TypeA = build_row_type([_mock_column("a", Float(1.0))], base=BaseRow, name="A")
    TypeB = build_row_type([_mock_column("b", Float(2.0))], base=BaseRow, name="B")
    a = TypeA()
    b = TypeB()
    assert hasattr(a, "a") and not hasattr(a, "b")
    assert hasattr(b, "b") and not hasattr(b, "a")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row.py -v"
```

Expected: 4 new tests fail with `ImportError: cannot import name 'build_row_type'`.

- [ ] **Step 3: Implement `build_row_type`**

Append to `src/pluggable_protocol_tree/models/row.py`:

```python
def build_row_type(columns, base=BaseRow, name="ProtocolStepRow") -> type:
    """Build a fresh HasTraits subclass of `base` with one trait per column.

    Called once per protocol open (twice actually: for step and group
    subclasses). The subclass is per-protocol-session; closing a protocol
    lets Python garbage-collect it. This avoids mutating shared classes,
    preserves full Traits semantics (observers, validation, defaults),
    and keeps the row schema explicit.

    Args:
        columns: List of IColumn instances contributing traits.
        base: BaseRow (for steps) or GroupRow (for groups).
        name: Name for the new class (shown in tracebacks only).

    Returns:
        A new class derived from `base` with each column's trait added.
    """
    class_dict = {
        col.model.col_id: col.model.trait_for_row()
        for col in columns
    }
    return type(name, (base,), class_dict)
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row.py -v"
```

Expected: 14 passed (10 from Task 4 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row.py pluggable_protocol_tree/tests/test_row.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] build_row_type() dynamic row-subclass builder

Per-protocol factory that composes a fresh HasTraits subclass from the
active column set. Each column contributes one trait via
model.trait_for_row(); the subclass inherits uuid/name/parent/path from
BaseRow (or GroupRow) unchanged. Invoked twice per protocol-open:
StepRowType and GroupRowType.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Column interfaces

**Files:**
- Create: `src/pluggable_protocol_tree/interfaces/i_column.py`
- Modify: `src/pluggable_protocol_tree/tests/test_interfaces.py` (append)

- [ ] **Step 1: Write the interface file**

Create `src/pluggable_protocol_tree/interfaces/i_column.py`:

```python
"""Traits interfaces for protocol-tree columns.

Every column is a trio: model (semantics), view (presentation), handler
(behaviour). The IColumn interface bundles them. This split lets two
plugins reuse the same model with different views, or the same view with
different handlers, with no coupling.
"""

from traits.api import Interface, Str, Any, Int, Bool, Instance, List


class IColumnModel(Interface):
    """Semantic definition: what kind of value this column holds."""
    col_id = Str
    col_name = Str
    default_value = Any

    def trait_for_row(self):
        """Return the Traits TraitType (Float, Int, Str, List, ...) that
        this column contributes to the dynamic row class. Type validation
        and defaults live here."""

    def get_value(self, row):
        """Read the column's value off `row`."""

    def set_value(self, row, value):
        """Write `value` to the column on `row`. Returns True on success."""

    def serialize(self, value):
        """Convert a trait value to a JSON-native form."""

    def deserialize(self, raw):
        """Convert a JSON-native form back to a trait value."""


class IColumnView(Interface):
    """How the column looks and edits in the tree grid."""
    hidden_by_default = Bool(False)
    renders_on_group = Bool(True)

    def format_display(self, value, row):
        """String shown in the cell (DisplayRole)."""

    def get_flags(self, row):
        """Qt.ItemFlag bitmask for this cell on this row."""

    def get_check_state(self, value, row):
        """Qt.CheckState or None (returning None means no checkbox)."""

    def create_editor(self, parent, context):
        """Create a QWidget for editing. Return None for non-editable cells."""

    def set_editor_data(self, editor, value):
        """Push `value` into the editor widget."""

    def get_editor_data(self, editor):
        """Pull the current value out of the editor widget."""


class IColumnHandler(Interface):
    """Runtime behaviour. Five execution hooks + one UI-edit hook.

    Priority bucket (lower runs first, equal priorities run in parallel)
    applies to all five execution hooks in PPT-2 onward. In PPT-1 the
    hooks are defined but never invoked (no executor yet).
    """
    priority = Int(50)
    wait_for_topics = List(Str,
        desc="Topics this handler may call ctx.wait_for() on. Aggregated "
             "by core plugin for the executor's dramatiq subscription. "
             "Unused in PPT-1; reserved for PPT-2.")

    def on_interact(self, row, model, value):
        """Called when the UI commits an edit. Default: model.set_value."""

    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


class IColumn(Interface):
    """Composition of model + view + handler."""
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)
```

- [ ] **Step 2: Write interface smoke tests**

Append to `src/pluggable_protocol_tree/tests/test_interfaces.py`:

```python
from pluggable_protocol_tree.interfaces.i_column import (
    IColumnModel, IColumnView, IColumnHandler, IColumn,
)


def test_column_interfaces_are_interfaces():
    for iface in (IColumnModel, IColumnView, IColumnHandler, IColumn):
        assert issubclass(iface, Interface)
```

- [ ] **Step 3: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_interfaces.py -v"
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/interfaces/i_column.py pluggable_protocol_tree/tests/test_interfaces.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Column interfaces (IColumn, IColumnModel, IColumnView, IColumnHandler)

Three-way concern split: model = semantics (trait type, default, serialize),
view = presentation (display string, flags, editor widget), handler =
behaviour (priority, wait_for_topics, five execution hooks + on_interact).
IColumn bundles them. Hooks are defined but wiring lives in PPT-2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Base column model, handler, and composite

**Files:**
- Create: `src/pluggable_protocol_tree/models/column.py`
- Create: `src/pluggable_protocol_tree/tests/test_column.py`

- [ ] **Step 1: Write failing tests**

Create `src/pluggable_protocol_tree/tests/test_column.py`:

```python
"""Tests for BaseColumnModel, BaseColumnHandler, Column composite."""

from traits.api import Float, Str

from pluggable_protocol_tree.models.row import BaseRow, build_row_type
from pluggable_protocol_tree.models.column import (
    BaseColumnModel, BaseColumnHandler, Column,
)


def test_base_column_model_stores_metadata():
    m = BaseColumnModel(col_id="voltage", col_name="Voltage", default_value=100.0)
    assert m.col_id == "voltage"
    assert m.col_name == "Voltage"
    assert m.default_value == 100.0


def test_base_column_model_trait_for_row_returns_any_by_default():
    """Base model uses Any trait; typed variants override."""
    m = BaseColumnModel(col_id="x", col_name="X", default_value="hello")
    trait = m.trait_for_row()
    # Trait descriptor should accept the declared default when used
    RowType = build_row_type([_fake_col(m, trait)], base=BaseRow)
    r = RowType()
    assert r.x == "hello"


def _fake_col(model, trait):
    """Test helper — mimics what Column does for build_row_type."""
    class _C:
        pass
    c = _C()
    c.model = model
    c.model.trait_for_row = lambda: trait
    return c


def test_base_column_model_get_set_value_on_row():
    m = BaseColumnModel(col_id="voltage", col_name="Voltage", default_value=100.0)
    RowType = build_row_type([_fake_col(m, Float(100.0))], base=BaseRow)
    r = RowType()
    assert m.get_value(r) == 100.0
    assert m.set_value(r, 150.0) is True
    assert m.get_value(r) == 150.0


def test_base_column_model_serialize_deserialize_identity():
    """Default serialize/deserialize are identity for JSON-native types."""
    m = BaseColumnModel(col_id="x", col_name="X", default_value=0)
    assert m.serialize(42) == 42
    assert m.deserialize(42) == 42
    assert m.serialize("hello") == "hello"
    assert m.deserialize(True) is True


def test_base_column_handler_defaults():
    h = BaseColumnHandler()
    assert h.priority == 50
    assert h.wait_for_topics == []


def test_base_column_handler_on_interact_delegates_to_model():
    m = BaseColumnModel(col_id="voltage", col_name="Voltage", default_value=0.0)
    RowType = build_row_type([_fake_col(m, Float(0.0))], base=BaseRow)
    r = RowType()
    h = BaseColumnHandler()
    assert h.on_interact(r, m, 42.0) is True
    assert m.get_value(r) == 42.0


def test_column_composite_auto_wires_model_into_view_and_handler():
    """Column.traits_init should set view.model and handler.{model,view}."""
    from pluggable_protocol_tree.views.columns.base import BaseColumnView
    m = BaseColumnModel(col_id="x", col_name="X", default_value=0)
    v = BaseColumnView()
    h = BaseColumnHandler()
    col = Column(model=m, view=v, handler=h)
    assert col.view.model is m
    assert col.handler.model is m
    assert col.handler.view is v


def test_column_composite_creates_default_handler_if_none_given():
    from pluggable_protocol_tree.views.columns.base import BaseColumnView
    m = BaseColumnModel(col_id="x", col_name="X", default_value=0)
    v = BaseColumnView()
    col = Column(model=m, view=v)
    assert isinstance(col.handler, BaseColumnHandler)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_column.py -v"
```

Expected: ImportError (column module doesn't exist) — some tests also rely on `views.columns.base` which we'll create in Task 8. Focus on the tests that don't need that; they should fail for the right reason.

- [ ] **Step 3: Implement the column classes**

Create `src/pluggable_protocol_tree/models/column.py`:

```python
"""Base model, handler, and composite for columns.

The 80%-case types. Plugin authors typically subclass BaseColumnModel to
declare a typed trait (see Task 9+ for built-in examples), and use
BaseColumnHandler as-is or override only the hooks they need. Column
itself is the composite that traits-wires model/view/handler together.
"""

from traits.api import (
    HasTraits, Instance, Str, Any, Int, List, Bool, provides, observe,
)

from pluggable_protocol_tree.interfaces.i_column import (
    IColumn, IColumnModel, IColumnView, IColumnHandler,
)


@provides(IColumnModel)
class BaseColumnModel(HasTraits):
    col_id = Str(desc="Stable id — used for storage, slicing, hook lookup")
    col_name = Str(desc="Display label for the column header")
    default_value = Any(None, desc="Value used on new-row insertion and as load-fallback")

    def trait_for_row(self):
        """Default: an Any trait seeded with default_value.

        Override in subclasses to use typed Traits (Float, Int, Str,
        List, ...) for proper validation and observer-friendliness.
        """
        return Any(self.default_value)

    def get_value(self, row):
        return getattr(row, self.col_id, None)

    def set_value(self, row, value):
        setattr(row, self.col_id, value)
        return True

    def serialize(self, value):
        """Identity for JSON-native types. Override for custom types."""
        return value

    def deserialize(self, raw):
        """Identity for JSON-native types. Override for custom types."""
        return raw


@provides(IColumnHandler)
class BaseColumnHandler(HasTraits):
    priority = Int(50)
    wait_for_topics = List(Str)

    # These are re-assigned by Column.traits_init so the handler can
    # reach its peers. Plugin authors generally do not set these.
    model = Instance(IColumnModel)
    view = Instance(IColumnView)

    def on_interact(self, row, model, value):
        """Default edit behaviour: write through to the model."""
        return model.set_value(row, value)

    # The five execution hooks — all no-ops by default.
    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


@provides(IColumn)
class Column(HasTraits):
    """Composite bundling model + view + handler.

    `traits_init` wires them together so view.model, handler.model,
    handler.view are all populated without the plugin author having to
    think about it. Re-assigning any of the three updates the wiring.
    """
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)

    def traits_init(self):
        if self.handler is None:
            self.handler = BaseColumnHandler()
        self.view.model = self.model
        self.handler.model = self.model
        self.handler.view = self.view

    @observe("model", post_init=True)
    def _on_model_change(self, event):
        self.view.model = self.model
        self.handler.model = self.model

    @observe("view", post_init=True)
    def _on_view_change(self, event):
        self.view.model = self.model
        self.handler.view = self.view

    @observe("handler", post_init=True)
    def _on_handler_change(self, event):
        self.handler.model = self.model
        self.handler.view = self.view
```

- [ ] **Step 4: Wait — BaseColumnView doesn't exist yet**

The Column composite's tests import `BaseColumnView` from `views.columns.base`. That module comes in Task 8. Skip running the Column tests for now; run only the model+handler tests:

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_column.py -v -k 'not composite'"
```

Expected: the 6 non-composite tests pass. The 2 composite tests collect-error on import; that's OK for now.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/column.py pluggable_protocol_tree/tests/test_column.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Base column model, handler, and composite

BaseColumnModel: col_id, col_name, default_value, trait_for_row (Any by
default), get/set_value, identity serialize/deserialize.
BaseColumnHandler: priority 50, empty wait_for_topics, on_interact
delegates to model.set_value, five execution hooks as no-ops.
Column: composite that auto-wires model/view/handler via traits_init
and keeps them wired on reassignment.

Tests for Column composite are skipped until BaseColumnView lands in
the next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Base column view

**Files:**
- Create: `src/pluggable_protocol_tree/views/columns/base.py`
- Create: `src/pluggable_protocol_tree/tests/test_views.py`

- [ ] **Step 1: Write failing tests**

Create `src/pluggable_protocol_tree/tests/test_views.py`:

```python
"""Tests for base column views.

Focused on the non-Qt surface: format_display, get_flags, get_check_state.
create_editor is exercised in the widget-level smoke test (Task 27).
"""

from pluggable_protocol_tree.models.row import BaseRow, GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


def test_base_view_default_hints():
    v = BaseColumnView()
    assert v.hidden_by_default is False
    assert v.renders_on_group is True


def test_base_view_format_display_is_str_of_value():
    v = BaseColumnView()
    assert v.format_display(42, BaseRow()) == "42"
    assert v.format_display("hello", BaseRow()) == "hello"


def test_base_view_format_display_empty_for_none():
    v = BaseColumnView()
    assert v.format_display(None, BaseRow()) == ""


def test_base_view_get_check_state_returns_none():
    v = BaseColumnView()
    assert v.get_check_state(True, BaseRow()) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_views.py -v"
```

Expected: ImportError (`views.columns.base`).

- [ ] **Step 3: Implement `BaseColumnView`**

Create `src/pluggable_protocol_tree/views/columns/base.py`:

```python
"""Base column view — non-editable text cell.

Plugin authors subclass this and override the subset of methods they
need. Concrete subclasses in this package: StringEditColumnView,
IntSpinBoxColumnView, DoubleSpinBoxColumnView, CheckboxColumnView,
ReadOnlyLabelColumnView.
"""

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QLineEdit
from traits.api import HasTraits, Bool, Instance, provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView, IColumnModel


@provides(IColumnView)
class BaseColumnView(HasTraits):
    hidden_by_default = Bool(False)
    renders_on_group = Bool(True)

    # Re-assigned by Column.traits_init; plugin authors don't set this.
    model = Instance(IColumnModel)

    def format_display(self, value, row):
        if value is None:
            return ""
        return str(value)

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def get_check_state(self, value, row):
        return None

    def create_editor(self, parent, context):
        """Default: a plain line edit. Non-editable views return None."""
        return QLineEdit(parent)

    def set_editor_data(self, editor, value):
        editor.setText("" if value is None else str(value))

    def get_editor_data(self, editor):
        return editor.text()
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_views.py pluggable_protocol_tree/tests/test_column.py -v"
```

Expected: All tests pass including the 2 Column composite tests that were collect-skipped in Task 7.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/views/columns/base.py pluggable_protocol_tree/tests/test_views.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] BaseColumnView — default text-cell view

Provides sensible defaults for all IColumnView methods: str(value)
display (empty for None), selectable-only flags, no check state, plain
QLineEdit editor. Subclasses override what they need.

Unblocks Column-composite tests that were collect-skipped earlier.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Concrete column views (StringEdit, SpinBox, Checkbox, ReadOnlyLabel)

**Files:**
- Create: `src/pluggable_protocol_tree/views/columns/string_edit.py`
- Create: `src/pluggable_protocol_tree/views/columns/spinbox.py`
- Create: `src/pluggable_protocol_tree/views/columns/checkbox.py`
- Create: `src/pluggable_protocol_tree/views/columns/readonly_label.py`
- Modify: `src/pluggable_protocol_tree/tests/test_views.py`

- [ ] **Step 1: Write failing tests for all four**

Append to `src/pluggable_protocol_tree/tests/test_views.py`:

```python
# --- StringEditColumnView ---

from pluggable_protocol_tree.views.columns.string_edit import StringEditColumnView


def test_string_edit_is_editable_on_step():
    v = StringEditColumnView()
    from pyface.qt.QtCore import Qt
    flags = v.get_flags(BaseRow())
    assert flags & Qt.ItemIsEditable


def test_string_edit_group_flags_default_editable_too():
    """StringEdit renders on groups by default (renders_on_group=True).

    A column that shouldn't be editable on groups — like Duration —
    overrides get_flags or sets renders_on_group=False."""
    v = StringEditColumnView()
    from pyface.qt.QtCore import Qt
    flags = v.get_flags(GroupRow())
    assert flags & Qt.ItemIsEditable


# --- SpinBox views ---

from pluggable_protocol_tree.views.columns.spinbox import (
    IntSpinBoxColumnView, DoubleSpinBoxColumnView,
)


def test_double_spinbox_stores_hints():
    v = DoubleSpinBoxColumnView(low=0.0, high=200.0, decimals=2, single_step=0.5)
    assert v.low == 0.0
    assert v.high == 200.0
    assert v.decimals == 2
    assert v.single_step == 0.5


def test_double_spinbox_format_display_applies_decimals():
    v = DoubleSpinBoxColumnView(decimals=2)
    assert v.format_display(3.14159, BaseRow()) == "3.14"


def test_double_spinbox_format_display_empty_for_none():
    v = DoubleSpinBoxColumnView()
    assert v.format_display(None, BaseRow()) == ""


def test_double_spinbox_group_is_not_editable():
    """Values on groups aren't meaningful for a per-step numeric column."""
    v = DoubleSpinBoxColumnView()
    from pyface.qt.QtCore import Qt
    flags = v.get_flags(GroupRow())
    assert not (flags & Qt.ItemIsEditable)


def test_int_spinbox_format_display_integer():
    v = IntSpinBoxColumnView()
    assert v.format_display(5, BaseRow()) == "5"
    assert v.format_display(5.9, BaseRow()) == "5"   # int cast


# --- CheckboxColumnView ---

from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView


def test_checkbox_display_is_empty_string():
    v = CheckboxColumnView()
    assert v.format_display(True, BaseRow()) == ""
    assert v.format_display(False, BaseRow()) == ""


def test_checkbox_check_state_on_step():
    from pyface.qt.QtCore import Qt
    v = CheckboxColumnView()
    assert v.get_check_state(True, BaseRow()) == Qt.Checked
    assert v.get_check_state(False, BaseRow()) == Qt.Unchecked


def test_checkbox_no_check_state_on_group():
    """Groups don't render the checkbox."""
    v = CheckboxColumnView()
    assert v.get_check_state(True, GroupRow()) is None


def test_checkbox_group_not_user_checkable():
    from pyface.qt.QtCore import Qt
    v = CheckboxColumnView()
    flags = v.get_flags(GroupRow())
    assert not (flags & Qt.ItemIsUserCheckable)


# --- ReadOnlyLabelColumnView ---

from pluggable_protocol_tree.views.columns.readonly_label import ReadOnlyLabelColumnView


def test_readonly_label_flags_not_editable():
    from pyface.qt.QtCore import Qt
    v = ReadOnlyLabelColumnView()
    assert not (v.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_readonly_label_create_editor_returns_none():
    v = ReadOnlyLabelColumnView()
    assert v.create_editor(None, None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_views.py -v"
```

Expected: ImportErrors on the new view modules.

- [ ] **Step 3: Implement StringEditColumnView**

Create `src/pluggable_protocol_tree/views/columns/string_edit.py`:

```python
"""Editable line-edit column view for Str-typed columns."""

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QLineEdit
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class StringEditColumnView(BaseColumnView):
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        return QLineEdit(parent)

    def set_editor_data(self, editor, value):
        editor.setText("" if value is None else str(value))

    def get_editor_data(self, editor):
        return editor.text()
```

- [ ] **Step 4: Implement SpinBox views**

Create `src/pluggable_protocol_tree/views/columns/spinbox.py`:

```python
"""Integer and floating-point spinbox column views.

Hints (low/high/decimals/single_step) live on the view — the model only
declares the type. Two plugins can reuse one model with different
spinbox hint configurations."""

import math

from pyface.qt.QtCore import Qt
from pyface.qt.QtGui import QSpinBox, QDoubleSpinBox
from traits.api import Float, Int, provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class IntSpinBoxColumnView(BaseColumnView):
    low = Int(0, desc="Spinbox minimum")
    high = Int(1000, desc="Spinbox maximum")

    def format_display(self, value, row):
        if value is None:
            return ""
        return str(int(value))

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base   # non-editable on groups
        return base | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        e = QSpinBox(parent)
        e.setMinimum(self.low)
        e.setMaximum(self.high)
        return e

    def set_editor_data(self, editor, value):
        editor.setValue(int(value) if value is not None else 0)

    def get_editor_data(self, editor):
        return editor.value()


@provides(IColumnView)
class DoubleSpinBoxColumnView(BaseColumnView):
    low = Float(0.0, desc="Spinbox minimum")
    high = Float(1000.0, desc="Spinbox maximum")
    decimals = Int(2, desc="Decimal places shown")
    single_step = Float(0.5, desc="Spinbox arrow step")

    def format_display(self, value, row):
        if value is None:
            return ""
        return f"{float(value):.{self.decimals}f}"

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base
        return base | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        e = QDoubleSpinBox(parent)
        # QDoubleSpinBox doesn't accept math.inf — clamp to a very large value.
        e.setMinimum(self.low if math.isfinite(self.low) else -1e12)
        e.setMaximum(self.high if math.isfinite(self.high) else 1e12)
        e.setDecimals(self.decimals)
        e.setSingleStep(self.single_step)
        return e

    def set_editor_data(self, editor, value):
        editor.setValue(float(value) if value is not None else 0.0)

    def get_editor_data(self, editor):
        return editor.value()
```

- [ ] **Step 5: Implement CheckboxColumnView**

Create `src/pluggable_protocol_tree/views/columns/checkbox.py`:

```python
"""Checkbox column view for Bool-typed columns.

Checkboxes render only on step rows; groups show an empty cell.
Editing happens via the Qt check-role mechanism (no separate widget),
so create_editor returns None.
"""

from pyface.qt.QtCore import Qt
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class CheckboxColumnView(BaseColumnView):
    def format_display(self, value, row):
        return ""   # cell has no text; check role carries the state

    def get_check_state(self, value, row):
        if isinstance(row, GroupRow):
            return None
        return Qt.Checked if value else Qt.Unchecked

    def get_flags(self, row):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if isinstance(row, GroupRow):
            return base
        return base | Qt.ItemIsUserCheckable

    def create_editor(self, parent, context):
        return None   # Qt handles check-role edits directly

    def set_editor_data(self, editor, value):
        pass   # unused

    def get_editor_data(self, editor):
        pass   # unused
```

- [ ] **Step 6: Implement ReadOnlyLabelColumnView**

Create `src/pluggable_protocol_tree/views/columns/readonly_label.py`:

```python
"""Non-editable text column. Used for type, id, and any derived cells."""

from pyface.qt.QtCore import Qt
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class ReadOnlyLabelColumnView(BaseColumnView):
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable   # no editable flag

    def create_editor(self, parent, context):
        return None
```

- [ ] **Step 7: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_views.py -v"
```

Expected: all view tests pass.

- [ ] **Step 8: Commit**

```bash
git add pluggable_protocol_tree/views/columns/ pluggable_protocol_tree/tests/test_views.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Concrete column views: StringEdit, IntSpinBox, DoubleSpinBox, Checkbox, ReadOnlyLabel

Five base views covering the common-case editor widgets. Hints
(low/high/decimals/single_step) live on the view, not the model.
Groups get non-editable flags for SpinBox + Checkbox (values don't
apply); StringEdit renders on groups (for Name, etc.); ReadOnlyLabel
never edits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Built-in columns (type, name, duration)

**Files:**
- Create: `src/pluggable_protocol_tree/builtins/type_column.py`
- Create: `src/pluggable_protocol_tree/builtins/name_column.py`
- Create: `src/pluggable_protocol_tree/builtins/duration_column.py`
- Create: `src/pluggable_protocol_tree/tests/test_builtins.py`

- [ ] **Step 1: Write failing tests for all three**

Create `src/pluggable_protocol_tree/tests/test_builtins.py`:

```python
"""Tests for built-in columns shipped by the core plugin."""

from traits.api import Float, Str

from pluggable_protocol_tree.models.row import BaseRow, GroupRow, build_row_type
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column


# --- type column ---

def test_type_column_has_expected_metadata():
    col = make_type_column()
    assert col.model.col_id == "type"
    assert col.model.col_name == "Type"


def test_type_column_displays_row_type():
    col = make_type_column()
    assert col.view.format_display(None, BaseRow()) == "step"
    assert col.view.format_display(None, GroupRow()) == "group"


def test_type_column_is_read_only():
    from pyface.qt.QtCore import Qt
    col = make_type_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


# --- name column ---

def test_name_column_renders_name_trait():
    col = make_name_column()
    r = BaseRow(name="Hello")
    assert col.model.get_value(r) == "Hello"


def test_name_column_is_editable():
    from pyface.qt.QtCore import Qt
    col = make_name_column()
    assert col.view.get_flags(BaseRow()) & Qt.ItemIsEditable


# --- duration column ---

def test_duration_column_default_one_second():
    col = make_duration_column()
    assert col.model.default_value == 1.0


def test_duration_column_trait_is_float():
    col = make_duration_column()
    trait = col.model.trait_for_row()
    # Building a row-type and instantiating should yield float default
    RowType = build_row_type([col], base=BaseRow)
    assert RowType().duration_s == 1.0


def test_duration_column_renders_on_group_but_not_editable_there():
    """Duration is not meaningful on groups (Q5 A + X: groups just
    organize)."""
    from pyface.qt.QtCore import Qt
    col = make_duration_column()
    # renders_on_group is True (so cell is shown) but the double-spinbox
    # view makes it non-editable on groups.
    flags = col.view.get_flags(GroupRow())
    assert not (flags & Qt.ItemIsEditable)


def test_duration_column_hidden_by_default_false():
    col = make_duration_column()
    assert col.view.hidden_by_default is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: ImportError on all three builtin modules.

- [ ] **Step 3: Implement type column**

Create `src/pluggable_protocol_tree/builtins/type_column.py`:

```python
"""Read-only column displaying each row's type ('step' or 'group')."""

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


class TypeColumnModel(BaseColumnModel):
    def get_value(self, row):
        return row.row_type


class TypeColumnView(ReadOnlyLabelColumnView):
    def format_display(self, value, row):
        return row.row_type


def make_type_column():
    return Column(
        model=TypeColumnModel(col_id="type", col_name="Type"),
        view=TypeColumnView(),
    )
```

- [ ] **Step 4: Implement name column**

Create `src/pluggable_protocol_tree/builtins/name_column.py`:

```python
"""Editable free-text Name column backed by the BaseRow.name trait."""

from traits.api import Str

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.string_edit import StringEditColumnView


class NameColumnModel(BaseColumnModel):
    def trait_for_row(self):
        """Name already exists on BaseRow — this Str here is safe to
        re-declare; Traits will use the subclass-level trait, preserving
        the default from the base."""
        return Str("Step")

    def get_value(self, row):
        return row.name

    def set_value(self, row, value):
        row.name = "" if value is None else str(value)
        return True


def make_name_column():
    return Column(
        model=NameColumnModel(col_id="name", col_name="Name", default_value="Step"),
        view=StringEditColumnView(),
    )
```

- [ ] **Step 5: Implement duration column**

Create `src/pluggable_protocol_tree/builtins/duration_column.py`:

```python
"""Step duration in seconds.

Stored as a Float trait on each row. Not meaningful on groups; the
double-spinbox view already marks group cells non-editable."""

from traits.api import Float

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import DoubleSpinBoxColumnView


class DurationColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Float(1.0, desc="Dwell time for this step in seconds")


def make_duration_column():
    return Column(
        model=DurationColumnModel(
            col_id="duration_s", col_name="Duration (s)", default_value=1.0,
        ),
        view=DoubleSpinBoxColumnView(
            low=0.0, high=3600.0, decimals=2, single_step=0.1,
        ),
    )
```

- [ ] **Step 6: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: 9 passed.

- [ ] **Step 7: Commit**

```bash
git add pluggable_protocol_tree/builtins/ pluggable_protocol_tree/tests/test_builtins.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Built-in columns: type, name, duration

Three of the four always-on core columns (id is next).
- type: read-only, shows 'step'/'group' from row.row_type
- name: editable string, backed by BaseRow.name
- duration_s: float seconds, 1.0 default, non-editable on groups

Each is exposed via a make_*_column() factory so the plugin can
instantiate them fresh per protocol.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Built-in `id` column (1-indexed dotted path)

**Files:**
- Create: `src/pluggable_protocol_tree/builtins/id_column.py`
- Modify: `src/pluggable_protocol_tree/tests/test_builtins.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_builtins.py`:

```python
# --- id column ---

from pluggable_protocol_tree.builtins.id_column import make_id_column


def test_id_column_read_only():
    from pyface.qt.QtCore import Qt
    col = make_id_column()
    assert not (col.view.get_flags(BaseRow()) & Qt.ItemIsEditable)


def test_id_column_top_level_display():
    """A top-level row at position 0 displays '1' (1-indexed)."""
    col = make_id_column()
    root = GroupRow(name="Root")
    a = BaseRow()
    b = BaseRow()
    root.add_row(a)
    root.add_row(b)
    assert col.view.format_display(None, a) == "1"
    assert col.view.format_display(None, b) == "2"


def test_id_column_nested_display():
    """Step 0 inside Group 0 inside Root displays '1.1'."""
    col = make_id_column()
    root = GroupRow(name="Root")
    g = GroupRow(name="G")
    s = BaseRow()
    root.add_row(g)
    g.add_row(s)
    assert col.view.format_display(None, g) == "1"
    assert col.view.format_display(None, s) == "1.1"


def test_id_column_orphan_row_empty():
    col = make_id_column()
    assert col.view.format_display(None, BaseRow()) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: ImportError for `id_column`.

- [ ] **Step 3: Implement id column**

Create `src/pluggable_protocol_tree/builtins/id_column.py`:

```python
"""Read-only dotted-path ID column.

Internal paths are 0-indexed tuples; the id column formats them
1-indexed so users see natural '1.2.3' rather than '0.1.2'. Orphan rows
(no parent) display the empty string.
"""

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)


class IdColumnModel(BaseColumnModel):
    def get_value(self, row):
        return row.path   # 0-indexed tuple

    def set_value(self, row, value):
        return False   # ID is derived, not assignable


class IdColumnView(ReadOnlyLabelColumnView):
    def format_display(self, value, row):
        path = row.path
        if not path:
            return ""
        return ".".join(str(i + 1) for i in path)


def make_id_column():
    return Column(
        model=IdColumnModel(col_id="id", col_name="ID"),
        view=IdColumnView(),
    )
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_builtins.py -v"
```

Expected: 13 passed (9 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/builtins/id_column.py pluggable_protocol_tree/tests/test_builtins.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Built-in id column (1-indexed dotted path)

Read-only column formatting each row's internal 0-indexed path tuple as
a 1-indexed dotted string for display ('1.2.3' rather than '0.1.2').
Orphan rows (no parent) show empty. Not assignable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: RowManager — structure operations

**Files:**
- Create: `src/pluggable_protocol_tree/models/row_manager.py`
- Create: `src/pluggable_protocol_tree/tests/test_row_manager.py`

- [ ] **Step 1: Write failing tests for structure ops**

Create `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
"""Tests for RowManager structure, selection, clipboard, iteration, slicing."""

import pytest

from pluggable_protocol_tree.models.row import BaseRow, GroupRow
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column


@pytest.fixture
def columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_duration_column(),
    ]


@pytest.fixture
def manager(columns):
    return RowManager(columns=columns)


# --- construction ---

def test_row_manager_has_empty_root_on_construction(manager):
    assert manager.root is not None
    assert isinstance(manager.root, GroupRow)
    assert manager.root.children == []


def test_row_manager_builds_step_and_group_subclasses(manager):
    assert manager.step_type is not None
    assert manager.group_type is not None
    # Dynamic subclasses should carry the duration trait from the column
    step = manager.step_type()
    assert step.duration_s == 1.0


# --- add_step / add_group ---

def test_add_step_at_root(manager):
    path = manager.add_step()
    assert path == (0,)
    assert len(manager.root.children) == 1


def test_add_group_at_root(manager):
    path = manager.add_group(name="Wash")
    assert path == (0,)
    assert manager.root.children[0].name == "Wash"


def test_add_step_inside_group(manager):
    gpath = manager.add_group(name="Wash")
    spath = manager.add_step(parent_path=gpath)
    assert spath == (0, 0)
    g = manager.root.children[0]
    assert len(g.children) == 1


def test_add_step_with_values(manager):
    path = manager.add_step(values={"duration_s": 3.5, "name": "DropOn"})
    row = manager.get_row(path)
    assert row.duration_s == 3.5
    assert row.name == "DropOn"


# --- remove ---

def test_remove_single_row(manager):
    manager.add_step()
    p = manager.add_step()
    manager.remove([p])
    assert len(manager.root.children) == 1


def test_remove_group_removes_children(manager):
    gpath = manager.add_group()
    manager.add_step(parent_path=gpath)
    manager.add_step(parent_path=gpath)
    manager.remove([gpath])
    assert manager.root.children == []


# --- move ---

def test_move_reorders_within_parent(manager):
    a = manager.add_step(values={"name": "A"})
    b = manager.add_step(values={"name": "B"})
    manager.move([a], target_parent_path=(), target_index=2)   # move A after B
    names = [r.name for r in manager.root.children]
    assert names == ["B", "A"]


def test_move_reparents_into_group(manager):
    g = manager.add_group()
    s = manager.add_step(values={"name": "S"})
    manager.move([s], target_parent_path=g, target_index=0)
    new_group = manager.root.children[0]
    assert len(new_group.children) == 1
    assert new_group.children[0].name == "S"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: ImportError (`models.row_manager`).

- [ ] **Step 3: Implement RowManager structure ops**

Create `src/pluggable_protocol_tree/models/row_manager.py`:

```python
"""Central manager for the protocol tree — structure, selection, clipboard,
slicing, iteration, persistence.

Selection is stored as a list of 0-indexed path tuples, not row refs: paths
survive tree mutations during paste, but row references don't. The
dynamic step/group subclasses are built once at construction from the
active column set.
"""

from typing import Iterator, List, Optional, Tuple

from traits.api import (
    HasTraits, Instance, List as ListTrait, Tuple as TupleTrait, Int,
    Event, Str, observe,
)

from pluggable_protocol_tree.consts import PROTOCOL_ROWS_MIME
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row import BaseRow, GroupRow, build_row_type


Path = Tuple[int, ...]


class RowManager(HasTraits):
    """Single public API for every tree operation."""

    root = Instance(GroupRow)
    columns = ListTrait(Instance(IColumn))

    step_type = Instance(type)
    group_type = Instance(type)

    selection = ListTrait(TupleTrait(Int),
        desc="List of 0-indexed path tuples currently selected")

    clipboard_mime = Str(PROTOCOL_ROWS_MIME)

    rows_changed = Event(
        desc="Fires on structure or value changes. Batch-coalesced by UI.")

    # --- construction ---

    def traits_init(self):
        if self.root is None:
            self.root = GroupRow(name="Root")
        self._rebuild_types()

    @observe("columns.items")
    def _on_columns_change(self, event):
        self._rebuild_types()

    def _rebuild_types(self):
        self.step_type = build_row_type(
            self.columns, base=BaseRow, name="ProtocolStepRow",
        )
        self.group_type = build_row_type(
            self.columns, base=GroupRow, name="ProtocolGroupRow",
        )

    # --- tree lookup ---

    def get_row(self, path: Path) -> BaseRow:
        """Navigate to the row at `path`. Raises IndexError if invalid."""
        current = self.root
        for idx in path:
            current = current.children[idx]
        return current

    def _parent_for_path(self, parent_path: Path) -> GroupRow:
        target = self.root if parent_path == () else self.get_row(parent_path)
        if not isinstance(target, GroupRow):
            raise ValueError(f"Path {parent_path} is not a group")
        return target

    # --- structure mutation ---

    def add_step(self, parent_path: Path = (), index: Optional[int] = None,
                 values: Optional[dict] = None) -> Path:
        parent = self._parent_for_path(parent_path)
        row = self.step_type()
        if values:
            for k, v in values.items():
                setattr(row, k, v)
        if index is None:
            index = len(parent.children)
        parent.insert_row(index, row)
        self.rows_changed = True
        return parent_path + (index,)

    def add_group(self, parent_path: Path = (), index: Optional[int] = None,
                  name: str = "Group") -> Path:
        parent = self._parent_for_path(parent_path)
        row = self.group_type(name=name)
        if index is None:
            index = len(parent.children)
        parent.insert_row(index, row)
        self.rows_changed = True
        return parent_path + (index,)

    def remove(self, paths: List[Path]) -> None:
        """Remove all rows at `paths`. Paths that refer to a descendant of
        another removed path are skipped (the ancestor removal already
        takes them out)."""
        paths = [tuple(p) for p in paths]
        # Sort reverse-lexicographically so deeper removes don't shift
        # the indices of later ones.
        paths_sorted = sorted(paths, reverse=True)
        seen_ancestors: List[Path] = []
        for p in paths_sorted:
            if any(self._is_ancestor(a, p) for a in seen_ancestors):
                continue
            seen_ancestors.append(p)
            row = self.get_row(p)
            parent = row.parent
            if parent is not None:
                parent.remove_row(row)
        self.rows_changed = True

    @staticmethod
    def _is_ancestor(ancestor: Path, descendant: Path) -> bool:
        return (len(ancestor) < len(descendant)
                and descendant[: len(ancestor)] == ancestor)

    def move(self, paths: List[Path], target_parent_path: Path,
             target_index: int) -> None:
        """Move rows to a new parent. Collects rows first (while paths are
        still valid), then inserts at the target, removing from the old
        location afterwards."""
        rows = [self.get_row(tuple(p)) for p in paths]
        target = self._parent_for_path(target_parent_path)
        # Remove from old parents (in reverse order of the old paths so
        # indices don't shift).
        for row in rows:
            if row.parent is not None:
                row.parent.remove_row(row)
        for offset, row in enumerate(rows):
            target.insert_row(target_index + offset, row)
        self.rows_changed = True
```

- [ ] **Step 4: Run structure-ops tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: 10 passed (fixtures + 2 construction + 4 add + 2 remove + 2 move).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] RowManager — structure operations

Core tree manager (HasTraits). Builds per-protocol step/group subclasses
from the column set, exposes add_step/add_group/remove/move, and fires
rows_changed for UI observers. Selection/clipboard/iteration/slicing/
persistence follow in later tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: RowManager — selection and lookup

**Files:**
- Modify: `src/pluggable_protocol_tree/models/row_manager.py`
- Modify: `src/pluggable_protocol_tree/tests/test_row_manager.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- selection ---

def test_select_set_replaces_selection(manager):
    a = manager.add_step()
    b = manager.add_step()
    manager.select([a])
    manager.select([b], mode="set")
    assert manager.selection == [b]


def test_select_add_appends(manager):
    a = manager.add_step()
    b = manager.add_step()
    manager.select([a])
    manager.select([b], mode="add")
    assert manager.selection == [a, b]


def test_select_range_fills_between(manager):
    paths = [manager.add_step() for _ in range(5)]
    manager.select([paths[1], paths[3]], mode="range")
    # Range selects all top-level siblings between the two
    assert manager.selection == [paths[1], paths[2], paths[3]]


def test_selected_rows_returns_row_objects(manager):
    a = manager.add_step(values={"name": "A"})
    b = manager.add_step(values={"name": "B"})
    manager.select([a, b])
    names = [r.name for r in manager.selected_rows()]
    assert names == ["A", "B"]


# --- uuid lookup ---

def test_get_row_by_uuid_returns_row(manager):
    p = manager.add_step()
    row = manager.get_row(p)
    assert manager.get_row_by_uuid(row.uuid) is row


def test_get_row_by_uuid_none_for_unknown(manager):
    assert manager.get_row_by_uuid("does-not-exist") is None


def test_get_row_by_uuid_searches_nested(manager):
    g = manager.add_group()
    s = manager.add_step(parent_path=g)
    row = manager.get_row(s)
    assert manager.get_row_by_uuid(row.uuid) is row
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v -k 'select or uuid'"
```

Expected: AttributeError (methods not defined).

- [ ] **Step 3: Implement selection and uuid lookup**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    # --- selection ---

    def select(self, paths: List[Path], mode: str = "set") -> None:
        """Update `selection`.

        Modes:
        - 'set'   : replace selection with `paths`
        - 'add'   : append `paths`, deduplicating
        - 'range' : selection becomes all top-level siblings between the
                    first and last of `paths`. Only meaningful when the
                    given paths have a common parent.
        """
        paths = [tuple(p) for p in paths]
        if mode == "set":
            self.selection = paths
        elif mode == "add":
            seen = set(tuple(p) for p in self.selection)
            new = [p for p in paths if p not in seen]
            self.selection = list(self.selection) + new
        elif mode == "range":
            if not paths:
                return
            # Take common parent of first and last; select siblings
            # between their positions.
            first, last = paths[0], paths[-1]
            if first[:-1] != last[:-1]:
                # Different parents — fall back to 'set'.
                self.selection = [first, last]
                return
            parent_path = first[:-1]
            lo, hi = sorted([first[-1], last[-1]])
            self.selection = [parent_path + (i,) for i in range(lo, hi + 1)]
        else:
            raise ValueError(f"Unknown selection mode: {mode}")

    def selected_rows(self) -> List[BaseRow]:
        return [self.get_row(p) for p in self.selection]

    # --- uuid lookup ---

    def get_row_by_uuid(self, uuid: str) -> Optional[BaseRow]:
        return self._find_by_uuid(self.root, uuid)

    @classmethod
    def _find_by_uuid(cls, node, uuid: str) -> Optional[BaseRow]:
        if isinstance(node, GroupRow):
            for child in node.children:
                if child.uuid == uuid:
                    return child
                found = cls._find_by_uuid(child, uuid)
                if found is not None:
                    return found
        return None
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: all row-manager tests pass (10 + 7 new = 17).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] RowManager — selection + uuid lookup

select(paths, mode='set'|'add'|'range'), selected_rows(), and
get_row_by_uuid() for cross-tree identity lookup (the latter used by
the device-viewer binding in PPT-3). Selection is stored as path
tuples so it survives tree mutations.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: RowManager — clipboard (copy/cut/paste via JSON)

**Files:**
- Modify: `src/pluggable_protocol_tree/models/row_manager.py`
- Modify: `src/pluggable_protocol_tree/tests/test_row_manager.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- clipboard ---

def test_copy_paste_round_trip_preserves_names(manager):
    a = manager.add_step(values={"name": "A", "duration_s": 2.0})
    manager.select([a])
    # Use an in-memory clipboard surrogate so tests don't depend on a
    # running QApplication — RowManager exposes a serialize_selection
    # helper that returns the payload, and paste_from_json accepts it.
    payload = manager._serialize_selection()
    assert payload["rows"][0][manager._field_index("name")] == "A"

    manager._paste_from_payload(payload, target_path=None)
    assert len(manager.root.children) == 2
    assert manager.root.children[1].name == "A"


def test_copy_paste_regenerates_uuids(manager):
    a = manager.add_step()
    original_uuid = manager.get_row(a).uuid
    manager.select([a])
    payload = manager._serialize_selection()
    manager._paste_from_payload(payload, target_path=None)
    pasted = manager.root.children[1]
    assert pasted.uuid != original_uuid


def test_cut_removes_originals(manager):
    a = manager.add_step(values={"name": "A"})
    b = manager.add_step(values={"name": "B"})
    manager.select([a])
    payload = manager._serialize_selection()
    manager.remove([a])   # cut = copy + remove; here we drive manually
    assert [r.name for r in manager.root.children] == ["B"]
    manager._paste_from_payload(payload, target_path=None)
    assert [r.name for r in manager.root.children] == ["B", "A"]


def test_copy_paste_includes_children_of_groups(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "Inner"})
    manager.select([g])
    payload = manager._serialize_selection()
    manager._paste_from_payload(payload, target_path=None)
    copied_group = manager.root.children[1]
    assert copied_group.name == "G"
    assert len(copied_group.children) == 1
    assert copied_group.children[0].name == "Inner"
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v -k 'copy or cut or paste'"
```

Expected: AttributeError on `_serialize_selection` / `_paste_from_payload`.

- [ ] **Step 3: Implement internal payload helpers + QClipboard-facing methods**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    # --- clipboard (payload-layer; QClipboard IO lives in copy/cut/paste) ---

    def _field_index(self, col_id: str) -> int:
        """Position of col_id in the serialized row tuple (depth/uuid/type/name
        come first, then columns in their self.columns order)."""
        fields = ["depth", "uuid", "type", "name"] + [c.model.col_id for c in self.columns]
        return fields.index(col_id)

    def _serialize_selection(self) -> dict:
        """Return a clipboard-style payload covering the current selection.

        Format mirrors persistence (no schema_version on the clipboard):
        {"columns": [...], "fields": [...], "rows": [[depth, uuid, type, name, *values], ...]}
        Children of a selected group are included automatically.
        """
        rows_out: list = []
        field_names = ["depth", "uuid", "type", "name"] + [
            c.model.col_id for c in self.columns
        ]

        def emit(row: BaseRow, depth: int):
            vals = [depth, row.uuid, row.row_type, row.name]
            for col in self.columns:
                raw = col.model.get_value(row)
                vals.append(col.model.serialize(raw))
            rows_out.append(vals)
            if isinstance(row, GroupRow):
                for child in row.children:
                    emit(child, depth + 1)

        # Emit top-level selected rows; children handled recursively.
        for p in self.selection:
            row = self.get_row(p)
            # Skip rows whose ancestor is also selected (covered already).
            if any(self._is_ancestor(tuple(other), tuple(p))
                   for other in self.selection if other != p):
                continue
            emit(row, depth=0)

        return {
            "columns": [
                {
                    "id": c.model.col_id,
                    "cls": f"{type(c.model).__module__}.{type(c.model).__name__}",
                }
                for c in self.columns
            ],
            "fields": field_names,
            "rows": rows_out,
        }

    def _paste_from_payload(self, payload: dict, target_path: Optional[Path]) -> None:
        """Reconstruct rows from `payload` and insert after `target_path`
        (or at the end of root if None). Each pasted row gets a fresh uuid."""
        import uuid as _uuid

        fields: list = payload["fields"]
        col_ids_in_payload: list = fields[4:]   # skip depth, uuid, type, name
        live_by_col_id = {c.model.col_id: c for c in self.columns}

        # Determine insertion target.
        if target_path is None or target_path == ():
            target_parent = self.root
            insert_idx = len(self.root.children)
        else:
            target_row = self.get_row(target_path)
            if isinstance(target_row, GroupRow):
                target_parent = target_row
                insert_idx = len(target_row.children)
            else:
                target_parent = target_row.parent or self.root
                insert_idx = target_parent.children.index(target_row) + 1

        # Reconstruct, honoring depth stacking.
        stack: list = [target_parent]   # stack[-1] is the current parent
        base_depth = 0
        first = True
        for row_tuple in payload["rows"]:
            depth = row_tuple[0]
            row_type = row_tuple[2]
            row_name = row_tuple[3]
            values = row_tuple[4:]

            if first:
                base_depth = depth
                first = False

            relative_depth = depth - base_depth
            # Trim stack to relative_depth + 1 entries (we're a child of
            # stack[relative_depth]).
            stack = stack[: relative_depth + 1]
            parent = stack[-1]

            row_cls = self.step_type if row_type == "step" else self.group_type
            row = row_cls(name=row_name, uuid=_uuid.uuid4().hex)
            for col_id, raw in zip(col_ids_in_payload, values):
                col = live_by_col_id.get(col_id)
                if col is None:
                    continue   # orphan column (PPT-1 scope: skip silently)
                setattr(row, col_id, col.model.deserialize(raw))

            # Insert either at the computed position (top-level) or
            # just append for nested.
            if relative_depth == 0:
                parent.insert_row(insert_idx, row)
                insert_idx += 1
            else:
                parent.add_row(row)

            if row_type == "group":
                stack.append(row)

        self.rows_changed = True

    # --- public clipboard API (wraps QClipboard) ---

    def copy(self) -> None:
        """Serialize the current selection onto the system QClipboard."""
        from pyface.qt.QtWidgets import QApplication
        import json
        payload = self._serialize_selection()
        mime_text = json.dumps(payload)
        cb = QApplication.clipboard()
        cb.setText(mime_text)   # TODO(PPT-1): use MIME-typed QMimeData for xplat
        # NOTE: PPT-1 uses plain-text clipboard for simplicity; upgrading to
        # a proper application/x-microdrop-rows+json MIME type via QMimeData
        # lands when we also need cross-app paste. For within-app round-trip
        # the plain-text path is sufficient.

    def cut(self) -> None:
        self.copy()
        self.remove(list(self.selection))

    def paste(self, target_path: Optional[Path] = None) -> None:
        import json
        from pyface.qt.QtWidgets import QApplication
        cb = QApplication.clipboard()
        text = cb.text()
        if not text:
            return
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            return
        if "rows" not in payload:
            return
        self._paste_from_payload(payload, target_path)
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: all 21 tests pass (17 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] RowManager — clipboard via serialized payload

_serialize_selection() builds a compact depth-encoded payload of the
current selection (children of groups included). _paste_from_payload()
reconstructs it at the target. Fresh UUIDs are generated for each pasted
row so duplicates don't collide with originals. Public copy/cut/paste
go through QApplication.clipboard() as plain JSON text; a MIME-typed
upgrade for cross-app paste is flagged for later.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: RowManager — iter_execution_steps

**Files:**
- Modify: `src/pluggable_protocol_tree/models/row_manager.py`
- Modify: `src/pluggable_protocol_tree/tests/test_row_manager.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- iter_execution_steps ---

def test_iter_execution_flat_protocol(manager):
    manager.add_step(values={"name": "A"})
    manager.add_step(values={"name": "B"})
    names = [r.name for r in manager.iter_execution_steps()]
    assert names == ["A", "B"]


def test_iter_execution_flattens_groups(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "A"})
    manager.add_step(parent_path=g, values={"name": "B"})
    manager.add_step(values={"name": "C"})
    names = [r.name for r in manager.iter_execution_steps()]
    assert names == ["A", "B", "C"]


def test_iter_execution_expands_repetitions(manager):
    """Until PPT-1 integrates the repetitions column, the default
    repetitions value is 1. The iter_execution_steps loop reads a
    `repetitions` attribute if present, defaulting to 1."""
    manager.add_step(values={"name": "A"})
    s = manager.add_step(values={"name": "B"})
    # Simulate the repetitions column by assigning the attribute dynamically
    # (real repetitions column lands alongside this method — see comment in
    # RowManager.iter_execution_steps for the contract).
    setattr(manager.get_row(s), "repetitions", 3)
    names = [r.name for r in manager.iter_execution_steps()]
    # A once, B three times (in order)
    assert names == ["A", "B", "B", "B"]


def test_iter_execution_group_repetitions_expand(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "A"})
    manager.add_step(parent_path=g, values={"name": "B"})
    setattr(manager.get_row(g), "repetitions", 2)
    names = [r.name for r in manager.iter_execution_steps()]
    assert names == ["A", "B", "A", "B"]
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v -k 'iter_execution'"
```

Expected: AttributeError (`iter_execution_steps`).

- [ ] **Step 3: Implement iter_execution_steps**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    # --- execution iteration ---

    def iter_execution_steps(self) -> Iterator[BaseRow]:
        """Yield rows in execution order, flattening groups and expanding
        repetitions.

        Repetitions contract: any row may have an integer attribute named
        ``repetitions``. When present, that row's yield is multiplied. If
        the row is a step, it's yielded `n` times. If a group, its entire
        child-subtree is expanded n times. Missing attribute defaults to
        1 rep. (The repetitions column is a core built-in that lands
        alongside PPT-3's trail-config columns; PPT-1 establishes the
        contract so the executor in PPT-2 can rely on it.)
        """
        yield from self._expand(self.root)

    @classmethod
    def _expand(cls, node) -> Iterator[BaseRow]:
        reps = max(1, int(getattr(node, "repetitions", 1) or 1))
        if isinstance(node, GroupRow):
            for _ in range(reps):
                for child in node.children:
                    yield from cls._expand(child)
        else:
            for _ in range(reps):
                yield node
```

Also, adjust the root iteration — the root itself doesn't have a
`repetitions` attribute, but it's a GroupRow, so `getattr(root,
"repetitions", 1)` returns 1 and the recursion works correctly.

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: all 25 pass.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] RowManager.iter_execution_steps

Yields rows in execution order: groups flattened to their children,
repetitions expanded via a 'repetitions' attribute on the row (step or
group). Default rep = 1 when the attribute is absent. This is the
contract the PPT-2 executor consumes; the repetitions column itself
is a core built-in landing alongside trail-config in a later task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: RowManager — pandas slicing facade

**Files:**
- Modify: `src/pluggable_protocol_tree/models/row_manager.py`
- Modify: `src/pluggable_protocol_tree/tests/test_row_manager.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- slicing ---

import pandas as pd


def test_table_is_dataframe_indexed_by_path(manager):
    manager.add_step(values={"name": "A", "duration_s": 2.0})
    manager.add_step(values={"name": "B", "duration_s": 3.0})
    df = manager.table
    assert isinstance(df, pd.DataFrame)
    assert list(df.index) == [(0,), (1,)]
    assert "name" in df.columns
    assert "duration_s" in df.columns


def test_table_values_correct(manager):
    p = manager.add_step(values={"name": "X", "duration_s": 4.5})
    df = manager.table
    assert df.loc[(0,), "name"] == "X"
    assert df.loc[(0,), "duration_s"] == 4.5


def test_cols_subset(manager):
    manager.add_step(values={"name": "A", "duration_s": 1.0})
    manager.add_step(values={"name": "B", "duration_s": 2.0})
    df = manager.cols(["duration_s"])
    assert list(df.columns) == ["duration_s"]
    assert df.shape == (2, 1)


def test_rows_slice(manager):
    for i in range(5):
        manager.add_step(values={"name": f"S{i}"})
    df = manager.rows(slice(1, 3))
    assert df.shape[0] == 2
    assert df.iloc[0]["name"] == "S1"


def test_rows_predicate(manager):
    manager.add_step(values={"name": "A", "duration_s": 1.0})
    manager.add_step(values={"name": "B", "duration_s": 5.0})
    df = manager.rows(lambda r: r["duration_s"] > 3.0)
    assert df.shape[0] == 1
    assert df.iloc[0]["name"] == "B"


def test_slice_combines_rows_and_cols(manager):
    manager.add_step(values={"name": "A", "duration_s": 1.0})
    manager.add_step(values={"name": "B", "duration_s": 2.0})
    df = manager.slice(rows=slice(0, 1), cols=["name"])
    assert df.shape == (1, 1)
    assert df.iloc[0]["name"] == "A"
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v -k 'table or cols or rows or slice'"
```

Expected: AttributeError.

- [ ] **Step 3: Implement the pandas facade**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    # --- slicing (pandas facade) ---

    @property
    def table(self):
        """Snapshot DataFrame. Index = path tuples. Columns = col_ids.
        Rebuilt on each access (O(N rows)); not cached."""
        import pandas as pd
        rows_data = []
        index = []
        for path, row in self._walk():
            index.append(path)
            row_vals = {}
            for col in self.columns:
                row_vals[col.model.col_id] = col.model.get_value(row)
            rows_data.append(row_vals)
        col_ids = [c.model.col_id for c in self.columns]
        return pd.DataFrame(rows_data, index=pd.Index(index, tupleize_cols=False),
                            columns=col_ids)

    def _walk(self, node=None, prefix=()):
        """Depth-first traversal yielding (path, row). Skips the root."""
        if node is None:
            for i, child in enumerate(self.root.children):
                yield from self._walk(child, (i,))
            return
        yield (prefix, node)
        if isinstance(node, GroupRow):
            for i, child in enumerate(node.children):
                yield from self._walk(child, prefix + (i,))

    def rows(self, selector):
        df = self.table
        if isinstance(selector, slice):
            return df.iloc[selector]
        if callable(selector):
            mask = df.apply(selector, axis=1)
            return df[mask]
        if isinstance(selector, list):
            # selector is a list of path tuples
            return df.loc[[tuple(p) for p in selector]]
        raise TypeError(f"Unsupported selector type: {type(selector)}")

    def cols(self, col_ids):
        return self.table[list(col_ids)]

    def slice(self, rows=None, cols=None):
        df = self.table
        if rows is not None:
            df = self.rows(rows) if not isinstance(rows, slice) else df.iloc[rows]
        if cols is not None:
            df = df[list(cols)]
        return df
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: all 31 pass.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] RowManager — pandas slicing facade

Read-only DataFrame view over the tree, indexed by path tuples with one
column per IColumn. rows(selector) accepts slice/callable/path-list;
cols(ids) projects; slice(rows=, cols=) combines. Rebuilt O(N) on each
access. Writes still go through set_value/set_values/apply (imperative).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: RowManager — imperative bulk write

**Files:**
- Modify: `src/pluggable_protocol_tree/models/row_manager.py`
- Modify: `src/pluggable_protocol_tree/tests/test_row_manager.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_row_manager.py`:

```python
# --- bulk write ---

def test_set_value_single(manager):
    p = manager.add_step()
    manager.set_value(p, "name", "Updated")
    assert manager.get_row(p).name == "Updated"


def test_set_values_bulk(manager):
    a = manager.add_step()
    b = manager.add_step()
    manager.set_values([a, b], "duration_s", 4.2)
    assert manager.get_row(a).duration_s == 4.2
    assert manager.get_row(b).duration_s == 4.2


def test_apply_runs_callable_per_row(manager):
    a = manager.add_step(values={"duration_s": 1.0})
    b = manager.add_step(values={"duration_s": 2.0})
    manager.apply([a, b], lambda r: setattr(r, "duration_s", r.duration_s * 10))
    assert manager.get_row(a).duration_s == 10.0
    assert manager.get_row(b).duration_s == 20.0
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v -k 'set_value or set_values or apply'"
```

Expected: AttributeError.

- [ ] **Step 3: Implement bulk write**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    # --- imperative bulk write ---

    def set_value(self, path: Path, col_id: str, value) -> None:
        col = self._column_by_id(col_id)
        row = self.get_row(path)
        col.model.set_value(row, value)
        self.rows_changed = True

    def set_values(self, paths: List[Path], col_id: str, value) -> None:
        col = self._column_by_id(col_id)
        for p in paths:
            col.model.set_value(self.get_row(p), value)
        self.rows_changed = True

    def apply(self, paths: List[Path], fn) -> None:
        for p in paths:
            fn(self.get_row(p))
        self.rows_changed = True

    def _column_by_id(self, col_id: str) -> IColumn:
        for c in self.columns:
            if c.model.col_id == col_id:
                return c
        raise KeyError(col_id)
```

- [ ] **Step 4: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_row_manager.py -v"
```

Expected: all 34 pass.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] RowManager — imperative bulk write

set_value(path, col_id, value), set_values(paths, col_id, value),
apply(paths, fn). All routes through the column's model.set_value
(or user callable) and emit rows_changed. Writes do not go through
the DataFrame facade — snapshot mutation would introduce two sources
of truth.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Persistence — save (to_json)

**Files:**
- Create: `src/pluggable_protocol_tree/services/persistence.py`
- Create: `src/pluggable_protocol_tree/tests/test_persistence.py`
- Modify: `src/pluggable_protocol_tree/models/row_manager.py` (delegate to_json)

- [ ] **Step 1: Write failing tests for save**

Create `src/pluggable_protocol_tree/tests/test_persistence.py`:

```python
"""Tests for persistence (save/load)."""

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.consts import PERSISTENCE_SCHEMA_VERSION


@pytest.fixture
def columns():
    return [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]


@pytest.fixture
def manager(columns):
    return RowManager(columns=columns)


# --- save ---

def test_to_json_schema_version(manager):
    data = manager.to_json()
    assert data["schema_version"] == PERSISTENCE_SCHEMA_VERSION


def test_to_json_columns_metadata(manager):
    data = manager.to_json()
    ids = [c["id"] for c in data["columns"]]
    assert ids == ["type", "id", "name", "duration_s"]
    for c in data["columns"]:
        assert "cls" in c


def test_to_json_fields_order(manager):
    data = manager.to_json()
    assert data["fields"] == ["depth", "uuid", "type", "name",
                              "type", "id", "name", "duration_s"]


def test_to_json_rows_encoded_with_depth(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "A"})
    manager.add_step(values={"name": "B"})
    data = manager.to_json()
    rows = data["rows"]
    # Three rows total: G (depth 0), A (depth 1), B (depth 0)
    assert len(rows) == 3
    depths = [r[0] for r in rows]
    assert depths == [0, 1, 0]
    names = [r[3] for r in rows]
    assert names == ["G", "A", "B"]


def test_to_json_empty_tree_has_zero_rows(manager):
    data = manager.to_json()
    assert data["rows"] == []
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_persistence.py -v"
```

Expected: AttributeError (`to_json`).

- [ ] **Step 3: Implement save**

Create `src/pluggable_protocol_tree/services/persistence.py`:

```python
"""Save and load the protocol tree as compact JSON.

Format:
  {
    "schema_version": 1,
    "columns": [{"id": ..., "cls": "module.ClassName"}, ...],
    "fields":  ["depth", "uuid", "type", "name", ...col_ids],
    "rows":    [[depth, uuid, type, name, *values], ...]
  }

Depth encodes tree nesting: each row becomes a child of the most recent
open row at depth-1 during reconstruction. Group membership is derived
from sequence + depth — no separate shape structure is stored.
"""

from typing import Iterator, List

from pluggable_protocol_tree.consts import PERSISTENCE_SCHEMA_VERSION
from pluggable_protocol_tree.models.row import BaseRow, GroupRow


def serialize_tree(root: GroupRow, columns: list) -> dict:
    """Build the full JSON dict for `root` using the given column set."""
    col_specs = [
        {
            "id": c.model.col_id,
            "cls": f"{type(c.model).__module__}.{type(c.model).__name__}",
        }
        for c in columns
    ]
    fields = ["depth", "uuid", "type", "name"] + [c["id"] for c in col_specs]

    rows_out = list(_walk_with_depth(root, columns, depth=0, skip_root=True))

    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "columns": col_specs,
        "fields": fields,
        "rows": rows_out,
    }


def _walk_with_depth(node, columns: list, depth: int, skip_root: bool) -> Iterator[list]:
    if not skip_root:
        vals = [depth, node.uuid, node.row_type, node.name]
        for col in columns:
            raw = col.model.get_value(node)
            vals.append(col.model.serialize(raw))
        yield vals
    if isinstance(node, GroupRow):
        for child in node.children:
            yield from _walk_with_depth(child, columns, depth + (0 if skip_root else 1),
                                         skip_root=False)
```

- [ ] **Step 4: Wire RowManager.to_json**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    # --- persistence ---

    def to_json(self) -> dict:
        from pluggable_protocol_tree.services.persistence import serialize_tree
        return serialize_tree(self.root, list(self.columns))
```

- [ ] **Step 5: Run tests**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_persistence.py -v"
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/persistence.py pluggable_protocol_tree/tests/test_persistence.py pluggable_protocol_tree/models/row_manager.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Persistence — save (to_json)

Compact JSON format: column class paths in metadata, rows as positional
tuples prefixed with their depth. Group membership is reconstructed
from depth on load. RowManager.to_json() delegates to services/persistence.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: Persistence — load (from_json)

**Files:**
- Modify: `src/pluggable_protocol_tree/services/persistence.py`
- Modify: `src/pluggable_protocol_tree/models/row_manager.py` (classmethod)
- Modify: `src/pluggable_protocol_tree/tests/test_persistence.py`

- [ ] **Step 1: Write failing tests**

Append to `src/pluggable_protocol_tree/tests/test_persistence.py`:

```python
# --- load ---

def test_round_trip_flat(manager):
    manager.add_step(values={"name": "A", "duration_s": 2.5})
    manager.add_step(values={"name": "B", "duration_s": 1.0})
    data = manager.to_json()
    new_manager = RowManager.from_json(data, columns=list(manager.columns))
    assert [c.name for c in new_manager.root.children] == ["A", "B"]
    assert new_manager.root.children[0].duration_s == 2.5


def test_round_trip_nested(manager):
    g = manager.add_group(name="Wash")
    manager.add_step(parent_path=g, values={"name": "Drop"})
    manager.add_step(parent_path=g, values={"name": "Off"})
    manager.add_step(values={"name": "Settle"})
    data = manager.to_json()
    nm = RowManager.from_json(data, columns=list(manager.columns))
    wash = nm.root.children[0]
    assert wash.name == "Wash"
    assert [c.name for c in wash.children] == ["Drop", "Off"]
    assert nm.root.children[1].name == "Settle"


def test_round_trip_preserves_uuids(manager):
    p = manager.add_step()
    original_uuid = manager.get_row(p).uuid
    data = manager.to_json()
    nm = RowManager.from_json(data, columns=list(manager.columns))
    assert nm.root.children[0].uuid == original_uuid


def test_from_json_missing_column_warns_and_skips(manager, caplog):
    """If the saved column set has an entry that's not in the live
    column set, the value is skipped (PPT-1 behavior) and a warning is
    logged. Full orphan preservation is deferred to a later PR."""
    data = manager.to_json()
    # Inject a fake column entry into the saved data
    data["columns"].append({
        "id": "fake", "cls": "nonexistent.module.FakeColumn",
    })
    # The row tuples also need a placeholder value per new column
    data["fields"].append("fake")
    for r in data["rows"]:
        r.append("ignored")
    # Load with live columns that don't include 'fake'
    nm = RowManager.from_json(data, columns=list(manager.columns))
    # Loader should have warned; no exception; row count preserved
    assert len(nm.root.children) == len(manager.root.children)
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_persistence.py -v -k 'round_trip or missing_column'"
```

Expected: AttributeError (`from_json`).

- [ ] **Step 3: Implement load**

Append to `src/pluggable_protocol_tree/services/persistence.py`:

```python
import importlib
import logging

logger = logging.getLogger(__name__)


def deserialize_tree(data: dict, columns: list, step_type, group_type) -> GroupRow:
    """Reconstruct a tree from a saved-JSON dict.

    Args:
        data: output of serialize_tree (possibly from another session).
        columns: live IColumn list to load values into.
        step_type: dynamic step subclass for this protocol.
        group_type: dynamic group subclass for this protocol.
    """
    live_by_col_id = {c.model.col_id: c for c in columns}
    col_specs: list = data["columns"]
    fields: list = data["fields"]

    # Per-saved-column resolution: (col_id, live_col_or_None)
    resolved: list = []
    for spec in col_specs:
        col_id = spec["id"]
        cls_path = spec["cls"]
        live = live_by_col_id.get(col_id)
        if live is None:
            # Try to import the class to distinguish orphan-present-but-unused
            # from missing-plugin — in PPT-1 we just warn in both cases.
            try:
                importlib.import_module(cls_path.rsplit(".", 1)[0])
                logger.warning(
                    "Column '%s' exists in save but not in live column set — "
                    "its values will be skipped.", col_id,
                )
            except ImportError:
                logger.warning(
                    "Column '%s' class '%s' could not be imported — "
                    "plugin missing? Values will be skipped.",
                    col_id, cls_path,
                )
        resolved.append((col_id, live))

    root = group_type(name="Root")
    stack: list = [root]

    first_value_idx = 4   # fields = depth, uuid, type, name, *col_ids
    for row_tuple in data["rows"]:
        depth = int(row_tuple[0])
        uuid_ = str(row_tuple[1])
        row_type = str(row_tuple[2])
        name = str(row_tuple[3])
        values = row_tuple[first_value_idx:]

        stack = stack[: depth + 1]   # trim to the right ancestor
        parent = stack[-1]

        row_cls = step_type if row_type == "step" else group_type
        row = row_cls(name=name, uuid=uuid_)

        for (col_id, live_col), raw in zip(resolved, values):
            if live_col is None:
                continue
            setattr(row, col_id, live_col.model.deserialize(raw))

        parent.add_row(row)

        if row_type == "group":
            stack.append(row)

    return root
```

- [ ] **Step 4: Wire RowManager.from_json**

Append to `src/pluggable_protocol_tree/models/row_manager.py`:

```python
    @classmethod
    def from_json(cls, data: dict, columns: list) -> "RowManager":
        from pluggable_protocol_tree.services.persistence import deserialize_tree
        # Construct an empty manager so we can use its step_type/group_type
        manager = cls(columns=columns)
        manager.root = deserialize_tree(
            data, columns, manager.step_type, manager.group_type,
        )
        return manager
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_persistence.py -v"
```

Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/services/persistence.py pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_persistence.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Persistence — load (from_json) with class resolution

Reconstructs the tree from the depth-encoded save format. Resolves each
saved column against the live column set by id (full class-path
resolution lands when we need cross-plugin contribution). Missing
columns log a warning and skip values. UUIDs round-trip.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: QAbstractItemModel adapter

**Files:**
- Create: `src/pluggable_protocol_tree/views/qt_tree_model.py`
- Create: `src/pluggable_protocol_tree/tests/test_qt_tree_model.py`

- [ ] **Step 1: Write failing tests**

Create `src/pluggable_protocol_tree/tests/test_qt_tree_model.py`:

```python
"""Smoke tests for the Qt tree model adapter.

Qt model tests don't need a QApplication for structural queries
(rowCount, columnCount, data for DisplayRole). Editor interactions
are exercised in the widget-level smoke test (Task 22)."""

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column


@pytest.fixture
def manager():
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]
    m = RowManager(columns=cols)
    return m


def test_column_count(manager):
    qm = MvcTreeModel(manager)
    assert qm.columnCount() == 4


def test_row_count_empty(manager):
    qm = MvcTreeModel(manager)
    assert qm.rowCount() == 0


def test_row_count_after_add(manager):
    manager.add_step()
    manager.add_step()
    qm = MvcTreeModel(manager)
    assert qm.rowCount() == 2


def test_display_role_renders_name_column(manager):
    from pyface.qt.QtCore import Qt
    manager.add_step(values={"name": "Hello"})
    qm = MvcTreeModel(manager)
    # Find the 'name' column index
    name_idx = [c.model.col_id for c in manager.columns].index("name")
    idx = qm.index(0, name_idx)
    assert qm.data(idx, Qt.DisplayRole) == "Hello"


def test_header_data(manager):
    from pyface.qt.QtCore import Qt
    qm = MvcTreeModel(manager)
    for col_idx, col in enumerate(manager.columns):
        assert qm.headerData(col_idx, Qt.Horizontal, Qt.DisplayRole) == col.model.col_name
```

- [ ] **Step 2: Run to verify failure**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_qt_tree_model.py -v"
```

Expected: ImportError.

- [ ] **Step 3: Implement the adapter**

Create `src/pluggable_protocol_tree/views/qt_tree_model.py`:

```python
"""QAbstractItemModel adapter binding RowManager to a QTreeView.

Reads column definitions from the RowManager's column list; delegates
display/edit to each column's view and handler. Signal emissions are
coarse (layoutChanged on structural mutations) in PPT-1; finer-grained
rowsInserted/dataChanged can be added when performance matters.
"""

from pyface.qt.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal
from pyface.qt.QtGui import QBrush, QColor

from pluggable_protocol_tree.models.row import GroupRow


class MvcTreeModel(QAbstractItemModel):
    """Qt tree model over a RowManager.

    An 'active' row (set via set_active_node) gets a light-green
    background via BackgroundRole — used in PPT-2 by the executor to
    highlight the running step. In PPT-1 this stays None.
    """

    structure_changed = Signal()   # high-level "redraw" nudge

    _ACTIVE_BG = QBrush(QColor(200, 255, 200))

    def __init__(self, row_manager, parent=None):
        super().__init__(parent)
        self._manager = row_manager
        self._active_node = None

        # Rebroadcast manager changes as layoutChanged
        row_manager.observe(self._on_rows_changed, "rows_changed")

    # ------------ Qt structural API ------------

    def rowCount(self, parent=QModelIndex()):
        node = parent.internalPointer() if parent.isValid() else self._manager.root
        return len(node.children) if isinstance(node, GroupRow) else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self._manager.columns)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = parent.internalPointer() if parent.isValid() else self._manager.root
        if row >= len(node.children):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        node = index.internalPointer()
        parent_node = node.parent
        if parent_node is None or parent_node is self._manager.root:
            return QModelIndex()
        grandparent = parent_node.parent
        row_in_grandparent = (grandparent.children.index(parent_node)
                              if grandparent is not None else 0)
        return self.createIndex(row_in_grandparent, 0, parent_node)

    # ------------ data / flags / header ------------

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        col = self._manager.columns[index.column()]

        if role == Qt.BackgroundRole and node is self._active_node:
            return self._ACTIVE_BG

        value = col.model.get_value(node)

        if role == Qt.DisplayRole:
            return col.view.format_display(value, node)
        if role == Qt.CheckStateRole:
            return col.view.get_check_state(value, node)
        if role == Qt.UserRole:
            return node
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        col = self._manager.columns[index.column()]
        node = index.internalPointer()
        if role in (Qt.EditRole, Qt.CheckStateRole):
            if role == Qt.CheckStateRole:
                value = value == Qt.Checked or value == 2 or value is True
            if col.handler.on_interact(node, col.model, value):
                self.dataChanged.emit(index, index, [role])
                return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        col = self._manager.columns[index.column()]
        return col.view.get_flags(index.internalPointer())

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._manager.columns[section].model.col_name
        return None

    # ------------ helpers ------------

    def set_active_node(self, node):
        self._active_node = node
        self.layoutChanged.emit()

    def _on_rows_changed(self, event):
        self.layoutChanged.emit()
        self.structure_changed.emit()
```

- [ ] **Step 4: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_qt_tree_model.py -v"
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/views/qt_tree_model.py pluggable_protocol_tree/tests/test_qt_tree_model.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] QAbstractItemModel adapter (MvcTreeModel)

Binds RowManager to a QTreeView. Reads column defs live from the
manager; delegates display/flags/edit to each column's view and
handler. Subscribes to rows_changed and rebroadcasts as layoutChanged
(coarse; fine-grained dataChanged only on explicit edits). An
_active_node hook paints a light-green background — used by the PPT-2
executor for step highlighting.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 21: QStyledItemDelegate for editors

**Files:**
- Create: `src/pluggable_protocol_tree/views/delegate.py`

- [ ] **Step 1: Implement the delegate directly (no unit test needed — exercised via smoke test in Task 22)**

Create `src/pluggable_protocol_tree/views/delegate.py`:

```python
"""Qt delegate that routes editor create/set/get through each column's view.

Pure forwarding — no state. Lives as its own file so the tree widget in
Task 22 can import it without circular dependencies."""

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QStyledItemDelegate


class ProtocolItemDelegate(QStyledItemDelegate):
    def __init__(self, row_manager, parent=None):
        super().__init__(parent)
        self._manager = row_manager

    def createEditor(self, parent, option, index):
        col = self._manager.columns[index.column()]
        return col.view.create_editor(parent, None)

    def setEditorData(self, editor, index):
        if editor is None:
            return
        col = self._manager.columns[index.column()]
        node = index.data(Qt.UserRole)
        col.view.set_editor_data(editor, col.model.get_value(node))

    def setModelData(self, editor, model, index):
        if editor is None:
            return
        col = self._manager.columns[index.column()]
        node = index.data(Qt.UserRole)
        value = col.view.get_editor_data(editor)
        if col.handler.on_interact(node, col.model, value):
            model.dataChanged.emit(index, index)
```

- [ ] **Step 2: Smoke-check import**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.views.delegate import ProtocolItemDelegate; print(ProtocolItemDelegate)'"
```

Expected: prints the class.

- [ ] **Step 3: Commit**

```bash
git add pluggable_protocol_tree/views/delegate.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] ProtocolItemDelegate — editor forwarding

Thin QStyledItemDelegate that routes createEditor/setEditorData/
setModelData through each column's view, with edits dispatched to
the column's handler. No state; no surprises.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 22: ProtocolTreeWidget with context menu

**Files:**
- Create: `src/pluggable_protocol_tree/views/tree_widget.py`

- [ ] **Step 1: Implement the widget**

Create `src/pluggable_protocol_tree/views/tree_widget.py`:

```python
"""Qt widget: QTreeView over a RowManager, with context menu for add /
remove / copy / cut / paste / group."""

from enum import Enum

from pyface.qt.QtCore import Qt, QPersistentModelIndex
from pyface.qt.QtWidgets import QWidget, QVBoxLayout, QTreeView, QMenu, QAbstractItemView

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.delegate import ProtocolItemDelegate
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


class ProtocolTreeWidget(QWidget):
    def __init__(self, row_manager: RowManager, parent=None):
        super().__init__(parent)
        self._manager = row_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeView()
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setEditTriggers(QAbstractItemView.DoubleClicked
                                  | QAbstractItemView.EditKeyPressed)
        layout.addWidget(self.tree)

        self.model = MvcTreeModel(row_manager, parent=self.tree)
        self.tree.setModel(self.model)

        self.delegate = ProtocolItemDelegate(row_manager, parent=self.tree)
        self.tree.setItemDelegate(self.delegate)

        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        # Keyboard shortcuts for copy/cut/paste
        from pyface.qt.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence.Copy, self, self._copy)
        QShortcut(QKeySequence.Cut, self, self._cut)
        QShortcut(QKeySequence.Paste, self, self._paste)
        QShortcut(QKeySequence.Delete, self, self._delete_selection)

        # Mirror Qt selection → RowManager selection
        self.tree.selectionModel().selectionChanged.connect(self._sync_selection)

    # --- selection sync ---

    def _sync_selection(self, *_):
        paths = []
        for idx in self.tree.selectionModel().selectedRows(0):
            paths.append(self._index_to_path(idx))
        self._manager.select(paths, mode="set")

    def _index_to_path(self, index):
        if not index.isValid():
            return ()
        parts = []
        cur = index
        while cur.isValid():
            parts.insert(0, cur.row())
            cur = cur.parent()
        return tuple(parts)

    # --- context menu actions ---

    def _on_context_menu(self, pos):
        idx = self.tree.indexAt(pos)
        menu = QMenu()
        menu.addAction("Add Step", lambda: self._add_step_at(idx))
        menu.addAction("Add Group", lambda: self._add_group_at(idx))
        menu.addSeparator()
        menu.addAction("Copy", self._copy)
        menu.addAction("Cut", self._cut)
        menu.addAction("Paste", self._paste)
        menu.addSeparator()
        menu.addAction("Delete", self._delete_selection)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _add_step_at(self, idx):
        parent_path = self._parent_path_for_anchor(idx)
        self._manager.add_step(parent_path=parent_path)

    def _add_group_at(self, idx):
        parent_path = self._parent_path_for_anchor(idx)
        self._manager.add_group(parent_path=parent_path)

    def _parent_path_for_anchor(self, idx):
        """If anchored on a group → insert inside. On a step → insert as
        sibling. No anchor → root."""
        if not idx.isValid():
            return ()
        from pluggable_protocol_tree.models.row import GroupRow
        node = idx.internalPointer()
        if isinstance(node, GroupRow):
            return self._index_to_path(idx)
        # sibling: parent path
        path = self._index_to_path(idx)
        return path[:-1]

    def _copy(self):
        self._manager.copy()

    def _cut(self):
        self._manager.cut()

    def _paste(self):
        # Use current anchor as target
        idxs = self.tree.selectionModel().selectedRows(0)
        target = self._index_to_path(idxs[-1]) if idxs else None
        self._manager.paste(target_path=target)

    def _delete_selection(self):
        self._manager.remove(list(self._manager.selection))
```

- [ ] **Step 2: Smoke-test import**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && python -c 'from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget; print(ProtocolTreeWidget)'"
```

Expected: prints the class.

- [ ] **Step 3: Commit**

```bash
git add pluggable_protocol_tree/views/tree_widget.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] ProtocolTreeWidget — QTreeView with context menu + shortcuts

Single-widget view: QTreeView over MvcTreeModel, ProtocolItemDelegate
for editors, right-click menu (Add Step / Add Group / Copy / Cut /
Paste / Delete), and keyboard shortcuts (Ctrl+C/X/V/Del). Qt selection
is mirrored into the RowManager so copy/paste operate on the GUI
selection.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 23: Envisage dock pane and plugin

**Files:**
- Create: `src/pluggable_protocol_tree/views/dock_pane.py`
- Create: `src/pluggable_protocol_tree/plugin.py`
- Create: `src/pluggable_protocol_tree/tests/test_plugin.py`

- [ ] **Step 1: Write failing tests for plugin shape**

Create `src/pluggable_protocol_tree/tests/test_plugin.py`:

```python
"""Minimal plugin smoke tests — verify the extension point is registered."""

from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS


def test_plugin_id():
    p = PluggableProtocolTreePlugin()
    assert p.id.startswith("pluggable_protocol_tree")


def test_plugin_declares_extension_point():
    p = PluggableProtocolTreePlugin()
    point_ids = [ep.id for ep in p.get_extension_points()]
    assert PROTOCOL_COLUMNS in point_ids
```

- [ ] **Step 2: Run to verify failures**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_plugin.py -v"
```

Expected: ImportError.

- [ ] **Step 3: Implement the dock pane**

Create `src/pluggable_protocol_tree/views/dock_pane.py`:

```python
"""Pyface TaskPane hosting ProtocolTreeWidget.

Receives its column set from the plugin on construction."""

from pyface.tasks.api import TraitsDockPane
from traits.api import Instance, List, Str

from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models.row_manager import RowManager


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = "Protocol"

    columns = List(Instance(IColumn))
    manager = Instance(RowManager)

    def create_contents(self, parent):
        from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget
        self.manager = RowManager(columns=self.columns)
        return ProtocolTreeWidget(self.manager, parent=parent)
```

- [ ] **Step 4: Implement the plugin**

Create `src/pluggable_protocol_tree/plugin.py`:

```python
"""Envisage plugin wiring for the pluggable protocol tree.

Registers the PROTOCOL_COLUMNS extension point; contributes a dock
pane via TASK_EXTENSIONS. Other plugins contribute IColumn instances
by declaring `List(contributes_to=PROTOCOL_COLUMNS)` in their own
plugin class."""

from envisage.api import ExtensionPoint, Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.task_extension import TaskExtension
from traits.api import Instance, List, Str

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ACTOR_TOPIC_DICT, PKG, PKG_name, PROTOCOL_COLUMNS,
)
from pluggable_protocol_tree.interfaces.i_column import IColumn


class PluggableProtocolTreePlugin(Plugin):
    id = f"{PKG}.plugin"
    name = PKG_name

    #: Other plugins contribute IColumn instances here
    contributed_columns = ExtensionPoint(
        List(Instance(IColumn)), id=PROTOCOL_COLUMNS,
        desc="Columns contributed by other plugins",
    )

    # Standard plumbing
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self._make_dock_pane],
            ),
        ]

    def _make_dock_pane(self, *args, **kwargs):
        from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane
        columns = self._assemble_columns()
        return PluggableProtocolDockPane(columns=columns, *args, **kwargs)

    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
        return builtins + list(self.contributed_columns)
```

- [ ] **Step 5: Run tests and verify they pass**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_plugin.py -v"
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/views/dock_pane.py pluggable_protocol_tree/plugin.py pluggable_protocol_tree/tests/test_plugin.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Envisage plugin + dock pane

PluggableProtocolTreePlugin registers the PROTOCOL_COLUMNS extension
point for column contributions from other plugins and ships a dock
pane factory. _assemble_columns merges the four builtins (type/id/
name/duration) with contributed columns in extension order. Dock pane
constructs a fresh RowManager and ProtocolTreeWidget.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 24: Demo run script

**Files:**
- Create: `src/pluggable_protocol_tree/demos/run_widget.py`

- [ ] **Step 1: Implement the demo**

Create `src/pluggable_protocol_tree/demos/run_widget.py`:

```python
"""Standalone demo — open ProtocolTreeWidget in a QMainWindow.

No envisage, no dramatiq, no hardware. Smoke-tests the whole data
path: add/remove/move rows, edit cells, select, copy/cut/paste,
save/load (save uses a file dialog).

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget
"""

import json
import sys

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QToolBar,
)

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


def _columns():
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_duration_column(),
    ]


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pluggable Protocol Tree — Demo")
        self.resize(900, 600)

        self.manager = RowManager(columns=_columns())
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.setCentralWidget(self.widget)

        tb = QToolBar("File")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())
        tb.addAction("Add Group", lambda: self.manager.add_group())
        tb.addSeparator()
        tb.addAction("Save…", self._save)
        tb.addAction("Load…", self._load)

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.manager.to_json(), f, indent=2)

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        try:
            self.manager = RowManager.from_json(data, columns=_columns())
        except Exception as e:
            QMessageBox.critical(self, "Load error", str(e))
            return
        self.widget = ProtocolTreeWidget(self.manager, parent=self)
        self.setCentralWidget(self.widget)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the demo briefly to verify it opens**

Run with a short timeout (macro-smoke test; the user closes the window):

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && timeout 5 python -m pluggable_protocol_tree.demos.run_widget || true"
```

Expected: the window opens; after 5s timeout kills it, no crash traceback printed. On Windows, `timeout 5 python ...` under `bash` via pixi should still behave; if not, verify by running without `timeout` and closing the window manually.

- [ ] **Step 3: Add a small interactive test script**

Create `src/pluggable_protocol_tree/tests/test_end_to_end.py`:

```python
"""End-to-end smoke test.

Headless test that exercises the full stack: create a manager, add
groups and steps via the manager, verify the QAbstractItemModel
reflects them, save to JSON, load back, confirm identical tree shape.
Does not require pytest-qt — a QCoreApplication is sufficient for the
tree model's structural queries."""

import json

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column


def _cols():
    return [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]


def test_full_round_trip():
    m = RowManager(columns=_cols())
    g = m.add_group(name="Wash")
    m.add_step(parent_path=g, values={"name": "Drop", "duration_s": 2.0})
    m.add_step(parent_path=g, values={"name": "Off", "duration_s": 1.5})
    m.add_step(values={"name": "Settle", "duration_s": 5.0})

    qm = MvcTreeModel(m)
    assert qm.rowCount() == 2   # top-level: Wash + Settle

    data = m.to_json()
    serialized = json.dumps(data)

    data_back = json.loads(serialized)
    m2 = RowManager.from_json(data_back, columns=_cols())
    qm2 = MvcTreeModel(m2)
    assert qm2.rowCount() == 2

    wash = m2.root.children[0]
    assert wash.name == "Wash"
    assert [c.name for c in wash.children] == ["Drop", "Off"]
    assert [c.duration_s for c in wash.children] == [2.0, 1.5]
    assert m2.root.children[1].name == "Settle"
```

- [ ] **Step 4: Run the end-to-end test**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/test_end_to_end.py -v"
```

Expected: 1 passed.

- [ ] **Step 5: Run the full test suite one more time**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ -v"
```

Expected: every test green. Count roughly: interfaces 3, row 14, column 8, views ~20, builtins 13, row_manager 34, persistence 9, qt_tree_model 5, plugin 2, end_to_end 1 → ~109 tests.

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/demos/run_widget.py pluggable_protocol_tree/tests/test_end_to_end.py && \
  git commit -m "$(cat <<'EOF'
[PPT-1] Demo run script + end-to-end round-trip test

demos/run_widget.py opens a QMainWindow with ProtocolTreeWidget and a
toolbar for save/load. Headless end-to-end test exercises the whole
stack: manager → QAbstractItemModel → JSON → load → back to manager.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 25: Final verification + push + PR

**Files:** none (git/gh only)

- [ ] **Step 1: Verify clean git state**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git status
```

Expected: "nothing to commit, working tree clean" — aside from the pre-existing `protocol_grid/preferences.py` modification that was there at plan start (leave it alone).

- [ ] **Step 2: Run full tests one more time**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run bash -c "cd src && pytest pluggable_protocol_tree/tests/ -v"
```

Expected: all green.

- [ ] **Step 3: Open the demo and verify by hand**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && pixi run python -m pluggable_protocol_tree.demos.run_widget
```

Manual checks (then close the window):
- Right-click → Add Step; double-click the Name cell, type, Enter. Value persists.
- Right-click → Add Group; expand; Add Step inside.
- Select multiple rows (Ctrl/Shift-click); Ctrl+C; Ctrl+V → duplicates appear with new IDs.
- Edit Duration — spinbox appears; change; Enter.
- Save to a file; File → Load → same tree comes back.

- [ ] **Step 4: Push the branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src" && git push -u origin feat/ppt-1-core-skeleton
```

- [ ] **Step 5: Open the PR**

Replace `<PPT_1_ISSUE_NUMBER>` with the sub-issue number created in Task 0 Step 2:

```bash
gh pr create \
  --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "[PPT-1] Core skeleton: interfaces, BaseRow/GroupRow, RowManager" \
  --body "$(cat <<'EOF'
Closes #<PPT_1_ISSUE_NUMBER>

## Summary

Ships the core skeleton of the pluggable protocol tree plugin:

- **Interfaces**: `IColumn`, `IColumnModel`, `IColumnView`, `IColumnHandler`; `IRow`, `IGroupRow`.
- **Row model**: `BaseRow` + `GroupRow` (uuid, name, parent, row_type, derived path); `build_row_type()` composes a fresh HasTraits subclass from the active column set.
- **Column abstraction**: `BaseColumnModel` / `BaseColumnHandler` / `Column` composite, five view types (StringEdit, IntSpinBox, DoubleSpinBox, Checkbox, ReadOnlyLabel).
- **Built-in columns**: `type`, `id` (1-indexed dotted path), `name`, `duration_s`.
- **RowManager**: structure (add/remove/move), selection via paths, clipboard via QClipboard JSON, pandas-backed slicing facade, `iter_execution_steps` with repetitions expansion contract, imperative bulk write.
- **Persistence**: compact depth-encoded JSON with column class paths; orphan columns logged + skipped.
- **Qt view**: `MvcTreeModel` + `ProtocolItemDelegate` + `ProtocolTreeWidget` with context menu and keyboard shortcuts.
- **Envisage plugin** with `PROTOCOL_COLUMNS` extension point + dock pane.
- **Demo**: `demos/run_widget.py` opens a standalone QMainWindow.

## Test plan

- [x] `pytest pluggable_protocol_tree/tests/ -v` — all green (~109 tests).
- [x] Manual demo verification: add/remove/move rows, edit cells, copy/paste, save/load round-trip.
- [x] Plugin extension point registered — verified by test_plugin::test_plugin_declares_extension_point.

## Not in scope (see follow-ups)

- Executor + `ctx.wait_for` → PPT-2
- Electrode + Routes columns + device-viewer binding → PPT-3
- Voltage/Frequency columns → PPT-4
- Migration of remaining `protocol_grid` features → PPT-5..8
- Removal of legacy plugin → PPT-9

Design doc: `src/docs/superpowers/specs/2026-04-21-pluggable-protocol-tree-design.md`.
Plan: `src/docs/superpowers/plans/2026-04-21-ppt-1-core-skeleton.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Confirm PR opens cleanly**

Copy the PR URL the command prints. Visit in browser; verify description and the `Closes #<PPT_1_ISSUE_NUMBER>` link. The umbrella issue's checklist should tick automatically once the PR is merged.

---

## Done

All PPT-1 work is merged-ready. Subsequent PRs (PPT-2..9) each get their own plan written as we reach them, following the same bite-sized-task structure.
