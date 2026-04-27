# PPT-4 Voltage + Frequency Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-step `voltage` and `frequency` Int columns to the pluggable protocol tree, contributed by a new `dropbot_protocol_controls` plugin. Both setpoints land on the connected DropBot before electrode actuation runs in each step.

**Architecture:** New sibling plugin `dropbot_protocol_controls/` contributes two columns through the existing `PROTOCOL_COLUMNS` extension point. `dropbot_controller/` gains 4 new topic constants and 2 new request handlers (`on_protocol_set_voltage_request` / `on_protocol_set_frequency_request`) that bypass the realtime-mode gate and skip prefs persistence. Voltage/frequency handlers run at priority 20 (parallel within bucket); RoutesHandler stays at priority 30, so setpoints are always applied before any phase publish.

**Tech Stack:** Python 3.x, Traits/HasTraits, Envisage plugins, Pyface Qt for views, Dramatiq + Redis for pub/sub, pytest for tests, dropbot.py SerialProxy for hardware.

**Spec:** `src/docs/superpowers/specs/2026-04-24-ppt-4-voltage-frequency-design.md`

**Type policy:** voltage and frequency are **Ints** end-to-end — column trait, payload string, ack value, preference. No floats anywhere in this feature.

**Branch:** `feat/ppt-4-dropbot-columns` — branched from `feat/ppt-3-electrodes-routes` HEAD (which has the PPT-3 implementation in place; PPT-4 depends on the executor, RoutesHandler at priority 30, ProtocolSession, etc. that PPT-3 introduced). The 3 PPT-4 spec/plan commits live on this branch only (PPT-3 branch was reset back to its last PPT-3 commit). All implementation commits in this plan land here.

**Test runner:** All commands run from the outer repo root `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py`. Use `pixi run pytest …` — `pixi run` activates the right Python environment.

---

## Task 1: `on_protocol_set_voltage_request` handler + topic constants

**Files:**
- Modify: `src/dropbot_controller/consts.py` (append constants)
- Modify: `src/dropbot_controller/services/dropbot_states_setting_mixin_service.py` (add handler + import)
- Create: `src/dropbot_controller/tests/test_protocol_set_handlers.py`

**Why these locations:** `dropbot_controller` owns all dropbot-namespaced topics and all RPC handlers. The new column handler in `dropbot_protocol_controls` will publish `PROTOCOL_SET_VOLTAGE`; the dropbot listener (subscribed to `dropbot/requests/#` wildcard at `consts.py:64-71`) routes it to `on_protocol_set_voltage_request` per the dispatch rule at `dropbot_controller_base.py:100-126` (extract rightmost segment, prefix `on_`, suffix `_request`).

- [ ] **Step 1: Write the failing test**

```python
# src/dropbot_controller/tests/test_protocol_set_handlers.py
"""Tests for the protocol-driven voltage/frequency setpoint handlers.

These handlers exist alongside the UI-driven on_set_voltage_request /
on_set_frequency_request but bypass the realtime-mode gate and skip
prefs persistence — protocol writes are unconditional and transient.
"""
from unittest.mock import MagicMock, patch

from dropbot_controller.consts import VOLTAGE_APPLIED
from dropbot_controller.services.dropbot_states_setting_mixin_service import (
    DropbotStatesSettingMixinService,
)


def _make_service():
    svc = DropbotStatesSettingMixinService()
    svc.proxy = MagicMock()  # MagicMock supports the transaction_lock context manager
    svc.preferences = MagicMock()
    return svc


def test_on_protocol_set_voltage_request_calls_proxy_and_publishes_ack():
    svc = _make_service()
    published = []
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        svc.on_protocol_set_voltage_request("100")

    svc.proxy.update_state.assert_called_once_with(voltage=100)
    assert published == [{"topic": VOLTAGE_APPLIED, "message": "100"}]


def test_on_protocol_set_voltage_request_bypasses_realtime_mode():
    """Unlike on_set_voltage_request, this handler runs even when realtime_mode is False."""
    svc = _make_service()
    svc.realtime_mode = False
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
    ):
        svc.on_protocol_set_voltage_request("75")

    svc.proxy.update_state.assert_called_once_with(voltage=75)


def test_on_protocol_set_voltage_request_does_not_persist_prefs():
    """Prefs are user-action-driven only; protocol writes don't churn them."""
    svc = _make_service()
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
    ):
        svc.on_protocol_set_voltage_request("90")

    # last_voltage should NOT have been assigned on preferences
    assert not any(
        call_name == "__setattr__" and call_args[0] == "last_voltage"
        for call_name, call_args, _ in svc.preferences.method_calls
    )
    # Stronger check: the setattr happens via attribute access on the mock,
    # so check no last_voltage write was recorded:
    setattr_calls = [
        c for c in svc.preferences.mock_calls
        if str(c).startswith("call.last_voltage") or "last_voltage" in str(c)
    ]
    assert setattr_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_controller/tests/test_protocol_set_handlers.py -v
```

Expected: FAIL with `ImportError: cannot import name 'VOLTAGE_APPLIED' from 'dropbot_controller.consts'`.

- [ ] **Step 3: Add the topic constants**

In `src/dropbot_controller/consts.py`, after the existing `SET_FREQUENCY = ...` line (around line 36), add:

```python
# Protocol-driven setpoint topics (separate from UI SET_VOLTAGE/SET_FREQUENCY
# so the realtime-mode gate and prefs-persistence side effects don't apply).
PROTOCOL_SET_VOLTAGE = "dropbot/requests/protocol_set_voltage"
PROTOCOL_SET_FREQUENCY = "dropbot/requests/protocol_set_frequency"
VOLTAGE_APPLIED = "dropbot/signals/voltage_applied"
FREQUENCY_APPLIED = "dropbot/signals/frequency_applied"
```

No `ACTOR_TOPIC_DICT` change — the existing `dropbot/requests/#` wildcard at `consts.py:64-71` already routes `protocol_set_voltage` to the listener.

- [ ] **Step 4: Implement the handler**

In `src/dropbot_controller/services/dropbot_states_setting_mixin_service.py`:

Add `VOLTAGE_APPLIED` to the existing import line:
```python
from ..consts import REALTIME_MODE_UPDATED, HARDWARE_MIN_VOLTAGE, HARDWARE_MIN_FREQUENCY, VOLTAGE_APPLIED
```

After the existing `on_set_voltage_request` method (around line 82), add:

```python
def on_protocol_set_voltage_request(self, message):
    """Set voltage on the dropbot for protocol-driven writes.

    Symmetric to on_set_voltage_request but bypasses the realtime-mode
    gate and does NOT persist to DropbotPreferences.last_voltage —
    protocol writes are unconditional and transient. Publishes
    VOLTAGE_APPLIED ack on RPC return so the protocol executor's
    wait_for unblocks.
    """
    v = int(message)
    with self.proxy.transaction_lock:
        self.proxy.update_state(voltage=v)
    publish_message(topic=VOLTAGE_APPLIED, message=str(v))
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pixi run pytest src/dropbot_controller/tests/test_protocol_set_handlers.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git -C src add dropbot_controller/consts.py dropbot_controller/services/dropbot_states_setting_mixin_service.py dropbot_controller/tests/test_protocol_set_handlers.py
git -C src commit -m "[PPT-4] Add on_protocol_set_voltage_request handler + topic constants"
```

