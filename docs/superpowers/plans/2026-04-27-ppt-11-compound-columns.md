# PPT-11 Compound Column Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `CompoundColumn` framework parallel to today's single-cell `IColumn` so a single plugin contribution can declare N coupled cells sharing one model + one handler. Verified end-to-end with a synthetic demo column.

**Architecture:** New `ICompoundColumn` interface + `CompoundColumn` composite live alongside `IColumn`. `_assemble_columns()` expands compound contributions into N synthesized per-cell `Column` instances (via thin `_CompoundFieldAdapter` + `_CompoundFieldHandlerAdapter` shims) so RowManager, executor, MvcTreeModel, and persistence keep speaking `Column` / `IColumnModel` unchanged. JSON persistence uses a flat schema with `compound_id` discriminator.

**Tech Stack:** Python 3.x, Traits/HasTraits, PySide6/Qt for views, pytest, no Redis/dramatiq concerns (this is a UI/model framework feature).

**Spec:** `src/docs/superpowers/specs/2026-04-27-ppt-11-compound-columns-design.md`

**Branch:** `feat/ppt-11-compound-columns` (already created from main).

**Test runner:** `pixi run pytest …` from outer repo root `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py`.

---

## Task 1: Interfaces — `ICompoundColumn` family + `FieldSpec`

**Files:**
- Create: `src/pluggable_protocol_tree/interfaces/i_compound_column.py`
- Create: `src/pluggable_protocol_tree/tests/test_compound_interfaces.py`

**Why:** Lay down the four parallel interfaces (`ICompoundColumnModel`, `ICompoundColumnView`, `ICompoundColumnHandler`, `ICompoundColumn`) plus the `FieldSpec` named tuple. No behavior — just contracts. Smoke-test that they import cleanly.

- [ ] **Step 1: Write the failing test**

```python
# src/pluggable_protocol_tree/tests/test_compound_interfaces.py
"""Smoke tests for the ICompoundColumn family — confirms the module
imports and the four interfaces + FieldSpec can be referenced."""

def test_interfaces_importable():
    from pluggable_protocol_tree.interfaces.i_compound_column import (
        FieldSpec, ICompoundColumn, ICompoundColumnHandler,
        ICompoundColumnModel, ICompoundColumnView,
    )
    assert FieldSpec._fields == ("field_id", "col_name", "default_value")


def test_field_spec_construction():
    from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
    spec = FieldSpec(field_id="foo", col_name="Foo", default_value=42)
    assert spec.field_id == "foo"
    assert spec.col_name == "Foo"
    assert spec.default_value == 42
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_interfaces.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.interfaces.i_compound_column'`.

- [ ] **Step 3: Implement the interfaces**

Create `src/pluggable_protocol_tree/interfaces/i_compound_column.py`:

```python
"""Interfaces for the compound column framework.

A compound column contributes N coupled cells that share one model +
one handler. Parallel to IColumn (does NOT extend it). Tree assembly
expands a compound contribution into N synthesized per-cell Column
instances at runtime; downstream consumers (RowManager, executor,
persistence, MvcTreeModel) keep speaking Column / IColumnModel.
"""

from typing import NamedTuple

from traits.api import Instance, Int, Interface, List, Str

from .i_column import IColumnView


class FieldSpec(NamedTuple):
    """One field of a compound column."""
    field_id: str        # row attribute name AND col_id of the rendered cell
    col_name: str        # column header label
    default_value: object   # applied at row construction


class ICompoundColumnModel(Interface):
    """Model owning N coupled fields. Each field becomes a row trait
    AND a visible cell. The handler sees all field values."""

    base_id = Str(desc="Logical name for the compound — appears in JSON "
                       "as 'compound_id' on each field's column entry.")

    def field_specs(self):
        """Returns ordered list[FieldSpec] of fields this compound contributes."""

    def trait_for_field(self, field_id):
        """Return the Traits TraitType for the given field. Same role as
        IColumnModel.trait_for_row but per-field."""

    def get_value(self, row, field_id): ...
    def set_value(self, row, field_id, value): ...
    def serialize(self, field_id, value): ...
    def deserialize(self, field_id, raw): ...


class ICompoundColumnView(Interface):
    """N per-cell views, one per field."""
    def cell_view_for_field(self, field_id):
        """Return the IColumnView for the given field."""


class ICompoundColumnHandler(Interface):
    """Five execution hooks (same as IColumnHandler) plus field-aware on_interact."""
    priority = Int(50)
    wait_for_topics = List(Str)

    def on_interact(self, row, model, field_id, value):
        """Default: model.set_value(row, field_id, value)."""

    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


class ICompoundColumn(Interface):
    """Composition of model + view + handler."""
    model = Instance(ICompoundColumnModel)
    view = Instance(ICompoundColumnView)
    handler = Instance(ICompoundColumnHandler)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_interfaces.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/interfaces/i_compound_column.py pluggable_protocol_tree/tests/test_compound_interfaces.py
git -C src commit -m "[PPT-11] Add ICompoundColumn family + FieldSpec"
```

---

## Task 2: Base classes + `CompoundColumn` composite

**Files:**
- Create: `src/pluggable_protocol_tree/models/compound_column.py`
- Create: `src/pluggable_protocol_tree/tests/test_compound_column.py`

**Why:** Implement `BaseCompoundColumnModel`, `BaseCompoundColumnHandler`, `BaseCompoundColumnView`, `DictCompoundColumnView`, and the `CompoundColumn` composite. Mirrors `models/column.py`'s `BaseColumnModel` / `BaseColumnHandler` / `Column` patterns. Verifies identity defaults, set_value/get_value, traits_init wiring (handler.model = compound_model).

- [ ] **Step 1: Write the failing test**

```python
# src/pluggable_protocol_tree/tests/test_compound_column.py
"""Tests for the compound column base classes + CompoundColumn composite."""

import pytest
from traits.api import Bool, HasTraits, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel,
    BaseCompoundColumnView, CompoundColumn, DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [
            FieldSpec("ec_enabled", "Enabled", False),
            FieldSpec("ec_count",   "Count",   0),
        ]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def test_base_model_serialize_deserialize_identity():
    m = _DemoModel()
    assert m.serialize("ec_enabled", True) is True
    assert m.deserialize("ec_count", 42) == 42


def test_base_model_get_set_value_via_attribute():
    m = _DemoModel()
    class Row(HasTraits):
        ec_enabled = Bool(False)
    r = Row()
    assert m.get_value(r, "ec_enabled") is False
    assert m.set_value(r, "ec_enabled", True) is True
    assert r.ec_enabled is True


def test_base_handler_on_interact_writes_through_to_model():
    m = _DemoModel()
    h = BaseCompoundColumnHandler()
    h.model = m
    class Row(HasTraits):
        ec_count = Int(0)
    r = Row()
    h.on_interact(r, m, "ec_count", 7)
    assert r.ec_count == 7


def test_dict_compound_column_view_lookup():
    cb = CheckboxColumnView()
    sb = IntSpinBoxColumnView(low=0, high=999)
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": cb,
        "ec_count": sb,
    })
    assert v.cell_view_for_field("ec_enabled") is cb
    assert v.cell_view_for_field("ec_count") is sb


def test_dict_compound_column_view_unknown_field_raises():
    v = DictCompoundColumnView(cell_views={})
    with pytest.raises(KeyError):
        v.cell_view_for_field("missing")


def test_compound_column_traits_init_wires_handler_model():
    """CompoundColumn.traits_init injects the model into the handler."""
    m = _DemoModel()
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": CheckboxColumnView(),
        "ec_count": IntSpinBoxColumnView(low=0, high=999),
    })
    h = BaseCompoundColumnHandler()
    cc = CompoundColumn(model=m, view=v, handler=h)
    assert cc.handler.model is m


def test_compound_column_default_handler_when_none_provided():
    """If handler is omitted, traits_init substitutes BaseCompoundColumnHandler."""
    m = _DemoModel()
    v = DictCompoundColumnView(cell_views={
        "ec_enabled": CheckboxColumnView(),
        "ec_count": IntSpinBoxColumnView(low=0, high=999),
    })
    cc = CompoundColumn(model=m, view=v)
    assert isinstance(cc.handler, BaseCompoundColumnHandler)
    assert cc.handler.model is m
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_column.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.models.compound_column'`.

