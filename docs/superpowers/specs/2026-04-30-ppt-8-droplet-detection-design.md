# PPT-8 Design — Migrate droplet detection to per-step column

**Date:** 2026-04-30
**Status:** Draft, pre-implementation
**Issue:** [#370](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/370)
**Parent:** [#361 — Pluggable Protocol Tree umbrella](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/361)
**Parent design:** [`2026-04-21-pluggable-protocol-tree-design.md`](./2026-04-21-pluggable-protocol-tree-design.md)
**Closest precedent:** PPT-7 force column (PR #401) — same plugin home (`dropbot_protocol_controls`), same listener-via-`ACTOR_TOPIC_DICT` wiring, same demo skeleton.

## 0. Scope

Migrate the per-step droplet-presence verification feature out of the legacy `protocol_grid` plugin and into a contributed column on the pluggable protocol tree. The dropbot backend (`DropletDetectionMixinService`) is unchanged — only the *caller* side moves.

The new feature surface:
- A per-step `check_droplets: Bool` column (hidden by default, defaults to `True`).
- An `on_post_step` handler that publishes `DETECT_DROPLETS`, `wait_for`s `DROPLETS_DETECTED`, compares expected vs detected channels.
- On missing channels: a topic round-trip via two new UI topics (`DROPLET_CHECK_DECISION_REQUEST` / `_RESPONSE`) drives a styled `confirm` dialog. User picks "Continue" → step proceeds; "Stay Paused" → handler raises `AbortError` → executor aborts the protocol.
- A demo (`run_droplet_check_demo.py`) with an in-process responder switchable between succeed / drop-one / drop-all / error modes via a Tools menu.

Backend logic, threshold preference, detection frequency, and retry mechanics stay exactly as they are — this PR is about migrating the *protocol-side caller*, not redesigning the detection algorithm.

## 1. Decisions locked in during brainstorming

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Toggle scope (per-step / global / both) | **A** — per-step Bool column, hidden by default, default `True` | Most PPT-native answer; matches trail/loop knob precedent; per-step opt-out is meaningfully more flexible than legacy global toggle. |
| 2 | Failure dialog mechanism | **A** — topic round-trip via `ctx.wait_for` | No new executor primitives; uses the existing `wait_for` shape; latency irrelevant for a user-facing dialog; pattern is reusable for the next column that needs mid-step user input. |
| 3 | Per-step threshold override | **A** — global preference only | Legacy doesn't support it; threshold is a chip/liquid property that doesn't change between steps; YAGNI. Add later if a real use case appears. |
| 4 | Failure dialog UI | `pyface_wrapper.confirm` with structured message | Per the no-raw-`QDialog` feedback rule. Loses the colored Expected/Detected/Missing rows from legacy `DropletDetectionFailureDialog`; can be promoted to a `BaseMessageDialog` subclass later if needed. |
| 5 | Plugin location | `dropbot_protocol_controls` | Same plugin as voltage/frequency/force — keeps all dropbot-coupled columns in one place. Set by PPT-7 precedent. |
| 6 | Actor naming | `droplet_check_decision_listener` (no `ppt8_` prefix) | Cross-issue policy: actor names decouple from issue tracking. |

## 2. File layout

```
src/dropbot_protocol_controls/
├── consts.py                                          # MODIFIED — add 2 UI topics + listener name; extend ACTOR_TOPIC_DICT
├── plugin.py                                          # MODIFIED — wire DropletCheckDecisionDialogActor in start();
│                                                     #            add make_droplet_check_column() to defaults
├── protocol_columns/
│   └── droplet_check_column.py                        # NEW — model + view + handler + factory + expected_channels_for_step
├── services/
│   └── droplet_check_decision_dialog_actor.py        # NEW — UI-side actor; marshals to Qt thread; calls confirm
└── demos/
    ├── run_droplet_check_demo.py                      # NEW — 3-step demo + Tools menu
    └── droplet_detection_responder.py                 # NEW — in-process fake of DropletDetectionMixinService

src/dropbot_protocol_controls/tests/
├── test_expected_channels.py                          # NEW
├── test_droplet_check_column.py                       # NEW
├── test_droplet_check_handler.py                      # NEW
├── test_decision_dialog_actor.py                      # NEW
├── test_persistence.py                                # MODIFIED — add check_droplets round-trip section
└── tests_with_redis_server_need/
    └── test_droplet_check_round_trip.py               # NEW

src/microdrop_utils/api.py                             # MODIFIED — re-export new UI topics for discoverability

docs/superpowers/specs/
└── 2026-04-30-ppt-8-droplet-detection-design.md       # this file
```

**Backend (`dropbot_controller/services/droplet_detection_mixin_service.py`)** — unchanged.
**Legacy `protocol_grid/`** — unchanged (deletion deferred to PPT-9, both pipes coexist).

## 3. Topics and constants

### New constants in `dropbot_protocol_controls/consts.py`

```python
DROPLET_CHECK_DECISION_REQUEST  = "ui/droplet_check/decision_request"
DROPLET_CHECK_DECISION_RESPONSE = "ui/droplet_check/decision_response"

DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME = "droplet_check_decision_listener"

ACTOR_TOPIC_DICT = {
    CALIBRATION_LISTENER_ACTOR_NAME: [CALIBRATION_DATA],                              # existing (PPT-7)
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME: [DROPLET_CHECK_DECISION_REQUEST],     # NEW
}
```

### Topic re-imports

- `DETECT_DROPLETS` and `DROPLETS_DETECTED` stay in `dropbot_controller/consts.py` (their canonical home — they're hardware-coupled). The new column imports them directly:
  ```python
  from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED
  ```

### `microdrop_utils/api.py` extension

Add the two new UI topics to the `DropbotProtocolControlsTopics` namespace alongside `CALIBRATION_DATA` from PPT-7, so cross-plugin code can discover them via the central API surface.

## 4. The column

### `droplet_check_column.py`

```python
class DropletCheckColumnModel(BaseColumnModel):
    """Per-step Bool: 'verify expected droplets after this step's phases complete'."""
    col_id        = Str("check_droplets")
    col_name      = Str("Check Droplets")
    default_value = Bool(True)

    def trait_for_row(self):
        return Bool(True)
    # serialize / deserialize / get_value / set_value: BaseColumnModel defaults are fine
    # (Bool is JSON-native, no custom handling needed)


class DropletCheckColumnView(CheckboxColumnView):
    renders_on_group   = False
    hidden_by_default  = True   # follows trail/loop precedent — surfaces via header right-click


class DropletCheckHandler(BaseColumnHandler):
    priority        = 80                           # after voltage(20) / electrodes/routes(30); near end of step
    wait_for_topics = [DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE]

    def on_post_step(self, row, ctx):
        if not row.check_droplets:
            return                                 # column off → skip silently

        electrode_to_channel = ctx.protocol.scratch.get("electrode_to_channel", {})
        expected = expected_channels_for_step(row, electrode_to_channel)
        if not expected:
            return                                 # nothing to check (no electrodes / no routes)

        publish_message(topic=DETECT_DROPLETS, message=json.dumps(expected))
        try:
            ack_raw = ctx.wait_for(DROPLETS_DETECTED, timeout=12.0)   # backend's 10s + 2s slack
        except TimeoutError:
            logger.warning(f"Droplet detection timed out for step {row.uuid}; proceeding")
            return                                 # legacy parity: backend handles its own retries
        ack = json.loads(ack_raw)
        if not ack["success"]:
            logger.warning(f"Droplet detection error: {ack['error']}; proceeding")
            return                                 # legacy parity: log and continue on backend errors

        detected = [int(c) for c in ack["detected_channels"]]
        missing  = sorted(set(expected) - set(detected))
        if not missing:
            return                                 # all expected droplets present — happy path

        # ---- failure path: ask the user via UI round-trip ----
        publish_message(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            message=json.dumps({
                "step_uuid": row.uuid,
                "expected":  expected,
                "detected":  detected,
                "missing":   missing,
            }),
        )
        decision_raw = ctx.wait_for(
            DROPLET_CHECK_DECISION_RESPONSE,
            timeout=None,                          # block until user answers; stop_event interrupts
            predicate=lambda payload: json.loads(payload).get("step_uuid") == row.uuid,
        )
        decision = json.loads(decision_raw)["choice"]
        if decision == "pause":
            raise AbortError(f"User chose to pause after droplet check on step {row.uuid}")
        # decision == "continue" → fall through, executor moves to next step


def expected_channels_for_step(row, electrode_to_channel: dict[str, int]) -> list[int]:
    """Channels we expect droplets on after this step's phases finish.

    Mirrors legacy _get_expected_droplet_channels (protocol_runner_controller.py:1763):
    union of (statically activated electrodes) and (last electrode of each route).
    The 'last electrode' captures route-end positions where droplets settle.
    """
    expected: set[int] = set()
    for eid in (row.activated_electrodes or []):
        ch = electrode_to_channel.get(eid)
        if ch is not None:
            expected.add(int(ch))
    for route in (row.routes or []):
        if route:
            ch = electrode_to_channel.get(route[-1])
            if ch is not None:
                expected.add(int(ch))
    return sorted(expected)


def make_droplet_check_column() -> Column:
    return Column(
        model   = DropletCheckColumnModel(),
        view    = DropletCheckColumnView(),
        handler = DropletCheckHandler(),
    )
```

### Design notes

1. **`wait_for(..., predicate=...)`** — the executor's listener is shared across all hooks, and `DROPLET_CHECK_DECISION_RESPONSE` could carry a stale answer from a different step (race during fast pauses, retries, etc.). The predicate filters by `step_uuid`, so we only resolve on the response that matches *this* step. This requires `wait_for` to support a `predicate` callable, which the parent design already specifies in §10.

2. **`AbortError` on "pause"** — repurposing the existing executor abort path (parent design §9). The executor sets `stop_event`, drains the bucket, runs `on_protocol_end`, emits `protocol_aborted`. We do not invent a new "pause-from-hook" verb. User can manually restart from the UI.

3. **Two simplifications vs legacy `_get_expected_droplet_channels`:**
   - Legacy walks `_current_execution_plan`'s last phase to handle staggered route endings. In PPT-3, `RoutesHandler` already drives one-phase-per-publish with `wait_for(ELECTRODES_STATE_APPLIED)`, so by the time `on_post_step` runs, all routes have reached their final electrode — the union of route last-elements is exact, no staggering to compensate for.
   - Legacy reads `device_state.id_to_channel`; we read `electrode_to_channel` from `protocol_metadata` (surfaced via `ctx.protocol.scratch` per PPT-3 design). Same dict, different source.

## 5. UI dialog actor

### `services/droplet_check_decision_dialog_actor.py`

```python
class DropletCheckDecisionDialogActor(HasTraits):
    """GUI-side: receives DROPLET_CHECK_DECISION_REQUEST, shows dialog on Qt
    thread, publishes user's choice on DROPLET_CHECK_DECISION_RESPONSE."""

    listener_name = DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def listener_actor_routine(self, message, topic):
        # Worker thread — must marshal to GUI thread before showing dialog
        payload = json.loads(message)
        QTimer.singleShot(0, lambda: self._show_dialog_and_respond(payload))

    def _show_dialog_and_respond(self, payload):
        # GUI thread — safe to use pyface_wrapper
        message = self._format_message(payload)
        user_continue = confirm(
            parent=QApplication.activeWindow(),
            message=message,
            title="Droplet Detection Failed",
            yes_label="Continue", no_label="Stay Paused",
        )
        publish_message(
            topic=DROPLET_CHECK_DECISION_RESPONSE,
            message=json.dumps({
                "step_uuid": payload["step_uuid"],
                "choice":    "continue" if user_continue else "pause",
            }),
        )

    @staticmethod
    def _format_message(payload):
        return (
            "Droplet detection failed at the end of the step.\n\n"
            f"Expected: {', '.join(map(str, payload['expected'])) or 'none'}\n"
            f"Detected: {', '.join(map(str, payload['detected'])) or 'none'}\n"
            f"Missing:  {', '.join(map(str, payload['missing']))}\n\n"
            "Continue with the protocol anyway?"
        )

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )
```

### Wiring

`dropbot_protocol_controls/plugin.py:start()` instantiates the actor (alongside the existing `CalibrationCache` actor wiring from PPT-7). Subscription is automatic via `ACTOR_TOPIC_DICT` → `actor_topic_routing` extension contribution → `MessageRouterPlugin.start()`. No manual `add_subscriber_to_topic` in production code.

### Why not lift the legacy dialog?

`DropletDetectionFailureDialog` (`protocol_grid/extra_ui_elements.py:805`) is a custom `QDialog` subclass with hardcoded styling (`QLabel.setStyleSheet("font-size: 14pt; ...; color: #cc3300;")`). The user feedback rule (saved memory: `feedback_pyface_dialog_wrapper`) forbids raw `QDialog`/`QMessageBox` — all dialogs go through `microdrop_application.dialogs.pyface_wrapper`. Using `confirm(...)` keeps app styling consistent at the cost of losing the colored Expected/Detected/Missing rows. Rebuilding on `BaseMessageDialog` is a follow-up if the plain text proves insufficient.

## 6. Demo

### `demos/run_droplet_check_demo.py`

Built on `BasePluggableProtocolDemoWindow` (PPT-12 base), same shape as `run_force_demo.py`. Three steps, each with different activated electrodes, exercising:

The demo's responder defaults to `mode="drop_one"` so the failure path is visible on first run without any menu interaction. Steps:

| Step | activated_electrodes | check_droplets | Expected behavior (default `drop_one` mode) |
|---|---|---|---|
| S1 | `["e1", "e2"]` | True | Responder returns `[2]` (missing `1`) → dialog appears → user picks |
| S2 | `["e3", "e4", "e5"]` | True | Responder returns `[4, 5]` (missing `3`) → dialog appears → user picks |
| S3 | `["e6"]` | False | Column off → handler short-circuits, no detect/response traffic |

The window seeds `electrode_to_channel = {"e1": 1, "e2": 2, ..., "e6": 6}` into `RowManager.protocol_metadata`.

### Tools menu

```
Tools
├── Responder Mode ▶ ● Always succeed     (returns expected channels)
│                    ○ Drop one channel    (returns expected[1:])
│                    ○ Drop all channels   (returns [])
│                    ○ Error reply         ({"success": False, "error": "..."})
└── Re-run Protocol               (Ctrl+R)
```

Switching the mode re-configures the in-process responder. "Re-run" calls `executor.run()` again from step 0 (same protocol, fresh state) so the user can iterate: tweak mode → run → watch dialog → tweak mode → run.

### `demos/droplet_detection_responder.py`

In-process Dramatiq actor mirroring `voltage_frequency_responder.py`:

```python
class DropletDetectionResponder(HasTraits):
    """In-process fake of DropletDetectionMixinService for demos."""

    listener_name = "demo_droplet_detection_responder"
    mode = Enum("succeed", "drop_one", "drop_all", "error")
    last_request_channels = List(Int)   # for assertions in tests

    def listener_actor_routine(self, message, topic):
        requested = json.loads(message)
        self.last_request_channels = requested
        if self.mode == "error":
            payload = {"success": False, "detected_channels": [], "error": "Demo: simulated error"}
        elif self.mode == "drop_all":
            payload = {"success": True,  "detected_channels": [], "error": ""}
        elif self.mode == "drop_one":
            payload = {"success": True,  "detected_channels": requested[1:], "error": ""}
        else:  # "succeed"
            payload = {"success": True,  "detected_channels": requested, "error": ""}
        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(payload))

    def subscribe(self, router):
        router.message_router_data.add_subscriber_to_topic(
            topic=DETECT_DROPLETS, subscribing_actor_name=self.listener_name)
```

Wired into the demo via `routing_setup=lambda router: responder.subscribe(router)` (same pattern PPT-7's `subscribe_calibration_listener`).

### Demo walkthrough

1. Window opens with 3 steps. Force/Frequency/Voltage columns visible. **Check Droplets column is hidden by default** — header right-click to show it (this exercises hidden-column UI from PPT-3).
2. Click "Run". S1 triggers the dialog (default `drop_one` mode): *"Droplet detection failed at the end of the step. Expected: 1, 2. Detected: 2. Missing: 1. Continue?"*
3. **Continue** → S2 runs, triggers the dialog again with `Expected: 3, 4, 5. Detected: 4, 5. Missing: 3.` Continue again → S3 starts (skips droplet check, column off), protocol completes.
4. **Stay Paused** (at any dialog) → executor aborts, `protocol_aborted` signal fires, no further steps run, status bar reflects aborted state.
5. Tools → Responder Mode → "Always succeed" → Re-run → all three steps pass silently, no dialog. Protocol completes cleanly.
6. Tools → Responder Mode → "Drop all channels" → Re-run → S1 dialog says `Detected: none. Missing: 1, 2.`; S2 dialog says `Detected: none. Missing: 3, 4, 5.`
7. Tools → Responder Mode → "Error reply" → Re-run → no dialogs (handler logs the backend error and proceeds); all three steps complete.

## 7. Tests

Six new test files in `dropbot_protocol_controls/tests/`:

| File | What it covers | Tests (est.) |
|---|---|---|
| `test_expected_channels.py` | Pure helper — empty step, electrodes only, routes only, both, missing IDs in mapping, deduplication, sorted output, last-electrode-of-route logic | ~10 |
| `test_droplet_check_column.py` | Factory (`make_droplet_check_column`), default value, serialize/deserialize Bool round-trip, view class attrs (`hidden_by_default=True`, `renders_on_group=False`), handler `priority=80` and `wait_for_topics` declarations | ~8 |
| `test_droplet_check_handler.py` | Handler `on_post_step` with mocked `ctx.wait_for`: column off → no publish; no expected channels → no publish; happy path → success ack → returns; missing channels → publishes decision request → continue/pause; backend error → logs + returns; predicate filters by step_uuid; timeout → logs + returns | ~10 |
| `test_decision_dialog_actor.py` | Routes `DROPLET_CHECK_DECISION_REQUEST` payload to `_show_dialog_and_respond`; mock `confirm` returning True → publishes `{choice: "continue"}`; returning False → `{choice: "pause"}`; preserves `step_uuid` in response | ~5 |
| `test_persistence.py` (new section) | `check_droplets` Bool round-trips through JSON; column metadata in `payload["columns"]`; per-row Bool in `rows`; legacy load (no `check_droplets` field) defaults to `True` | ~5 |
| `tests_with_redis_server_need/test_droplet_check_round_trip.py` | Real Redis end-to-end: handler publishes → fake responder replies → handler proceeds; failure path → mock dialog publishes pre-decided choice → handler returns or raises `AbortError` | ~3 |

### Two test conventions to pin

1. **Mock dialog in unit tests** — `test_decision_dialog_actor.py` patches `microdrop_application.dialogs.pyface_wrapper.confirm` so no actual GUI fires. The Redis integration test does the same — replaces the actor's `_show_dialog_and_respond` with a stub that publishes a pre-decided choice.

2. **`stop_event` interrupts `wait_for(timeout=None)`** — the handler's `wait_for(DROPLET_CHECK_DECISION_RESPONSE, timeout=None)` blocks indefinitely waiting for the user. Tests verify that setting the executor's `stop_event` unblocks it (parent design §10), so a stuck dialog can't wedge the protocol if the user hits Stop.

## 8. What we don't touch

Same posture as PPT-7. The legacy `protocol_grid` plugin keeps running in parallel until PPT-9 deletes it wholesale:

- `protocol_grid/services/protocol_runner_controller.py` (the 2394-line file with `_perform_droplet_detection_check`) — untouched.
- `protocol_grid/extra_ui_elements.py:805-934` (`DropletDetectionFailureDialog` + `DropletDetectionFailureDialogAction`) — untouched.
- `protocol_grid/services/message_listener.py:67` (`elif topic == DROPLETS_DETECTED:` branch) — untouched.
- `protocol_grid/widget.py:1239,1276,1385,1465` (`set_droplet_check_enabled` / nav-bar checkbox) — untouched.

### Coexistence

Both pipes (legacy and new) will subscribe to `DROPLETS_DETECTED` simultaneously. Legacy's branch only fires when its own `_waiting_for_droplet_check` flag is set (which only the legacy runner sets), so coexistence is safe — the same response payload reaches both subscribers but only one acts on it. The new column only fires if the user is running a protocol via the pluggable tree (not via legacy), and the new fake responder in the demo only runs in the demo process.

### Backend

`DropletDetectionMixinService` in `dropbot_controller` is unchanged. Wire format (`List[int]` channels in request, `{success, detected_channels, error}` in response) is preserved.

## 9. Follow-ups (file as separate issues at PR time)

- **Protocol menu → "Toggle Check Droplets on all steps"** — bulk-set across the tree, replaces the legacy global checkbox. (User-confirmed during brainstorming as a follow-up.)
- **Custom-styled droplet failure dialog** — if the plain `confirm` text loses too much information, build a `DropletCheckFailureDialog(BaseMessageDialog)` subclass with the colored Expected/Detected/Missing rows.
- **Staggered route-end verification** — the legacy code has an extra `_get_individual_path_last_phase_electrodes` branch for routes finishing at different times. Once we have hardware-time data showing how often this matters, file an issue to revisit.

## 10. Out of scope (deferred)

- Deletion of the legacy `protocol_grid` droplet-detection code (PPT-9).
- Per-step threshold override (`droplet_threshold_pf` column) — global preference only for now.
- "Stay Paused with continue option" — current `AbortError` aborts cleanly, user can manually restart. A true mid-protocol pause-and-resume from a hook is a parent-design open question, not PPT-8 scope.
- Backend changes to `DropletDetectionMixinService` (algorithm, retry behavior, threshold normalization).

## 11. Acceptance criteria

- [ ] `pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo` opens the window with 3 steps and the new column hidden.
- [ ] Header right-click → "Show Check Droplets" surfaces the column with the expected default values (T, T, F).
- [ ] Run with default `drop_one` responder → S1 and S2 each show the failure dialog with correct Expected/Detected/Missing values; S3 skips check entirely (column off).
- [ ] Continue through both dialogs → protocol completes after S3; Stay Paused at any dialog → executor aborts, no later steps run.
- [ ] Tools → Responder Mode → "Always succeed" → Re-run → all 3 steps pass; protocol completes.
- [ ] All ~41 new unit tests pass + ~3 Redis integration tests pass.
- [ ] Full PPT-3/4/5/6/7/8 regression sweep is green (one pre-existing flaky `test_run_hooks_fans_same_priority_in_parallel` excepted, confirmed not a regression).
- [ ] Save → reload protocol round-trips `check_droplets` Bool per step.
- [ ] No regression in legacy `protocol_grid` droplet detection (the legacy nav-bar checkbox + dialog still work as today).