---

## Task 2: `on_protocol_set_frequency_request` handler

**Files:**
- Modify: `src/dropbot_controller/services/dropbot_states_setting_mixin_service.py` (add handler + import)
- Modify: `src/dropbot_controller/tests/test_protocol_set_handlers.py` (add 3 tests)

**Why this is its own task:** symmetric implementation, but a separate test cycle keeps each commit small and isolates failures.

- [ ] **Step 1: Write the failing test**

Append to `src/dropbot_controller/tests/test_protocol_set_handlers.py`:

```python
from dropbot_controller.consts import FREQUENCY_APPLIED


def test_on_protocol_set_frequency_request_calls_proxy_and_publishes_ack():
    svc = _make_service()
    published = []
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        svc.on_protocol_set_frequency_request("10000")

    svc.proxy.update_state.assert_called_once_with(frequency=10000)
    assert published == [{"topic": FREQUENCY_APPLIED, "message": "10000"}]


def test_on_protocol_set_frequency_request_bypasses_realtime_mode():
    svc = _make_service()
    svc.realtime_mode = False
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
    ):
        svc.on_protocol_set_frequency_request("5000")

    svc.proxy.update_state.assert_called_once_with(frequency=5000)


def test_on_protocol_set_frequency_request_does_not_persist_prefs():
    """Sentinel pre-set on prefs.last_frequency must survive the call.
    Plain MagicMock doesn't track attribute writes via mock_calls, so a
    sentinel-comparison is the only reliable way to assert no-write."""
    svc = _make_service()
    svc.preferences.last_frequency = 99999  # sentinel
    with patch(
        "dropbot_controller.services.dropbot_states_setting_mixin_service.publish_message",
    ):
        svc.on_protocol_set_frequency_request("8000")

    assert svc.preferences.last_frequency == 99999, (
        "Handler must not write to preferences.last_frequency; "
        f"sentinel 99999 was overwritten with {svc.preferences.last_frequency}"
    )
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
pixi run pytest src/dropbot_controller/tests/test_protocol_set_handlers.py -v
```

Expected: 3 voltage tests pass, 3 frequency tests FAIL with ImportError or AttributeError.

- [ ] **Step 3: Implement the handler**

In `src/dropbot_controller/services/dropbot_states_setting_mixin_service.py`, add `FREQUENCY_APPLIED` to the import:

```python
from ..consts import (
    REALTIME_MODE_UPDATED, HARDWARE_MIN_VOLTAGE, HARDWARE_MIN_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
```

Add after `on_protocol_set_voltage_request`:

```python
def on_protocol_set_frequency_request(self, message):
    """Set frequency on the dropbot for protocol-driven writes.

    Symmetric to on_set_frequency_request but bypasses the realtime-mode
    gate and does NOT persist to DropbotPreferences.last_frequency.
    Publishes FREQUENCY_APPLIED ack on RPC return. On hardware error,
    the ack is NOT published — the executor's wait_for times out and
    the protocol step fails.
    """
    try:
        v = int(message)
        with self.proxy.transaction_lock:
            self.proxy.update_state(frequency=v)
        publish_message(topic=FREQUENCY_APPLIED, message=str(v))
    except (TimeoutError, RuntimeError) as e:
        logger.error(f"Proxy error setting protocol frequency: {e}")
    except Exception as e:
        logger.error(f"Error setting protocol frequency: {e}")
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_controller/tests/test_protocol_set_handlers.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_controller/services/dropbot_states_setting_mixin_service.py dropbot_controller/tests/test_protocol_set_handlers.py
git -C src commit -m "[PPT-4] Add on_protocol_set_frequency_request handler"
```

---

## Task 3: Scaffold `dropbot_protocol_controls/` package + plugin shell

**Files:**
- Create: `src/dropbot_protocol_controls/__init__.py` (empty)
- Create: `src/dropbot_protocol_controls/consts.py`
- Create: `src/dropbot_protocol_controls/plugin.py`
- Create: `src/dropbot_protocol_controls/tests/__init__.py` (empty)
- Create: `src/dropbot_protocol_controls/tests/test_plugin_shell.py`

**Why this is its own task:** brings the package into existence with a passing import test before any column code lands. Subsequent tasks have a stable home for their files.

- [ ] **Step 1: Write the failing test**

```python
# src/dropbot_protocol_controls/tests/test_plugin_shell.py
"""Smoke tests for the dropbot_protocol_controls package shell."""

def test_can_import_plugin():
    """Envisage Plugin.id is a Trait — accessible on an instance, not the
    class. (Class-level access raises AttributeError.)"""
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    p = DropbotProtocolControlsPlugin()
    assert p.id.endswith(".plugin")


def test_plugin_instantiates_with_no_columns_yet():
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
    p = DropbotProtocolControlsPlugin()
    # contributed_protocol_columns may be empty until task 11 wires it up.
    assert hasattr(p, "id")
    assert hasattr(p, "name")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dropbot_protocol_controls'`.

- [ ] **Step 3: Create the package files**

Create `src/dropbot_protocol_controls/__init__.py` — empty.

Create `src/dropbot_protocol_controls/consts.py`:
```python
"""Package-level constants for dropbot_protocol_controls.

Topic constants live in dropbot_controller/consts.py — this plugin
imports them. See PPT-4 spec section 3, "Topic ownership rationale"
for the layering reasoning.
"""

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
```

Create `src/dropbot_protocol_controls/plugin.py`:
```python
"""DropbotProtocolControlsPlugin — contributes voltage/frequency
columns to the pluggable protocol tree.

Sibling plugin to dropbot_controller; depends on dropbot_controller
for topic constants and request-handler dispatch. Loaded as part of
DROPBOT_BACKEND_PLUGINS in examples/plugin_consts.py.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from .consts import PKG, PKG_name


logger = get_logger(__name__)


class DropbotProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    # contributed_protocol_columns is added in task 11.
```

Create `src/dropbot_protocol_controls/tests/__init__.py` — empty.