- [ ] **Step 3: Implement the base classes**

Create `src/pluggable_protocol_tree/models/compound_column.py`:

```python
"""Base classes + composite for compound columns. Mirrors the structure
of models/column.py for single-cell columns. See spec section 2."""

from traits.api import Dict, HasTraits, Instance, Int, List, Str, provides

from ..interfaces.i_column import IColumnView
from ..interfaces.i_compound_column import (
    FieldSpec, ICompoundColumn, ICompoundColumnHandler,
    ICompoundColumnModel, ICompoundColumnView,
)


@provides(ICompoundColumnModel)
class BaseCompoundColumnModel(HasTraits):
    base_id = Str(desc="Logical compound name; persistence discriminator.")

    def field_specs(self) -> list[FieldSpec]:
        return []

    def trait_for_field(self, field_id):
        raise NotImplementedError(
            f"{type(self).__name__}.trait_for_field({field_id!r}) must be overridden"
        )

    def get_value(self, row, field_id):
        return getattr(row, field_id, None)

    def set_value(self, row, field_id, value):
        setattr(row, field_id, value)
        return True

    def serialize(self, field_id, value):
        return value

    def deserialize(self, field_id, raw):
        return raw


@provides(ICompoundColumnView)
class BaseCompoundColumnView(HasTraits):
    """Subclass and override cell_view_for_field, OR use DictCompoundColumnView
    for a static field_id → view dict."""

    def cell_view_for_field(self, field_id) -> IColumnView:
        raise NotImplementedError


class DictCompoundColumnView(BaseCompoundColumnView):
    """Cell views indexed by field_id. Raises KeyError for unknown fields."""
    cell_views = Dict(Str, Instance(IColumnView))

    def cell_view_for_field(self, field_id):
        return self.cell_views[field_id]


@provides(ICompoundColumnHandler)
class BaseCompoundColumnHandler(HasTraits):
    priority = Int(50)
    wait_for_topics = List(Str)
    model = Instance(ICompoundColumnModel)

    def on_interact(self, row, model, field_id, value):
        return model.set_value(row, field_id, value)

    def on_protocol_start(self, ctx): pass
    def on_pre_step(self, row, ctx): pass
    def on_step(self, row, ctx): pass
    def on_post_step(self, row, ctx): pass
    def on_protocol_end(self, ctx): pass


@provides(ICompoundColumn)
class CompoundColumn(HasTraits):
    """Composite. Auto-substitutes BaseCompoundColumnHandler if the
    handler kwarg is omitted; auto-wires handler.model = model."""
    model = Instance(ICompoundColumnModel)
    view = Instance(ICompoundColumnView)
    handler = Instance(ICompoundColumnHandler)

    def traits_init(self):
        if self.handler is None:
            self.handler = BaseCompoundColumnHandler()
        self.handler.model = self.model
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_column.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/models/compound_column.py pluggable_protocol_tree/tests/test_compound_column.py
git -C src commit -m "[PPT-11] Add BaseCompoundColumn* classes + CompoundColumn composite"
```

---

## Task 3: `_CompoundFieldAdapter` + `_CompoundFieldHandlerAdapter`

**Files:**
- Create: `src/pluggable_protocol_tree/models/_compound_adapters.py`
- Create: `src/pluggable_protocol_tree/tests/test_compound_adapters.py`

**Why:** The shim that lets every downstream consumer keep speaking single-cell `Column` / `IColumnModel` while the real model + handler are shared across N synthesized per-cell columns. The `is_owner` flag ensures execution hooks fire exactly once per row, not N times.

- [ ] **Step 1: Write the failing test**

```python
# src/pluggable_protocol_tree/tests/test_compound_adapters.py
"""Tests for the compound→single-cell adapter shims used by _assemble_columns."""

from unittest.mock import MagicMock

from traits.api import Bool, HasTraits, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models._compound_adapters import (
    _CompoundFieldAdapter, _CompoundFieldHandlerAdapter,
)
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel,
)


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def test_field_adapter_proxies_to_compound_model():
    m = _DemoModel()
    a = _CompoundFieldAdapter(
        col_id="ec_count", col_name="Count", default_value=0,
        compound_model=m, field_id="ec_count",
        compound_base_id="demo", is_owner=False,
    )
    class Row(HasTraits):
        ec_count = Int(5)
    r = Row()
    assert a.get_value(r) == 5
    a.set_value(r, 9)
    assert r.ec_count == 9
    assert a.serialize(7) == 7
    assert a.deserialize(7) == 7


def test_field_adapter_trait_for_row_proxies_to_compound_model():
    m = _DemoModel()
    a = _CompoundFieldAdapter(
        col_id="ec_enabled", col_name="Enabled", default_value=False,
        compound_model=m, field_id="ec_enabled",
        compound_base_id="demo", is_owner=True,
    )
    trait = a.trait_for_row()
    # Trait should be the same shape as compound_model.trait_for_field returns:
    class Row(HasTraits):
        ec_enabled = trait
    r = Row()
    assert r.ec_enabled is False


def test_handler_adapter_on_interact_calls_compound_with_field_id():
    """Single-cell on_interact(row, model, value) translates to
    compound on_interact(row, compound_model, field_id, value)."""
    m = _DemoModel()
    h = MagicMock(spec=BaseCompoundColumnHandler)
    h.on_interact.return_value = True
    a = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_count",
        is_owner=False, priority=20, wait_for_topics=[],
    )
    class Row(HasTraits):
        ec_count = Int(0)
    r = Row()
    result = a.on_interact(r, a.model_for_setdata(), 11)
    h.on_interact.assert_called_once_with(r, m, "ec_count", 11)
    assert result is True


def test_handler_adapter_owner_field_fires_on_step_once():
    m = _DemoModel()
    h = MagicMock(spec=BaseCompoundColumnHandler)
    owner = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_enabled",
        is_owner=True, priority=20, wait_for_topics=[],
    )
    follower = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_count",
        is_owner=False, priority=20, wait_for_topics=[],
    )
    row = object()
    ctx = object()
    owner.on_step(row, ctx)
    follower.on_step(row, ctx)
    h.on_step.assert_called_once_with(row, ctx)


def test_handler_adapter_mirrors_priority_and_wait_for_topics():
    """Adapter must report the compound's priority + wait_for_topics
    (used by _assemble_columns aggregation for executor subscriptions)."""
    m = _DemoModel()
    h = BaseCompoundColumnHandler()
    h.priority = 35
    h.wait_for_topics = ["t/applied"]
    a = _CompoundFieldHandlerAdapter(
        compound_handler=h, compound_model=m, field_id="ec_count",
        is_owner=False, priority=35, wait_for_topics=["t/applied"],
    )
    assert a.priority == 35
    assert a.wait_for_topics == ["t/applied"]
```

