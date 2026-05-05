# PPT-8 Implementation Plan — Droplet Detection per-step Column

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the legacy `protocol_grid` per-step droplet-presence verification into a contributed PPT column on `dropbot_protocol_controls`. Surface as a hidden-by-default `check_droplets: Bool` column whose `on_post_step` handler publishes `DETECT_DROPLETS`, waits for the backend's `DROPLETS_DETECTED` reply, and on missing channels drives a topic-round-trip failure dialog. Demoable with an in-process responder. Backend (`DropletDetectionMixinService`) is unchanged.

**Architecture:** Per-step `Bool` column + `on_post_step` handler at priority 80. Failure path uses two new UI topics (`DROPLET_CHECK_DECISION_REQUEST` / `_RESPONSE`) and a Dramatiq actor on the GUI process that marshals to the Qt thread via `QTimer.singleShot` to call `pyface_wrapper.confirm`. Subscription wiring is automatic via `ACTOR_TOPIC_DICT` → `actor_topic_routing` → `MessageRouterPlugin.start()` (production); the demo manually subscribes both the responder and the executor listener. Branch already created: `feat/ppt-8-droplet-check-column` on the inner `src/` submodule.

**Tech Stack:** Python, Traits/Pyface, PySide6 (Qt6), Dramatiq + Redis (message bus), pytest, Envisage plugins, the `pluggable_protocol_tree` core (existing — PPT-1/2/3 wait_for + `Mailbox` infrastructure).

**Spec:** [`../specs/2026-04-30-ppt-8-droplet-detection-design.md`](../specs/2026-04-30-ppt-8-droplet-detection-design.md). Design and decisions are locked in there. The plan below assumes you have read it.

**Branch state at task start:**
```
feat/ppt-8-droplet-check-column
├── f7147e5 [PPT-8] spec: use finite 24h timeout
├── 5d4b49b [PPT-8] spec: align demo walkthrough with responder behavior
├── 95eda59 [PPT-8] design spec
└── 64fbbc7 Merge pull request #401   <- PPT-7 merge, on main
```

All work on the inner `src/` submodule (the standalone `Microdrop` repo, the source of truth). All paths in this plan are relative to `microdrop-py/src/`.

---

## Quick reference: relevant existing files

