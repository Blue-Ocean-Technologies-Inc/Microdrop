# PPT-4 — Voltage + Frequency columns (dropbot_controller contribution)

**Status:** WORK-IN-PROGRESS — design draft, not yet finalised. Sections 2-4 + spec self-review + user approval still pending. See "Open Questions / TODO" at the bottom.

**Issue:** [#366](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/366) (umbrella [#361](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/361))

**Brainstorming session (paused):** 2026-04-24, in conversation with the user. All decisions captured below were confirmed by the user one at a time. Sections marked DRAFT have not yet been presented for approval.

---

## Section 1 — Architecture & Topics ✅ CONFIRMED

Two new columns (`voltage` Float V, `frequency` Float Hz) **contributed by the dropbot_controller plugin** through the existing `PROTOCOL_COLUMNS` extension point. They appear after the PPT-3 builtins in the assembled column list. dropbot_controller becomes the first non-core plugin to contribute columns — sets the template for any future hardware contributions.

### New topics for protocol-driven hardware writes

Separate from the existing UI-driven `SET_VOLTAGE`/`SET_FREQUENCY` so the realtime-mode gate and prefs-persistence side effects don't apply to protocol writes.

| Direction | Topic | Payload |
|---|---|---|
| Protocol → DropBot | `dropbot/requests/protocol_set_voltage` | `"100.0"` |
| Protocol → DropBot | `dropbot/requests/protocol_set_frequency` | `"10000.0"` |
| DropBot → Protocol | `dropbot/signals/voltage_applied` | `"100.0"` (echo) |
| DropBot → Protocol | `dropbot/signals/frequency_applied` | `"10000.0"` (echo) |

### New request handlers in `DropbotStatesSettingMixinService`

```python
def on_protocol_set_voltage_request(self, message):
    v = float(message)
    with self.proxy.transaction_lock:
        self.proxy.update_state(voltage=v)
    publish_message(topic=VOLTAGE_APPLIED, message=str(v))

def on_protocol_set_frequency_request(self, message):
    # symmetric
```

No realtime-mode gate, no prefs write — protocol writes are unconditional and transient. Existing `on_set_voltage_request` / `on_set_frequency_request` stay untouched (UI path unchanged).

### Priority slot

Both `VoltageHandler` and `FrequencyHandler` at `priority = 20`. Same bucket → run in parallel via the executor's bucket pool. Different ack topics so no within-bucket conflict. Both finish their roundtrip before `RoutesHandler` at priority 30 publishes its first phase.

### Ack semantics

`on_protocol_set_voltage_request` publishes `VOLTAGE_APPLIED` immediately after `proxy.update_state(voltage=...)` returns successfully — i.e. RPC-write-completed semantics. Roundtrip ~10ms in production. Closed-loop confirmation via `capacitance_updated` could be added later if voltage settle time becomes a problem; out of scope for PPT-4.

---

## Section 2 — Column factories, defaults, and per-edit side effects ✅ CONFIRMED (decisions made; spec text DRAFT)

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

## Section 3 — File layout & plugin contribution 🟡 DRAFT (not yet presented to user)

Tentative layout — to be confirmed in section presentation:

```
dropbot_controller/
├── plugin.py                                  # extend with contributed_protocol_columns
├── consts.py                                  # add 4 new topics + ACTOR_TOPIC_DICT entries
├── services/
│   └── dropbot_states_setting_mixin_service.py  # add 2 new on_*_request handlers
└── protocol_columns/
    ├── __init__.py
    ├── voltage_column.py                      # VoltageColumnModel + VoltageHandler + factory
    └── frequency_column.py                    # symmetric
```

`dropbot_controller/plugin.py` gets:

```python
from traits.api import List, Instance
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn
from .protocol_columns.voltage_column import make_voltage_column
from .protocol_columns.frequency_column import make_frequency_column

contributed_protocol_columns = List(
    Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
)

def _contributed_protocol_columns_default(self):
    return [make_voltage_column(), make_frequency_column()]
```

---

## Section 4 — Tests, demo wiring, persistence 🟡 DRAFT (not yet presented to user)

### Unit tests

- `dropbot_controller/tests/test_protocol_columns.py` — VoltageHandler / FrequencyHandler behaviour with mocked broker (publish + wait_for sequence; ack flows; no-prefs-write under run; prefs-write under interact).
- Test that the column factories instantiate cleanly and read prefs correctly.

### Integration test (Redis required)

- `dropbot_controller/tests/tests_with_redis_server_need/test_voltage_frequency_protocol_round_trip.py` — full end-to-end: subscribe a stand-in voltage/frequency responder, build a protocol with voltage=120, frequency=5000, run executor, assert the responder received both setpoints and that the ack arrived before any actuation publish.

### Demo wiring

Extend `pluggable_protocol_tree/demos/run_widget.py`, `run_widget_auto.py`, `run_session_demo.py`, `run_headless.py` so:

- A voltage/frequency stand-in responder actor (similar to `electrode_responder`) is registered when `with_demo_hardware=True`.
- The auto-demo's sample protocol sets voltage + frequency on at least one step so the chain is exercised end-to-end.

### Persistence

`Float` traits round-trip through the existing JSON persistence with no changes (model.serialize/deserialize defaults to identity for Float). Confirm in a unit test.

---

## Open Questions / TODO

1. **Section 3 + 4 not yet presented** — present them to the user for sign-off before writing the impl plan.
2. **Where exactly does `handler.on_interact` write the preference?** Confirm the column's `BaseColumnHandler.on_interact` signature lets it reach a singleton DropbotPreferences instance, or pass it via factory closure.
3. **What about the legacy `protocol_grid`?** Same approach as PPT-3: leave it alone, let it keep using its own voltage/frequency code path. Confirm this with user.
4. **Backwards compat for old protocol files** — old saves won't have voltage/frequency columns. ProtocolSession.from_file resolves columns from the file, so old files would load without these columns and run with no voltage/frequency setpoint. The full app uses `_assemble_columns` (all columns), so opening an old file in the GUI fills voltage/frequency from defaults. Worth a one-paragraph callout in the spec; no code change needed.
5. **Spec self-review** — placeholder scan, internal consistency, scope check (per the brainstorming skill checklist).
6. **User reviews written spec** — gate before invoking writing-plans.
7. **Then writing-plans** — once approved, generate `docs/superpowers/plans/2026-04-24-ppt-4-voltage-frequency.md`.

## Resumption checklist

When picking this back up:

1. Re-read this spec to refresh decisions.
2. Open the brainstorming dialog at "Section 3 (File layout & plugin contribution) — does this look right?".
3. After Section 3 approval, ask about Section 4.
4. Resolve open questions 2-4.
5. Run spec self-review.
6. Get user sign-off.
7. Invoke `superpowers:writing-plans`.

The PPT-3 plan/spec are good templates: see `2026-04-23-ppt-3-electrodes-routes-design.md` and the corresponding plan file for tone, level of detail, and task structure.