(`a.model_for_setdata()` is just a placeholder — `setData` passes whatever `col.model` is, which is the adapter itself; the test argument is ignored by the adapter. Keep the call signature true to `MvcTreeModel.setData`.)

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_adapters.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the adapters**

Create `src/pluggable_protocol_tree/models/_compound_adapters.py`:

```python
"""Internal: adapter shims that present a compound column's per-field
state as single-cell Column components. Used by _assemble_columns
expansion. Not part of the public API — callers should never construct
these directly; build a CompoundColumn and let _assemble_columns expand it.
"""

from traits.api import Bool, Instance, Str

from ..interfaces.i_compound_column import (
    ICompoundColumnHandler, ICompoundColumnModel,
)
from .column import BaseColumnHandler, BaseColumnModel


class _CompoundFieldAdapter(BaseColumnModel):
    """Single-cell IColumnModel facade for one field of a compound model.

    col_id, col_name, default_value are inherited Trait attributes from
    BaseColumnModel — set them at construction. By convention
    field_id == col_id (could differ but no reason to).
    compound_base_id is cached at construction so persistence doesn't
    need to round-trip through compound_model.base_id at serialize time.
    """
    compound_model = Instance(ICompoundColumnModel)
    field_id = Str
    is_owner = Bool(False)
    compound_base_id = Str

    def trait_for_row(self):
        return self.compound_model.trait_for_field(self.field_id)

    def get_value(self, row):
        return self.compound_model.get_value(row, self.field_id)

    def set_value(self, row, value):
        return self.compound_model.set_value(row, self.field_id, value)

    def serialize(self, value):
        return self.compound_model.serialize(self.field_id, value)

    def deserialize(self, raw):
        return self.compound_model.deserialize(self.field_id, raw)


class _CompoundFieldHandlerAdapter(BaseColumnHandler):
    """Single-cell IColumnHandler facade. on_interact translates the
    single-field call into the compound handler's field-aware call.
    Execution hooks fire only on the OWNER field (is_owner=True) so the
    compound's on_step / on_pre_step / etc. run exactly once per row,
    not N times.

    priority and wait_for_topics are mirrored from the compound handler
    at construction time so the executor's subscription aggregation in
    PluggableProtocolTreePlugin.start() picks up the right topics.
    """
    compound_handler = Instance(ICompoundColumnHandler)
    compound_model = Instance(ICompoundColumnModel)
    field_id = Str
    is_owner = Bool(False)

    def on_interact(self, row, model, value):
        # `model` is the per-field _CompoundFieldAdapter (passed in by
        # MvcTreeModel.setData via col.model). Ignore it — pass the real
        # compound_model to the compound handler so it sees its own model
        # type instead of the adapter wrapper.
        return self.compound_handler.on_interact(
            row, self.compound_model, self.field_id, value,
        )

    def on_protocol_start(self, ctx):
        if self.is_owner:
            self.compound_handler.on_protocol_start(ctx)

    def on_pre_step(self, row, ctx):
        if self.is_owner:
            self.compound_handler.on_pre_step(row, ctx)

    def on_step(self, row, ctx):
        if self.is_owner:
            self.compound_handler.on_step(row, ctx)

    def on_post_step(self, row, ctx):
        if self.is_owner:
            self.compound_handler.on_post_step(row, ctx)

    def on_protocol_end(self, ctx):
        if self.is_owner:
            self.compound_handler.on_protocol_end(ctx)
```

Now adjust the test — `a.model_for_setdata()` was a sketch placeholder. Replace it in `test_handler_adapter_on_interact_calls_compound_with_field_id` with just `None` (or a sentinel) since the adapter ignores the arg:

```python
    result = a.on_interact(r, None, 11)   # second arg ignored
    h.on_interact.assert_called_once_with(r, m, "ec_count", 11)
    assert result is True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_adapters.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/models/_compound_adapters.py pluggable_protocol_tree/tests/test_compound_adapters.py
git -C src commit -m "[PPT-11] Add _CompoundFieldAdapter + _CompoundFieldHandlerAdapter shims"
```

---

## Task 4: `_assemble_columns` expansion

**Files:**
- Modify: `src/pluggable_protocol_tree/plugin.py` (extend `_assemble_columns`)
- Create: `src/pluggable_protocol_tree/tests/test_compound_assembly.py`

**Why:** This is the seam that makes compounds invisible to every downstream consumer. After this, RowManager / executor / MvcTreeModel / persistence all see flat `Column` instances even when the contribution was a `CompoundColumn`.

- [ ] **Step 1: Write the failing test**

```python
# src/pluggable_protocol_tree/tests/test_compound_assembly.py
"""Tests for _assemble_columns expansion of compound contributions."""

from traits.api import Bool, Int
from unittest.mock import MagicMock, patch

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models._compound_adapters import (
    _CompoundFieldAdapter, _CompoundFieldHandlerAdapter,
)
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class _TwoFieldModel(BaseCompoundColumnModel):
    base_id = "two_field"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def _make_compound():
    return CompoundColumn(
        model=_TwoFieldModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )


def test_assemble_expands_compound_into_n_columns():
    """A two-field CompoundColumn contribution yields exactly 2 entries
    in _assemble_columns output, with col_id == field_id for each."""
    p = PluggableProtocolTreePlugin()
    p.contributed_columns = [_make_compound()]
    cols = p._assemble_columns()
    ids = [c.model.col_id for c in cols]
    assert "ec_enabled" in ids
    assert "ec_count" in ids
    assert ids.index("ec_enabled") + 1 == ids.index("ec_count"), (
        "compound fields must be adjacent in declaration order"
    )


def test_assemble_compound_columns_share_compound_model_and_handler():
    """All synthesized columns from one compound must share the same
    underlying compound model + handler instances (so on_step sees all
    fields and prefs round-trips work)."""
    p = PluggableProtocolTreePlugin()
    cc = _make_compound()
    p.contributed_columns = [cc]
    cols = [c for c in p._assemble_columns()
            if isinstance(c.model, _CompoundFieldAdapter)]
    assert len(cols) == 2
    assert cols[0].model.compound_model is cc.model
    assert cols[1].model.compound_model is cc.model
    assert cols[0].handler.compound_handler is cc.handler
    assert cols[1].handler.compound_handler is cc.handler


def test_assemble_first_compound_field_is_owner_others_are_not():
    """Only the first field's handler adapter has is_owner=True;
    follower fields are is_owner=False (so on_step fires once per row)."""
    p = PluggableProtocolTreePlugin()
    p.contributed_columns = [_make_compound()]
    adapters = [c.handler for c in p._assemble_columns()
                if isinstance(c.handler, _CompoundFieldHandlerAdapter)]
    assert adapters[0].is_owner is True
    assert all(a.is_owner is False for a in adapters[1:])


def test_assemble_mixed_contribution_simple_and_compound_both_render():
    """Mixed contributions: one simple Column + one CompoundColumn.
    Both should appear in the assembled list (compound expanded inline)."""
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    p = PluggableProtocolTreePlugin()
    simple = make_repetitions_column()
    p.contributed_columns = [simple, _make_compound()]
    ids = [c.model.col_id for c in p._assemble_columns()]
    # Simple column survives:
    assert ids.count("repetitions") >= 1   # builtins also include it
    # Both compound fields present:
    assert "ec_enabled" in ids
    assert "ec_count" in ids


def test_existing_single_cell_columns_still_assemble_unchanged():
    """Regression: PPT-3/4 single-cell columns continue to work."""
    p = PluggableProtocolTreePlugin()
    cols = p._assemble_columns()   # builtins only
    ids = [c.model.col_id for c in cols]
    assert "type" in ids
    assert "duration_s" in ids
    assert "electrodes" in ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_assembly.py -v
```
Expected: 4 of the 5 tests FAIL (the regression test passes since the existing builtins-only path is unchanged).

