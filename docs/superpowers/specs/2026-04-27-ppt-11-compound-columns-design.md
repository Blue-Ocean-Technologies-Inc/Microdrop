# PPT-11 — Compound column framework (multi-cell columns sharing one model + handler)

**Status:** READY FOR REVIEW — all four sections confirmed by the user during brainstorming. Pending self-review pass + final approval, then transition to writing-plans.

**Issue:** [#378](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/378) (umbrella [#361](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/361))

**Brainstorming session:** 2026-04-27, in conversation with the user. All decisions captured below were confirmed one at a time.

---

## Why this exists

Today's pluggable protocol tree column abstraction is one model + one view + one handler producing **one** visible cell per row. Several upcoming column migrations need **coupled fields** that should be modelled as one logical unit but rendered as N visible cells:

- **PPT-5 (#367)** — Magnet: a Bool ('engage') + a Float ('height in mm'); the height cell should be read-only when the engage cell is unchecked, and the handler decides per step whether to engage at the stored height or retract.
- **PPT-7 (#369)** — Force calculation: multiple parameters that together drive one calculation.
- **PPT-8 (#370)** — Droplet detection: a Bool toggle + a Float threshold.

Without a framework for coupled fields, each plugin would have to reinvent cross-cell concerns (conditional editability, single-handler-call-per-row) on top of N independent `IColumn` instances. PPT-11 introduces `CompoundColumn` as a sibling shape to `IColumn` so that one plugin contribution can render N cells while still owning a single model + handler.

---

## Section 1 — Architecture ✅ CONFIRMED

`CompoundColumn` is a **new column shape parallel to** the existing `IColumn` (not extending; not replacing). The contract:

- **One model** holds N coupled fields. Each field is exposed as a row trait + a visible cell. Model declares its fields via a `field_specs()` method returning `[FieldSpec(field_id, col_name, default_value), ...]`.
- **One view** is composed of N per-cell views (one `IColumnView` per field). The cell view's existing `get_flags(row)` is the conditional-editability hook — it can read sibling field values from `row`.
- **One handler** with the existing 5-hook protocol (`on_protocol_start`, `on_pre_step`, `on_step`, `on_post_step`, `on_protocol_end`) plus a field-aware `on_interact(row, model, field_id, value)`.

PROTOCOL_COLUMNS extension point accepts both `IColumn` and `ICompoundColumn`. `PluggableProtocolTreePlugin._assemble_columns()` returns a flat list of "rendered cells" by **expanding** each compound contribution into N synthesized per-cell `Column` instances; the model + handler are shared across those entries.

**Layering:** the framework lives entirely inside `pluggable_protocol_tree/`. No changes to `dropbot_controller`, `dropbot_protocol_controls`, or any other plugin (they keep using `IColumn` as-is). PPT-3/4 columns continue to work without modification.

### Why parallel rather than extends or replace

- **Parallel (chosen):** zero risk to PPT-3/4. Existing `IColumn` works unchanged. New compound shape is opt-in.
- **Extends:** `ICompoundColumn extends IColumn` would inherit single-field methods that are confusing for true multi-field cases (`on_interact(row, model, value)` — which value? which field?).
- **Replace:** refactoring `IColumn` itself into the compound shape would force every existing PPT-3/4 column factory to be rewritten as a 1-field compound. Big churn for no immediate user value. A future cleanup PR can promote parallel→replace if it proves worth it.

---

## Section 2 — Interfaces + base classes ✅ CONFIRMED

### `pluggable_protocol_tree/interfaces/i_compound_column.py`

```python
from typing import NamedTuple
from traits.api import Interface, Str, Any, Int, List, Instance
from .i_column import IColumnView   # reuse the per-cell view interface


class FieldSpec(NamedTuple):
    field_id: str        # row attribute name AND col_id of the rendered cell
    col_name: str        # column header label
    default_value: Any   # applied at row construction


class ICompoundColumnModel(Interface):
    """One model owning N coupled fields. Each field becomes a row trait +
    a visible cell in the protocol tree. The handler sees ALL field values."""

    base_id = Str(desc="Logical name for the compound — appears in JSON "
                       "as 'compound_id' on each field's column entry.")

    def field_specs(self) -> list[FieldSpec]:
        """Returns the ordered list of fields the compound contributes."""

    def trait_for_field(self, field_id):
        """Return the Traits TraitType for the given field. Same role as
        IColumnModel.trait_for_row but per-field."""

    def get_value(self, row, field_id):  ...
    def set_value(self, row, field_id, value): ...
    def serialize(self, field_id, value): ...
    def deserialize(self, field_id, raw): ...


class ICompoundColumnView(Interface):
    """N per-cell views, one per field."""
    def cell_view_for_field(self, field_id) -> IColumnView:
        """Return the IColumnView for the given field. Each cell's
        get_flags(row) can read sibling field values from `row` to express
        conditional editability."""


class ICompoundColumnHandler(Interface):
    """Same five execution hooks as IColumnHandler, but on_interact knows
    which field was edited."""
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
    model = Instance(ICompoundColumnModel)
    view = Instance(ICompoundColumnView)
    handler = Instance(ICompoundColumnHandler)
```

### `pluggable_protocol_tree/models/compound_column.py`

Base classes mirror the single-cell `Column` from `models/column.py`:

```python
from traits.api import Bool, Dict, Instance, Int, List, Str, HasTraits, provides

from ..interfaces.i_column import IColumnView
from ..interfaces.i_compound_column import (
    FieldSpec, ICompoundColumn, ICompoundColumnHandler,
    ICompoundColumnModel, ICompoundColumnView,
)


@provides(ICompoundColumnModel)
class BaseCompoundColumnModel(HasTraits):
    base_id = Str

    # Subclass overrides field_specs() and trait_for_field()
    def field_specs(self) -> list[FieldSpec]:
        return []

    def trait_for_field(self, field_id):
        raise NotImplementedError

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
    """Subclass provides cell_view_for_field. Or use DictCompoundColumnView
    (below) for a static field_id → view map."""
    def cell_view_for_field(self, field_id) -> IColumnView:
        raise NotImplementedError


class DictCompoundColumnView(BaseCompoundColumnView):
    """Convenience: build with a {field_id: IColumnView} dict."""
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
    """Composite. Auto-wires handler.model in traits_init."""
    model = Instance(ICompoundColumnModel)
    view = Instance(ICompoundColumnView)
    handler = Instance(ICompoundColumnHandler)

    def traits_init(self):
        if self.handler is None:
            self.handler = BaseCompoundColumnHandler()
        self.handler.model = self.model
```

---

## Section 3 — Assembly + persistence + UI dispatch ✅ CONFIRMED

### 3.1 Adapter shim approach (the load-bearing decision)

Every consumer downstream of `_assemble_columns()` already speaks `Column` / `IColumnModel`: RowManager constructs row classes from `column.model.col_id` + `column.model.trait_for_row()`; the executor walks `columns` and calls handler hooks; MvcTreeModel.setData calls `column.handler.on_interact(row, column.model, value)`; persistence walks `column.model.serialize/deserialize`.

Rather than teach every consumer about a new `ICompoundColumn` shape, we **expand compound contributions at assembly time** into N synthesized per-cell `Column` instances, each wrapping the compound's model + handler with thin field-id-bound adapters:

```python
class _CompoundFieldAdapter(BaseColumnModel):
    """Single-cell IColumnModel facade for one field of a compound model."""
    compound_model = Instance(ICompoundColumnModel)
    field_id = Str
    is_owner = Bool(False)   # True for the FIRST field of the compound
                              # — used by the handler adapter to ensure
                              # on_step / on_pre_step / on_post_step
                              # fire exactly once per row, not N times.

    @property
    def col_id(self): return self.field_id
    @property
    def col_name(self): return self._col_name   # set at adapter construction
    @property
    def compound_base_id(self): return self.compound_model.base_id

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
    single-field call into the compound handler's field-aware call. The
    five execution hooks fire only on the OWNER field (is_owner=True)
    so the compound's on_step runs exactly once per row, not N times."""
    compound_handler = Instance(ICompoundColumnHandler)
    compound_model = Instance(ICompoundColumnModel)
    field_id = Str
    is_owner = Bool(False)

    @property
    def priority(self): return self.compound_handler.priority
    @property
    def wait_for_topics(self): return self.compound_handler.wait_for_topics

    def on_interact(self, row, model, value):
        return self.compound_handler.on_interact(
            row, self.compound_model, self.field_id, value,
        )

    def on_protocol_start(self, ctx):
        if self.is_owner: self.compound_handler.on_protocol_start(ctx)
    def on_pre_step(self, row, ctx):
        if self.is_owner: self.compound_handler.on_pre_step(row, ctx)
    def on_step(self, row, ctx):
        if self.is_owner: self.compound_handler.on_step(row, ctx)
    def on_post_step(self, row, ctx):
        if self.is_owner: self.compound_handler.on_post_step(row, ctx)
    def on_protocol_end(self, ctx):
        if self.is_owner: self.compound_handler.on_protocol_end(ctx)
```

### 3.2 `pluggable_protocol_tree/plugin.py` — `_assemble_columns()`

Today's body (`pluggable_protocol_tree/plugin.py:63-83`) builds `builtins + contributed`. Updated body inserts a single expansion pass:

```python
def _assemble_columns(self):
    builtins = [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
    ]
    try:
        contributed = list(self.contributed_columns)
    except Exception:
        contributed = []
    out: list[Column] = []
    for c in (builtins + contributed):
        if isinstance(c, ICompoundColumn):
            out.extend(_expand_compound(c))
        else:
            out.append(c)
    return out


def _expand_compound(c: ICompoundColumn) -> list[Column]:
    specs = c.model.field_specs()
    expanded = []
    for idx, spec in enumerate(specs):
        model_adapter = _CompoundFieldAdapter(
            compound_model=c.model,
            field_id=spec.field_id,
            _col_name=spec.col_name,
            default_value=spec.default_value,
            is_owner=(idx == 0),
        )
        handler_adapter = _CompoundFieldHandlerAdapter(
            compound_handler=c.handler,
            compound_model=c.model,
            field_id=spec.field_id,
            is_owner=(idx == 0),
        )
        view = c.view.cell_view_for_field(spec.field_id)
        expanded.append(Column(
            model=model_adapter, view=view, handler=handler_adapter,
        ))
    return expanded
```

### 3.3 Persistence — `services/persistence.py`

Per Section "Q2 — flat with discriminator", every compound field gets its own entry in `columns` with a `compound_id` field linking related entries. The `cls` qualname points at the **compound model class** (importable, real); `compound_field_id` distinguishes which field within the compound. Old single-cell columns lacking `compound_id` keep working unchanged.

Today's `serialize_tree` (`services/persistence.py:22-46`) builds `col_specs` as a list of `{"id": col_id, "cls": qualname}` dicts. Updated builder adds two optional discriminator fields when the column is a synthesized compound field:

```python
def serialize_tree(root, columns, protocol_metadata=None):
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
    # `fields` array, `rows` walker, and the rest of the function body
    # stay byte-for-byte identical — compound fields are flat values
    # in the row tuple, indistinguishable in shape from single-cell columns.
    fields = ["depth", "uuid", "type", "name"] + [s["id"] for s in col_specs]
    rows_out = list(_walk_with_depth(root, columns, depth=0, skip_root=True))
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "protocol_metadata": dict(protocol_metadata or {}),
        "columns": col_specs,
        "fields": fields,
        "rows": rows_out,
    }
```

`_persisted_cls_qualname` returns `f"{type(c.model.compound_model).__module__}.{type(c.model.compound_model).__name__}"` for adapters (so the saved cls qualname is the importable compound model class, not the private `_CompoundFieldAdapter`), falling back to the existing logic (`f"{type(c.model).__module__}.{type(c.model).__name__}"`) for plain models.

### 3.4 Resolver — `session.py`

`resolve_columns()` (today: walks `payload['columns']`, finds the matching `make_*_column` factory in each module, calls it) gains a grouping pass for compound entries:

```python
def resolve_columns(payload) -> list:
    entries = payload.get("columns", [])
    out = []
    i = 0
    while i < len(entries):
        e = entries[i]
        if e.get("compound_id") is None:
            out.append(_resolve_simple_column(e))
            i += 1
            continue
        # Group consecutive entries with the same (cls, compound_id).
        group_cls = e["cls"]; group_id = e["compound_id"]
        j = i
        while (j < len(entries) and entries[j].get("cls") == group_cls
               and entries[j].get("compound_id") == group_id):
            j += 1
        compound = _resolve_compound_column(group_cls, group_id)
        out.append(compound)   # one entry, NOT expanded — _assemble_columns
                                # does the expansion when this is loaded back
                                # into the plugin
        i = j
    return out
```

The grouping assumes consecutive ordering — `_assemble_columns` already produces compound fields in declaration order, so `serialize_tree` writes them adjacent. Defensive: if entries are non-consecutive, fall back to grouping by `(cls, compound_id)` regardless of position.

### 3.5 UI dispatch — no changes

`MvcTreeModel.setData` already calls `column.handler.on_interact(row, column.model, value)` — and the synthesized per-field `Column` has the right `_CompoundFieldHandlerAdapter` that translates to `compound_handler.on_interact(row, compound_model, field_id, value)`. **No changes to MvcTreeModel.** Conditional editability also already works because `column.view.get_flags(row)` is already called per-cell with the row instance, which has all of the compound's fields as attributes.

---

## Section 4 — Tests + demo + scope ✅ CONFIRMED

### 4.1 Unit tests

| File | Covers |
|---|---|
| `pluggable_protocol_tree/tests/test_compound_column.py` | base classes (`BaseCompoundColumnModel.serialize/deserialize` identity defaults), `CompoundColumn.traits_init` wires `handler.model`, `DictCompoundColumnView.cell_view_for_field` lookup |
| `pluggable_protocol_tree/tests/test_compound_assembly.py` | `_assemble_columns` expands a compound contribution into N synthesized `Column` instances with the right `field_id`, shared model, shared handler; the "owner field" guard makes `on_step` fire exactly once per row regardless of N |
| `pluggable_protocol_tree/tests/test_compound_persistence.py` | A protocol with compound + simple columns round-trips through `to_json` / `from_json` with all field values intact; the resolver groups multiple `(cls, compound_id)` entries into one compound instance |
| `pluggable_protocol_tree/tests/test_compound_view_dispatch.py` | When the GUI edits cell N of a compound, `compound_handler.on_interact(row, model, field_id, value)` is called with the right `field_id` (verified via the adapter); when conditional editability triggers (e.g., demo's `enabled=False`), the count cell's `get_flags(row)` returns flags WITHOUT `Qt.ItemIsEditable` |

### 4.2 Regression coverage

PPT-3 + PPT-4 single-cell columns continue to work — the existing `test_assemble_columns_*` and `test_persistence` suites stay green. No behaviour changes for `IColumn` consumers.

### 4.3 Demo column + script

**`pluggable_protocol_tree/demos/enabled_count_compound.py`** — internal demo synthetic compound. Two fields with conditional editability:

```python
from pyface.qt.QtCore import Qt
from traits.api import Bool, Int

from pluggable_protocol_tree.interfaces.i_compound_column import FieldSpec
from pluggable_protocol_tree.models.compound_column import (
    BaseCompoundColumnHandler, BaseCompoundColumnModel, CompoundColumn,
    DictCompoundColumnView,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class EnabledCountCompoundModel(BaseCompoundColumnModel):
    base_id = "enabled_count_demo"
    def field_specs(self):
        return [
            FieldSpec("ec_enabled", "Enabled", False),
            FieldSpec("ec_count",   "Count",   0),
        ]
    def trait_for_field(self, field_id):
        return Bool(False) if field_id == "ec_enabled" else Int(0)


class CountCellView(IntSpinBoxColumnView):
    """Read-only when the row's ec_enabled field is False."""
    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "ec_enabled", False):
            flags &= ~Qt.ItemIsEditable
        return flags


def make_enabled_count_compound():
    return CompoundColumn(
        model=EnabledCountCompoundModel(),
        view=DictCompoundColumnView(cell_views={
            "ec_enabled": CheckboxColumnView(),
            "ec_count":   CountCellView(low=0, high=999),
        }),
        handler=BaseCompoundColumnHandler(),  # demo: no runtime side-effect
    )
```

**`pluggable_protocol_tree/demos/run_widget_compound_demo.py`** — Qt window with the protocol tree showing the existing PPT-3 columns + the synthetic compound. Auto-populates 3 sample steps with varied `ec_enabled` / `ec_count` values. Manual verification:

1. Two columns render (`Enabled` checkbox + `Count` spinner) for one compound contribution.
2. The Count cell is read-only when Enabled is unchecked.
3. Toggle Enabled and the Count cell becomes editable.
4. Save → quit → reload, both fields round-trip.
5. Run the protocol — `on_step` fires exactly once per row (verified via a logger info line in a custom handler subclass that counts invocations).

### 4.4 Scope check / non-goals

**In scope:** the framework, the synthetic demo column, tests, the headed verification script.

**Explicitly out:**
- Column-group **visual headers** (a banner spanning the N cells) — clean follow-up if useful, not blocking.
- Cross-row dependencies (purely intra-row here).
- Migrating PPT-3/4 columns to compound shape (no value, no churn).
- Backwards-compat shims for old persistence files (the schema is **additive** — old files lacking `compound_id` continue to load via the unchanged single-column codepath).

---

## Resolved during brainstorming

| Question | Resolution |
|---|---|
| Interface shape: extends, parallel, or replace IColumn? | **Parallel.** No risk to PPT-3/4. |
| Persistence shape for compound? | **Flat with `compound_id` discriminator.** Minimal schema change. Old single-cell saves keep working. |
| Demo column scope? | **Demo-only synthetic** (`pluggable_protocol_tree/demos/`), not a builtin. Two fields: `ec_enabled` Bool + `ec_count` Int with the count cell read-only when enabled is False. |
| Adapter approach vs parallel codepath? | **Adapter shim** — every consumer downstream of `_assemble_columns` keeps speaking `Column`/`IColumnModel`. Zero changes to RowManager, executor, MvcTreeModel, persistence walker. |
| Owner-field guard for execution hooks? | First field per compound is `is_owner=True`; only owner fires `on_step` / `on_pre_step` / `on_post_step` / `on_protocol_start` / `on_protocol_end`. `on_interact` always fires (per cell edit). |

## Remaining TODO

1. **User reviews written spec** — gate before invoking writing-plans.
2. **Invoke `superpowers:writing-plans`** — once approved, generate `docs/superpowers/plans/2026-04-27-ppt-11-compound-columns.md`.

The PPT-4 plan/spec are good templates: see `2026-04-24-ppt-4-voltage-frequency-design.md` and the corresponding plan file for tone, level of detail, and task structure.
