# PPT-12 — Demo base window + full integration demo (composition)

**Status:** READY FOR REVIEW — all three sections confirmed by the user during brainstorming. Pending self-review pass + final approval, then transition to writing-plans.

**Issue:** [#385](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/385) (standalone — not under #361)

**Follow-up issue:** [#386](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/386) — replace per-demo Dramatiq ack listeners with an executor-emitted `step_phase_started` Qt signal. Out of scope for PPT-12; will land after #385 merges.

**Brainstorming session:** 2026-04-28, in conversation with the user.

---

## Why this exists

Each existing demo (`pluggable_protocol_tree.demos.run_widget` PPT-3, `dropbot_protocol_controls.demos.run_widget_with_vf` PPT-4, `pluggable_protocol_tree.demos.run_widget_compound_demo` PPT-11, `peripheral_protocol_controls.demos.run_widget_magnet_demo` PPT-5) reimplements the same UX scaffolding: active-row highlight, status bar with step counter + row name + step/phase timers, button state machine, Save/Load, stale-subscriber purge, phase-ack listener. Each new column-migration sub-issue copies the boilerplate again.

Today PPT-5's demo is missing some of these features (no active-row highlight, no per-step/per-phase timers) — caught by the user during manual testing. Rather than patch PPT-5's demo inline, this issue extracts the common UX into a single base class so:

1. Every demo gets the standard UX **for free**.
2. Future column-migration sub-issues (PPT-6/7/8/10) cost ~50 LOC of demo glue instead of ~500 LOC of full demo file.
3. A single integration demo can exercise EVERY column at once — exposes priority-bucketing behaviour and integration concerns no individual demo can show.

---

## Section 1 — Architecture: composition shape ✅ CONFIRMED

The base is a Qt window class that takes a `DemoConfig` dataclass. Demos are tiny scripts that build the config and call `BasePluggableProtocolDemoWindow.run(config)`. **No subclassing**.

### `pluggable_protocol_tree/demos/base_demo_window.py`

```python
@dataclass
class StatusReadout:
    """One ack-driven readout label in the status bar.

    The base creates one Dramatiq actor per StatusReadout (auto-named
    ppt12_demo_<label_slug>_listener) that subscribes to `topic`,
    emits a Qt signal, and updates a QLabel in the status bar with
    `f"{label}: {fmt(message)}"`. Until the first ack, the label
    shows `f"{label}: {initial}"`.
    """
    label: str           # display prefix, e.g. "Voltage"
    topic: str           # ack topic to subscribe to
    fmt: Callable[[str], str]   # message → displayed text after the prefix
    initial: str = "--"  # initial text shown before any ack lands


@dataclass
class DemoConfig:
    """Everything a demo needs to declare. All fields except
    columns_factory have sensible defaults."""

    # Required: returns the column list.
    columns_factory: Callable[[], list[Column]]

    # Cosmetic.
    title: str = "Pluggable Protocol Tree Demo"
    window_size: tuple[int, int] = (1100, 650)

    # Optional sample steps populated after RowManager construction.
    pre_populate: Callable[[RowManager], None] = lambda rm: None

    # Subscribe demo responders / additional listeners on the router.
    # Called AFTER the base wires the standard PPT-3 electrode chain
    # + the phase-ack listener (if phase_ack_topic is set) +
    # the StatusReadout listeners.
    routing_setup: Callable[[Any], None] = lambda router: None

    # Single ack topic that drives the per-phase timer.
    # If None: only step-elapsed timer shown, no per-phase timer.
    # Default ELECTRODES_STATE_APPLIED matches PPT-3 / integration-demo
    # semantics (the priority-30 ack is the real phase boundary).
    phase_ack_topic: str | None = ELECTRODES_STATE_APPLIED

    # Right-side status bar readouts.
    status_readouts: list[StatusReadout] = field(default_factory=list)

    # Side panel (e.g., SimpleDeviceViewer for PPT-3 / integration demo).
    # Returns a QWidget or None. Called once during window setup.
    side_panel_factory: Callable[[RowManager], QWidget | None] | None = None


class BasePluggableProtocolDemoWindow(QMainWindow):
    """Hosts a ProtocolTreeWidget + ProtocolExecutor with the standard
    UX scaffolding."""

    def __init__(self, config: DemoConfig): ...

    @classmethod
    def run(cls, config: DemoConfig) -> int:
        """Convenience: creates QApplication if none exists, builds
        the window, shows it, runs app.exec(). Returns exit code."""
```

### What the base owns

- `RowManager`, `ProtocolTreeWidget`, `ProtocolExecutor` construction
- Active-row highlight wired from `executor.qsignals.step_started`
- Status bar with: step counter / row label + path / reps / step elapsed timer / phase elapsed timer (if `phase_ack_topic` set) / one QLabel per `StatusReadout`
- 10 Hz tick timer for elapsed-time refresh
- Phase-ack listener — auto-named Dramatiq actor subscribed to `phase_ack_topic` if set; emits Qt signal that restarts per-phase timer from the actual ack moment
- StatusReadout listeners — one Dramatiq actor per readout
- Pause/Resume/Stop button state machine (Run, Pause→Resume toggle, Stop)
- Save/Load toolbar buttons (open file dialog, JSON serialize/deserialize via `RowManager.to_json` / `set_state_from_json`)
- Add Step / Add Group toolbar buttons
- Stale-subscriber purge — drops actor names recorded in Redis whose actors aren't registered in the current process; only touches `ppt_demo_*`, `ppt4_demo_*`, `ppt5_demo_*`, `ppt11_demo_*`, `ppt12_demo_*`, `ppt_vf_demo_*` prefixed names (leaves real listeners belonging to other processes alone)
- `_clear_all_highlights` on protocol end / abort / error — restores idle visual state including resetting StatusReadout labels to their `initial` text
- In-process Dramatiq Worker started in `__init__`, stopped in `closeEvent`
- Splitter layout — protocol tree + side panel (if `side_panel_factory` returns one)
- Standard middleware strip via `microdrop_utils.broker_server_helpers.remove_middleware_from_dramatiq_broker`
- PPT-3 electrode actuation chain wired automatically (electrode_responder + executor listener for ELECTRODES_STATE_APPLIED) — every demo gets electrode end-to-end for free

### What the demo declares

- Columns (the only required field)
- Title / window size (cosmetic)
- Sample steps + protocol metadata (`pre_populate`)
- Demo-specific responder subscriptions (`routing_setup`) — called AFTER the base wires the standard machinery
- Which ack drives the phase timer (`phase_ack_topic`)
- Extra status bar readouts (`status_readouts`)
- Side panel (`side_panel_factory`)

### Why composition (not inheritance)

User's call. Composition advantages: the base "demo window" is a polished, well-tested Qt class with no per-demo subclass requirement; demos become tiny declarative scripts; easier to test the base in isolation; easier for the integration demo (just a much bigger config). Composition disadvantages: extra-status-widget wiring needed an explicit API (the `StatusReadout` dataclass solves this).

---

## Section 2 — Refactor mapping for the 4 existing demos ✅ CONFIRMED

Each demo collapses to ~50-100 lines: just its specific columns + responders + readouts.

### `pluggable_protocol_tree/demos/run_widget.py` (PPT-3, currently 531 LOC → ~80 LOC)

```python
def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
        make_message_column(), make_ack_roundtrip_column(),
    ]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }


def _routing_setup(router):
    # PPT-2 ack-roundtrip column responder (specific to run_widget)
    router.add_subscriber_to_topic(DEMO_REQUEST_TOPIC, RESPONDER_ACTOR_NAME)
    router.add_subscriber_to_topic(
        DEMO_APPLIED_TOPIC, "pluggable_protocol_tree_executor_listener",
    )


config = DemoConfig(
    columns_factory=_columns,
    title="Pluggable Protocol Tree — PPT-3 Demo",
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            BasePluggableProtocolDemoWindow.run(config)
```

### `dropbot_protocol_controls/demos/run_widget_with_vf.py` (PPT-4, currently 658 → ~80 LOC)

```python
def _columns():
    return [...PPT-3 builtins..., make_voltage_column(), make_frequency_column()]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {f"e{i:02d}": i for i in range(25)}
    rm.add_step(values={"name": "Step 1: 100V/10kHz on e00,e01",
                        "duration_s": 0.3, "electrodes": ["e00", "e01"],
                        "voltage": 100, "frequency": 10000})
    rm.add_step(values={"name": "Step 2: 120V/5kHz on e02,e03", ...})
    rm.add_step(values={"name": "Step 3: 75V/1kHz cooldown", ...})


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-4 Demo — Voltage + Frequency",
    pre_populate=_pre_populate,
    routing_setup=lambda r: subscribe_demo_responder(r),  # PPT-4 V/F responder
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    status_readouts=[
        StatusReadout("Voltage",   VOLTAGE_APPLIED,   lambda m: f"{int(m)} V"),
        StatusReadout("Frequency", FREQUENCY_APPLIED, lambda m: f"{int(m)} Hz"),
    ],
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
)
```

### `peripheral_protocol_controls/demos/run_widget_magnet_demo.py` (PPT-5, currently 213 → ~50 LOC)

```python
def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_magnet_column()),
    ]


def _pre_populate(rm):
    rm.add_step(values={"name": "Step 1: engage at Default",
                        "duration_s": 0.2, "magnet_on": True, "magnet_height_mm": 0.0})
    rm.add_step(values={"name": "Step 2: engage at 12.0 mm",
                        "duration_s": 0.2, "magnet_on": True, "magnet_height_mm": 12.0})
    rm.add_step(values={"name": "Step 3: retract",
                        "duration_s": 0.2, "magnet_on": False, "magnet_height_mm": 0.0})


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-5 Demo — Magnet",
    pre_populate=_pre_populate,
    routing_setup=lambda r: subscribe_demo_responder(r),
    phase_ack_topic=MAGNET_APPLIED,
    status_readouts=[
        StatusReadout("Magnet", MAGNET_APPLIED,
                      lambda m: "engaged" if m == "1" else "retracted"),
    ],
)
```

### `pluggable_protocol_tree/demos/run_widget_compound_demo.py` (PPT-11, currently 131 → ~50 LOC)

```python
def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_duration_column(),
        *_expand_compound(make_enabled_count_compound()),
    ]


def _pre_populate(rm):
    rm.add_step(values={"name": "Step 1: enabled, count=5",
                        "duration_s": 0.2, "ec_enabled": True, "ec_count": 5})
    rm.add_step(values={"name": "Step 2: disabled (count read-only)",
                        "duration_s": 0.2, "ec_enabled": False, "ec_count": 0})
    rm.add_step(values={"name": "Step 3: enabled, count=99",
                        "duration_s": 0.2, "ec_enabled": True, "ec_count": 99})


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-11 Demo — Compound Column Framework",
    pre_populate=_pre_populate,
    phase_ack_topic=None,    # no ack-emitting handlers
)
```

The PPT-11 demo gains Run/Pause/Stop + step elapsed timer for free (synthetic compound has no `wait_for`, so each step completes instantly + the duration_s sleep) — useful regression test that the framework actually runs without errors.

### Net lines deleted

~1330 → ~260 across the four demos. Base class is ~250 LOC. Net ~820 LOC removed; future demos cost ~50 LOC each.

---

## Section 3 — Integration demo ✅ CONFIRMED

`src/examples/demos/run_full_integration_demo.py` — single runnable that exercises every column type at once. Lives in `examples/demos/` (not a sibling-plugin demo) because it's the cross-plugin integration smoke runner.

### Sample protocol (3 steps)

| Step | Voltage | Frequency | Magnet | Routes |
|---|---|---|---|---|
| 1 | 100 V | 10000 Hz | engage at Default | top row e00→e04 |
| 2 | 120 V | 5000 Hz | engage at 12.0 mm | diagonal e00→e24 |
| 3 | 75 V | 1000 Hz | retract | none (cooldown) |

### Code

```python
"""Full-stack integration demo: PPT-3 electrodes/routes + PPT-4 voltage/
frequency + PPT-5 magnet, all in one window. Verifies the priority
bucketing in practice (priority 20 V/F/magnet bucket completes before
priority 30 RoutesHandler publishes electrodes).

Run: pixi run python -m examples.demos.run_full_integration_demo
"""

# ...all PPT-3 builtin column factories...
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig, StatusReadout,
)
from pluggable_protocol_tree.demos.simple_device_viewer import (
    GRID_H, GRID_W, SimpleDeviceViewer,
)
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.models._compound_adapters import _expand_compound

from dropbot_controller.consts import VOLTAGE_APPLIED, FREQUENCY_APPLIED
from dropbot_protocol_controls.protocol_columns.voltage_column import make_voltage_column
from dropbot_protocol_controls.protocol_columns.frequency_column import make_frequency_column
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder as subscribe_vf_responder,
)

from peripheral_controller.consts import MAGNET_APPLIED
from peripheral_protocol_controls.protocol_columns.magnet_column import make_magnet_column
from peripheral_protocol_controls.demos.magnet_responder import (
    subscribe_demo_responder as subscribe_magnet_responder,
)


def _columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
        # PPT-4
        make_voltage_column(), make_frequency_column(),
        # PPT-5 (compound, expanded)
        *_expand_compound(make_magnet_column()),
    ]


def _pre_populate(rm):
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(GRID_W * GRID_H)
    }
    rm.add_step(values={
        "name": "Step 1: 100V/10kHz, magnet=Default, route top row",
        "duration_s": 0.3,
        "voltage": 100, "frequency": 10000,
        "magnet_on": True, "magnet_height_mm": 0.0,
        "routes": [["e00", "e01", "e02", "e03", "e04"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Step 2: 120V/5kHz, magnet=12mm, diagonal",
        "duration_s": 0.3,
        "voltage": 120, "frequency": 5000,
        "magnet_on": True, "magnet_height_mm": 12.0,
        "routes": [["e00", "e06", "e12", "e18", "e24"]],
        "trail_length": 1,
    })
    rm.add_step(values={
        "name": "Step 3: 75V/1kHz cooldown, retract magnet",
        "duration_s": 0.3,
        "voltage": 75, "frequency": 1000,
        "magnet_on": False, "magnet_height_mm": 0.0,
    })


def _routing_setup(router):
    """Wire all three demo responders. Each turnkey helper subscribes
    its responder + the executor listener for its ack topic. The PPT-3
    electrode chain is wired by the base automatically."""
    subscribe_vf_responder(router)
    subscribe_magnet_responder(router)


config = DemoConfig(
    columns_factory=_columns,
    title="Full Integration Demo — PPT-3 routes + PPT-4 V/F + PPT-5 magnet",
    window_size=(1300, 700),
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,   # priority-30 ack = real phase boundary
    status_readouts=[
        StatusReadout("Voltage",   VOLTAGE_APPLIED,   lambda m: f"{int(m)} V"),
        StatusReadout("Frequency", FREQUENCY_APPLIED, lambda m: f"{int(m)} Hz"),
        StatusReadout("Magnet",    MAGNET_APPLIED,
                      lambda m: "engaged" if m == "1" else "retracted"),
    ],
    side_panel_factory=lambda rm: SimpleDeviceViewer(rm),
)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            BasePluggableProtocolDemoWindow.run(config)
```

### What the user can verify by running it

1. Status bar shows all three readouts updating per step (`Voltage: 100 V → 120 V → 75 V`, `Frequency: 10000 Hz → 5000 Hz → 1000 Hz`, `Magnet: engaged → engaged → retracted`).
2. Active row highlight tracks step progression.
3. Step + Phase timers refresh at 10 Hz.
4. Device viewer's electrode overlay paints each phase's electrodes during the route.
5. **Priority bucketing in practice:** all three priority-20 readouts (V, F, Magnet) update BEFORE the device viewer's electrode overlay starts changing for that step — proves V/F/magnet bucket completes before RoutesHandler at priority 30.
6. Save → quit → reload → run again — full round-trip persistence with mixed simple + compound columns.
7. Pause mid-route, resume, stop — full executor control.

---

## Tests

### Unit tests (`pluggable_protocol_tree/tests/test_base_demo_window.py`)

| Test | Verifies |
|---|---|
| `test_demo_config_minimum_required_fields` | `DemoConfig(columns_factory=...)` constructs with all defaults |
| `test_status_readout_dataclass_shape` | `StatusReadout(label, topic, fmt)` constructs; `initial` defaults to `"--"` |
| `test_window_constructs_with_minimal_config` | Window builds with just a columns_factory; title/size defaults applied |
| `test_window_pre_populate_runs_after_manager_construction` | The `pre_populate` callback receives the live `RowManager` and added rows are present |
| `test_window_routing_setup_called_after_base_subscriptions` | `routing_setup` callback receives the router with PPT-3 electrode chain already wired |
| `test_status_readout_creates_actor_per_entry` | One Dramatiq actor registered per StatusReadout, named `ppt12_demo_<slug>_listener` |
| `test_status_readout_label_initial_text` | Each readout's QLabel shows `"<label>: <initial>"` until first ack |
| `test_phase_ack_topic_none_hides_phase_timer` | When `phase_ack_topic=None`, no phase-elapsed label in status bar |
| `test_run_classmethod_returns_exit_code` | `run(config)` returns int from `app.exec()` (mocked) |
| `test_clear_highlights_resets_status_readouts_to_initial` | After protocol terminates, each readout label is back to `f"{label}: {initial}"` |
| `test_stale_subscriber_purge_only_touches_demo_prefixes` | Real-listener subscribers (e.g., `dropbot_controller_listener`) are NOT removed |

### Integration test (Redis required) — `tests_with_redis_server_need/test_base_demo_window_redis.py`

| Test | Verifies |
|---|---|
| `test_status_readout_updates_on_ack` | Run a fake ack on a registered readout's topic; assert the QLabel text becomes `f"{label}: {fmt(message)}"` |
| `test_phase_timer_restarts_on_each_phase_ack` | Run a 3-phase fake protocol with phase acks; assert the phase elapsed timer reset between acks |

### Demo regression smoke

After refactor, each of the four refactored demos imports cleanly + window builds without crash + 3 sample steps appear in the protocol tree. (Headed verification = manual.)

---

## Out of scope

- The framework itself (`models/`, `interfaces/`, `executor/`, `services/`) — no changes
- New column types
- Headless integration tests (already covered by per-PPT Redis-backed tests)
- Replacing per-demo Dramatiq listeners with executor signals — tracked in #386, depends on PPT-12 merging first

## Resolved during brainstorming

| Question | Resolution |
|---|---|
| Inheritance vs composition? | **Composition.** Demos are tiny declarative scripts; base class needs no subclassing. |
| Phase ack: single topic, multi-topic, or executor-emitted signal? | **Single topic** (`phase_ack_topic: str \| None`) — covers all 4 demos. Executor-emitted signal is the future cleaner path, tracked in #386. |
| Extra status widgets API? | **Declarative `list[StatusReadout]`** — base auto-creates one Dramatiq actor + Qt signal + QLabel per entry. |
| File location for the integration demo? | `examples/demos/run_full_integration_demo.py` — the existing home for cross-plugin one-off scripts. |
| PPT-11 demo gains Run/Pause/Stop? | **Yes** — useful regression test that the synthetic compound runs end-to-end. |

## Remaining TODO

1. **User reviews written spec** — gate before invoking writing-plans.
2. **Invoke `superpowers:writing-plans`** — once approved, generate `docs/superpowers/plans/2026-04-28-ppt-12-demo-base.md`.