- [ ] **Step 3a: Add `_expand_compound` helper next to the adapters**

`_expand_compound` is tightly coupled to the adapters (it constructs them) and is consumed by both `plugin.py` and `session.py`. Put it in `_compound_adapters.py` to avoid any chance of `session.py → plugin.py → session.py` circular-import surprises.

Append to `src/pluggable_protocol_tree/models/_compound_adapters.py` (created in Task 3):

```python
from .column import Column
from ..interfaces.i_compound_column import ICompoundColumn


def _expand_compound(c: ICompoundColumn) -> list:
    """Expand a CompoundColumn contribution into N synthesized per-cell
    Column instances. The model + handler are shared via adapter shims
    so downstream consumers (RowManager, executor, MvcTreeModel,
    persistence) keep speaking single-cell Column / IColumnModel."""
    specs = c.model.field_specs()
    expanded = []
    for idx, spec in enumerate(specs):
        model_adapter = _CompoundFieldAdapter(
            col_id=spec.field_id,
            col_name=spec.col_name,
            default_value=spec.default_value,
            compound_model=c.model,
            field_id=spec.field_id,
            compound_base_id=c.model.base_id,
            is_owner=(idx == 0),
        )
        handler_adapter = _CompoundFieldHandlerAdapter(
            compound_handler=c.handler,
            compound_model=c.model,
            field_id=spec.field_id,
            is_owner=(idx == 0),
            priority=c.handler.priority,
            wait_for_topics=list(c.handler.wait_for_topics or []),
        )
        view = c.view.cell_view_for_field(spec.field_id)
        expanded.append(Column(
            model=model_adapter, view=view, handler=handler_adapter,
        ))
    return expanded
```

- [ ] **Step 3b: Wire it into `_assemble_columns`**

In `src/pluggable_protocol_tree/plugin.py`, add imports near the top (alongside the existing builtins imports):

```python
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
```

Modify the existing `_assemble_columns` method (replace lines 63-83 in the existing file):

```python
    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_repetitions_column(),
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
        try:
            contributed = list(self.contributed_columns)
        except Exception:
            contributed = []
        out = []
        for c in (builtins + contributed):
            if isinstance(c, ICompoundColumn):
                out.extend(_expand_compound(c))
            else:
                out.append(c)
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_assembly.py src/pluggable_protocol_tree/tests/test_plugin.py -v
```
Expected: all 5 new tests pass + existing test_plugin.py tests still pass.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/plugin.py pluggable_protocol_tree/tests/test_compound_assembly.py
git -C src commit -m "[PPT-11] _assemble_columns expands compound contributions into per-cell Columns"
```

---

## Task 5: Persistence — serialize compound discriminators

**Files:**
- Modify: `src/pluggable_protocol_tree/services/persistence.py` (extend `serialize_tree` col_specs builder)
- Create: `src/pluggable_protocol_tree/tests/test_compound_persistence.py`

**Why:** When a synthesized compound field is persisted, the JSON entry needs `compound_id` + `compound_field_id` discriminators so the resolver can reconstruct the compound. The flat row format stays unchanged — the discriminators only affect the column-spec list.

- [ ] **Step 1: Write the failing test (serialize-only — round-trip is Task 7)**

```python
# src/pluggable_protocol_tree/tests/test_compound_persistence.py
"""Tests for compound column persistence (serialize discriminators)."""

from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.services.persistence import serialize_tree
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


def _expand():
    cc = CompoundColumn(
        model=_DemoModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )
    return _expand_compound(cc)


def test_serialize_compound_field_entries_have_discriminators():
    """Each compound-field column entry has compound_id +
    compound_field_id; cls points at the compound MODEL class (not
    the adapter)."""
    cols = _expand()
    root = GroupRow(name="Root")
    payload = serialize_tree(root, cols)

    by_id = {e["id"]: e for e in payload["columns"]}
    assert "ec_enabled" in by_id
    assert "ec_count" in by_id

    enabled_entry = by_id["ec_enabled"]
    assert enabled_entry["compound_id"] == "demo"
    assert enabled_entry["compound_field_id"] == "ec_enabled"
    # cls qualname points at the compound model class, NOT the adapter:
    assert enabled_entry["cls"].endswith(".") is False   # sanity
    assert "_CompoundFieldAdapter" not in enabled_entry["cls"]
    assert "_DemoModel" in enabled_entry["cls"]


def test_serialize_simple_column_entries_have_no_discriminators():
    """Regression: single-cell columns continue to omit compound_id."""
    from pluggable_protocol_tree.builtins.repetitions_column import (
        make_repetitions_column,
    )
    root = GroupRow(name="Root")
    payload = serialize_tree(root, [make_repetitions_column()])
    entry = payload["columns"][0]
    assert "compound_id" not in entry
    assert "compound_field_id" not in entry


def test_serialize_compound_field_order_preserved():
    """Compound fields must appear in field_specs declaration order
    in the columns list (so the resolver's grouping pass works)."""
    cols = _expand()
    root = GroupRow(name="Root")
    payload = serialize_tree(root, cols)
    ids = [e["id"] for e in payload["columns"]]
    assert ids.index("ec_enabled") < ids.index("ec_count")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_persistence.py -v