| Where | What you need from it |
|---|---|
| `dropbot_protocol_controls/consts.py` | Pattern for adding listener actor name + extending `ACTOR_TOPIC_DICT`. PPT-7's `CALIBRATION_LISTENER_ACTOR_NAME` is the precedent. |
| `dropbot_protocol_controls/plugin.py` | Where `make_droplet_check_column()` gets registered in `_contributed_protocol_columns_default`. |
| `dropbot_protocol_controls/services/calibration_cache.py` | Pattern for `@dramatiq.actor` decorated module-level function with malformed-input guard (PPT-7's `_apply_calibration` try/except). |
| `dropbot_protocol_controls/protocol_columns/force_column.py` | Pattern for column file layout (model + view + factory). |
| `dropbot_protocol_controls/demos/voltage_frequency_responder.py` | Pattern for fake responder + `subscribe_*(router)` helper that subscribes both the responder AND the executor listener. |
| `dropbot_protocol_controls/demos/run_force_demo.py` | Pattern for full `BasePluggableProtocolDemoWindow` demo with Tools menu + dialog interaction. |
| `dropbot_protocol_controls/tests/conftest.py` | Just imports `configure_dramatiq_broker()`; nothing else needed at the package level. |
| `pluggable_protocol_tree/builtins/routes_column.py:82` | Confirms `wait_for_topics = [...]` declaration syntax for handlers. |
| `pluggable_protocol_tree/execution/step_context.py:154-177` | `wait_for(topic, timeout=5.0, predicate=...)` signature. Returns the payload (raw string). Raises `TimeoutError`, `AbortError`, `KeyError`. |
| `pluggable_protocol_tree/execution/exceptions.py:4` | `AbortError` import location. |
| `dropbot_controller/consts.py:27,53` | Existing `DETECT_DROPLETS` and `DROPLETS_DETECTED` constants — import directly. |
| `microdrop_application/dialogs/pyface_wrapper.py` | `confirm(parent, message, title, yes_label, no_label) -> bool`. Returns True for YES (left button), False for NO. |
| `microdrop_utils/dramatiq_pub_sub_helpers.py` | `publish_message(topic, message)` for sending; `generate_class_method_dramatiq_listener_actor(listener_name, class_method)` for class-method-bound actors. |

---

## Task 1: Topic constants + ACTOR_TOPIC_DICT extension

**Files:**
- Modify: `dropbot_protocol_controls/consts.py`
- Test: `dropbot_protocol_controls/tests/test_consts.py` (NEW)

- [ ] **Step 1: Write the failing test** — create `dropbot_protocol_controls/tests/test_consts.py`:

```python
"""Topic constants and ACTOR_TOPIC_DICT for PPT-8 droplet check."""

from dropbot_protocol_controls.consts import (
    ACTOR_TOPIC_DICT,
    CALIBRATION_LISTENER_ACTOR_NAME,
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
)


def test_droplet_check_decision_topics_are_strings():
    assert DROPLET_CHECK_DECISION_REQUEST == "ui/droplet_check/decision_request"
    assert DROPLET_CHECK_DECISION_RESPONSE == "ui/droplet_check/decision_response"


def test_droplet_check_listener_actor_name_has_no_ppt_prefix():
    # Cross-issue policy (memory: actor names decouple from issue tracking)
    assert DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME == "droplet_check_decision_listener"
    assert "ppt" not in DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME.lower()


def test_actor_topic_dict_routes_decision_request_to_listener():
    assert (
        ACTOR_TOPIC_DICT[DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME]
        == [DROPLET_CHECK_DECISION_REQUEST]
    )


def test_actor_topic_dict_preserves_calibration_listener_from_ppt7():
    # Don't break the existing PPT-7 routing
    from dropbot_protocol_controls.consts import CALIBRATION_DATA
    assert ACTOR_TOPIC_DICT[CALIBRATION_LISTENER_ACTOR_NAME] == [CALIBRATION_DATA]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_consts.py -v`
Expected: ImportError on `DROPLET_CHECK_DECISION_REQUEST` (and other new symbols).

- [ ] **Step 3: Implement constants** — edit `dropbot_protocol_controls/consts.py` to:

```python
"""Package-level constants for dropbot_protocol_controls.

Hardware request/ack topic constants live in dropbot_controller/consts.py
— this plugin imports them. UI/measurement topics like CALIBRATION_DATA
live in device_viewer/consts.py. See PPT-4 spec section 3, "Topic
ownership rationale" for the layering reasoning.
"""

from device_viewer.consts import CALIBRATION_DATA

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# --- PPT-7: calibration data listener ---
CALIBRATION_LISTENER_ACTOR_NAME = "calibration_data_listener"

# --- PPT-8: droplet check decision dialog ---
# UI round-trip topics for the droplet-check failure dialog. The handler
# publishes _REQUEST when expected != detected; a GUI-side actor shows
# the dialog and publishes _RESPONSE with {"step_uuid", "choice"}.
DROPLET_CHECK_DECISION_REQUEST  = "ui/droplet_check/decision_request"
DROPLET_CHECK_DECISION_RESPONSE = "ui/droplet_check/decision_response"
DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME = "droplet_check_decision_listener"

ACTOR_TOPIC_DICT = {
    CALIBRATION_LISTENER_ACTOR_NAME: [CALIBRATION_DATA],
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME: [DROPLET_CHECK_DECISION_REQUEST],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_consts.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/consts.py src/dropbot_protocol_controls/tests/test_consts.py
git commit -m "[PPT-8] Task 1 — add UI decision topics + ACTOR_TOPIC_DICT entry"
```

---

## Task 2: `expected_channels_for_step` helper + tests

**Files:**
- Create: `dropbot_protocol_controls/protocol_columns/droplet_check_column.py` (skeleton — only the helper for now)
- Create: `dropbot_protocol_controls/tests/test_expected_channels.py`

- [ ] **Step 1: Write the failing tests** — create `dropbot_protocol_controls/tests/test_expected_channels.py`:

```python
"""Pure helper that derives 'expected' channels from a step row + the
electrode_to_channel mapping. Mirrors legacy
_get_expected_droplet_channels (protocol_runner_controller.py:1763)."""

import pytest
from traits.api import HasTraits, List, Str

from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    expected_channels_for_step,
)


class _FakeRow(HasTraits):
    activated_electrodes = List(Str)
    routes               = List  # List[List[Str]]


# A small fixed mapping used across most tests.
MAP = {"e1": 1, "e2": 2, "e3": 3, "e4": 4, "e5": 5, "e6": 6}


def test_empty_step_returns_empty_list():
    assert expected_channels_for_step(_FakeRow(), MAP) == []


def test_only_activated_electrodes():
    row = _FakeRow(activated_electrodes=["e1", "e2"])
    assert expected_channels_for_step(row, MAP) == [1, 2]


def test_only_routes_takes_last_electrode_of_each():
    row = _FakeRow(routes=[["e1", "e2", "e3"], ["e4", "e5"]])
    assert expected_channels_for_step(row, MAP) == [3, 5]


def test_activated_and_routes_are_unioned():
    row = _FakeRow(
        activated_electrodes=["e1"],
        routes=[["e2", "e3"]],
    )
    assert expected_channels_for_step(row, MAP) == [1, 3]


def test_duplicate_channels_are_deduplicated():
    # Activated includes e3, route also ends at e3.
    row = _FakeRow(
        activated_electrodes=["e1", "e3"],
        routes=[["e2", "e3"]],
    )
    assert expected_channels_for_step(row, MAP) == [1, 3]


def test_result_is_sorted():
    row = _FakeRow(activated_electrodes=["e5", "e2", "e4", "e1"])
    assert expected_channels_for_step(row, MAP) == [1, 2, 4, 5]


def test_unknown_electrode_id_is_silently_dropped():
    # 'e99' isn't in the mapping — drop it, don't crash.
    row = _FakeRow(activated_electrodes=["e1", "e99", "e2"])
    assert expected_channels_for_step(row, MAP) == [1, 2]


def test_route_with_unknown_last_electrode_is_silently_dropped():
    row = _FakeRow(routes=[["e1", "e99"], ["e2", "e3"]])
    # First route's last 'e99' missing → dropped. Second route ends 'e3'.
    assert expected_channels_for_step(row, MAP) == [3]


def test_empty_route_inside_routes_list_is_skipped():
    # Defensive: a route with zero electrodes should not crash on route[-1].
    row = _FakeRow(routes=[[], ["e2", "e3"]])
    assert expected_channels_for_step(row, MAP) == [3]


def test_empty_mapping_returns_empty_list_even_with_inputs():
    row = _FakeRow(activated_electrodes=["e1"], routes=[["e2", "e3"]])
    assert expected_channels_for_step(row, {}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_expected_channels.py -v`
Expected: ImportError on `expected_channels_for_step` (module doesn't exist yet).

- [ ] **Step 3: Implement the helper** — create `dropbot_protocol_controls/protocol_columns/droplet_check_column.py`:

```python
"""PPT-8: per-step droplet check column. After a step's phases complete,
the handler publishes DETECT_DROPLETS for the channels we expect droplets
on, awaits the backend's DROPLETS_DETECTED reply, and on missing channels
drives a UI confirm dialog via topic round-trip.

This file holds the pure helper, the model/view/factory, and the handler.
Splitting them across files would just spread cohesive logic; see PPT-7's
force_column.py for the same single-file convention.
"""

from logger.logger_service import get_logger

logger = get_logger(__name__)


def expected_channels_for_step(row, electrode_to_channel: dict) -> list:
    """Channels we expect droplets on after this step's phases finish.

    Mirrors legacy _get_expected_droplet_channels
    (protocol_runner_controller.py:1763): the union of
    (statically activated electrodes) and (the LAST electrode of each
    route — that's where the droplet ends up). Returns a sorted unique
    list of int channels. Unknown electrode IDs are silently dropped
    rather than raising — same behavior as legacy.
    """
    expected = set()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_expected_channels.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/protocol_columns/droplet_check_column.py src/dropbot_protocol_controls/tests/test_expected_channels.py
git commit -m "[PPT-8] Task 2 — expected_channels_for_step helper + 10 tests"
```

---

## Task 3: Column model, view, factory + persistence test

**Files:**
- Modify: `dropbot_protocol_controls/protocol_columns/droplet_check_column.py` (add model + view + factory)
- Create: `dropbot_protocol_controls/tests/test_droplet_check_column.py`
- Modify: `dropbot_protocol_controls/tests/test_persistence.py` (add `check_droplets` round-trip section)

The column trait is a real per-row Bool (unlike PPT-7's force, which was derived). Persistence is just JSON-native bool round-trip — `BaseColumnModel`'s default serialize/deserialize handle it; we don't override.

- [ ] **Step 1: Write column tests** — create `dropbot_protocol_controls/tests/test_droplet_check_column.py`:

```python
"""Tests for the droplet-check column — model factory, view class
attributes, handler declarations. Handler behavior (publish + wait_for)
is in test_droplet_check_handler.py."""

import pytest
from traits.api import HasTraits

from pluggable_protocol_tree.models.column import Column

from dropbot_protocol_controls.consts import (
    DROPLETS_DETECTED,
    DROPLET_CHECK_DECISION_RESPONSE,
)
from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    DropletCheckColumnModel,
    DropletCheckColumnView,
    DropletCheckHandler,
    make_droplet_check_column,
)


def test_make_droplet_check_column_returns_column_with_check_droplets_id():
    col = make_droplet_check_column()
    assert isinstance(col, Column)
    assert col.model.col_id == "check_droplets"
    assert col.model.col_name == "Check Droplets"


def test_default_value_is_true():
    model = DropletCheckColumnModel()
    assert model.default_value is True


def test_trait_for_row_returns_bool_trait_with_true_default():
    # The trait that goes onto each row's dynamic class.
    model = DropletCheckColumnModel()
    trait = model.trait_for_row()
    # Build a tiny class that uses the trait, instantiate, check default.
    Row = type("Row", (HasTraits,), {"check_droplets": trait})
    row = Row()
    assert row.check_droplets is True


def test_serialize_and_deserialize_roundtrip_true_and_false():
    model = DropletCheckColumnModel()
    assert model.serialize(True)  is True
    assert model.serialize(False) is False
    assert model.deserialize(True)  is True
    assert model.deserialize(False) is False


def test_view_class_attributes():
    view = DropletCheckColumnView()
    assert view.hidden_by_default is True   # follows trail/loop precedent
    assert view.renders_on_group  is False


def test_handler_priority_is_80_post_step_late():
    # Priority 80 — droplet check is the only on_post_step hook today,
    # so 80 is conventional rather than load-bearing. (Lower priorities
    # like routes(30) are on_step hooks, not on_post_step — different
    # bucket.) See spec § 4.
    handler = DropletCheckHandler()
    assert handler.priority == 80


def test_handler_declares_both_response_topics_in_wait_for():
    handler = DropletCheckHandler()
    assert DROPLETS_DETECTED in handler.wait_for_topics
    assert DROPLET_CHECK_DECISION_RESPONSE in handler.wait_for_topics


def test_factory_wires_model_view_handler_together():
    col = make_droplet_check_column()
    assert isinstance(col.model,   DropletCheckColumnModel)
    assert isinstance(col.view,    DropletCheckColumnView)
    assert isinstance(col.handler, DropletCheckHandler)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_column.py -v`
Expected: ImportError on `DropletCheckColumnModel` etc.

- [ ] **Step 3: Add model + view + handler skeleton + factory** — append to `dropbot_protocol_controls/protocol_columns/droplet_check_column.py`:

```python
from traits.api import Bool, Str

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView

from ..consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED


class DropletCheckColumnModel(BaseColumnModel):
    """Per-step Bool: 'verify expected droplets after this step's phases'.
    Default True; user can disable per-step via header right-click on the
    hidden column."""

    col_id        = Str("check_droplets")
    col_name      = Str("Check Droplets")
    default_value = Bool(True)

    def trait_for_row(self):
        return Bool(True)
    # serialize / deserialize / get_value / set_value: BaseColumnModel
    # defaults are correct (Bool is JSON-native).


class DropletCheckColumnView(CheckboxColumnView):
    """Hidden by default — surfaces via header right-click. Same posture
    as PPT-3's trail/loop knob columns."""

    renders_on_group  = False
    hidden_by_default = True


class DropletCheckHandler(BaseColumnHandler):
    """Skeleton — Tasks 4–7 fill in on_post_step body."""

    priority        = 80
    wait_for_topics = [DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE]

    def on_post_step(self, row, ctx):
        # Body added in Tasks 4–7. Empty here so column-shape tests
        # (Task 3) can run without pulling in handler integration tests.
        return None


def make_droplet_check_column() -> Column:
    return Column(
        model   = DropletCheckColumnModel(),
        view    = DropletCheckColumnView(),
        handler = DropletCheckHandler(),
    )
```

- [ ] **Step 4: Run column tests to verify they pass**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_column.py -v`
Expected: 8 passed.

- [ ] **Step 5: Add persistence section to existing `test_persistence.py`**

Append to `dropbot_protocol_controls/tests/test_persistence.py` (after the existing tests):

```python
# ---------------------------------------------------------------------------
# PPT-8 — check_droplets Bool column persistence (added in Task 3)
# ---------------------------------------------------------------------------

def _build_eight_columns():
    """7-column set from PPT-7 + check_droplets."""
    from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
        make_droplet_check_column,
    )
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(),
            make_voltage_column(), make_frequency_column(),
            make_force_column(),
            make_droplet_check_column(),
        ]


def test_check_droplets_per_row_round_trip_through_json():
    cols = _build_eight_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "check_droplets": True})
    rm.add_step(values={"name": "S2", "check_droplets": False})
    rm.add_step(values={"name": "S3"})  # default → True

    payload = rm.to_json()
    parsed = json.loads(json.dumps(payload))

    rm2 = RowManager.from_json(parsed, columns=_build_eight_columns())
    steps = rm2.root.children
    assert [s.check_droplets for s in steps] == [True, False, True]
    assert all(isinstance(s.check_droplets, bool) for s in steps)