- [ ] **Step 4: Run test to verify it passes**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/
git -C src commit -m "[PPT-4] Scaffold dropbot_protocol_controls plugin package"
```

---

## Task 4: `VoltageColumnModel` + `make_voltage_column` factory

**Files:**
- Create: `src/dropbot_protocol_controls/protocol_columns/__init__.py` (empty)
- Create: `src/dropbot_protocol_controls/protocol_columns/voltage_column.py`
- Create: `src/dropbot_protocol_controls/tests/test_voltage_column.py`

**Why this is its own task:** stands up the column without any runtime behaviour. Handler in this task is a placeholder `BaseColumnHandler()` so the factory works end-to-end; tasks 5+6 add the actual handler logic.

- [ ] **Step 1: Write the failing test**

```python
# src/dropbot_protocol_controls/tests/test_voltage_column.py
"""Tests for the voltage column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

import pytest
from traits.api import HasTraits

from dropbot_protocol_controls.protocol_columns.voltage_column import (
    VoltageColumnModel, make_voltage_column,
)


def test_voltage_column_model_id_and_name():
    m = VoltageColumnModel(col_id="voltage", col_name="Voltage (V)",
                           default_value=100)
    assert m.col_id == "voltage"
    assert m.col_name == "Voltage (V)"
    assert m.default_value == 100


def test_voltage_column_trait_for_row_is_int():
    """Row trait stores Int — never Float."""
    m = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    trait = m.trait_for_row()
    class Row(HasTraits):
        voltage = trait
    r = Row()
    assert r.voltage == 100
    r.voltage = 75
    assert r.voltage == 75
    assert isinstance(r.voltage, int)


def test_voltage_column_serialize_identity():
    m = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    assert m.serialize(100) == 100
    assert m.deserialize(100) == 100


def test_make_voltage_column_returns_column_with_voltage_id():
    """Factory yields a Column whose model.col_id is 'voltage'."""
    # Patch DropbotPreferences so test doesn't need a real envisage app.
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_voltage = 100
        col = make_voltage_column()
    assert col.model.col_id == "voltage"
    assert col.view is not None
    assert col.handler is not None


def test_make_voltage_column_default_reads_from_prefs():
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_voltage = 75
        col = make_voltage_column()
    assert col.model.default_value == 75
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_voltage_column.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dropbot_protocol_controls.protocol_columns'`.

- [ ] **Step 3: Implement the model + factory**

Create `src/dropbot_protocol_controls/protocol_columns/__init__.py` — empty.

Create `src/dropbot_protocol_controls/protocol_columns/voltage_column.py`:

```python
"""Voltage column — per-step voltage setpoint in volts (Int).

Edit via Int spinbox in the protocol tree; runtime behaviour publishes
PROTOCOL_SET_VOLTAGE and waits for VOLTAGE_APPLIED ack from
dropbot_controller. Priority 20 — runs before RoutesHandler at
priority 30 so the voltage is applied before any electrode actuation.
"""
from traits.api import Int

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView

from dropbot_controller.consts import HARDWARE_MIN_VOLTAGE
from dropbot_controller.preferences import DropbotPreferences

# Static spinbox upper. Hardware-reported max isn't known at column
# construction time (DropBot reports via app_globals only after connect),
# and the trait can't be re-bounded after instantiation. The backend
# validates the actual write against proxy.config.max_voltage anyway.
_DEFAULT_HARDWARE_MAX_V = 140  # DropBot DB3-120 nominal max


class VoltageColumnModel(BaseColumnModel):
    """Per-step voltage setpoint stored as an Int on each row."""

    def trait_for_row(self):
        return Int(int(self.default_value), desc="Step voltage in V")


def make_voltage_column():
    prefs = DropbotPreferences()
    return Column(
        model=VoltageColumnModel(
            col_id="voltage",
            col_name="Voltage (V)",
            default_value=int(prefs.last_voltage),
        ),
        view=IntSpinBoxColumnView(
            low=HARDWARE_MIN_VOLTAGE, high=_DEFAULT_HARDWARE_MAX_V,
        ),
        handler=BaseColumnHandler(),  # replaced in tasks 5 + 6
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_voltage_column.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/protocol_columns/ dropbot_protocol_controls/tests/test_voltage_column.py
git -C src commit -m "[PPT-4] Add VoltageColumnModel + make_voltage_column factory"
```

---

## Task 5: `VoltageHandler.on_step` (publish + wait_for ack)

**Files:**
- Modify: `src/dropbot_protocol_controls/protocol_columns/voltage_column.py` (add handler class + use it in factory)
- Modify: `src/dropbot_protocol_controls/tests/test_voltage_column.py` (add handler tests)

**Why this is its own task:** the runtime publish/wait behaviour has its own failure modes (mocked broker, mocked ctx) — separate from the model/factory tests.

- [ ] **Step 1: Write the failing test**

Append to `src/dropbot_protocol_controls/tests/test_voltage_column.py`:

```python
from unittest.mock import MagicMock, patch

from dropbot_controller.consts import PROTOCOL_SET_VOLTAGE, VOLTAGE_APPLIED


def test_voltage_handler_priority_20():
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    assert handler.priority == 20


def test_voltage_handler_wait_for_topics_includes_voltage_applied():
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    assert VOLTAGE_APPLIED in handler.wait_for_topics


def test_voltage_handler_on_step_publishes_and_waits():
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    row = MagicMock()
    row.voltage = 120
    ctx = MagicMock()
    ctx.protocol.stop_event.is_set.return_value = False

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published == [{"topic": PROTOCOL_SET_VOLTAGE, "message": "120"}]
    ctx.wait_for.assert_called_once_with(VOLTAGE_APPLIED, timeout=5.0)


def test_voltage_handler_on_step_publishes_int_payload():
    """Even if row.voltage is somehow a float, payload is a stringified int."""
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler,
    )
    handler = VoltageHandler()
    row = MagicMock()
    row.voltage = 99.7  # float — should be coerced to int
    ctx = MagicMock()

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published[0]["message"] == "99"  # int(99.7) = 99
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_voltage_column.py -v
```

Expected: 5 prior tests pass; 4 new tests FAIL with ImportError on `VoltageHandler`.

- [ ] **Step 3: Implement `VoltageHandler` and use it in the factory**

Edit `src/dropbot_protocol_controls/protocol_columns/voltage_column.py`. Add imports near the top:

```python
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import (
    HARDWARE_MIN_VOLTAGE, PROTOCOL_SET_VOLTAGE, VOLTAGE_APPLIED,
)
```

(merge with existing dropbot_controller import.)

After `VoltageColumnModel` class, add:

```python
class VoltageHandler(BaseColumnHandler):
    """Publishes the row's voltage setpoint and waits for the dropbot ack.

    Priority 20 — runs in parallel with FrequencyHandler in the same
    bucket, and strictly before RoutesHandler at priority 30. The
    timeout matches RoutesHandler's: 5.0s of headroom for cold-broker
    first-publish (~1-2s) and worker-queue contention.
    """
    priority = 20
    wait_for_topics = [VOLTAGE_APPLIED]

    def on_step(self, row, ctx):
        v = int(row.voltage)
        publish_message(topic=PROTOCOL_SET_VOLTAGE, message=str(v))
        ctx.wait_for(VOLTAGE_APPLIED, timeout=5.0)
```

Update `make_voltage_column` to use `VoltageHandler()`:

```python
def make_voltage_column():
    prefs = DropbotPreferences()
    return Column(
        model=VoltageColumnModel(
            col_id="voltage",
            col_name="Voltage (V)",
            default_value=int(prefs.last_voltage),
        ),
        view=IntSpinBoxColumnView(
            low=HARDWARE_MIN_VOLTAGE, high=_DEFAULT_HARDWARE_MAX_V,
        ),
        handler=VoltageHandler(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_voltage_column.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/protocol_columns/voltage_column.py dropbot_protocol_controls/tests/test_voltage_column.py
git -C src commit -m "[PPT-4] Add VoltageHandler.on_step (publish + wait for ack)"
```

---

## Task 6: `VoltageHandler.on_interact` (persist user edits to prefs)

**Files:**
- Modify: `src/dropbot_protocol_controls/protocol_columns/voltage_column.py` (add `on_interact` to handler)
- Modify: `src/dropbot_protocol_controls/tests/test_voltage_column.py` (add 2 tests)

- [ ] **Step 1: Write the failing test**

Append to `src/dropbot_protocol_controls/tests/test_voltage_column.py`:

```python
def test_voltage_handler_on_interact_writes_through_to_row():
    """super().on_interact behavior: model.set_value writes to row."""
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler, VoltageColumnModel,
    )
    handler = VoltageHandler()
    model = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    handler.model = model

    class FakeRow:
        voltage = 100
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ):
        handler.on_interact(row, model, 120)

    assert row.voltage == 120


def test_voltage_handler_on_interact_persists_to_prefs():
    """User cell-edit becomes the new default for next session."""
    from dropbot_protocol_controls.protocol_columns.voltage_column import (
        VoltageHandler, VoltageColumnModel,
    )
    handler = VoltageHandler()
    model = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    handler.model = model

    class FakeRow:
        voltage = 100
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        prefs_instance = MockPrefs.return_value
        handler.on_interact(row, model, 120)

    MockPrefs.assert_called_once_with()  # no-arg construct hits global prefs
    assert prefs_instance.last_voltage == 120
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_voltage_column.py -v
```

Expected: 9 prior tests pass; 2 new tests FAIL — `on_interact` falls through to `BaseColumnHandler.on_interact` which doesn't touch prefs.

- [ ] **Step 3: Implement `on_interact`**

Add to `VoltageHandler` in `src/dropbot_protocol_controls/protocol_columns/voltage_column.py`:

```python
    def on_interact(self, row, model, value):
        """User edited a voltage cell — write through AND persist to prefs.

        DropbotPreferences() with no args attaches to the global preferences
        object set during envisage startup (PreferencesHelper convention,
        see dropbot_controller/preferences.py:22-25). Storing here means
        the next session's status-panel boot value matches the last
        cell-edit, just like editing the spinner in the dropbot status panel.
        """
        super().on_interact(row, model, value)
        DropbotPreferences().last_voltage = int(value)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_voltage_column.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/protocol_columns/voltage_column.py dropbot_protocol_controls/tests/test_voltage_column.py
git -C src commit -m "[PPT-4] VoltageHandler.on_interact persists edits to DropbotPreferences"
```

---

## Task 7: `FrequencyColumnModel` + `make_frequency_column` factory

**Files:**
- Create: `src/dropbot_protocol_controls/protocol_columns/frequency_column.py`
- Create: `src/dropbot_protocol_controls/tests/test_frequency_column.py`

**Why this is its own task:** mirror of task 4 with `frequency` instead of `voltage`. Symmetric implementation, isolated commit.

- [ ] **Step 1: Write the failing test**

```python
# src/dropbot_protocol_controls/tests/test_frequency_column.py
"""Tests for the frequency column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