```
Expected: 2 of 3 tests FAIL (the simple-column regression test passes; the two compound tests fail because discriminators aren't being written).

- [ ] **Step 3: Implement the discriminators**

Edit `src/pluggable_protocol_tree/services/persistence.py`. Add an import at the top:

```python
from pluggable_protocol_tree.models._compound_adapters import _CompoundFieldAdapter
```

Replace the existing `col_specs` list-comp in `serialize_tree` (around lines 29-35) with:

```python
    col_specs = []
    for c in columns:
        spec = {
            "id": c.model.col_id,
            "cls": _persisted_cls_qualname(c.model),
        }
        if isinstance(c.model, _CompoundFieldAdapter):
            spec["compound_id"] = c.model.compound_base_id
            spec["compound_field_id"] = c.model.field_id
        col_specs.append(spec)
```

Add the helper at module level (just below the imports):

```python
def _persisted_cls_qualname(model) -> str:
    """The 'cls' qualname stored in column entries. For compound-field
    adapters, returns the compound MODEL class's qualname (importable);
    for ordinary single-cell models, returns the model's own class
    qualname."""
    if isinstance(model, _CompoundFieldAdapter):
        target = model.compound_model
    else:
        target = model
    return f"{type(target).__module__}.{type(target).__name__}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_persistence.py src/pluggable_protocol_tree/tests/test_persistence.py -v
```
Expected: 3 new + existing persistence tests pass. (The existing `test_persistence.py` covers PPT-3 single-cell round-trip — must stay green.)

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/services/persistence.py pluggable_protocol_tree/tests/test_compound_persistence.py
git -C src commit -m "[PPT-11] Persist compound_id + compound_field_id discriminators"
```

---

## Task 6: Resolver — group + expand compound entries

**Files:**
- Modify: `src/pluggable_protocol_tree/session.py` (extend `resolve_columns`)
- Create: `src/pluggable_protocol_tree/tests/test_compound_resolver.py`

**Why:** `resolve_columns` currently calls `factory()` for each column entry independently. For compounds, we need to GROUP consecutive entries with the same `(cls, compound_id)`, call the factory ONCE (it returns a `CompoundColumn`), then expand into N synthesized fields — so the returned list is flat and `RowManager.from_json` doesn't need to change.

- [ ] **Step 1: Write the failing test**