def test_check_droplets_column_metadata_in_json_payload():
    rm = RowManager(columns=_build_eight_columns())
    rm.add_step(values={"name": "S1"})
    payload = rm.to_json()

    entries = [c for c in payload["columns"] if c["id"] == "check_droplets"]
    assert len(entries) == 1
    assert entries[0]["cls"] == (
        "dropbot_protocol_controls.protocol_columns.droplet_check_column.DropletCheckColumnModel"
    )


def test_legacy_load_without_check_droplets_field_defaults_to_true():
    # Build a JSON payload as if check_droplets had never existed (i.e.
    # a protocol saved before PPT-8). After load, all rows should have
    # check_droplets=True (the column default).
    cols_no_check = [c for c in _build_eight_columns()
                     if c.model.col_id != "check_droplets"]
    rm = RowManager(columns=cols_no_check)
    rm.add_step(values={"name": "S1"})
    rm.add_step(values={"name": "S2"})
    payload = rm.to_json()                # no check_droplets in payload

    rm2 = RowManager.from_json(json.loads(json.dumps(payload)),
                                columns=_build_eight_columns())
    for step in rm2.root.children:
        assert step.check_droplets is True
```

- [ ] **Step 6: Run persistence tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_persistence.py -v`
Expected: All previously-passing tests still pass; 3 new tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/dropbot_protocol_controls/protocol_columns/droplet_check_column.py src/dropbot_protocol_controls/tests/test_droplet_check_column.py src/dropbot_protocol_controls/tests/test_persistence.py
git commit -m "[PPT-8] Task 3 — column model + view + factory; persistence round-trip"
```

---

## Task 4: Handler short-circuit paths

The handler's first two early-return branches: column off, no expected channels. Easy TDD with mocked `ctx.publish` and `ctx.wait_for`.

**Files:**
- Modify: `dropbot_protocol_controls/protocol_columns/droplet_check_column.py:on_post_step`
- Create: `dropbot_protocol_controls/tests/test_droplet_check_handler.py`

- [ ] **Step 1: Write the short-circuit tests** — create `dropbot_protocol_controls/tests/test_droplet_check_handler.py`:

```python
"""Tests for DropletCheckHandler.on_post_step.

We mock ctx.wait_for and intercept publish_message via monkeypatch so the
tests don't need a real broker/listener. Round-trip via real Dramatiq is
covered in tests_with_redis_server_need/test_droplet_check_round_trip.py.
"""

import json
from unittest.mock import MagicMock

import pytest
from traits.api import Bool, HasTraits, List, Str

from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    DropletCheckHandler,
)


# ---------- fixtures ----------

class _FakeRow(HasTraits):
    uuid                 = Str("step-uuid-1")
    check_droplets       = Bool(True)
    activated_electrodes = List(Str)
    routes               = List


class _FakeProtocolCtx:
    def __init__(self, electrode_to_channel=None):
        self.scratch = {"electrode_to_channel": electrode_to_channel or {}}


class _FakeStepCtx:
    def __init__(self, protocol):
        self.protocol = protocol
        # wait_for tests set this to a function returning the next ack.
        self._wait_responses = []  # list of (topic, payload-or-exception)
        self.wait_for_calls = []   # for inspection

    def wait_for(self, topic, timeout=5.0, predicate=None):
        self.wait_for_calls.append((topic, timeout, predicate))
        if not self._wait_responses:
            raise AssertionError(f"unexpected wait_for({topic!r})")
        next_topic, value = self._wait_responses.pop(0)
        assert next_topic == topic, (
            f"test expected wait_for({next_topic!r}) but got wait_for({topic!r})"
        )
        if isinstance(value, Exception):
            raise value
        # Apply predicate filter if test set one (matches real wait_for).
        if predicate is not None:
            assert predicate(value), (
                f"predicate rejected payload {value!r} — test setup mismatch"
            )
        return value


@pytest.fixture
def published(monkeypatch):
    """Intercepts publish_message; returns a list of (topic, message) tuples
    captured during the test."""
    calls = []
    def _capture(topic, message):
        calls.append((topic, message))
    monkeypatch.setattr(
        "dropbot_protocol_controls.protocol_columns.droplet_check_column.publish_message",
        _capture,
    )
    return calls


# ---------- short-circuit paths ----------

def test_column_off_short_circuits_without_publishing(published):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=False, activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))

    result = handler.on_post_step(row, ctx)

    assert result is None
    assert published == []                  # no publish at all
    assert ctx.wait_for_calls == []         # no wait_for either


def test_no_expected_channels_short_circuits_without_publishing(published):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True)     # no electrodes/routes
    ctx = _FakeStepCtx(_FakeProtocolCtx({}))

    result = handler.on_post_step(row, ctx)

    assert result is None
    assert published == []
    assert ctx.wait_for_calls == []


def test_missing_electrode_to_channel_in_scratch_treated_as_empty(published):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx())  # no scratch entry

    result = handler.on_post_step(row, ctx)

    # 'e1' can't map to a channel → expected is empty → short-circuit.
    assert result is None
    assert published == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: tests probably pass trivially because the handler's `on_post_step` returns `None` (skeleton). Verify by reading the test output: no assertion failure. If they pass: that's correct — the skeleton already short-circuits implicitly. Still proceed to step 3, which adds the explicit early returns.

- [ ] **Step 3: Implement the short-circuit early returns** — replace the `on_post_step` body in `droplet_check_column.py`:

```python
import json
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# ... existing imports above ...

class DropletCheckHandler(BaseColumnHandler):
    priority        = 80
    wait_for_topics = [DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE]

    def on_post_step(self, row, ctx):
        if not row.check_droplets:
            return                               # column off → skip silently

        electrode_to_channel = ctx.protocol.scratch.get("electrode_to_channel", {})
        expected = expected_channels_for_step(row, electrode_to_channel)
        if not expected:
            return                               # nothing to check
        # Tasks 5–7 add publish + wait_for + failure path here.
```

- [ ] **Step 4: Re-run tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/protocol_columns/droplet_check_column.py src/dropbot_protocol_controls/tests/test_droplet_check_handler.py
git commit -m "[PPT-8] Task 4 — handler short-circuits when column off / no expected"
```

---

## Task 5: Handler happy path — publish DETECT_DROPLETS, wait for ack, success

- [ ] **Step 1: Add happy-path tests** — append to `test_droplet_check_handler.py`:

```python
# ---------- happy path ----------

def test_happy_path_publishes_detect_and_returns_on_success_match(published):
    handler = DropletCheckHandler()
    row = _FakeRow(
        check_droplets=True,
        activated_electrodes=["e1", "e2"],
    )
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2}))
    ctx._wait_responses = [(
        # backend returns BOTH expected channels → no failure path
        "dropbot/signals/drops_detected",
        json.dumps({"success": True, "detected_channels": [1, 2], "error": ""}),
    )]

    result = handler.on_post_step(row, ctx)

    assert result is None
    # one publish: the DETECT_DROPLETS request
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "dropbot/requests/detect_droplets"
    assert json.loads(payload) == [1, 2]
    # one wait_for, on the response topic, with backend timeout
    assert ctx.wait_for_calls == [(
        "dropbot/signals/drops_detected", 12.0, None
    )]


def test_detect_payload_is_list_of_int_channels_not_electrode_ids(published):
    # Critical wire-format check: backend expects List[int].
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, activated_electrodes=["e3", "e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e3": 3}))
    ctx._wait_responses = [(
        "dropbot/signals/drops_detected",
        json.dumps({"success": True, "detected_channels": [1, 3], "error": ""}),
    )]

    handler.on_post_step(row, ctx)

    sent = json.loads(published[0][1])
    assert sent == [1, 3]                   # sorted, ints
    assert all(isinstance(c, int) for c in sent)