import pytest
from traits.api import HasTraits

from dropbot_protocol_controls.protocol_columns.frequency_column import (
    FrequencyColumnModel, make_frequency_column,
)


def test_frequency_column_model_id_and_name():
    m = FrequencyColumnModel(col_id="frequency", col_name="Frequency (Hz)",
                             default_value=10000)
    assert m.col_id == "frequency"
    assert m.col_name == "Frequency (Hz)"
    assert m.default_value == 10000


def test_frequency_column_trait_for_row_is_int():
    m = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                             default_value=10000)
    trait = m.trait_for_row()
    class Row(HasTraits):
        frequency = trait
    r = Row()
    assert r.frequency == 10000
    r.frequency = 5000
    assert r.frequency == 5000
    assert isinstance(r.frequency, int)


def test_frequency_column_serialize_identity():
    m = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                             default_value=10000)
    assert m.serialize(10000) == 10000
    assert m.deserialize(10000) == 10000


def test_make_frequency_column_returns_column_with_frequency_id():
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_frequency = 10000
        col = make_frequency_column()
    assert col.model.col_id == "frequency"


def test_make_frequency_column_default_reads_from_prefs():
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_frequency = 5000
        col = make_frequency_column()
    assert col.model.default_value == 5000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_frequency_column.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the model + factory**

Create `src/dropbot_protocol_controls/protocol_columns/frequency_column.py`:

```python
"""Frequency column — per-step frequency setpoint in Hertz (Int).

Mirrors voltage_column.py. Edit via Int spinbox in the protocol tree;
runtime behaviour publishes PROTOCOL_SET_FREQUENCY and waits for
FREQUENCY_APPLIED ack from dropbot_controller. Priority 20 — runs in
parallel with VoltageHandler in the same bucket.
"""
from traits.api import Int

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView

from dropbot_controller.consts import HARDWARE_MIN_FREQUENCY
from dropbot_controller.preferences import DropbotPreferences

# Static spinbox upper. Hardware-reported max isn't known at column
# construction time. Backend validates against proxy.config.max_frequency.
_DEFAULT_HARDWARE_MAX_HZ = 10_000  # DropBot DB3-120 nominal max


class FrequencyColumnModel(BaseColumnModel):
    """Per-step frequency setpoint stored as an Int on each row."""

    def trait_for_row(self):
        return Int(int(self.default_value), desc="Step frequency in Hz")


def make_frequency_column():
    prefs = DropbotPreferences()
    return Column(
        model=FrequencyColumnModel(
            col_id="frequency",
            col_name="Frequency (Hz)",
            default_value=int(prefs.last_frequency),
        ),
        view=IntSpinBoxColumnView(
            low=HARDWARE_MIN_FREQUENCY, high=_DEFAULT_HARDWARE_MAX_HZ,
        ),
        handler=BaseColumnHandler(),  # replaced in tasks 8 + 9
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_frequency_column.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/protocol_columns/frequency_column.py dropbot_protocol_controls/tests/test_frequency_column.py
git -C src commit -m "[PPT-4] Add FrequencyColumnModel + make_frequency_column factory"
```

---

## Task 8: `FrequencyHandler.on_step` (publish + wait_for ack)

**Files:**
- Modify: `src/dropbot_protocol_controls/protocol_columns/frequency_column.py` (add handler + use it in factory)
- Modify: `src/dropbot_protocol_controls/tests/test_frequency_column.py` (add 4 tests)

- [ ] **Step 1: Write the failing test**

Append to `src/dropbot_protocol_controls/tests/test_frequency_column.py`:

```python
from dropbot_controller.consts import PROTOCOL_SET_FREQUENCY, FREQUENCY_APPLIED


def test_frequency_handler_priority_20():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    assert handler.priority == 20


def test_frequency_handler_wait_for_topics_includes_frequency_applied():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    assert FREQUENCY_APPLIED in handler.wait_for_topics


def test_frequency_handler_on_step_publishes_and_waits():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    row = MagicMock()
    row.frequency = 8000
    ctx = MagicMock()

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published == [{"topic": PROTOCOL_SET_FREQUENCY, "message": "8000"}]
    ctx.wait_for.assert_called_once_with(FREQUENCY_APPLIED, timeout=5.0)


def test_frequency_handler_on_step_publishes_int_payload():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler,
    )
    handler = FrequencyHandler()
    row = MagicMock()
    row.frequency = 5000.9  # float — should be coerced
    ctx = MagicMock()

    published = []
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        handler.on_step(row, ctx)

    assert published[0]["message"] == "5000"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_frequency_column.py -v
```

Expected: 5 prior tests pass; 4 new tests FAIL.

- [ ] **Step 3: Implement `FrequencyHandler` + use it in factory**

Edit `src/dropbot_protocol_controls/protocol_columns/frequency_column.py`. Update imports:

```python
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import (
    HARDWARE_MIN_FREQUENCY, PROTOCOL_SET_FREQUENCY, FREQUENCY_APPLIED,
)
```

After `FrequencyColumnModel`, add:

```python
class FrequencyHandler(BaseColumnHandler):
    """Publishes the row's frequency setpoint and waits for the dropbot ack.

    Priority 20 — runs in parallel with VoltageHandler in the same bucket,
    and strictly before RoutesHandler at priority 30.
    """
    priority = 20
    wait_for_topics = [FREQUENCY_APPLIED]

    def on_step(self, row, ctx):
        v = int(row.frequency)
        publish_message(topic=PROTOCOL_SET_FREQUENCY, message=str(v))
        ctx.wait_for(FREQUENCY_APPLIED, timeout=5.0)
```

Update `make_frequency_column` to use `FrequencyHandler()`:

```python
def make_frequency_column():
    prefs = DropbotPreferences()
    return Column(
        model=FrequencyColumnModel(
            col_id="frequency",
            col_name="Frequency (Hz)",
            default_value=int(prefs.last_frequency),
        ),
        view=IntSpinBoxColumnView(
            low=HARDWARE_MIN_FREQUENCY, high=_DEFAULT_HARDWARE_MAX_HZ,
        ),
        handler=FrequencyHandler(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_frequency_column.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/protocol_columns/frequency_column.py dropbot_protocol_controls/tests/test_frequency_column.py
git -C src commit -m "[PPT-4] Add FrequencyHandler.on_step (publish + wait for ack)"
```

---

## Task 9: `FrequencyHandler.on_interact` (persist user edits to prefs)

**Files:**
- Modify: `src/dropbot_protocol_controls/protocol_columns/frequency_column.py` (add `on_interact`)
- Modify: `src/dropbot_protocol_controls/tests/test_frequency_column.py` (add 2 tests)

- [ ] **Step 1: Write the failing test**

Append to `src/dropbot_protocol_controls/tests/test_frequency_column.py`:

```python
def test_frequency_handler_on_interact_writes_through_to_row():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler, FrequencyColumnModel,
    )
    handler = FrequencyHandler()
    model = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                                  default_value=10000)
    handler.model = model

    class FakeRow:
        frequency = 10000
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ):
        handler.on_interact(row, model, 5000)

    assert row.frequency == 5000


def test_frequency_handler_on_interact_persists_to_prefs():
    from dropbot_protocol_controls.protocol_columns.frequency_column import (
        FrequencyHandler, FrequencyColumnModel,
    )
    handler = FrequencyHandler()
    model = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                                  default_value=10000)
    handler.model = model

    class FakeRow:
        frequency = 10000
    row = FakeRow()

    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        prefs_instance = MockPrefs.return_value
        handler.on_interact(row, model, 5000)

    MockPrefs.assert_called_once_with()
    assert prefs_instance.last_frequency == 5000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_frequency_column.py -v
```

Expected: 9 prior tests pass; 2 new FAIL.

- [ ] **Step 3: Implement `on_interact`**

Add to `FrequencyHandler` in `src/dropbot_protocol_controls/protocol_columns/frequency_column.py`:

```python
    def on_interact(self, row, model, value):
        """User edited a frequency cell — write through AND persist to prefs."""
        super().on_interact(row, model, value)
        DropbotPreferences().last_frequency = int(value)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_frequency_column.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/protocol_columns/frequency_column.py dropbot_protocol_controls/tests/test_frequency_column.py
git -C src commit -m "[PPT-4] FrequencyHandler.on_interact persists edits to DropbotPreferences"
```

---

## Task 10: Persistence — Int trait JSON round-trip test

**Files:**
- Create: `src/dropbot_protocol_controls/tests/test_persistence.py`

**Why this is its own task:** spec calls out persistence as its own concern. Confirms that `Int` traits round-trip through `RowManager.to_json` / `from_json` with no custom serialize/deserialize needed.

- [ ] **Step 1: Write the failing test**

```python
# src/dropbot_protocol_controls/tests/test_persistence.py
"""JSON persistence round-trip for Int voltage/frequency columns."""

import json
from unittest.mock import patch

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column

from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)


def _build_columns():
    """Patch DropbotPreferences so column factories don't need an envisage app."""
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_voltage_column(), make_frequency_column(),
        ]


def test_voltage_frequency_int_round_trip_through_json():
    cols = _build_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "voltage": 120, "frequency": 5000})

    payload = rm.to_json()
    json_str = json.dumps(payload)  # Confirms it's JSON-serializable
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=_build_columns())
    step = rm2.root.children[0]
    assert step.voltage == 120
    assert step.frequency == 5000
    assert isinstance(step.voltage, int)
    assert isinstance(step.frequency, int)
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_persistence.py -v
```

Expected: 1 passed (no implementation work needed — `BaseColumnModel.serialize`/`deserialize` defaults are identity for JSON-native types per `column.py:42-46`).

If this fails, investigate whether `RowManager.from_json` correctly resolves the columns and applies their values. Likely indicates a real bug in row reconstruction worth fixing before moving on.

- [ ] **Step 3: Commit**

```bash
git -C src add dropbot_protocol_controls/tests/test_persistence.py
git -C src commit -m "[PPT-4] Add Int trait JSON round-trip persistence test"
```

---

## Task 11: Wire plugin to contribute columns via `PROTOCOL_COLUMNS`

**Files:**
- Modify: `src/dropbot_protocol_controls/plugin.py` (add `contributed_protocol_columns`)
- Modify: `src/dropbot_protocol_controls/tests/test_plugin_shell.py` (add contribution test)

**Why this is its own task:** scaffolds the Envisage extension wiring. Up to now the columns existed as Python objects but weren't part of the application's column set. After this, `PluggableProtocolTreePlugin._assemble_columns()` includes voltage + frequency when this plugin is loaded.

- [ ] **Step 1: Write the failing test**

Append to `src/dropbot_protocol_controls/tests/test_plugin_shell.py`:

```python
from unittest.mock import patch


def test_plugin_contributes_voltage_and_frequency_columns():
    """The plugin's contributed_protocol_columns default factory yields
    a list containing both voltage and frequency Column instances."""
    from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin

    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000

        p = DropbotProtocolControlsPlugin()
        col_ids = [c.model.col_id for c in p.contributed_protocol_columns]

    assert "voltage" in col_ids
    assert "frequency" in col_ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: 2 prior tests pass; 1 new test FAILs — `contributed_protocol_columns` doesn't exist yet.

- [ ] **Step 3: Add the contribution to the plugin**

Edit `src/dropbot_protocol_controls/plugin.py`. Update imports + add the trait + default:

```python
"""DropbotProtocolControlsPlugin — contributes voltage/frequency
columns to the pluggable protocol tree.
"""

from envisage.plugin import Plugin
from traits.api import List, Instance

from logger.logger_service import get_logger

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn

from .consts import PKG, PKG_name
from .protocol_columns.voltage_column import make_voltage_column
from .protocol_columns.frequency_column import make_frequency_column


logger = get_logger(__name__)


class DropbotProtocolControlsPlugin(Plugin):
    id = PKG + '.plugin'
    name = f'{PKG_name} Plugin'

    contributed_protocol_columns = List(
        Instance(IColumn), contributes_to=PROTOCOL_COLUMNS,
    )

    def _contributed_protocol_columns_default(self):
        return [make_voltage_column(), make_frequency_column()]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_plugin_shell.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/plugin.py dropbot_protocol_controls/tests/test_plugin_shell.py