```python
# src/pluggable_protocol_tree/tests/test_compound_resolver.py
"""Tests for resolve_columns handling of compound entries."""

import pytest
from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models._compound_adapters import _CompoundFieldAdapter
from pluggable_protocol_tree.session import resolve_columns
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


# Module-level so the resolver's importlib + dir() walk can find both
# the model class AND the make_*_compound factory.

class _RTestModel(BaseCompoundColumnModel):
    base_id = "rtest"
    def field_specs(self):
        return [FieldSpec("rt_a", "A", False),
                FieldSpec("rt_b", "B", 0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "rt_a" else Int(0)


def make_rtest_compound():
    return CompoundColumn(
        model=_RTestModel(),
        view=DictCompoundColumnView(cell_views={
            "rt_a": CheckboxColumnView(),
            "rt_b": IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )


def test_resolve_compound_returns_n_synthesized_columns():
    """Two compound-field entries in the payload resolve to N flat
    Column instances (after expansion) — same shape as if they had
    been assembled live."""
    payload = {
        "columns": [
            {"id": "rt_a",
             "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest",
             "compound_field_id": "rt_a"},
            {"id": "rt_b",
             "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest",
             "compound_field_id": "rt_b"},
        ],
    }
    cols = resolve_columns(payload)
    assert len(cols) == 2
    assert all(isinstance(c.model, _CompoundFieldAdapter) for c in cols)
    assert [c.model.col_id for c in cols] == ["rt_a", "rt_b"]


def test_resolve_compound_calls_factory_once_per_compound():
    """Multiple field entries for the same compound must share the
    underlying compound model + handler instance — proves the factory
    was called once, not N times."""
    payload = {
        "columns": [
            {"id": "rt_a", "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest", "compound_field_id": "rt_a"},
            {"id": "rt_b", "cls": f"{__name__}._RTestModel",
             "compound_id": "rtest", "compound_field_id": "rt_b"},
        ],
    }
    cols = resolve_columns(payload)
    assert cols[0].model.compound_model is cols[1].model.compound_model


def test_resolve_simple_columns_unchanged():
    """Regression: a payload with only simple columns resolves the
    same way as before PPT-11."""
    from pluggable_protocol_tree.builtins.repetitions_column import (
        RepetitionsColumnModel,
    )
    payload = {
        "columns": [
            {"id": "repetitions",
             "cls": "pluggable_protocol_tree.builtins.repetitions_column.RepetitionsColumnModel"},
        ],
    }
    cols = resolve_columns(payload)
    assert len(cols) == 1
    assert cols[0].model.col_id == "repetitions"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_resolver.py -v
```
Expected: 2 of 3 tests FAIL (the simple-columns regression passes; compound tests fail — current resolver treats each entry independently and expects each field's `cls` to have its own factory).

- [ ] **Step 3: Implement the grouping pass**

Edit `src/pluggable_protocol_tree/session.py`. Add an import at the top:

```python
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
```

Replace the `resolve_columns` body (lines 47-87) with:

```python
def resolve_columns(payload: dict) -> List[IColumn]:
    """Walk ``payload['columns']`` and instantiate each column from the
    recorded model class name.

    Two shapes:
    - **Simple column entry** (no ``compound_id``): instantiated via its
      module's ``make_*_column`` factory, appended as-is.
    - **Compound field entries** (have ``compound_id``): consecutive
      entries with the same ``(cls, compound_id)`` are grouped; the
      factory is called ONCE and the returned ``CompoundColumn`` is
      expanded into N per-cell ``Column`` instances inline — so the
      caller sees a flat list and downstream consumers (RowManager,
      executor, persistence) keep speaking single-cell Column.
    """
    entries = payload.get("columns", [])
    out: List[IColumn] = []
    i = 0
    while i < len(entries):
        e = entries[i]
        compound_id = e.get("compound_id")
        if compound_id is None:
            out.append(_resolve_simple_entry(e))
            i += 1
            continue
        # Group consecutive entries with the same (cls, compound_id).
        cls_qualname = e["cls"]
        j = i
        while (j < len(entries)
               and entries[j].get("cls") == cls_qualname
               and entries[j].get("compound_id") == compound_id):
            j += 1
        compound_col = _resolve_compound_entry(cls_qualname, e.get("id", "<unknown>"))
        # _expand_compound returns N per-cell Column instances. The
        # field order from the LIVE compound's field_specs() is used
        # (must match the saved order; if it doesn't, that's a real
        # plugin-version mismatch and we let the caller hit the missing
        # data at deserialize_tree time).
        out.extend(_expand_compound(compound_col))
        i = j
    return out


def _resolve_simple_entry(entry: dict) -> IColumn:
    """Instantiate a simple (non-compound) column from a payload entry."""
    cls_qualname = entry.get("cls")
    col_id = entry.get("id", "<unknown>")
    if not cls_qualname:
        raise ColumnResolutionError(
            f"column {col_id!r} has no 'cls' qualname in payload"
        )
    target_cls, module = _import_target_class(cls_qualname, col_id)
    factory = _find_factory(module, target_cls)
    if factory is None:
        raise ColumnResolutionError(
            f"no make_*_column factory in {module.__name__!r} returns a "
            f"Column with model {target_cls.__name__} (needed for column {col_id!r})"
        )
    return factory()


def _resolve_compound_entry(cls_qualname: str, col_id: str):
    """Instantiate a CompoundColumn from a (cls, compound_id) group."""
    target_cls, module = _import_target_class(cls_qualname, col_id)
    factory = _find_factory(module, target_cls)
    if factory is None:
        raise ColumnResolutionError(
            f"no make_*_compound factory in {module.__name__!r} returns a "
            f"CompoundColumn with model {target_cls.__name__} (needed for "
            f"compound column entry {col_id!r})"
        )
    result = factory()
    if not isinstance(result, ICompoundColumn):
        raise ColumnResolutionError(
            f"factory in {module.__name__!r} for compound entry {col_id!r} "
            f"returned {type(result).__name__}, expected ICompoundColumn"
        )
    return result


def _import_target_class(cls_qualname: str, col_id: str):
    """Resolve cls_qualname to (target_cls, module). Raises ColumnResolutionError."""
    module_name, class_name = cls_qualname.rsplit(".", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ColumnResolutionError(
            f"can't import {module_name!r} for column {col_id!r}: {e}"
        ) from e
    target_cls = getattr(module, class_name, None)
    if target_cls is None:
        raise ColumnResolutionError(
            f"module {module_name!r} has no class {class_name!r} "
            f"(needed for column {col_id!r})"
        )
    return target_cls, module
```

The existing `_find_factory` already iterates `make_*` candidates and matches by `isinstance(model, target_cls)` — it works for both `make_*_column` and `make_*_compound` factories without changes. (The factory's return value's `.model` is checked, which is the compound model in the compound case.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_resolver.py src/pluggable_protocol_tree/tests/test_session.py -v
```
Expected: 3 new compound tests pass + existing test_session.py still passes.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/session.py pluggable_protocol_tree/tests/test_compound_resolver.py
git -C src commit -m "[PPT-11] resolve_columns groups + expands compound field entries"
```

---

## Task 7: End-to-end persistence round-trip integration test

**Files:**
- Modify: `src/pluggable_protocol_tree/tests/test_compound_persistence.py` (add round-trip tests)

**Why:** Tasks 5 + 6 each tested half of the persistence story (serialize and resolve). This task verifies the full to_json → from_json round-trip preserves all compound field values.

- [ ] **Step 1: Append to the test file**

```python
# Append to src/pluggable_protocol_tree/tests/test_compound_persistence.py:

import json

from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import resolve_columns


# Module-level so resolve_columns can find both the model and factory:

class _RTModel(BaseCompoundColumnModel):
    base_id = "rt"
    def field_specs(self):
        return [FieldSpec("rt_a", "A", False),
                FieldSpec("rt_b", "B", 0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "rt_a" else Int(0)


def make_rt_compound():
    return CompoundColumn(
        model=_RTModel(),
        view=DictCompoundColumnView(cell_views={
            "rt_a": CheckboxColumnView(),
            "rt_b": IntSpinBoxColumnView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )


def _all_columns():
    """Required builtins for a runnable RowManager + the compound under test."""
    return [
        make_type_column(), make_id_column(), make_name_column(),
        *_expand_compound(make_rt_compound()),
    ]


def test_compound_round_trip_through_json_preserves_all_fields():
    """to_json -> from_json -> read row.* yields the saved values for
    BOTH fields of the compound."""
    cols = _all_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "rt_a": True, "rt_b": 42})

    payload = rm.to_json()
    json_str = json.dumps(payload)
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=resolve_columns(parsed))
    step = rm2.root.children[0]
    assert step.rt_a is True
    assert step.rt_b == 42
    assert isinstance(step.rt_b, int)


def test_compound_round_trip_via_protocol_session(tmp_path):
    """Same round-trip but through ProtocolSession.from_file (resolves
    columns automatically from the saved cls qualnames)."""
    from pluggable_protocol_tree.session import ProtocolSession

    cols = _all_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "rt_a": True,  "rt_b": 11})
    rm.add_step(values={"name": "S2", "rt_a": False, "rt_b": 22})

    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(rm.to_json()))

    session = ProtocolSession.from_file(str(path), with_demo_hardware=False)
    assert session.manager.root.children[0].rt_a is True
    assert session.manager.root.children[0].rt_b == 11
    assert session.manager.root.children[1].rt_a is False
    assert session.manager.root.children[1].rt_b == 22
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_persistence.py -v
```
Expected: 5 tests pass (3 from Task 5 + 2 new round-trip tests).

- [ ] **Step 3: Commit**

```bash
git -C src add pluggable_protocol_tree/tests/test_compound_persistence.py
git -C src commit -m "[PPT-11] Add compound JSON round-trip integration tests"
```

---

## Task 8: View dispatch test (MvcTreeModel.setData via adapter)

**Files:**
- Create: `src/pluggable_protocol_tree/tests/test_compound_view_dispatch.py`

**Why:** Tasks 3 + 4 verified the adapters in isolation; Task 8 verifies the actual UI codepath: when `MvcTreeModel.setData` calls `col.handler.on_interact(node, col.model, value)` on a synthesized compound field, the call reaches the compound handler with the correct `field_id`. Also verifies conditional editability — the `get_flags(row)` mechanism works because `row` has all the compound's fields as attributes.

- [ ] **Step 1: Write the test**

```python
# src/pluggable_protocol_tree/tests/test_compound_view_dispatch.py
"""Tests for the UI-edit codepath: MvcTreeModel.setData -> adapter ->
compound handler with field_id; per-cell get_flags(row) reads sibling
field values for conditional editability."""

from unittest.mock import MagicMock

from pyface.qt.QtCore import Qt
from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


class _DemoModel(BaseCompoundColumnModel):
    base_id = "demo"
    def field_specs(self):
        return [FieldSpec("ec_enabled", "Enabled", False),
                FieldSpec("ec_count",   "Count",   0)]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


class _SpyHandler(BaseCompoundColumnHandler):
    """Records every on_interact call as (row, field_id, value)."""
    def __init__(self):
        super().__init__()
        self.calls = []
    def on_interact(self, row, model, field_id, value):
        self.calls.append((row, field_id, value))
        return model.set_value(row, field_id, value)


class _CountCellViewWithGate(IntSpinBoxColumnView):
    """Read-only when the row's ec_enabled field is False — the
    cross-cell editability mechanism we're testing here."""
    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "ec_enabled", False):
            flags &= ~Qt.ItemIsEditable
        return flags


def _build_manager():
    cc = CompoundColumn(
        model=_DemoModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   _CountCellViewWithGate(low=0, high=999),
        }),
        handler=_SpyHandler(),
    )
    cols = _expand_compound(cc)
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "ec_enabled": False, "ec_count": 0})
    return rm, cols, cc.handler


def test_setdata_on_compound_cell_calls_compound_handler_with_field_id():
    """Editing the count cell via setData must call compound_handler.on_interact
    with field_id='ec_count' and the new value."""
    rm, cols, handler = _build_manager()
    model = MvcTreeModel(rm)
    # Step row at index 0; column index = position of 'ec_count' in cols
    field_col_idx = next(i for i, c in enumerate(cols)
                         if c.model.col_id == "ec_count")
    step_index = model.index(0, field_col_idx)
    model.setData(step_index, 7, role=Qt.EditRole)
    assert handler.calls[-1][1] == "ec_count"
    assert handler.calls[-1][2] == 7


def test_count_cell_read_only_when_enabled_is_false():
    """The CountCellViewWithGate.get_flags(row) check returns flags
    WITHOUT Qt.ItemIsEditable when row.ec_enabled is False."""
    rm, cols, _ = _build_manager()
    count_col = next(c for c in cols if c.model.col_id == "ec_count")
    row = rm.root.children[0]
    row.ec_enabled = False
    flags = count_col.view.get_flags(row)
    assert not (flags & Qt.ItemIsEditable)


def test_count_cell_editable_when_enabled_is_true():
    """When ec_enabled flips to True, the count cell becomes editable."""
    rm, cols, _ = _build_manager()
    count_col = next(c for c in cols if c.model.col_id == "ec_count")
    row = rm.root.children[0]
    row.ec_enabled = True
    flags = count_col.view.get_flags(row)
    assert flags & Qt.ItemIsEditable


def test_setdata_on_owner_cell_does_not_double_fire_compound_handler():
    """Setting the FIRST (owner) field doesn't cause on_interact to
    fire twice. on_interact always fires per-cell-edit; the is_owner
    flag only gates execution hooks (on_step etc)."""
    rm, cols, handler = _build_manager()
    model = MvcTreeModel(rm)
    enabled_col_idx = next(i for i, c in enumerate(cols)
                           if c.model.col_id == "ec_enabled")
    step_index = model.index(0, enabled_col_idx)
    model.setData(step_index, True, role=Qt.CheckStateRole)
    # Exactly one on_interact call:
    enabled_calls = [c for c in handler.calls if c[1] == "ec_enabled"]
    assert len(enabled_calls) == 1
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_compound_view_dispatch.py -v
```
Expected: 4 tests pass. (No new implementation needed — this test exercises the existing setData + adapter path.)

- [ ] **Step 3: Commit**

```bash
git -C src add pluggable_protocol_tree/tests/test_compound_view_dispatch.py
git -C src commit -m "[PPT-11] Verify MvcTreeModel.setData routes compound edits to handler with field_id"
```

---

## Task 9: Demo synthetic compound — `enabled_count_compound.py`

**Files:**
- Create: `src/pluggable_protocol_tree/demos/enabled_count_compound.py`
- Create: `src/pluggable_protocol_tree/tests/test_enabled_count_compound.py`

**Why:** Stable, importable demo column for the runnable verification script (Task 11) AND for any future framework regression test. Lives in `demos/`, not `builtins/`, because it's only there to drive the demo — it's not a real protocol-authoring column.

- [ ] **Step 1: Write the failing test**

```python
# src/pluggable_protocol_tree/tests/test_enabled_count_compound.py
"""Tests for the synthetic demo enabled+count compound column."""

from pyface.qt.QtCore import Qt
from traits.api import Bool, HasTraits, Int

from pluggable_protocol_tree.demos.enabled_count_compound import (
    CountCellView, EnabledCountCompoundModel, make_enabled_count_compound,
)
from pluggable_protocol_tree.models.compound_column import (
    CompoundColumn, DictCompoundColumnView,
)


def test_factory_returns_compound_column_with_two_fields():
    cc = make_enabled_count_compound()
    assert isinstance(cc, CompoundColumn)
    specs = cc.model.field_specs()
    assert [s.field_id for s in specs] == ["ec_enabled", "ec_count"]
    assert [s.col_name for s in specs] == ["Enabled", "Count"]
    assert [s.default_value for s in specs] == [False, 0]


def test_model_traits_are_bool_and_int():
    m = EnabledCountCompoundModel()
    enabled_trait = m.trait_for_field("ec_enabled")
    count_trait = m.trait_for_field("ec_count")
    class Row(HasTraits):
        ec_enabled = enabled_trait
        ec_count = count_trait
    r = Row()
    assert r.ec_enabled is False
    assert r.ec_count == 0
    r.ec_enabled = True
    r.ec_count = 99
    assert r.ec_enabled is True
    assert r.ec_count == 99


def test_count_cell_view_read_only_when_enabled_false():
    v = CountCellView(low=0, high=999)
    class Row(HasTraits):
        ec_enabled = Bool(False)
        ec_count = Int(0)
    r = Row()
    flags = v.get_flags(r)
    assert not (flags & Qt.ItemIsEditable)


def test_count_cell_view_editable_when_enabled_true():
    v = CountCellView(low=0, high=999)
    class Row(HasTraits):
        ec_enabled = Bool(True)
        ec_count = Int(0)
    r = Row()
    flags = v.get_flags(r)
    assert flags & Qt.ItemIsEditable
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_enabled_count_compound.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the demo column**

Create `src/pluggable_protocol_tree/demos/enabled_count_compound.py`:

```python
"""Synthetic demo compound column — drives the framework verification
demo (run_widget_compound_demo.py) and proves the framework works
end-to-end with a real Qt window.

Two fields: a Bool 'ec_enabled' and an Int 'ec_count' where the count
cell is read-only when ec_enabled is False. Demonstrates conditional
editability via cross-cell get_flags(row) lookups. NOT a builtin —
deletable once compound columns have a real consumer (PPT-5 magnet).
"""

from pyface.qt.QtCore import Qt
from traits.api import Bool, Int

from ..interfaces.i_compound_column import FieldSpec
from ..models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from ..views.columns.checkbox import CheckboxColumnView
from ..views.columns.spinbox import IntSpinBoxColumnView


class EnabledCountCompoundModel(BaseCompoundColumnModel):
    """Two coupled fields. The compound's base_id 'enabled_count_demo'
    appears in JSON as 'compound_id' on each field's column entry."""
    base_id = "enabled_count_demo"

    def field_specs(self):
        return [
            FieldSpec("ec_enabled", "Enabled", False),
            FieldSpec("ec_count",   "Count",   0),
        ]

    def trait_for_field(self, field_id):
        if field_id == "ec_enabled":
            return Bool(False)
        if field_id == "ec_count":
            return Int(0)
        raise KeyError(field_id)


class CountCellView(IntSpinBoxColumnView):
    """Read-only when the row's ec_enabled field is False. This is the
    canonical cross-cell editability pattern — get_flags(row) reads a
    SIBLING field's value off the row to gate this cell."""

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "ec_enabled", False):
            flags &= ~Qt.ItemIsEditable
        return flags


def make_enabled_count_compound():
    """Factory — returns a fresh CompoundColumn instance. Demo handler
    has no runtime side-effect (the synthetic column is for framework
    verification only)."""
    return CompoundColumn(
        model=EnabledCountCompoundModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   CountCellView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/test_enabled_count_compound.py -v
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/enabled_count_compound.py pluggable_protocol_tree/tests/test_enabled_count_compound.py
git -C src commit -m "[PPT-11] Add synthetic enabled+count demo compound column"
```

---

## Task 10: Demo runnable script — `run_widget_compound_demo.py`

**Files:**
- Create: `src/pluggable_protocol_tree/demos/run_widget_compound_demo.py`

**Why:** Headed visual verification: the framework actually renders N cells from one compound, conditional editability flips correctly when the user clicks the Enabled checkbox, save/load round-trips the values. No automated test — manual smoke run is the verification (similar to `run_widget.py` for PPT-3 and `run_widget_with_vf.py` for PPT-4).

- [ ] **Step 1: Write the demo script**

Create `src/pluggable_protocol_tree/demos/run_widget_compound_demo.py`:

```python
"""Headed demo for the compound column framework.

Builds a protocol tree with the existing PPT-3 builtins + the
synthetic enabled+count compound from enabled_count_compound.py.
Auto-populates 3 sample steps so the user can immediately verify:

  1. Two columns render ('Enabled' checkbox + 'Count' spinner) for the
     one compound contribution
  2. The Count cell is read-only when Enabled is unchecked (greyed out
     spinner that won't accept clicks)
  3. Toggling Enabled makes the Count cell editable
  4. Save -> reload via the toolbar's Save / Load buttons preserves
     both fields
  5. The compound handler's on_step fires exactly once per row (via
     the logged invocation count line)

Run: pixi run python -m pluggable_protocol_tree.demos.run_widget_compound_demo
"""

import logging
import sys

import dramatiq

# Centralised middleware strip — see broker_server_helpers.
from microdrop_utils.broker_server_helpers import (
    remove_middleware_from_dramatiq_broker,
)
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QApplication, QMainWindow, QSplitter, QToolBar

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.demos.enabled_count_compound import (
    make_enabled_count_compound,
)
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.models._compound_adapters import _expand_compound
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget


logger = logging.getLogger(__name__)


class _CountingHandler(BaseCompoundColumnHandler):
    """Subclass of the demo's default handler that logs every on_step
    invocation count — so the user can verify the owner-field guard
    works (one log line per row, not two)."""
    _on_step_count = 0
    def on_step(self, row, ctx):
        type(self)._on_step_count += 1
        logger.info("[demo compound] on_step #%d for row %r",
                    type(self)._on_step_count, getattr(row, "name", "<?>"))


def _columns():
    cc = make_enabled_count_compound()
    cc.handler = _CountingHandler()
    cc.handler.model = cc.model
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(cc),
    ]


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PPT-11 Demo — Compound Column Framework")
        self.resize(900, 500)

        self.manager = RowManager(columns=_columns())
        # Pre-populate so Run / save+load have something to work with.
        self.manager.add_step(values={
            "name": "Step 1: enabled, count=5",
            "duration_s": 0.2,
            "ec_enabled": True,
            "ec_count": 5,
        })
        self.manager.add_step(values={
            "name": "Step 2: disabled (count read-only)",
            "duration_s": 0.2,
            "ec_enabled": False,
            "ec_count": 0,
        })
        self.manager.add_step(values={
            "name": "Step 3: enabled, count=99",
            "duration_s": 0.2,
            "ec_enabled": True,
            "ec_count": 99,
        })

        self.widget = ProtocolTreeWidget(self.manager, parent=self)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.widget)
        self.setCentralWidget(splitter)

        tb = QToolBar("Demo")
        self.addToolBar(tb)
        tb.addAction("Add Step", lambda: self.manager.add_step())


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = QApplication.instance() or QApplication(sys.argv)
    w = DemoWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script imports cleanly (no display needed)**