```

- [ ] **Step 2: Run to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py::test_happy_path_publishes_detect_and_returns_on_success_match -v`
Expected: AssertionError — `published` is empty (handler returns before publishing).

- [ ] **Step 3: Implement the publish + wait_for + happy path** — replace the body of `on_post_step` after the early returns:

```python
    def on_post_step(self, row, ctx):
        if not row.check_droplets:
            return

        electrode_to_channel = ctx.protocol.scratch.get("electrode_to_channel", {})
        expected = expected_channels_for_step(row, electrode_to_channel)
        if not expected:
            return

        publish_message(topic=DETECT_DROPLETS, message=json.dumps(expected))
        ack_raw = ctx.wait_for(DROPLETS_DETECTED, timeout=12.0)
        ack = json.loads(ack_raw)
        if not ack.get("success"):
            logger.warning(
                "Droplet detection backend error on step %s: %s; proceeding",
                row.uuid, ack.get("error"),
            )
            return                                 # legacy parity

        detected = [int(c) for c in ack.get("detected_channels", [])]
        missing  = sorted(set(expected) - set(detected))
        if not missing:
            return                                 # all expected → happy path
        # Failure path comes in Task 7.
```

- [ ] **Step 4: Re-run all handler tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: 5 passed (3 short-circuit + 2 happy path).

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/protocol_columns/droplet_check_column.py src/dropbot_protocol_controls/tests/test_droplet_check_handler.py
git commit -m "[PPT-8] Task 5 — handler happy path: publish + wait + success ack"
```

---

## Task 6: Handler timeout + backend-error paths

Both should log and return cleanly (don't crash the protocol). Mirrors legacy "log and proceed" behavior.

- [ ] **Step 1: Add tests** — append to `test_droplet_check_handler.py`:

```python
# ---------- timeout / error paths ----------

def test_backend_error_response_logs_and_returns(published, caplog):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [(
        "dropbot/signals/drops_detected",
        json.dumps({"success": False, "detected_channels": [], "error": "no proxy"}),
    )]

    with caplog.at_level("WARNING"):
        result = handler.on_post_step(row, ctx)

    assert result is None
    assert any("backend error" in r.message.lower() or "no proxy" in r.message.lower()
               for r in caplog.records), \
        f"expected a warning log; got: {[r.message for r in caplog.records]}"


def test_wait_for_timeout_logs_and_returns(published, caplog):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [(
        "dropbot/signals/drops_detected",
        TimeoutError("simulated 12s timeout"),
    )]

    with caplog.at_level("WARNING"):
        result = handler.on_post_step(row, ctx)

    assert result is None
    # The detect was published before the wait timed out.
    assert len(published) == 1
    assert any("timed out" in r.message.lower() for r in caplog.records), \
        f"expected timeout log; got: {[r.message for r in caplog.records]}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: `test_wait_for_timeout_logs_and_returns` fails with the raw TimeoutError propagating out (handler doesn't catch yet). Backend-error test may pass if the log assertion is loose enough — verify either way.

- [ ] **Step 3: Wrap the wait_for in try/except TimeoutError**

Edit the `on_post_step` body — replace the wait_for line:

```python
        publish_message(topic=DETECT_DROPLETS, message=json.dumps(expected))
        try:
            ack_raw = ctx.wait_for(DROPLETS_DETECTED, timeout=12.0)
        except TimeoutError:
            logger.warning(
                "Droplet detection timed out for step %s; proceeding "
                "(backend handles its own retries internally)",
                row.uuid,
            )
            return                                 # legacy parity
        ack = json.loads(ack_raw)
        # ... rest unchanged
```

- [ ] **Step 4: Re-run handler tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/protocol_columns/droplet_check_column.py src/dropbot_protocol_controls/tests/test_droplet_check_handler.py
git commit -m "[PPT-8] Task 6 — handler timeout + backend-error paths log and proceed"
```

---

## Task 7: Handler failure path — UI dialog round-trip + AbortError

Missing channels → publish DECISION_REQUEST → wait for DECISION_RESPONSE → "continue" returns; "pause" raises AbortError. The wait_for uses a predicate to filter by step_uuid (so a stale response from a different step doesn't unblock us).

- [ ] **Step 1: Add failure-path tests** — append to `test_droplet_check_handler.py`:

```python
# ---------- failure path: UI round-trip ----------

import pytest
from pluggable_protocol_tree.execution.exceptions import AbortError
from dropbot_protocol_controls.consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)


def test_missing_channels_publishes_decision_request_with_payload(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   activated_electrodes=["e1", "e2", "e3"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2, "e3": 3}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1, 3], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    handler.on_post_step(row, ctx)

    assert len(published) == 2
    detect_topic, _      = published[0]
    request_topic, body  = published[1]
    assert detect_topic  == "dropbot/requests/detect_droplets"
    assert request_topic == DROPLET_CHECK_DECISION_REQUEST

    parsed = json.loads(body)
    assert parsed["step_uuid"] == "abc"
    assert parsed["expected"]  == [1, 2, 3]
    assert parsed["detected"]  == [1, 3]
    assert parsed["missing"]   == [2]


def test_user_chooses_continue_returns_normally(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   activated_electrodes=["e1", "e2"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    result = handler.on_post_step(row, ctx)

    assert result is None                       # no exception, no return value
    assert len(ctx.wait_for_calls) == 2         # one for ack, one for decision


def test_user_chooses_pause_raises_abort_error(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   activated_electrodes=["e1", "e2"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "pause"})),
    ]

    with pytest.raises(AbortError) as exc_info:
        handler.on_post_step(row, ctx)

    assert "abc" in str(exc_info.value)         # mentions the step uuid


def test_decision_wait_uses_predicate_filtering_by_step_uuid(published):
    # Confirm the predicate accepts matching step_uuid and rejects others.
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="THIS_STEP", check_droplets=True,
                   activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "THIS_STEP", "choice": "continue"})),
    ]

    handler.on_post_step(row, ctx)

    # Inspect the predicate used for the second wait_for call.
    _, _, predicate = ctx.wait_for_calls[1]
    assert predicate is not None
    # Matching uuid → True; mismatched → False.
    assert predicate(json.dumps({"step_uuid": "THIS_STEP", "choice": "x"})) is True
    assert predicate(json.dumps({"step_uuid": "OTHER_STEP", "choice": "x"})) is False


