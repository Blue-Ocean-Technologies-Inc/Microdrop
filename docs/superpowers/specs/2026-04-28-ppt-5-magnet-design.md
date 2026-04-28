# PPT-5 — Magnet column (`peripheral_protocol_controls` plugin)

**Status:** READY FOR REVIEW — all three sections confirmed by the user during brainstorming. Pending self-review pass + final approval, then transition to writing-plans.

**Issue:** [#367](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/367) (umbrella [#361](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/361))

**Depends on:** [#378 / PR #379 (PPT-11)](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/pull/379) — compound column framework. **Merged into main.**

**Brainstorming session:** 2026-04-27 (paused for PPT-11 framework prereq), resumed 2026-04-28. All decisions captured below were confirmed by the user one at a time.

---

## Why this exists

Migrate the legacy `protocol_grid`'s coupled `Magnet` checkbox + `Magnet Height (mm)` columns to the new pluggable protocol tree, contributed by a new sibling plugin `peripheral_protocol_controls` (parallel to PPT-4's `dropbot_protocol_controls`). This is the **first real consumer of the PPT-11 compound column framework** — uses two coupled cells sharing one model + one handler.

---

## Section 1 — Architecture ✅ CONFIRMED

### Plugin layering

**New plugin: `peripheral_protocol_controls`** — sibling to `peripheral_controller` (mirrors PPT-4's `dropbot_protocol_controls` ↔ `dropbot_controller` pattern). Lives in `FRONTEND_PLUGINS`. Contributes ONE `MagnetCompoundColumn` (a `CompoundColumn`) through the existing `PROTOCOL_COLUMNS` extension point. The peripheral RPC handlers stay in `peripheral_controller` (backend).

### Compound shape (2 visible cells per row)

| Field | Type | Header | Default | Notes |
|---|---|---|---|---|
| `magnet_on` | Bool | "Magnet" | `False` | `CheckboxColumnView` |
| `magnet_height_mm` | Float | "Magnet Height (mm)" | `MIN_ZSTAGE_HEIGHT_MM - 0.5` (= 0.0, the "Default" sentinel) | Custom `MagnetHeightSpinBoxView` with `setSpecialValueText("Default")` |

**Conditional editability:** `magnet_height_mm` cell is read-only when `row.magnet_on=False` — implemented via the cell view's `get_flags(row)` reading the sibling field (the canonical PPT-11 cross-cell pattern).

**Type policy:** voltage/frequency are Int (PPT-4); magnet height is **Float** — physically meaningful as 0.5/0.6/.../28.0 mm on a 0.1 mm grid. Int would lose precision.

### Storage of the "Default" sentinel

Single Float field, no Union types. The sentinel value `MIN_ZSTAGE_HEIGHT_MM - 0.5 = 0.0` represents "Default mode" (use the user's live `up_height_mm` pref at runtime). Spinbox renders the sentinel as `"Default"` via Qt's `setSpecialValueText("Default")` (matches the legacy UX exactly — see `protocol_grid/protocol_grid_helpers.py:112-126` for the legacy pattern). The user can spin up from the sentinel to numeric values; the spinbox displays numeric for any value `>= MIN_ZSTAGE_HEIGHT_MM`.

This preserves the legacy "Default" semantic dynamically — when `magnet_height_mm < MIN_ZSTAGE_HEIGHT_MM`, the backend reads `PeripheralPreferences().up_height_mm` at runtime, so user pref changes take effect for "Default" steps without re-editing.

### Topics (new, on the peripheral side)

| Direction | Topic | Payload |
|---|---|---|
| Protocol → ZStage | `ZStage/requests/protocol_set_magnet` | JSON `{"on": bool, "height_mm": float}` |
| ZStage → Protocol | `ZStage/signals/magnet_applied` | `"1"` (engaged) or `"0"` (retracted) |

The `peripheral_controller` listener already subscribes to `f"{DEVICE_NAME}/requests/#"` (wildcard at `peripheral_controller/consts.py:30`), so the new request topic auto-routes to `on_protocol_set_magnet_request` — **no `ACTOR_TOPIC_DICT` change needed**.

### Backend handler in `ZStageStatesSetterMixinService`

`on_protocol_set_magnet_request(self, message)` — atomic protocol-driven engage/retract:

- Parse JSON `{"on": bool, "height_mm": float}`
- If `on=False` → run the legacy retract sequence (`proxy.zstage.down()`, `time.sleep(0.3)`, `proxy.zstage.home()`) atomically. Backend owns the settling-time + sequencing so the protocol handler stays simple.
- If `on=True` AND `height_mm < MIN_ZSTAGE_HEIGHT_MM` → sentinel = "use live pref": `proxy.zstage.position = PeripheralPreferences().up_height_mm`
- If `on=True` AND `height_mm >= MIN_ZSTAGE_HEIGHT_MM` → `proxy.zstage.position = height_mm`
- Publish `MAGNET_APPLIED` ack on completion (after the physical movement settles, since `proxy.zstage.position = ...` is synchronous and waits for hardware)
- Wraps the body in the same `try/except (TimeoutError, RuntimeError)` log+swallow + `except Exception` log+raise pattern used by the existing `on_set_voltage_request` / `on_set_position_request` handlers
- No realtime-mode gate (peripheral has no such gate); no prefs persistence (the user changes `up_height_mm` via the peripherals_ui status panel, not via protocol cells)

### Priority + ack semantics

`MagnetHandler.priority = 20` — same bucket as voltage/frequency (PPT-4). All three run in parallel within the bucket; bucket completes when the slowest finishes. Then `RoutesHandler` at priority 30 runs. Magnet movement is the slowest of the three (seconds vs. ms); the bucket-completion model handles this naturally.

`MagnetHandler.on_step` publishes once and `wait_for(MAGNET_APPLIED, timeout=10.0)` — longer than v/f's 5s because physical magnet movement is slow.

**Why a new `protocol_set_magnet` topic instead of reusing existing `MOVE_DOWN` + `GO_HOME` + `SET_POSITION`:** the off-state retract requires a sequenced two-publish dance with two ack-waits + a settling sleep on the protocol side. Putting that sequence on the backend (in one new handler) makes the protocol-side a single publish + single wait. Mirrors PPT-4's "new protocol_* topic" pattern.

---

## Section 2 — Column factories, defaults, file layout ✅ CONFIRMED

### File layout

```
peripheral_protocol_controls/                    NEW PLUGIN
├── __init__.py
├── plugin.py                                    # PeripheralProtocolControlsPlugin
├── consts.py                                    # PKG only; topics live in peripheral_controller/consts.py
├── protocol_columns/
│   ├── __init__.py
│   └── magnet_column.py                         # MagnetCompoundModel + handler + factory + custom view
├── demos/
│   ├── __init__.py
│   ├── magnet_responder.py                      # in-process responder + subscribe_demo_responder helper
│   └── run_widget_magnet_demo.py                # headed visual smoke
└── tests/
    ├── __init__.py
    ├── conftest.py                              # broker setup (mirrors PPT-4)
    ├── test_magnet_column.py                    # model + handler + view tests
    └── tests_with_redis_server_need/
        ├── __init__.py
        ├── conftest.py
        └── test_magnet_protocol_round_trip.py   # priority ordering + setpoint values
```

### Edits to existing `peripheral_controller/`

| File | Change |
|---|---|
| `consts.py` | Add 2 topic constants: `PROTOCOL_SET_MAGNET = f"{DEVICE_NAME}/requests/protocol_set_magnet"` and `MAGNET_APPLIED = f"{DEVICE_NAME}/signals/magnet_applied"`. **No `ACTOR_TOPIC_DICT` change** — existing `f"{DEVICE_NAME}/requests/#"` wildcard already routes the new request topic. |
| `services/zstage_state_setter_service.py` | Add 1 new handler `on_protocol_set_magnet_request(self, message)` — atomic engage/retract per Section 1. Existing UI handlers (`on_set_position_request`, `on_move_up_request`, `on_move_down_request`, `on_go_home_request`) untouched. |

### `magnet_column.py` skeleton

```python
class MagnetCompoundModel(BaseCompoundColumnModel):
    base_id = "magnet"

    def field_specs(self):
        return [
            FieldSpec("magnet_on", "Magnet", False),
            FieldSpec("magnet_height_mm", "Magnet Height (mm)",
                      float(MIN_ZSTAGE_HEIGHT_MM - 0.5)),  # sentinel = "Default"
        ]

    def trait_for_field(self, field_id):
        if field_id == "magnet_on":
            return Bool(False)
        if field_id == "magnet_height_mm":
            return Float(float(MIN_ZSTAGE_HEIGHT_MM - 0.5))
        raise KeyError(field_id)


class MagnetHeightSpinBoxView(DoubleSpinBoxColumnView):
    """Spinbox that displays the sentinel value as 'Default' (legacy UX
    parity) and is read-only when row.magnet_on is False. Cross-cell
    editability via the canonical PPT-11 get_flags(row) pattern."""

    def create_editor(self, parent, context):
        e = super().create_editor(parent, context)
        e.setSpecialValueText("Default")
        return e

    def format_display(self, value, row):
        # Sentinel range matches the backend's threshold: any value
        # below MIN_ZSTAGE_HEIGHT_MM is interpreted as "Default" (use
        # live pref). Keeps the cell display + backend semantics aligned.
        if value < MIN_ZSTAGE_HEIGHT_MM:
            return "Default"
        return super().format_display(value, row)

    def get_flags(self, row):
        flags = super().get_flags(row)
        if not getattr(row, "magnet_on", False):
            flags &= ~Qt.ItemIsEditable
        return flags


class MagnetHandler(BaseCompoundColumnHandler):
    """Priority 20 — parallel with VoltageHandler / FrequencyHandler in
    the same bucket; runs before RoutesHandler (priority 30). 10s timeout
    on the ack — physical magnet movement is slower than RPC writes."""
    priority = 20
    wait_for_topics = [MAGNET_APPLIED]

    def on_step(self, row, ctx):
        payload = json.dumps({
            "on": bool(row.magnet_on),
            "height_mm": float(row.magnet_height_mm),
        })
        publish_message(topic=PROTOCOL_SET_MAGNET, message=payload)
        ctx.wait_for(MAGNET_APPLIED, timeout=10.0)

    # No on_interact override — magnet column does NOT persist user
    # cell-edits to PeripheralPreferences. The user changes up_height_mm
    # via the peripherals_ui status panel, not via protocol cells.


def make_magnet_column():
    return CompoundColumn(
        model=MagnetCompoundModel(),
        view=DictCompoundColumnView(cell_views={
            "magnet_on": CheckboxColumnView(),
            "magnet_height_mm": MagnetHeightSpinBoxView(
                low=float(MIN_ZSTAGE_HEIGHT_MM - 0.5),
                high=float(MAX_ZSTAGE_HEIGHT_MM),
                decimals=2, single_step=0.1,
            ),
        }),
        handler=MagnetHandler(),
    )
```

### Backend `on_protocol_set_magnet_request` skeleton

In `ZStageStatesSetterMixinService` (decorator stack matches the existing handlers in the same file):

```python
@thread_lock_with_error_handling
@zstage_motor_context
@publish_position_update
def on_protocol_set_magnet_request(self, message):
    """Protocol-driven magnet engage/retract. Atomic: handles the
    retract sequence (MOVE_DOWN + 0.3s settle + GO_HOME) on the backend
    so the protocol handler only does one publish + one wait_for. On
    hardware error, ack is NOT published — protocol's wait_for times
    out and the step fails (consistent with PPT-4's protocol handler
    pattern)."""
    try:
        payload = json.loads(message)
        on = bool(payload["on"])
        height_mm = float(payload["height_mm"])

        if not on:
            # Retract sequence — matches legacy publish_magnet_home()
            self.proxy.zstage.down()
            time.sleep(0.3)   # settling time before next command
            self.proxy.zstage.home()
        elif height_mm < MIN_ZSTAGE_HEIGHT_MM:
            # Sentinel = "use live pref"
            target = PeripheralPreferences().up_height_mm
            self.proxy.zstage.position = float(target)
        else:
            self.proxy.zstage.position = float(height_mm)

        publish_message(topic=MAGNET_APPLIED, message=str(int(on)))
    except (TimeoutError, RuntimeError) as e:
        logger.error(f"Proxy error on protocol_set_magnet: {e}")
    except Exception as e:
        logger.error(f"Error on protocol_set_magnet: {e}")
        raise
```

### `peripheral_protocol_controls/plugin.py`

```python
from envisage.plugin import Plugin
from traits.api import Instance, List

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn

from .consts import PKG, PKG_name
from .protocol_columns.magnet_column import make_magnet_column


class PeripheralProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(ICompoundColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_magnet_column()]
```

Note the trait type: `List(Instance(ICompoundColumn))` — magnet is the only contribution, and it's a compound, so the trait can be narrowly typed. (PPT-4's `dropbot_protocol_controls` plugin uses `List(Instance(IColumn))` because voltage/frequency are simple columns.)

### Run-script wiring

Append `PeripheralProtocolControlsPlugin` to whatever bundle already loads `PeripheralControllerPlugin` — concretely, add to `FRONTEND_PLUGINS` in `examples/plugin_consts.py` (where the other `*_protocol_controls` and `pluggable_protocol_tree` plugins live).

### Defaults / no-prefs-write policy

- `magnet_on` defaults `False` on new steps (no engage by default — user opts in)
- `magnet_height_mm` defaults to `MIN_ZSTAGE_HEIGHT_MM - 0.5` (= 0.0 = "Default" sentinel) — new steps say "use the user's current pref at runtime"
- **`on_interact` does NOT persist user cell-edits to `PeripheralPreferences`** (this differs from PPT-4 voltage/frequency, which DO persist). Reasoning: voltage/frequency are typically global session settings that the user wants to "stick" across protocols; magnet height is more experiment-step-specific. The user changes `up_height_mm` via the peripherals_ui status panel for global behaviour.

---

## Section 3 — Tests, demo wiring, persistence ✅ CONFIRMED

### Unit tests (`peripheral_protocol_controls/tests/test_magnet_column.py`)

| Test | Verifies |
|---|---|
| `test_magnet_compound_model_field_specs` | Two fields with right ids/names/defaults; `magnet_height_mm` default = sentinel value |
| `test_magnet_compound_model_traits` | `trait_for_field("magnet_on")` is Bool; `magnet_height_mm` is Float |
| `test_magnet_height_view_displays_default_at_sentinel` | `format_display(0.0, row)` returns `"Default"`; `format_display(5.0, row)` returns formatted float |
| `test_magnet_height_view_read_only_when_magnet_off` | `get_flags(row)` strips `Qt.ItemIsEditable` when `row.magnet_on=False`; restores when True |
| `test_magnet_height_view_special_value_text_set_on_editor` | `create_editor(...)` returns a QDoubleSpinBox with `specialValueText() == "Default"` |
| `test_magnet_handler_priority_20` | priority is 20 |
| `test_magnet_handler_wait_for_topics_includes_magnet_applied` | wait_for_topics list |
| `test_magnet_handler_on_step_publishes_engage_payload` | mocked broker; `magnet_on=True, magnet_height_mm=5.0` → JSON payload `{"on": true, "height_mm": 5.0}`; `wait_for(MAGNET_APPLIED, timeout=10.0)` |
| `test_magnet_handler_on_step_publishes_retract_payload` | `magnet_on=False` → JSON `{"on": false, "height_mm": 0.0}` (height included but ignored backend-side) |
| `test_magnet_handler_on_step_publishes_default_sentinel_payload` | `magnet_on=True, magnet_height_mm=0.0` (sentinel) → JSON has `height_mm: 0.0`; the backend interprets the sentinel — handler doesn't pre-resolve |
| `test_make_magnet_column_returns_compound_with_two_fields` | factory returns `CompoundColumn` with `["magnet_on", "magnet_height_mm"]` field ids in order |

### Backend handler tests (`peripheral_controller/tests/test_protocol_set_magnet.py`)

| Test | Verifies |
|---|---|
| `test_protocol_set_magnet_off_runs_retract_sequence` | `{"on": false, ...}` → calls `proxy.zstage.down()`, then sleeps 0.3s, then `proxy.zstage.home()` (verify call order); publishes `MAGNET_APPLIED` with payload `"0"` |
| `test_protocol_set_magnet_on_with_specific_height` | `{"on": true, "height_mm": 12.5}` → assigns `proxy.zstage.position = 12.5`; publishes `MAGNET_APPLIED` with payload `"1"` |
| `test_protocol_set_magnet_on_with_sentinel_uses_live_pref` | `{"on": true, "height_mm": 0.0}` (sentinel) → patches `PeripheralPreferences()` to return `up_height_mm = 22.5`; asserts `proxy.zstage.position` was set to 22.5 (NOT 0.0) |
| `test_protocol_set_magnet_does_not_persist_to_prefs` | Sentinel pre-set on `prefs.up_height_mm = 999`; run handler with `height_mm=5.0` (explicit); assert `prefs.up_height_mm == 999` (handler reads pref only when sentinel; never writes pref) |

### Integration test (Redis required)

`peripheral_protocol_controls/tests/tests_with_redis_server_need/test_magnet_protocol_round_trip.py` — full chain with the in-process magnet responder. Three sub-tests:

1. **Setpoint values reach the responder:** build a protocol with magnet=on/height=5.0 step; run executor; assert the responder received the correct JSON payload.
2. **Priority ordering:** a step with magnet=on AND electrodes set; assert `MAGNET_APPLIED` ack arrived **before** any `ELECTRODES_STATE_CHANGE` publish (priority 20 < 30, architecturally enforced via `_run_hooks` bucket sequencing).
3. **No prefs interference:** pre-set `PeripheralPreferences().up_height_mm = 999`; run a protocol with `height_mm=5.0` (explicit); assert pref still 999 after run.

### Demo wiring (`peripheral_protocol_controls/demos/`)

**`magnet_responder.py`** — in-process Dramatiq actor + turnkey subscribe helper, mirroring `dropbot_protocol_controls.demos.voltage_frequency_responder`:

```python
DEMO_MAGNET_RESPONDER_ACTOR_NAME = "ppt_demo_magnet_responder"
EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"
DEMO_APPLY_DELAY_S = 0.05  # simulates physical movement


@dramatiq.actor(actor_name=DEMO_MAGNET_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_magnet_responder(message: str, topic: str, timestamp: float = None):
    logger.info("[demo magnet responder] received %r on %s", message, topic)
    payload = json.loads(message)
    time.sleep(DEMO_APPLY_DELAY_S)
    publish_message(message=str(int(payload["on"])), topic=MAGNET_APPLIED)


def subscribe_demo_responder(router) -> None:
    """Wire the in-process magnet demo responder + executor listener
    on `router`. Same turnkey shape as
    dropbot_protocol_controls.demos.voltage_frequency_responder."""
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_MAGNET,
        subscribing_actor_name=DEMO_MAGNET_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=MAGNET_APPLIED,
        subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
    )
```

**`run_widget_magnet_demo.py`** — Qt window with the protocol tree showing the existing PPT-3 builtins + the magnet compound column. Auto-populates 3 sample steps:
1. `magnet_on=True, magnet_height_mm=Default (sentinel)` — should engage at the live `up_height_mm` pref
2. `magnet_on=True, magnet_height_mm=12.0` — explicit height
3. `magnet_on=False` — retract sequence

Status bar shows current magnet state (last seen `MAGNET_APPLIED` payload). `ProtocolSession` stays oblivious — same opt-in pattern as PPT-4. Demo manually calls `subscribe_demo_responder(session._router)`.

### Persistence

The compound framework (PPT-11) handles round-trip natively via `compound_id` + `compound_field_id` discriminators. No custom serialize/deserialize needed — Float values round-trip through JSON identity. PPT-11's `test_compound_persistence` already covers the framework-level round-trip; this spec's test_magnet_column.py adds a column-level round-trip smoke test.

---

## Backwards compatibility

Old protocol JSON files saved before PPT-5 won't have the `magnet` compound column entries. Behaviour:
- `ProtocolSession.from_file(path)` resolves columns from the file's `cls` qualnames, so an old file loads with no magnet entries and runs with no magnet engage/retract published. Existing magnet position on the hardware is unchanged.
- Full GUI app uses `_assemble_columns` to build the union of all contributed columns, so opening an old file fills magnet cells from defaults (`magnet_on=False`, `magnet_height_mm=Default`). Saving re-emits with the magnet compound present.

No migration code needed.

## Resolved during brainstorming

| Question | Resolution |
|---|---|
| Column shape: 2 or 3 fields? | **2 fields** — `magnet_on` Bool + `magnet_height_mm` Float. The "Default" semantic lives in the spinbox `setSpecialValueText` + sentinel value (`MIN_ZSTAGE_HEIGHT_MM - 0.5 = 0.0`). |
| "Default" handling: freeze vs dynamic? | **Dynamic** — sentinel value in storage; backend reads live `up_height_mm` pref when sentinel is seen. Preserves legacy behaviour where pref changes affect "Default" steps. |
| Topic design: reuse existing or new protocol topic? | **New `protocol_set_magnet` topic** — backend owns the retract sequence (MOVE_DOWN + settle + GO_HOME). Mirrors PPT-4 pattern. |
| Type for magnet height? | **Float** (Int would lose precision on the 0.1 mm spinbox grid). |
| Wait timeout? | **10 seconds** (longer than v/f's 5s — physical movement is slow). |
| Persist user cell-edits to prefs? | **No** — magnet height is more step-specific than v/f. User changes `up_height_mm` via peripherals_ui status panel for global behaviour. |
| Plugin location? | `FRONTEND_PLUGINS` (column declarations are a UI concern; backend RPC handlers stay in `peripheral_controller`). |

## Remaining TODO

1. **User reviews written spec** — gate before invoking writing-plans.
2. **Invoke `superpowers:writing-plans`** — once approved, generate `docs/superpowers/plans/2026-04-28-ppt-5-magnet.md`.

The PPT-4 plan/spec are good single-cell-column templates: `2026-04-24-ppt-4-voltage-frequency-design.md`. The PPT-11 plan/spec are good compound-framework templates: `2026-04-27-ppt-11-compound-columns-design.md`. PPT-5 sits at the intersection.