```bash
pixi run python -c "import pluggable_protocol_tree.demos.run_widget_compound_demo"
```
Expected: clean exit, no traceback. (If it errors at import time that's a real bug — fix before continuing.)

- [ ] **Step 3: Run the demo manually for visual verification**

```bash
pixi run python -m pluggable_protocol_tree.demos.run_widget_compound_demo
```

Expect:
- A window opens with the protocol tree
- 3 pre-populated steps visible
- Two columns labelled `Enabled` (checkbox) and `Count` (spinner)
- Step 2's Count cell appears greyed out (read-only — cannot click into the spinner)
- Click the `Enabled` checkbox on Step 2 → Count cell becomes editable
- Uncheck Step 1's Enabled → Step 1's Count becomes read-only
- Close the window — clean exit, no errors

- [ ] **Step 4: Commit**

```bash
git -C src add pluggable_protocol_tree/demos/run_widget_compound_demo.py
git -C src commit -m "[PPT-11] Add headed demo for compound column framework"
```

---

## Task 11: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run all PPT-11 + regression tests**

```bash
pixi run pytest src/pluggable_protocol_tree/tests/ -v
```
Expected: all tests pass — new compound tests (interfaces, base classes, adapters, assembly, persistence, resolver, view dispatch, demo column) AND existing PPT-1/2/3/4 tests.

- [ ] **Step 2: Verify the demo runs cleanly**

```bash
pixi run python -m pluggable_protocol_tree.demos.run_widget_compound_demo
```
Expected: window opens, 3 steps render with the compound's two columns, conditional editability works as described in Task 10 Step 3.

- [ ] **Step 3: Verify PPT-3 and PPT-4 demos still run cleanly (regression)**

```bash
pixi run python -m pluggable_protocol_tree.demos.run_widget
```
And:
```bash
pixi run python -m dropbot_protocol_controls.demos.run_widget_with_vf
```
Expected: both demos open and behave exactly as before — single-cell columns are unaffected by the compound framework.

- [ ] **Step 4: git status clean**

```bash
git -C src status
```
Expected: clean working tree (no uncommitted changes from verification).

---

## Implementation Notes

**Branch hygiene:** branch is `feat/ppt-11-compound-columns`, branched from main (PPT-3 + PPT-4 already merged). When PR opens, target main.

**Layering:** all changes live inside `pluggable_protocol_tree/`. No changes to `dropbot_controller`, `dropbot_protocol_controls`, or any other plugin. The compound framework is opt-in — single-cell `IColumn` continues to work unchanged.

**The adapter approach (`_compound_adapters.py`)** is the single load-bearing decision: every consumer downstream of `_assemble_columns` keeps speaking single-cell `Column` / `IColumnModel`. RowManager, executor, MvcTreeModel, persistence are all unmodified beyond the persistence-discriminator addition. If a future PR finds that the adapter overhead is too costly (it shouldn't be — adapters are thin), the alternative is teaching every consumer about compound columns directly. Don't do that without strong evidence.

**Backwards compat:** the persistence schema is additive. Old single-cell-only protocol JSON files load unchanged (no `compound_id` discriminator → resolver takes the simple path). New files with compound entries fail gracefully on a system without the contributing plugin (the resolver raises `ColumnResolutionError` with the missing module name — same as today's simple-column-missing behaviour).

**If a test fails unexpectedly during execution:** use `superpowers:systematic-debugging` rather than guessing. Most likely failure modes: (1) `_expand_compound` ordering doesn't match `field_specs()` declaration order — the test_compound_assembly tests catch this; (2) the resolver groups across non-consecutive entries — shouldn't happen since `serialize_tree` writes them adjacent, but if it does, the grouping logic needs a stricter check.