def test_decision_wait_uses_24h_timeout(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True, activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    handler.on_post_step(row, ctx)

    _, timeout, _ = ctx.wait_for_calls[1]
    assert timeout == 86_400.0                  # spec § 4 design note
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: 5 new tests fail (handler doesn't yet publish DECISION_REQUEST or raise AbortError).

- [ ] **Step 3: Add the failure path** — append to `on_post_step` body, after `if not missing: return`:

```python
        # ---- failure path: ask the user via UI round-trip ----
        from pluggable_protocol_tree.execution.exceptions import AbortError

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
            timeout=86_400.0,                    # 24h "effectively infinite"; stop_event interrupts
            predicate=lambda payload: json.loads(payload).get("step_uuid") == row.uuid,
        )
        decision = json.loads(decision_raw).get("choice")
        if decision == "pause":
            raise AbortError(
                f"User chose to pause after droplet check on step {row.uuid}"
            )
        # else "continue" → fall through, executor moves to next step
```

Move the `from pluggable_protocol_tree.execution.exceptions import AbortError` to the top-level imports of the file (cleaner than inline import).

- [ ] **Step 4: Re-run handler tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_droplet_check_handler.py -v`
Expected: 12 passed (3 short-circuit + 2 happy + 2 timeout/error + 5 failure).

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/protocol_columns/droplet_check_column.py src/dropbot_protocol_controls/tests/test_droplet_check_handler.py
git commit -m "[PPT-8] Task 7 — handler failure path: UI round-trip + AbortError"
```

---

## Task 8: Decision dialog actor + tests

The GUI-side actor that subscribes to DROPLET_CHECK_DECISION_REQUEST, marshals to the Qt thread, calls `confirm`, publishes DROPLET_CHECK_DECISION_RESPONSE.

**Files:**
- Create: `dropbot_protocol_controls/services/droplet_check_decision_dialog_actor.py`
- Create: `dropbot_protocol_controls/tests/test_decision_dialog_actor.py`

- [ ] **Step 1: Write the actor tests** — create `dropbot_protocol_controls/tests/test_decision_dialog_actor.py`:

```python
"""Tests for DropletCheckDecisionDialogActor.

We patch QTimer.singleShot to invoke immediately (no Qt event loop in
tests) and patch pyface_wrapper.confirm to return a controllable bool."""

import json
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def patched_confirm():
    with patch(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.confirm"
    ) as mock_confirm:
        yield mock_confirm


@pytest.fixture
def captured_publishes(monkeypatch):
    calls = []
    def _capture(topic, message):
        calls.append((topic, message))
    monkeypatch.setattr(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.publish_message",
        _capture,
    )
    return calls


@pytest.fixture
def immediate_singleshot(monkeypatch):
    """Replace QTimer.singleShot(delay, fn) with an immediate fn() call so
    tests don't need a running Qt event loop."""
    monkeypatch.setattr(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.QTimer",
        MagicMock(singleShot=lambda delay, fn: fn()),
    )


def test_confirm_returning_true_publishes_continue(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE

    patched_confirm.return_value = True

    actor = DropletCheckDecisionDialogActor()
    payload = {"step_uuid": "abc", "expected": [1, 2], "detected": [1], "missing": [2]}
    actor.listener_actor_routine(json.dumps(payload), topic="ignored")

    assert len(captured_publishes) == 1
    topic, body = captured_publishes[0]
    assert topic == DROPLET_CHECK_DECISION_RESPONSE
    parsed = json.loads(body)
    assert parsed == {"step_uuid": "abc", "choice": "continue"}


def test_confirm_returning_false_publishes_pause(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE

    patched_confirm.return_value = False

    actor = DropletCheckDecisionDialogActor()
    payload = {"step_uuid": "abc", "expected": [1, 2], "detected": [], "missing": [1, 2]}
    actor.listener_actor_routine(json.dumps(payload), topic="ignored")

    topic, body = captured_publishes[0]
    parsed = json.loads(body)
    assert parsed == {"step_uuid": "abc", "choice": "pause"}


def test_dialog_message_includes_expected_detected_missing(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    patched_confirm.return_value = True

    actor = DropletCheckDecisionDialogActor()
    payload = {"step_uuid": "abc", "expected": [1, 2, 3], "detected": [1, 3], "missing": [2]}
    actor.listener_actor_routine(json.dumps(payload), topic="ignored")

    # Inspect the message string passed to confirm()
    args, kwargs = patched_confirm.call_args
    message = kwargs.get("message") or (args[1] if len(args) >= 2 else "")
    assert "1, 2, 3" in message    # expected
    assert "1, 3"    in message    # detected
    assert "2"       in message    # missing


def test_step_uuid_round_trips_through_dialog(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    patched_confirm.return_value = True

    actor = DropletCheckDecisionDialogActor()
    actor.listener_actor_routine(
        json.dumps({"step_uuid": "step-xyz-789",
                    "expected": [1], "detected": [], "missing": [1]}),
        topic="ignored",
    )

    parsed = json.loads(captured_publishes[0][1])
    assert parsed["step_uuid"] == "step-xyz-789"


def test_listener_name_is_pptN_free():
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    actor = DropletCheckDecisionDialogActor()
    assert actor.listener_name == "droplet_check_decision_listener"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_decision_dialog_actor.py -v`
Expected: ImportError on the actor class (module doesn't exist yet).

- [ ] **Step 3: Implement the actor** — create `dropbot_protocol_controls/services/droplet_check_decision_dialog_actor.py`:

```python
"""GUI-side actor for the PPT-8 droplet-check failure dialog.

Subscribes to DROPLET_CHECK_DECISION_REQUEST. When fired, marshals to
the Qt main thread via QTimer.singleShot, shows a styled confirm dialog
via the pyface_wrapper, and publishes the user's choice on
DROPLET_CHECK_DECISION_RESPONSE.

The actor instance is created at plugin start (see
dropbot_protocol_controls/plugin.py); the @dramatiq.actor registration
happens at module import time via generate_class_method_dramatiq_listener_actor.
"""

import json

import dramatiq
from pyface.qt.QtCore import QTimer
from pyface.qt.QtWidgets import QApplication
from traits.api import HasTraits, Instance, Str

from logger.logger_service import get_logger
from microdrop_application.dialogs.pyface_wrapper import confirm
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..consts import (
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
    DROPLET_CHECK_DECISION_RESPONSE,
)


logger = get_logger(__name__)


class DropletCheckDecisionDialogActor(HasTraits):
    """Receives DROPLET_CHECK_DECISION_REQUEST, shows a confirm dialog
    on the Qt main thread, publishes the user's choice."""

    listener_name = Str(DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def listener_actor_routine(self, message, topic):
        """Worker thread: parse payload, marshal to Qt thread to show dialog."""
        try:
            payload = json.loads(message)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "droplet_check_decision_listener: rejecting malformed message %r (%s)",
                message, exc,
            )
            return
        QTimer.singleShot(0, lambda: self._show_dialog_and_respond(payload))

    def _show_dialog_and_respond(self, payload):
        """Qt main thread: show confirm dialog, publish response."""
        message = self._format_message(payload)
        try:
            user_continue = confirm(
                parent=QApplication.activeWindow(),
                message=message,
                title="Droplet Detection Failed",
                yes_label="Continue", no_label="Stay Paused",
            )
        except Exception:
            logger.exception("droplet_check dialog raised; defaulting to pause")
            user_continue = False
        publish_message(
            topic=DROPLET_CHECK_DECISION_RESPONSE,
            message=json.dumps({
                "step_uuid": payload["step_uuid"],
                "choice":    "continue" if user_continue else "pause",
            }),
        )

    @staticmethod
    def _format_message(payload):
        def _fmt(seq):
            return ", ".join(str(c) for c in seq) if seq else "none"
        return (
            "Droplet detection failed at the end of the step.\n\n"
            f"Expected: {_fmt(payload.get('expected', []))}\n"
            f"Detected: {_fmt(payload.get('detected', []))}\n"
            f"Missing:  {_fmt(payload.get('missing', []))}\n\n"
            "Continue with the protocol anyway?"
        )

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )
```

- [ ] **Step 4: Re-run actor tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_decision_dialog_actor.py -v`
Expected: 5 passed.

If `confirm` import fails, check whether `pyface_wrapper.confirm` exists with that signature. If the real signature differs, adjust both the test and the actor — the assertion is "the actor calls a `confirm` whose return-bool drives the topic choice"; the exact kwarg names can flex.

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/services/droplet_check_decision_dialog_actor.py src/dropbot_protocol_controls/tests/test_decision_dialog_actor.py
git commit -m "[PPT-8] Task 8 — UI-side decision dialog actor"
```

---

## Task 9: Plugin wiring + api.py re-export

**Files:**
- Modify: `dropbot_protocol_controls/plugin.py`
- Modify: `microdrop_utils/api.py`
- Create: `dropbot_protocol_controls/tests/test_plugin_wiring_droplet.py`

- [ ] **Step 1: Write a small wiring test** — create `dropbot_protocol_controls/tests/test_plugin_wiring_droplet.py`:

```python
"""Confirm the DropbotProtocolControlsPlugin contributes the new column
and the dialog actor module is imported (which registers the actor)."""

def test_make_droplet_check_column_in_plugin_defaults():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin

    plugin = DropbotProtocolControlsPlugin()
    cols = plugin._contributed_protocol_columns_default()
    col_ids = [c.model.col_id for c in cols]
    assert "check_droplets" in col_ids


def test_dialog_actor_module_importable():
    # Just importing the module should register the @dramatiq.actor.
    import dropbot_protocol_controls.services.droplet_check_decision_dialog_actor  # noqa: F401


def test_actor_topic_routing_includes_decision_request_topic():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    from dropbot_protocol_controls.consts import (
        DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        DROPLET_CHECK_DECISION_REQUEST,
    )

    plugin = DropbotProtocolControlsPlugin()
    # actor_topic_routing is List([ACTOR_TOPIC_DICT], ...)
    routing = plugin.actor_topic_routing[0]
    assert routing[DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME] == [
        DROPLET_CHECK_DECISION_REQUEST,
    ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_plugin_wiring_droplet.py -v`
Expected: First test fails (column not in defaults).

- [ ] **Step 3: Update plugin.py** — modify `dropbot_protocol_controls/plugin.py`:

```python
"""DropbotProtocolControlsPlugin — contributes voltage/frequency/force/
droplet-check columns to the pluggable protocol tree, plus the
GUI-side actor for the droplet-check failure dialog (PPT-8).
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from message_router.consts import ACTOR_TOPIC_ROUTES
from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from .protocol_columns.voltage_column import make_voltage_column
from .protocol_columns.frequency_column import make_frequency_column
from .protocol_columns.force_column import make_force_column
from .protocol_columns.droplet_check_column import make_droplet_check_column
# Importing the actor module registers its @dramatiq.actor at import time;
# subscription is wired automatically via ACTOR_TOPIC_DICT below.
from .services import droplet_check_decision_dialog_actor as _ddialog_actor  # noqa: F401


logger = get_logger(__name__)


class DropbotProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [
            make_voltage_column(),
            make_frequency_column(),
            make_force_column(),
            make_droplet_check_column(),
        ]
```

Note on the actor instance: PPT-7's calibration listener works without an explicit instance because its `@dramatiq.actor` is on a module-level function. Our dialog actor is class-method-bound (needs `self` for state). Module import alone registers the actor IF we instantiate the class somewhere at import time — add this to the bottom of `droplet_check_decision_dialog_actor.py`:

```python
# Module-level singleton — instantiating registers the actor with Dramatiq.
# Plugin import (above) brings this module in and the actor wakes up.
_dialog_actor_singleton = DropletCheckDecisionDialogActor()
```

(Add this line to the actor module — it's part of Step 3.)

- [ ] **Step 4: Update `microdrop_utils/api.py`**

The new topics live in `dropbot_protocol_controls.consts`, which has no module alias in `api.py` yet. Add one, then add the two topic re-exports under the existing `UITopics` class.

Edit `src/microdrop_utils/api.py`:

```python
# After line 87 (the existing module-alias imports), add:
from dropbot_protocol_controls import consts as _dpc
```

Then in the `UITopics` class (line 163), add the two new topics next to the existing `CALIBRATION_DATA` line:

```python
class UITopics:
    """Topics for UI state synchronisation between frontend plugins."""
    # ... existing entries above ...
    CALIBRATION_DATA                = _device_viewer.CALIBRATION_DATA
    # PPT-8 — droplet check decision dialog round-trip
    DROPLET_CHECK_DECISION_REQUEST  = _dpc.DROPLET_CHECK_DECISION_REQUEST
    DROPLET_CHECK_DECISION_RESPONSE = _dpc.DROPLET_CHECK_DECISION_RESPONSE
    # ... existing entries below ...
```

- [ ] **Step 5: Re-run wiring tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_plugin_wiring_droplet.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the full dropbot_protocol_controls test sweep to catch any regressions**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/ -v --ignore=src/dropbot_protocol_controls/tests/tests_with_redis_server_need`
Expected: all green (existing PPT-4/PPT-7 + new PPT-8 unit tests).

- [ ] **Step 7: Commit**

```bash
git add src/dropbot_protocol_controls/plugin.py src/dropbot_protocol_controls/services/droplet_check_decision_dialog_actor.py src/microdrop_utils/api.py src/dropbot_protocol_controls/tests/test_plugin_wiring_droplet.py
git commit -m "[PPT-8] Task 9 — wire column + dialog actor into plugin; api.py re-exports"
```

---

## Task 10: In-process responder for the demo

**Files:**
- Create: `dropbot_protocol_controls/demos/droplet_detection_responder.py`
- Create: `dropbot_protocol_controls/tests/test_demo_responder_droplet.py`

- [ ] **Step 1: Write the responder tests** — create `dropbot_protocol_controls/tests/test_demo_responder_droplet.py`:

```python
"""Tests for the in-process demo responder that fakes
DropletDetectionMixinService."""

import json
from unittest.mock import patch


def test_succeed_mode_returns_all_requested_channels(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DROPLETS_DETECTED, DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="succeed")
    r.listener_actor_routine(json.dumps([1, 2, 3]), DETECT_DROPLETS)

    assert len(captured) == 1
    topic, body = captured[0]
    assert topic == DROPLETS_DETECTED
    parsed = json.loads(body)
    assert parsed["success"] is True
    assert parsed["detected_channels"] == [1, 2, 3]
    assert parsed["error"] == ""


def test_drop_one_mode_drops_first_channel(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="drop_one")
    r.listener_actor_routine(json.dumps([3, 4, 5]), DETECT_DROPLETS)

    parsed = json.loads(captured[0][1])
    assert parsed["detected_channels"] == [4, 5]
    assert parsed["success"] is True


def test_drop_all_mode_returns_empty_list(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="drop_all")
    r.listener_actor_routine(json.dumps([1, 2]), DETECT_DROPLETS)

    parsed = json.loads(captured[0][1])
    assert parsed["detected_channels"] == []
    assert parsed["success"] is True


def test_error_mode_returns_success_false(monkeypatch):
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    captured = []
    monkeypatch.setattr(
        "dropbot_protocol_controls.demos.droplet_detection_responder.publish_message",
        lambda topic, message: captured.append((topic, message)),
    )

    r = DropletDetectionResponder(mode="error")
    r.listener_actor_routine(json.dumps([1, 2]), DETECT_DROPLETS)

    parsed = json.loads(captured[0][1])
    assert parsed["success"] is False
    assert parsed["error"] != ""


def test_last_request_channels_is_recorded():
    from dropbot_protocol_controls.demos.droplet_detection_responder import (
        DropletDetectionResponder,
    )
    from dropbot_controller.consts import DETECT_DROPLETS

    r = DropletDetectionResponder(mode="succeed")
    # Don't bother capturing publish in this one
    r.listener_actor_routine(json.dumps([7, 8, 9]), DETECT_DROPLETS)
    assert list(r.last_request_channels) == [7, 8, 9]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_demo_responder_droplet.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the responder** — create `dropbot_protocol_controls/demos/droplet_detection_responder.py`:

```python
"""In-process Dramatiq actor that stands in for DropletDetectionMixinService
in demos. Subscribes to DETECT_DROPLETS, publishes DROPLETS_DETECTED with
a configurable response shape so the demo can exercise success / missing /
error paths without hardware.

Mirrors voltage_frequency_responder.py shape, but with class-method state
for the switchable mode (so the Tools menu can flip between scenarios at
runtime)."""

import json
import logging

import dramatiq
from traits.api import Enum, HasTraits, Instance, Int, List, Str

from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED


logger = logging.getLogger(__name__)

DEMO_DROPLET_RESPONDER_ACTOR_NAME = "demo_droplet_detection_responder"
EXECUTOR_LISTENER_ACTOR_NAME = "pluggable_protocol_tree_executor_listener"
"""Reference: matches what voltage_frequency_responder.py uses."""


class DropletDetectionResponder(HasTraits):
    """Configurable fake of the dropbot droplet-detection backend."""

    listener_name = Str(DEMO_DROPLET_RESPONDER_ACTOR_NAME)
    mode = Enum("succeed", "drop_one", "drop_all", "error")
    last_request_channels = List(Int)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    def listener_actor_routine(self, message, topic):
        try:
            requested = [int(c) for c in json.loads(message)]
        except (ValueError, TypeError) as exc:
            logger.warning(
                "[demo droplet responder] malformed request %r (%s); ignoring",
                message, exc,
            )
            return
        self.last_request_channels = requested

        if self.mode == "error":
            payload = {"success": False, "detected_channels": [],
                       "error": "Demo: simulated backend error"}
        elif self.mode == "drop_all":
            payload = {"success": True, "detected_channels": [], "error": ""}
        elif self.mode == "drop_one":
            # Drop the FIRST channel (responder is deterministic; demo's
            # walkthrough in the spec uses this convention).
            payload = {"success": True, "detected_channels": requested[1:],
                       "error": ""}
        else:  # "succeed"
            payload = {"success": True, "detected_channels": requested,
                       "error": ""}

        publish_message(topic=DROPLETS_DETECTED, message=json.dumps(payload))
        logger.info("[demo droplet responder] mode=%s replied %s",
                    self.mode, payload["detected_channels"])

    def traits_init(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine,
        )

    def subscribe(self, router):
        """Wire the responder + executor listener for the round-trip on
        ``router``. Must be called from the demo's routing_setup."""
        # 1. Responder subscribes to DETECT_DROPLETS so it sees the request.
        router.message_router_data.add_subscriber_to_topic(
            topic=DETECT_DROPLETS,
            subscribing_actor_name=self.listener_name,
        )
        # 2. Executor's listener subscribes to DROPLETS_DETECTED + the
        # decision-response topic so the handler's wait_for unblocks.
        from dropbot_protocol_controls.consts import (
            DROPLET_CHECK_DECISION_RESPONSE,
        )
        for topic in (DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE):
            router.message_router_data.add_subscriber_to_topic(
                topic=topic,
                subscribing_actor_name=EXECUTOR_LISTENER_ACTOR_NAME,
            )
        # 3. The dialog actor subscribes to DROPLET_CHECK_DECISION_REQUEST
        # via ACTOR_TOPIC_DICT in production. In the demo we manually wire
        # it (no MessageRouterPlugin lifecycle in demos).
        from dropbot_protocol_controls.consts import (
            DROPLET_CHECK_DECISION_REQUEST,
            DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
        router.message_router_data.add_subscriber_to_topic(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
```

- [ ] **Step 4: Re-run responder tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/test_demo_responder_droplet.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dropbot_protocol_controls/demos/droplet_detection_responder.py src/dropbot_protocol_controls/tests/test_demo_responder_droplet.py
git commit -m "[PPT-8] Task 10 — in-process droplet detection responder"
```

---

## Task 11: Demo window — `run_droplet_check_demo.py`

The full Tools-menu demo, mirroring `run_force_demo.py`. Three steps with electrodes set up, default `drop_one` mode, Tools menu to switch modes + re-run.

**Files:**
- Create: `dropbot_protocol_controls/demos/run_droplet_check_demo.py`

This file has no automated tests — it's manually verified in Task 13's acceptance run. Static-import-only check is enough for Step 4 below.

- [ ] **Step 1: Implement the demo** — create `dropbot_protocol_controls/demos/run_droplet_check_demo.py`:

```python
"""PPT-8 demo — droplet-check column with switchable in-process responder.

Opens a Qt window with 3 pre-populated steps. The 'Check Droplets' column
is hidden by default — header right-click to surface it.

The demo's responder defaults to 'drop_one' mode so the failure dialog
fires on the first run without any menu interaction. Use the Tools menu
to switch mode and Tools -> Re-run to iterate.

Run: pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo
"""

import logging

from pyface.qt.QtGui import QActionGroup
from pyface.qt.QtWidgets import QAction

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.demos.base_demo_window import (
    BasePluggableProtocolDemoWindow, DemoConfig,
)

from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    make_droplet_check_column,
)
from dropbot_protocol_controls.demos.droplet_detection_responder import (
    DropletDetectionResponder,
)


# Module-level so the Tools menu can flip its `mode` at runtime and the
# next protocol run picks up the change.
_responder = DropletDetectionResponder(mode="drop_one")


# Map electrode IDs to channels (1-indexed, deterministic).
_ELECTRODE_TO_CHANNEL = {f"e{i}": i for i in range(1, 7)}


def _columns():
    """PPT-3 builtins + droplet check (sufficient for the demo).
    Voltage/frequency/force are NOT needed here — focus is on the new
    column's behavior, not on integration with other PPT-7 columns."""
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_droplet_check_column(),
    ]


def _pre_populate(rm):
    """3 steps from the spec walkthrough."""
    rm.protocol_metadata["electrode_to_channel"] = dict(_ELECTRODE_TO_CHANNEL)
    rm.add_step(values={
        "name": "S1", "duration_s": 0.3,
        "activated_electrodes": ["e1", "e2"],
        "check_droplets": True,
    })
    rm.add_step(values={
        "name": "S2", "duration_s": 0.3,
        "activated_electrodes": ["e3", "e4", "e5"],
        "check_droplets": True,
    })
    rm.add_step(values={
        "name": "S3", "duration_s": 0.3,
        "activated_electrodes": ["e6"],
        "check_droplets": False,
    })


def _routing_setup(router):
    _responder.subscribe(router)


def _install_tools_menu(window):
    menu_bar = window.menuBar()
    tools_menu = menu_bar.addMenu("Tools")

    mode_menu = tools_menu.addMenu("Responder Mode")
    mode_group = QActionGroup(window)
    mode_group.setExclusive(True)
    for mode_label, mode_value in [
        ("Always succeed",      "succeed"),
        ("Drop one channel",    "drop_one"),
        ("Drop all channels",   "drop_all"),
        ("Error reply",         "error"),
    ]:
        action = QAction(mode_label, window, checkable=True)
        action.setChecked(mode_value == _responder.mode)
        action.triggered.connect(
            lambda _checked=False, mv=mode_value: _set_mode(mv)
        )
        mode_group.addAction(action)
        mode_menu.addAction(action)

    rerun = QAction("Re-run Protocol", window)
    rerun.setShortcut("Ctrl+R")
    rerun.triggered.connect(lambda: _rerun_protocol(window))
    tools_menu.addAction(rerun)


def _set_mode(mode_value):
    _responder.mode = mode_value
    logging.getLogger(__name__).info(
        "[droplet-check-demo] responder mode -> %s", mode_value,
    )


def _rerun_protocol(window):
    """Tell the demo's executor to start over from step 0."""
    # The base demo window exposes a 'run' button / method; if your
    # version uses a different name, follow base_demo_window.py.
    if hasattr(window, "_on_run_clicked"):
        window._on_run_clicked()
    elif hasattr(window, "run_protocol"):
        window.run_protocol()
    else:
        logging.getLogger(__name__).warning(
            "[droplet-check-demo] don't know how to re-run; click Run manually"
        )


def _post_build(window):
    _install_tools_menu(window)


config = DemoConfig(
    columns_factory=_columns,
    title="PPT-8 Demo — Droplet Check Column (switchable responder)",
    pre_populate=_pre_populate,
    routing_setup=_routing_setup,
    phase_ack_topic=ELECTRODES_STATE_APPLIED,
    post_build_setup=_post_build,
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    BasePluggableProtocolDemoWindow.run(config)


if __name__ == "__main__":
    from microdrop_utils.broker_server_helpers import (
        redis_server_context, dramatiq_workers_context,
    )
    with redis_server_context():
        with dramatiq_workers_context():
            main()
```

- [ ] **Step 2: Static import check**

Run: `pixi run python -c "import dropbot_protocol_controls.demos.run_droplet_check_demo; print('OK')"`
Expected: `OK` printed.

If the `_on_run_clicked` / `run_protocol` references don't match the base demo window's API, edit `_rerun_protocol(window)` to call whatever method the base actually exposes for "kick off the protocol from step 0". Check `pluggable_protocol_tree/demos/base_demo_window.py` for the right name.

- [ ] **Step 3: Manual smoke (skip if you can't run a Qt app right now — Task 13 covers this)**

If you have a Qt-capable environment available:
- Run: `pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo`
- Window opens with 3 steps, "Check Droplets" column hidden.
- Header right-click → "Show Check Droplets" → column appears with values T/T/F.
- Click Run → S1 dialog appears.
- Verify dialog text mentions Expected: 1, 2 / Detected: 2 / Missing: 1.
- Click "Continue" → S2 dialog appears with 3, 4, 5 / 4, 5 / 3.
- Click "Continue" → S3 runs (no dialog, column off) → protocol completes.
- Tools → Responder Mode → "Always succeed" → Tools → Re-run → all 3 steps complete with no dialog.

- [ ] **Step 4: Commit**

```bash
git add src/dropbot_protocol_controls/demos/run_droplet_check_demo.py
git commit -m "[PPT-8] Task 11 — run_droplet_check_demo with Tools menu"
```

---

## Task 12: Redis-backed end-to-end integration test

Real Dramatiq broker, real round-trip. Mirrors PPT-7's `test_calibration_round_trip.py`.

**Files:**
- Create: `dropbot_protocol_controls/tests/tests_with_redis_server_need/test_droplet_check_round_trip.py`

- [ ] **Step 1: Write the integration test**

```python
"""End-to-end Dramatiq round-trip for the PPT-8 droplet-check column.

Skipped automatically by the parent conftest if Redis is not running.
"""

import json
import time
from unittest.mock import patch

import pytest

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED
from dropbot_protocol_controls.consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)
from dropbot_protocol_controls.demos.droplet_detection_responder import (
    DropletDetectionResponder,
)


def _wait_for(condition_fn, timeout=5.0, poll=0.05):
    """Poll until condition_fn() returns True or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(poll)
    return False


def test_responder_replies_to_detect_droplets_with_succeed_mode(redis_router):
    responder = DropletDetectionResponder(mode="succeed")
    responder.subscribe(redis_router)

    received = []
    def _capture(message, topic, timestamp=None):
        received.append((topic, message))
    # Subscribe a capture actor to DROPLETS_DETECTED (in addition to the
    # executor listener subscribed by responder.subscribe).
    # ... use whatever helper your test framework already has for this;
    # PPT-7's test_calibration_round_trip.py is the precedent.

    publish_message(topic=DETECT_DROPLETS, message=json.dumps([1, 2, 3]))

    assert _wait_for(lambda: len(received) >= 1)
    topic, body = received[-1]
    assert topic == DROPLETS_DETECTED
    parsed = json.loads(body)
    assert parsed["success"] is True
    assert parsed["detected_channels"] == [1, 2, 3]


def test_decision_round_trip_continue(redis_router):
    """Publish a fake DECISION_REQUEST → mock the dialog to choose Continue
    → confirm DECISION_RESPONSE arrives with choice=continue."""
    # Patch confirm to immediately return True (Continue)
    with patch(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.confirm",
        return_value=True,
    ), patch(
        # Replace QTimer.singleShot with immediate execution so the test
        # doesn't need a Qt event loop.
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.QTimer.singleShot",
        side_effect=lambda delay, fn: fn(),
    ):
        # Wire the dialog actor's subscription on the test router.
        from dropbot_protocol_controls.consts import (
            DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
        redis_router.message_router_data.add_subscriber_to_topic(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
        # Capture DECISION_RESPONSE
        received = []
        # ... subscribe a capture actor — see PPT-7 precedent

        publish_message(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            message=json.dumps({
                "step_uuid": "test-uuid",
                "expected": [1, 2], "detected": [1], "missing": [2],
            }),
        )

        assert _wait_for(lambda: len(received) >= 1)
        topic, body = received[-1]
        assert topic == DROPLET_CHECK_DECISION_RESPONSE
        parsed = json.loads(body)
        assert parsed == {"step_uuid": "test-uuid", "choice": "continue"}
```

The `redis_router` fixture and capture-actor helper need to come from whatever pattern PPT-7's `test_calibration_round_trip.py` uses. **Read that file before implementing** — match its fixture structure exactly.

- [ ] **Step 2: Read PPT-7's integration test for the fixture pattern**

```bash
cat src/dropbot_protocol_controls/tests/tests_with_redis_server_need/test_calibration_round_trip.py
```

Adapt the test you wrote in Step 1 to use the same fixtures/helpers as that file. (Don't copy-paste-modify; match the import + fixture pattern so the team has consistent tests.)

- [ ] **Step 3: Run tests**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/tests_with_redis_server_need/test_droplet_check_round_trip.py -v`
Expected (Redis running): 2 passed. (Redis not running): all skipped via parent conftest.

- [ ] **Step 4: Commit**

```bash
git add src/dropbot_protocol_controls/tests/tests_with_redis_server_need/test_droplet_check_round_trip.py
git commit -m "[PPT-8] Task 12 — Redis-backed round-trip test for droplet check"
```

---

## Task 13: Regression sweep + PR

- [ ] **Step 1: Full unit sweep on dropbot_protocol_controls**

Run: `pixi run pytest src/dropbot_protocol_controls/tests/ -v --ignore=src/dropbot_protocol_controls/tests/tests_with_redis_server_need`
Expected: all PPT-4/PPT-7/PPT-8 tests green.

- [ ] **Step 2: Full unit sweep on pluggable_protocol_tree (no Redis)**

Run: `pixi run pytest src/pluggable_protocol_tree/tests/ -v --ignore=src/pluggable_protocol_tree/tests/tests_with_redis_server_need`
Expected: all green except the known-flaky `test_run_hooks_fans_same_priority_in_parallel` (timing-sensitive — pre-existing on master, NOT a PPT-8 regression). Confirm with `git stash && pixi run pytest <that test> && git stash pop` if uncertain.

- [ ] **Step 3: Full unit sweep on related downstream packages**

Run: `pixi run pytest src/peripheral_protocol_controls/tests/ src/video_protocol_controls/tests/ -v --ignore-glob=*tests_with_redis_server_need*`
Expected: all green (no PPT-8 changes touched these, but verify nothing broke through shared imports).

- [ ] **Step 4: Manual demo run** (acceptance criterion 1)

Run: `pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo`
Acceptance: see spec § 11. Walk through Continue, Stay Paused, Always-succeed, Drop-all, Error modes. Verify each behavior.

- [ ] **Step 5: Push the branch and open the PR**

```bash
git push -u origin feat/ppt-8-droplet-check-column
gh pr create --title "[PPT-8] Migrate droplet detection to per-step column" --body "$(cat <<'EOF'
## Summary

Closes #370. Migrates the per-step droplet-presence verification feature out of legacy `protocol_grid` into a contributed column on `dropbot_protocol_controls`. Per-step `check_droplets: Bool` (hidden by default, defaults `True`); `on_post_step` handler at priority 80 publishes `DETECT_DROPLETS`, waits for `DROPLETS_DETECTED`, drives a `confirm`-dialog round-trip via two new UI topics on missing channels.

## Design (locked in spec)

- See: `docs/superpowers/specs/2026-04-30-ppt-8-droplet-detection-design.md`
- Per-step Bool column (vs legacy global toggle) — picks up the framework's hidden-column UX for free.
- Failure dialog uses `pyface_wrapper.confirm` (not raw `QDialog`) per the project's dialog rule.
- "Stay Paused" raises `AbortError` → existing executor abort path → `protocol_aborted` signal. No new pause-from-hook primitive.
- Backend (`DropletDetectionMixinService`) unchanged; coexistence with legacy `protocol_grid` is safe (only one of the two callers fires `_waiting_for_droplet_check`).
- Actor naming: `droplet_check_decision_listener` (no `pptN_` prefix).

## What changed

| Layer | File(s) |
|---|---|
| Topic constants | `dropbot_protocol_controls/consts.py`, `microdrop_utils/api.py` |
| Column | `dropbot_protocol_controls/protocol_columns/droplet_check_column.py` (NEW) |
| GUI dialog actor | `dropbot_protocol_controls/services/droplet_check_decision_dialog_actor.py` (NEW) |
| Plugin contribution | `dropbot_protocol_controls/plugin.py` |
| Demo | `dropbot_protocol_controls/demos/run_droplet_check_demo.py` (NEW), `dropbot_protocol_controls/demos/droplet_detection_responder.py` (NEW) |

**Not touched** (deferred to PPT-9): `protocol_grid/services/protocol_runner_controller.py`, `protocol_grid/extra_ui_elements.py`, `protocol_grid/widget.py`, `protocol_grid/services/message_listener.py`. Both pipes coexist.

## Tests

- 8 unit tests for column (model/view/factory/handler declarations)
- 10 unit tests for `expected_channels_for_step` helper
- 12 unit tests for handler `on_post_step` (short-circuit, happy, timeout/error, failure round-trip, predicate, AbortError)
- 5 unit tests for dialog actor (mocked `confirm` + `QTimer.singleShot`)
- 5 unit tests for demo responder (modes)
- 3 unit tests for plugin wiring
- 3 persistence tests (Bool round-trip, metadata in payload, default on missing field)
- 2 Redis integration tests (responder round-trip, decision round-trip)

## Follow-ups (separate issues to file)

- Protocol menu → "Toggle Check Droplets on all steps" (replaces legacy global checkbox)
- Custom-styled `DropletCheckFailureDialog(BaseMessageDialog)` if plain `confirm` text loses too much info
- Staggered route-end verification revisit (legacy `_get_individual_path_last_phase_electrodes`)
- Add `timeout=None` support to `wait_for` in `pluggable_protocol_tree`

## Test plan

- [ ] CI: full unit sweep + 2 Redis integration tests pass
- [ ] Manual: `pixi run python -m dropbot_protocol_controls.demos.run_droplet_check_demo` walkthrough per spec § 11
- [ ] No regression in legacy droplet detection (legacy nav-bar checkbox still works)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: File the follow-up issues**

For each entry in the "Follow-ups" list above, file a separate GitHub issue:
- Title format: `[PPT-8 follow-up] <description>`
- Body: 2-3 sentences explaining what + why, link back to PR
- Add to umbrella issue #361's checklist if appropriate

- [ ] **Step 7: Commit submodule pointer in outer repo**

The inner `src/` submodule is now at the head of `feat/ppt-8-droplet-check-column`. Update the outer pointer:

```bash
cd /c/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py
git add src
git commit -m "[PPT-8] bump submodule to feat/ppt-8-droplet-check-column"
```

(Skip pushing the outer repo unless team workflow requires it. PPT-7 only updated the submodule pointer after the inner PR merged — same convention.)

---

## Spec coverage check

Mapping from spec § to plan tasks:

| Spec section | Implementing task(s) |
|---|---|
| § 0 Scope | All tasks together |
| § 1 Decisions | Reflected in design choices throughout |
| § 2 File layout | Tasks 1, 2/3, 8, 9, 10, 11 (file creations) |
| § 3 Topics | Task 1 (consts), Task 9 (api.py re-export) |
| § 4 The column | Tasks 2, 3, 4, 5, 6, 7 |
| § 5 UI dialog actor | Task 8 |
| § 6 Demo | Tasks 10, 11 |
| § 7 Tests | Tasks 1–12 each include their own test set; § 7 totals match |
| § 8 What we don't touch | Confirmed in the "Not touched" sections; verified by Task 13 regression sweep |
| § 9 Follow-ups | Task 13 step 6 |
| § 10 Out of scope | Not implemented (by design) |
| § 11 Acceptance criteria | Task 13 manual demo walkthrough |

All spec sections have implementing tasks except § 1 (decisions, just rationale) and § 10 (out of scope, deliberately not implemented).

---

## Total scope

**13 tasks**, ~50 unit tests, 2 Redis integration tests, 1 demo, 5 new files, 3 modified files. Comparable scope to PPT-7 (PR #401).