git -C src commit -m "[PPT-4] Wire DropbotProtocolControlsPlugin to contribute columns via PROTOCOL_COLUMNS"
```

---

## Task 12: Demo responder actor + `subscribe_demo_responder` helper

**Files:**
- Create: `src/dropbot_protocol_controls/demos/__init__.py` (empty)
- Create: `src/dropbot_protocol_controls/demos/voltage_frequency_responder.py`
- Create: `src/dropbot_protocol_controls/tests/test_demo_responder.py`

**Why this is its own task:** the demo responder is the in-process stand-in for a connected DropBot. Mirrors `pluggable_protocol_tree/demos/electrode_responder.py` exactly. Decoupled from the column tests since it depends on dramatiq actor registration.

- [ ] **Step 1: Write the failing test**

```python
# src/dropbot_protocol_controls/tests/test_demo_responder.py
"""Tests for the in-process voltage/frequency demo responder.

Doesn't require Redis — exercises the actor function directly.
"""
from unittest.mock import patch

from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    DEMO_VF_RESPONDER_ACTOR_NAME, _demo_voltage_frequency_responder,
)


def test_voltage_request_publishes_voltage_applied_ack():
    published = []
    with patch(
        "dropbot_protocol_controls.demos.voltage_frequency_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_voltage_frequency_responder("100", PROTOCOL_SET_VOLTAGE)

    assert published == [{"topic": VOLTAGE_APPLIED, "message": "100"}]


def test_frequency_request_publishes_frequency_applied_ack():
    published = []
    with patch(
        "dropbot_protocol_controls.demos.voltage_frequency_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_voltage_frequency_responder("10000", PROTOCOL_SET_FREQUENCY)

    assert published == [{"topic": FREQUENCY_APPLIED, "message": "10000"}]


def test_unknown_topic_does_not_publish():
    """Defensive: receiving an unrecognized topic should not ack anything."""
    published = []
    with patch(
        "dropbot_protocol_controls.demos.voltage_frequency_responder.publish_message",
        side_effect=lambda **kw: published.append(kw),
    ):
        _demo_voltage_frequency_responder("xyz", "dropbot/requests/some_other")

    assert published == []


def test_actor_name_constant_is_stable():
    """ProtocolSession demos rely on this name being stable for subscription."""
    assert DEMO_VF_RESPONDER_ACTOR_NAME == "ppt_demo_voltage_frequency_responder"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_demo_responder.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the responder + helper**

Create `src/dropbot_protocol_controls/demos/__init__.py` — empty.

Create `src/dropbot_protocol_controls/demos/voltage_frequency_responder.py`:

```python
"""In-process Dramatiq actor that stands in for a hardware DropBot
for protocol-driven voltage/frequency setpoint writes. Subscribes to
PROTOCOL_SET_VOLTAGE and PROTOCOL_SET_FREQUENCY, sleeps a small
'apply' delay, then publishes the matching _APPLIED ack.

Mirrors pluggable_protocol_tree/demos/electrode_responder.py.
"""

import logging
import time

import dramatiq

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)


logger = logging.getLogger(__name__)

DEMO_VF_RESPONDER_ACTOR_NAME = "ppt_demo_voltage_frequency_responder"
DEMO_APPLY_DELAY_S = 0.01  # Smaller than electrode responder; just enough to be observable.


@dramatiq.actor(actor_name=DEMO_VF_RESPONDER_ACTOR_NAME, queue_name="default")
def _demo_voltage_frequency_responder(message: str, topic: str,
                                       timestamp: float = None):
    """DropBot stand-in. Acks based on which topic the message arrived on."""
    logger.info("[demo vf responder] received %r on %s", message, topic)
    time.sleep(DEMO_APPLY_DELAY_S)

    if topic == PROTOCOL_SET_VOLTAGE:
        publish_message(message=message, topic=VOLTAGE_APPLIED)
    elif topic == PROTOCOL_SET_FREQUENCY:
        publish_message(message=message, topic=FREQUENCY_APPLIED)
    else:
        logger.warning("[demo vf responder] unknown topic %s, ignoring", topic)


def subscribe_demo_responder(router) -> None:
    """Subscribe the in-process voltage/frequency responder to its
    request topics on the given MessageRouterActor.

    Use after a ProtocolSession has been built with with_demo_hardware=True
    if your protocol uses voltage/frequency columns and you want the
    setpoint roundtrip to complete in-process. Importing this module
    already registers the dramatiq actor; this helper just wires the
    topic→actor subscriptions.
    """
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_VOLTAGE,
        subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
    )
    router.message_router_data.add_subscriber_to_topic(
        topic=PROTOCOL_SET_FREQUENCY,
        subscribing_actor_name=DEMO_VF_RESPONDER_ACTOR_NAME,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/test_demo_responder.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git -C src add dropbot_protocol_controls/demos/ dropbot_protocol_controls/tests/test_demo_responder.py
git -C src commit -m "[PPT-4] Add demo voltage/frequency responder actor + subscribe helper"
```

---

## Task 13: `run_voltage_frequency_demo.py` runnable script

**Files:**
- Create: `src/dropbot_protocol_controls/demos/run_voltage_frequency_demo.py`

**Why this is its own task:** standalone smoke runner so a developer can verify the new plugin works end-to-end without Redis-via-pytest. Mirrors `pluggable_protocol_tree/demos/run_session_demo.py`.

No automated test for the script itself (it's a `__main__` runnable). Verification is the manual run in step 3.

- [ ] **Step 1: Write the demo script**

Create `src/dropbot_protocol_controls/demos/run_voltage_frequency_demo.py`:

```python
"""Runnable demo for the dropbot_protocol_controls voltage/frequency columns.

Builds a protocol with voltage + frequency columns alongside the
PPT-3 builtins, opens a ProtocolSession with demo hardware, subscribes
the voltage/frequency demo responder, and runs end-to-end.

This is the script a developer runs to manually verify the new plugin
without the full GUI app and without real hardware.

Run: pixi run python -m dropbot_protocol_controls.demos.run_voltage_frequency_demo
"""

import json
import logging
import sys
import tempfile
import time
from pathlib import Path

import dramatiq

# Strip Prometheus middleware (matches the other demos); without this,
# every actor publish raises inside its after_process_message hook.
for _m in list(dramatiq.get_broker().middleware):
    if _m.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(_m)

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import ProtocolSession

from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.demos.voltage_frequency_responder import (
    subscribe_demo_responder,
)


logger = logging.getLogger(__name__)

# Spy that prints every voltage/frequency publish + ack so the demo
# output is interpretable.
SPY_ACTOR_NAME = "ppt_vf_demo_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _vf_spy(message: str, topic: str, timestamp: float = None):
    print(f"  vf-spy: {topic} = {message}", flush=True)


def _build_sample_protocol_file(path: Path) -> None:
    """3-step protocol exercising voltage + frequency + electrodes."""
    cols = [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_voltage_column(), make_frequency_column(),
    ]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(10)
    }
    rm.add_step(values={
        "name": "Hold pad with 100V/10kHz",
        "duration_s": 0.2,
        "electrodes": ["e00", "e01"],
        "voltage": 100,
        "frequency": 10000,
    })
    rm.add_step(values={
        "name": "Switch to 120V/5kHz",
        "duration_s": 0.2,
        "electrodes": ["e02", "e03"],
        "voltage": 120,
        "frequency": 5000,
    })
    rm.add_step(values={
        "name": "Cooldown 75V/1kHz",
        "duration_s": 0.2,
        "voltage": 75,
        "frequency": 1000,
    })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rm.to_json(), f, indent=2)


def _subscribe_spy(session: ProtocolSession) -> None:
    """Watch all voltage/frequency request + ack topics."""
    if session._router is None:
        return
    for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
                  VOLTAGE_APPLIED, FREQUENCY_APPLIED):
        try:
            session._router.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
            )
        except Exception:
            pass
        session._router.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    path = Path(tempfile.gettempdir()) / "ppt4_vf_demo_protocol.json"
    _build_sample_protocol_file(path)
    print(f"\nWrote sample protocol to: {path}\n")

    with ProtocolSession.from_file(str(path),
                                   with_demo_hardware=True) as session:
        n_steps = len(session.manager.root.children)
        print(f"Loaded {n_steps} top-level steps "
              f"({len(session.manager.columns)} columns resolved).")

        subscribe_demo_responder(session._router)
        _subscribe_spy(session)

        print("\nStarting protocol...\n")
        session.start()

        if not session.wait(timeout=30.0):
            print("Protocol still running after 30s, stopping...")
            session.stop()
            session.wait(timeout=5.0)

    print("\nDone -- ProtocolSession context exited cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the demo manually to smoke-test**

Make sure Redis is running first.

```bash
pixi run python -m dropbot_protocol_controls.demos.run_voltage_frequency_demo
```

Expected output (abbreviated):
```
Wrote sample protocol to: <tmp>/ppt4_vf_demo_protocol.json

Loaded 3 top-level steps (9 columns resolved).

Starting protocol...

  vf-spy: dropbot/requests/protocol_set_voltage = 100
  vf-spy: dropbot/requests/protocol_set_frequency = 10000
  vf-spy: dropbot/signals/voltage_applied = 100
  vf-spy: dropbot/signals/frequency_applied = 10000
  ... (repeated for steps 2 and 3) ...

Done -- ProtocolSession context exited cleanly.
```

If the protocol stalls, the most likely cause is a stale subscriber from a prior demo run — see `ProtocolSession._setup_demo_hardware` which already purges those.

- [ ] **Step 3: Commit**

```bash
git -C src add dropbot_protocol_controls/demos/run_voltage_frequency_demo.py
git -C src commit -m "[PPT-4] Add run_voltage_frequency_demo runnable smoke script"
```

---

## Task 14: Redis-backed integration test (round-trip with ack ordering)

**Files:**
- Create: `src/dropbot_protocol_controls/tests/tests_with_redis_server_need/__init__.py` (empty)
- Create: `src/dropbot_protocol_controls/tests/tests_with_redis_server_need/test_voltage_frequency_protocol_round_trip.py`

**Why this is its own task:** matches the project's test-partitioning convention (Redis-required tests live in `tests_with_redis_server_need/`). Asserts the priority-20-then-30 ordering — voltage/frequency acks land before any electrode publish.

- [ ] **Step 1: Write the integration test**

Create `src/dropbot_protocol_controls/tests/tests_with_redis_server_need/__init__.py` — empty.

Create `src/dropbot_protocol_controls/tests/tests_with_redis_server_need/test_voltage_frequency_protocol_round_trip.py`:

```python
"""End-to-end test: a protocol with voltage/frequency + electrodes
runs against an in-process responder, and the priority-20 acks land
strictly before any priority-30 electrode publish.

Requires a running Redis server on localhost:6379.
"""
import time
from threading import Lock

import dramatiq
import pytest

# Strip Prometheus middleware before importing anything that uses the broker.
for _m in list(dramatiq.get_broker().middleware):
    if _m.__module__ == "dramatiq.middleware.prometheus":
        dramatiq.get_broker().middleware.remove(_m)

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import ELECTRODES_STATE_CHANGE
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager

from dropbot_controller.consts import (
    PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
    VOLTAGE_APPLIED, FREQUENCY_APPLIED,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)


# Recording spy actor — captures every relevant topic with timestamps
# so we can assert on ordering.
EVENT_LOG = []
EVENT_LOG_LOCK = Lock()
SPY_ACTOR_NAME = "test_ppt4_round_trip_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _record_event(message: str, topic: str, timestamp: float = None):
    with EVENT_LOG_LOCK:
        EVENT_LOG.append((time.monotonic(), topic, message))


@pytest.fixture
def setup_responder_and_spy():
    """Subscribe the demo responder + spy; clean up after."""
    from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterActor
    from dramatiq import Worker

    EVENT_LOG.clear()

    # Importing this module registers the responder actor.
    from dropbot_protocol_controls.demos.voltage_frequency_responder import (
        subscribe_demo_responder, DEMO_VF_RESPONDER_ACTOR_NAME,
    )
    # Importing the listener registers it.
    from pluggable_protocol_tree.execution import listener as _listener  # noqa: F401
    from pluggable_protocol_tree.demos.electrode_responder import (
        DEMO_RESPONDER_ACTOR_NAME,
    )

    broker = dramatiq.get_broker()
    broker.flush_all()

    router = MessageRouterActor()

    # Voltage/frequency responder
    subscribe_demo_responder(router)

    # Electrode responder so RoutesHandler unblocks
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_CHANGE,
        subscribing_actor_name=DEMO_RESPONDER_ACTOR_NAME,
    )

    # Listener so executor wait_for unblocks
    from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
    router.message_router_data.add_subscriber_to_topic(
        topic=ELECTRODES_STATE_APPLIED,
        subscribing_actor_name="pluggable_protocol_tree_executor_listener",
    )

    # Spy on the topics we want to assert ordering on
    for topic in (PROTOCOL_SET_VOLTAGE, PROTOCOL_SET_FREQUENCY,
                  VOLTAGE_APPLIED, FREQUENCY_APPLIED,
                  ELECTRODES_STATE_CHANGE):
        router.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=SPY_ACTOR_NAME,
        )

    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        yield router
    finally:
        worker.stop()


def test_voltage_frequency_acks_before_electrode_change(setup_responder_and_spy):
    """Both _APPLIED acks must land before any ELECTRODES_STATE_CHANGE
    publish — proves priority 20 < priority 30 in practice."""
    cols = [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_voltage_column(), make_frequency_column(),
    ]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {f"e{i:02d}": i for i in range(5)}
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "electrodes": ["e00", "e01"],
        "voltage": 120,
        "frequency": 5000,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished, "Executor did not finish within 15s"

    # Find the timestamps of voltage/frequency acks and the first electrode change.
    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    def first_t(topic):
        for t, top, _ in events:
            if top == topic:
                return t
        return None

    t_v_ack = first_t(VOLTAGE_APPLIED)
    t_f_ack = first_t(FREQUENCY_APPLIED)
    t_e_change = first_t(ELECTRODES_STATE_CHANGE)

    assert t_v_ack is not None, f"No VOLTAGE_APPLIED ack received. Events: {events}"
    assert t_f_ack is not None, f"No FREQUENCY_APPLIED ack received. Events: {events}"
    assert t_e_change is not None, f"No ELECTRODES_STATE_CHANGE seen. Events: {events}"

    assert t_v_ack < t_e_change, (
        f"Voltage ack ({t_v_ack}) should land before electrode change ({t_e_change})"
    )
    assert t_f_ack < t_e_change, (
        f"Frequency ack ({t_f_ack}) should land before electrode change ({t_e_change})"
    )


def test_responder_received_correct_setpoints(setup_responder_and_spy):
    """The protocol writes voltage=120 and frequency=5000; the request
    publishes must carry those exact values."""
    cols = [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_voltage_column(), make_frequency_column(),
    ]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {"e00": 0}
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "electrodes": ["e00"],
        "voltage": 120,
        "frequency": 5000,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished

    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    voltage_msgs = [m for _, t, m in events if t == PROTOCOL_SET_VOLTAGE]
    frequency_msgs = [m for _, t, m in events if t == PROTOCOL_SET_FREQUENCY]
    assert "120" in voltage_msgs
    assert "5000" in frequency_msgs
```

- [ ] **Step 2: Run the integration test**

Make sure Redis is running.

```bash
pixi run pytest src/dropbot_protocol_controls/tests/tests_with_redis_server_need/test_voltage_frequency_protocol_round_trip.py -v
```

Expected: 2 passed.

If `wait` times out, the most common cause is a stale subscriber from a previous test run — clear Redis with `redis-cli flushall` and retry. If the ordering assertion fails, that's a real bug — investigate whether VoltageHandler/FrequencyHandler actually got priority 20 or whether RoutesHandler fired first.

- [ ] **Step 3: Commit**

```bash
git -C src add dropbot_protocol_controls/tests/tests_with_redis_server_need/
git -C src commit -m "[PPT-4] Add Redis-backed end-to-end round-trip test (priority ordering verified)"
```

---

## Task 15: Register `DropbotProtocolControlsPlugin` in `examples/plugin_consts.py`

**Files:**
- Modify: `src/examples/plugin_consts.py` (add import + append to `DROPBOT_BACKEND_PLUGINS`)

**Why this is its own task:** the plugin needs to be loaded by the application bundle to actually contribute its columns at app start. Until this lands, the unit/integration tests cover it but the full GUI app doesn't see it.

- [ ] **Step 1: Add the import + bundle entry**

In `src/examples/plugin_consts.py`, add the import alongside the other dropbot imports (around line 15):

```python
from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
```

Update `DROPBOT_BACKEND_PLUGINS` (lines 63-66):

```python
DROPBOT_BACKEND_PLUGINS = [
    PeripheralControllerPlugin,
    DropbotControllerPlugin,
    DropbotProtocolControlsPlugin,
]
```

- [ ] **Step 2: Verify the imports + bundle resolve cleanly**

```bash
pixi run python -c "from examples.plugin_consts import DROPBOT_BACKEND_PLUGINS; print([p.__name__ for p in DROPBOT_BACKEND_PLUGINS])"
```

Expected: `['PeripheralControllerPlugin', 'DropbotControllerPlugin', 'DropbotProtocolControlsPlugin']`

- [ ] **Step 3: Commit**

```bash
git -C src add examples/plugin_consts.py
git -C src commit -m "[PPT-4] Register DropbotProtocolControlsPlugin in DROPBOT_BACKEND_PLUGINS"
```

---

## Task 16: Final verification

**Files:** none (verification only)

**Why this is its own task:** confirms all PPT-4 tests + adjacent test suites still pass after the full set of edits. Catches any cross-cutting regression introduced over the prior 15 tasks.

- [ ] **Step 1: Run all new + impacted test suites**

```bash
pixi run pytest src/dropbot_protocol_controls/tests/ -v --ignore=src/dropbot_protocol_controls/tests/tests_with_redis_server_need
```

Expected: all PPT-4 unit tests pass (test_plugin_shell.py, test_voltage_column.py, test_frequency_column.py, test_persistence.py, test_demo_responder.py).

```bash
pixi run pytest src/dropbot_controller/tests/ -v
```

Expected: all dropbot_controller tests pass, including the new test_protocol_set_handlers.py.

```bash
pixi run pytest src/pluggable_protocol_tree/tests/ -v
```

Expected: PPT-3 + PPT-2 + PPT-1 tests still pass (no regressions). Confirms the new plugin's introduction didn't break anything in the pluggable protocol tree.

- [ ] **Step 2: Run the Redis-required integration test**

Make sure Redis is running.

```bash
pixi run pytest src/dropbot_protocol_controls/tests/tests_with_redis_server_need/ -v
```

Expected: 2 passed.

- [ ] **Step 3: Run the smoke demo**

```bash
pixi run python -m dropbot_protocol_controls.demos.run_voltage_frequency_demo
```

Expected: protocol completes within ~5s, spy prints 6 events per step (request + ack for each of voltage/frequency, plus electrode change), final "Done" line.

- [ ] **Step 4: Verify the assembled column list contains voltage + frequency**

```bash
pixi run python -c "
from envisage.api import CorePlugin, Application
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin

app = Application(plugins=[
    CorePlugin(),
    PluggableProtocolTreePlugin(),
    DropbotProtocolControlsPlugin(),
])
app.start()
ppt = next(p for p in app.plugins if isinstance(p, PluggableProtocolTreePlugin))
ids = [c.model.col_id for c in ppt._assemble_columns()]
print('voltage' in ids, 'frequency' in ids, ids)
"
```

Expected: `True True [...with 'voltage' and 'frequency' present...]`

- [ ] **Step 5: Commit any verification-script artifacts (none expected)**

If everything passes, no changes to commit. If verification surfaced a bug, fix it in a small follow-up commit before declaring the feature done.

```bash
git -C src status  # should report clean working tree
```

---

## Implementation Notes

**Branch hygiene:** the WIP spec was committed to `feat/ppt-3-electrodes-routes`. If you prefer a clean PPT-4 branch, `git checkout -b feat/ppt-4-voltage-frequency` before Task 1 — both approaches work. The merge target is the same.

**Dependency on `dropbot_controller`:** `dropbot_protocol_controls` imports topic constants and `DropbotPreferences` from `dropbot_controller`. This is the intentional layering — see Section 3 "Topic ownership rationale" in the spec.

**No `protocol_grid` changes:** same approach as PPT-3 — leave the legacy protocol_grid alone. It keeps using its existing voltage/frequency code path.

**Backwards compat:** old protocol JSON files saved before PPT-4 don't have voltage/frequency columns. `ProtocolSession.from_file` resolves columns from the file's `cls` qualnames, so an old file loads with no voltage/frequency setpoint and runs normally. The full GUI app uses `_assemble_columns` to build the union of all contributed columns, so opening an old file fills voltage/frequency cells from `DropbotPreferences` defaults; saving re-emits with the new columns present. No migration code needed.

**If a test fails unexpectedly during execution:** use `superpowers:systematic-debugging` rather than guessing. The most likely failure modes are (1) stale dramatiq subscribers in Redis from prior runs (`redis-cli flushall` then retry), (2) `DropbotPreferences()` no-arg construct hitting an envisage app that hasn't been started yet (the unit tests patch `DropbotPreferences` to avoid this; the integration test relies on it being safe — if not, wrap factories in a try/except).
