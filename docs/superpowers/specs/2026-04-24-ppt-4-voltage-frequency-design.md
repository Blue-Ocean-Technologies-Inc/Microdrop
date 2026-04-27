# PPT-4 — Voltage + Frequency columns (`dropbot_protocol_controls` plugin)

**Status:** READY FOR REVIEW — all four sections confirmed by the user. Pending spec self-review pass + user sign-off, then transition to writing-plans.

**Issue:** [#366](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/366) (umbrella [#361](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/361))

**Brainstorming session:** started 2026-04-24, paused, resumed 2026-04-27. All decisions captured below were confirmed by the user one at a time.

---

## Section 1 — Architecture & Topics ✅ CONFIRMED

Two new columns (`voltage` **Int V**, `frequency` **Int Hz**) **contributed by a new sibling plugin `dropbot_protocol_controls`** through the existing `PROTOCOL_COLUMNS` extension point. They appear after the PPT-3 builtins in the assembled column list. `dropbot_protocol_controls` is the first plugin to contribute through this extension point and **establishes the pattern** for future hardware controllers (each gets its own `<hw>_protocol_controls` sibling plugin — see Section 3 for the full rationale).

> **Type policy:** voltage and frequency are **Ints** end-to-end — column trait, payload, ack value, preference. Avoids float precision drift, matches the existing `on_set_voltage_request` which already writes `int(self.voltage)` to `DropbotPreferences.last_voltage`. dropbot.py's `proxy.update_state(voltage=...)` accepts ints transparently.

### New topics for protocol-driven hardware writes

Separate from the existing UI-driven `SET_VOLTAGE`/`SET_FREQUENCY` so the realtime-mode gate and prefs-persistence side effects don't apply to protocol writes.

| Direction | Topic | Payload |
|---|---|---|
| Protocol → DropBot | `dropbot/requests/protocol_set_voltage` | `"100"` |
| Protocol → DropBot | `dropbot/requests/protocol_set_frequency` | `"10000"` |
| DropBot → Protocol | `dropbot/signals/voltage_applied` | `"100"` (echo) |
| DropBot → Protocol | `dropbot/signals/frequency_applied` | `"10000"` (echo) |

### New request handlers in `DropbotStatesSettingMixinService`

```python
def on_protocol_set_voltage_request(self, message):
    v = int(message)
    with self.proxy.transaction_lock:
        self.proxy.update_state(voltage=v)
    publish_message(topic=VOLTAGE_APPLIED, message=str(v))

def on_protocol_set_frequency_request(self, message):
    # symmetric — int(message), update_state(frequency=...), publish FREQUENCY_APPLIED
```

No realtime-mode gate, no prefs write — protocol writes are unconditional and transient. Existing `on_set_voltage_request` / `on_set_frequency_request` stay untouched (UI path unchanged).

### Priority slot

Both `VoltageHandler` and `FrequencyHandler` at `priority = 20`. Same bucket → run in parallel via the executor's bucket pool. Different ack topics so no within-bucket conflict. Both finish their roundtrip before `RoutesHandler` at priority 30 publishes its first phase.

### Ack semantics

`on_protocol_set_voltage_request` publishes `VOLTAGE_APPLIED` immediately after `proxy.update_state(voltage=...)` returns successfully — i.e. RPC-write-completed semantics. Roundtrip ~10ms in production. Closed-loop confirmation via `capacitance_updated` could be added later if voltage settle time becomes a problem; out of scope for PPT-4.

---

## Section 2 — Column factories, defaults, and per-edit side effects ✅ CONFIRMED

### Default values

Column defaults read from the existing `DropbotPreferences.last_voltage` / `.last_frequency` at column-construction time (i.e. once per plugin start). Both the dropbot status panel and the protocol tree's Voltage / Frequency cells thus boot up to the same value.

### User cell-edit persists to prefs

When the user edits a Voltage / Frequency cell in the protocol tree, the column's `handler.on_interact` (called by `MvcTreeModel.setData` on EditRole / CheckStateRole) writes the new value back to `DropbotPreferences.last_voltage`. This means:

- Editing in the dropbot status panel spinner → updates prefs (existing behaviour).
- Editing in a protocol tree cell → updates prefs.
- Either edit becomes the default for the next new step + the next session's status-panel boot value.

### Executor run does NOT touch prefs

`VoltageHandler.on_step` and `FrequencyHandler.on_step` publish `PROTOCOL_SET_VOLTAGE` / `PROTOCOL_SET_FREQUENCY` and `wait_for` the ack — they do NOT write `preferences.last_voltage`. Protocol-driven writes are transient. Hundreds of step writes don't churn the user's preference.

---

## Section 3 — File layout & plugin contribution ✅ CONFIRMED

### New sibling plugin: `dropbot_protocol_controls/`

A new plugin package, sibling to `dropbot_controller/` and `pluggable_protocol_tree/`, that contributes hardware-coupled protocol columns. **Establishes the pattern:** any hardware-controller plugin that wants to expose protocol-tree columns gets a sibling `<hw>_protocol_controls` plugin. Keeps the runtime hardware controller (`dropbot_controller`) cleanly focused on USB/RPC, and keeps the protocol-tree extension code in its own package.

```
dropbot_protocol_controls/
├── __init__.py
├── plugin.py                            # DropbotProtocolControlsPlugin
├── consts.py                            # PKG only; topic constants live in dropbot_controller/consts.py
├── protocol_columns/
│   ├── __init__.py
│   ├── voltage_column.py                # VoltageColumnModel + spinner view + VoltageHandler + factory
│   └── frequency_column.py              # symmetric
└── tests/
    ├── test_voltage_column.py
    ├── test_frequency_column.py
    └── tests_with_redis_server_need/
        └── test_protocol_round_trip.py
```

### Edits to existing `dropbot_controller/`

| File | Change |
|---|---|
| `consts.py` | Add 4 topic constants: `PROTOCOL_SET_VOLTAGE`, `PROTOCOL_SET_FREQUENCY`, `VOLTAGE_APPLIED`, `FREQUENCY_APPLIED`. **No `ACTOR_TOPIC_DICT` changes** — existing `dropbot/requests/#` wildcard auto-routes the new request topics. |
| `services/dropbot_states_setting_mixin_service.py` | Add 2 new handlers `on_protocol_set_voltage_request` / `on_protocol_set_frequency_request` — symmetric to the existing UI handlers but **without** the realtime-mode gate and **without** the prefs persistence. Publish ack on RPC return. |

### `dropbot_protocol_controls/plugin.py`

```python
from envisage.plugin import Plugin
from traits.api import List, Instance

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name
from .protocol_columns.voltage_column import make_voltage_column
from .protocol_columns.frequency_column import make_frequency_column


class DropbotProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_voltage_column(), make_frequency_column()]
```

### Run-script wiring

Append `DropbotProtocolControlsPlugin` to whatever bundle already loads `DropbotControllerPlugin` (concretely: the backend / full-app entries in `examples/plugin_consts.py`). Pure-frontend bundles don't load it — they don't drive hardware.

### Topic ownership rationale

The 4 new topics are **dropbot-namespaced** (`dropbot/...`) and live in `dropbot_controller/consts.py`, even though one consumer (`VoltageHandler.wait_for(VOLTAGE_APPLIED)`) is in the new sibling plugin. This keeps topic constants colocated with the hardware controller that publishes them — `dropbot_protocol_controls` imports them. If we put topics in the sibling plugin, dropbot_controller would have to import from a plugin that depends on it, creating a back-edge.

---

## Section 4 — Tests, demo wiring, persistence ✅ CONFIRMED

### Unit tests (no Redis)

| File | Covers |
|---|---|
| `dropbot_protocol_controls/tests/test_voltage_column.py` | `VoltageHandler.on_step` publishes `PROTOCOL_SET_VOLTAGE` and waits for `VOLTAGE_APPLIED` (mocked broker); `on_step` does **not** touch prefs; `on_interact` writes `int(value)` to `DropbotPreferences.last_voltage`; factory instantiates cleanly; default reads from prefs. |
| `dropbot_protocol_controls/tests/test_frequency_column.py` | symmetric. |
| `dropbot_protocol_controls/tests/test_persistence.py` | Int traits round-trip through JSON via `RowManager.to_json` / `from_json`. (Confirms model.serialize/deserialize defaults are identity for Int; no custom code expected.) |
| `dropbot_controller/tests/test_protocol_set_handlers.py` | `on_protocol_set_voltage_request` / `..._frequency_request` call `proxy.update_state` and publish their ack topic; do **not** check `realtime_mode`; do **not** write prefs. Mock proxy + broker. |

### Integration test (Redis required)

`dropbot_protocol_controls/tests/tests_with_redis_server_need/test_voltage_frequency_protocol_round_trip.py` — full end-to-end:
- subscribe a stand-in voltage/frequency responder actor,
- build a protocol with `voltage=120`, `frequency=5000` on Step 1,
- run executor,
- assert the responder received both setpoints,
- assert both `_APPLIED` acks arrived **before** any `ELECTRODES_STATE_CHANGE` publish from priority-30 RoutesHandler.

### Demo responder

`dropbot_protocol_controls/demos/voltage_frequency_responder.py` — dramatiq actor that subscribes to `PROTOCOL_SET_VOLTAGE` / `PROTOCOL_SET_FREQUENCY`, sleeps a few ms, and publishes the matching `_APPLIED` ack. Mirrors `pluggable_protocol_tree/demos/electrode_responder.py`.

Also exports a small helper:

```python
def subscribe_demo_responder(router) -> None:
    """Subscribe the in-process voltage/frequency responder to its
    request topics on the given MessageRouterActor. Use after a
    ProtocolSession has been built with with_demo_hardware=True."""
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_VOLTAGE,
        subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_FREQUENCY,
        subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
    )
```

### ProtocolSession is oblivious

**No changes** to `pluggable_protocol_tree/session.py`. Layering stays clean — `pluggable_protocol_tree` has zero knowledge of `dropbot_protocol_controls`. Any demo that wants the voltage/frequency demo path opts in explicitly:

```python
session = ProtocolSession.from_file(path, with_demo_hardware=True)
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder,
)
subscribe_demo_responder(session._router)
```

### Auto-demo

`dropbot_protocol_controls/demos/run_voltage_frequency_demo.py` (NEW) is the dropbot-protocol-controls counterpart of `pluggable_protocol_tree/demos/run_session_demo.py`. Builds a sample protocol with all PPT-3 columns + the new voltage/frequency columns, opens a session with demo hardware, calls `subscribe_demo_responder`, runs end-to-end. This is the script someone runs to verify the new plugin works in isolation.

The existing `pluggable_protocol_tree/demos/*.py` are **not** modified — they stay pure to PPT-3.

### Persistence

`Int` traits round-trip through the existing JSON persistence with no changes (model.serialize/deserialize defaults to identity for Int). Confirm in `test_persistence.py` above.

---

## Backwards compatibility

Old protocol JSON files saved before PPT-4 won't have `voltage` / `frequency` columns recorded. Behaviour:
- **`ProtocolSession.from_file(path)`** resolves columns from the file's `cls` qualnames, so an old file loads with **no** voltage/frequency columns and runs with no setpoint write. (DropBot keeps whatever voltage/frequency it last had — typically the UI's `last_voltage` / `last_frequency`.)
- **Full GUI app** uses `_assemble_columns` to build the union of all contributed columns, so opening an old file fills voltage/frequency cells from `DropbotPreferences` defaults. Saving re-emits with the new columns present.

No migration code needed.

## Resolved during brainstorming

| Question | Resolution |
|---|---|
| Where does `handler.on_interact` write the preference? | `DropbotPreferences()` — `PreferencesHelper` attaches to the global preferences object set during envisage startup, so a no-arg construct in the handler is fine. Same pattern used in `dropbot_controller/preferences.py:22-25`. |
| What about the legacy `protocol_grid`? | Same approach as PPT-3: leave it alone. It keeps its existing voltage/frequency code path. The new columns are pluggable-protocol-tree-only. |
| Type for voltage/frequency? | **Int** end-to-end. See "Type policy" callout in Section 1. |

## Remaining TODO

1. **User reviews written spec** — gate before invoking writing-plans.
2. **Invoke `superpowers:writing-plans`** — once approved, generate `docs/superpowers/plans/2026-04-24-ppt-4-voltage-frequency.md`.

The PPT-3 plan/spec are good templates: see `2026-04-23-ppt-3-electrodes-routes-design.md` and the corresponding plan file for tone, level of detail, and task structure.
