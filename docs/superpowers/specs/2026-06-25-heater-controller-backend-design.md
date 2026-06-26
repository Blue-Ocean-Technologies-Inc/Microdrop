# Heater Controller Backend — Design

**Date:** 2026-06-25
**Status:** Approved (brainstorming)

## Goal

Add a backend plugin that connects to the heater controller (RP2040 / MicroPython,
`VID:PID=2E8A:0005`), maintains that connection, prints everything received from the
device, and can send basic (plain-text) commands to it — mirroring how the existing
`peripheral_controller` (the z-stage magnet) manages its device.

The heater speaks a different protocol than the magnet: newline-terminated plain-text
commands (`whoami`, `scan`, `dump_config`, `stream_all`, `pid_<heater>_<setpoint>`,
`pwm_<heater>_<v>`, `fan_on`/`fan_off`, `all_off`, …) and emits plain-text response
lines plus `§<FRAME>{json}` telemetry packets. The magnet uses `base_node_rpc`'s
structured RPC `SerialProxy`.

## Approach

The `peripheral_controller` backend is ~90% generic. Only four things are
device-specific: the serial **proxy class**, the **HWID** to scan for, the **device
name**, and the **command-setter service**. So we extract the generic machinery into a
new base package and make both the **magnet** and the **heater** thin subclasses.

```
peripheral_device_controller_base/        # NEW — generic, no device specifics
  __init__.py
  consts.py                               # topic/key factory helpers from a device name
  peripheral_device_controller_base.py    # PeripheralDeviceControllerBase (listener + routing)
  plugin.py                               # PeripheralDeviceControllerPlugin (composition)
  interfaces/
    __init__.py
    i_peripheral_device_control_mixin_service.py   # IPeripheralDeviceControlMixinService
  services/
    __init__.py
    peripheral_device_monitor_mixin_service.py     # PeripheralDeviceMonitorMixinService

peripheral_controller/                    # the MAGNET — now subclasses the base
  ... existing files, classes re-parented onto base; consts/topics UNCHANGED ...

heater_controller/                        # NEW — subclasses the base
  __init__.py
  consts.py
  heater_serial_proxy.py                  # HeaterSerialProxy (headless pyserial)
  heater_controller_base.py               # HeaterControllerBase(PeripheralDeviceControllerBase)
  plugin.py                               # HeaterControllerPlugin(PeripheralDeviceControllerPlugin)
  interfaces/__init__.py
  services/
    __init__.py
    heater_monitor_mixin_service.py       # HeaterMonitorMixinService(PeripheralDeviceMonitorMixinService)
    heater_command_setter_service.py      # HeaterCommandSetterService
```

## Base package: `peripheral_device_controller_base`

### `PeripheralDeviceControllerBase(HasTraits)`
Generalized from `PeripheralControllerBase`. The listener/routing is already written
against `self._device_name`; the device bits become overridable class attributes
instead of module-level imports:

- `_device_name = Str` — abstract; set by subclass (e.g. `"ZStage"`, `"Heater"`).
- `proxy = Any()` — subclass narrows to `Instance(SpecificProxy)`.
- Connection topics derived from `_device_name` at runtime: `{name}/signals/connected`,
  `{name}/signals/disconnected`, and app-globals key `{name}.connection_active`.
- `_always_allowed_subtopics = ["start_device_monitoring", "retry_connection"]` —
  requests allowed even when disconnected (replaces the hardcoded
  `START_DEVICE_MONITORING` special-case).
- `listener_name` derived from `_device_name` and **must equal** the `ACTOR_TOPIC_DICT`
  key the subclass plugin contributes.
- `connection_active = Bool(False)`, mirrored to `app_globals` on change.
- `_terminate_proxy()` hook — base default calls `self.proxy.terminate()`; the magnet
  overrides to also null `proxy.monitor` (base_node_rpc specifics).
- `cleanup()`, `traits_init()` (builds the dramatiq listener actor) — unchanged logic.

Routing rules preserved: messages whose head topic == `_device_name`; connected/
disconnected toggle `connection_active` → `on_<sub>_signal`; always-allowed subtopics →
`on_<sub>_request` regardless of connection; all other `requests/...` → `on_<sub>_request`
only when connected; stale-timestamp messages dropped.

### `PeripheralDeviceMonitorMixinService(HasTraits)`
Generalized from `PeripheralMonitorMixinService`. APScheduler `IntervalTrigger(2s)`
poll → on found → connect; disconnect handler terminates proxy + resumes polling.
Overridable bits:

- `_default_hwids` — list of HWIDs to scan when the request carries no payload.
- `_make_proxy(port_name)` — factory returning the device proxy (`DramatiqPeripheralSerialProxy`
  for the magnet, `HeaterSerialProxy` for the heater).
- `_find_port(hwids)` — defaults to `check_devices_available(hwids)`; the heater overrides
  to match `VID:PID` directly (RP2040 port description differs from the `'USB Serial'` default).

`on_disconnected_signal` calls `self._terminate_proxy()` (via the controller) rather than
reaching into `proxy.monitor`, so non-RPC proxies work.

### `PeripheralDeviceControllerPlugin(Plugin)`
Generalized `start()`/`stop()` that looks up the mixin services for its
`IPeripheralDeviceControlMixinService` protocol + the controller base, builds a combined
`Controller` class, instantiates it, and cleans up on stop. Subclass supplies
`service_offers`, `actor_topic_routing` (its `ACTOR_TOPIC_DICT`), and `id`/`name`.

### `IPeripheralDeviceControlMixinService(Interface)`
Generic mixin interface (`id`, `name`, `proxy`) — generalized from the peripheral one.

## Magnet refactor (`peripheral_controller`)

Behavior-preserving re-parenting; **public module paths and topics stay identical** so
nothing else in the app breaks:

- `PeripheralControllerBase(PeripheralDeviceControllerBase)` — `_device_name="ZStage"`,
  `proxy = Instance(DramatiqPeripheralSerialProxy)`, `preferences = Instance(PeripheralPreferences)`,
  override `_terminate_proxy` to null `proxy.monitor`.
- `PeripheralMonitorMixinService(PeripheralDeviceMonitorMixinService)` —
  `_default_hwids=[MR_BOX_HWID]`, `_make_proxy` → `DramatiqPeripheralSerialProxy(port=...)`.
- `ZStageStatesSetterMixinService`, `consts.py`, `plugin.py`, `preferences.py`,
  `datamodels.py` unchanged except `plugin.py`/base now extend the base classes.
- Safety net: existing `peripheral_controller/tests` must still pass.

## Heater package (`heater_controller`)

### `HeaterSerialProxy`
Headless serial wrapper (no Qt, no BLE, no firmware upload — distilled from
`heater_ui/controller.py`'s `Board` serial path):

- `__init__(port, baudrate=115200)` — opens `serial.Serial`, starts a daemon reader
  thread, publishes `Heater/signals/connected`.
- Reader thread: `readline()` loop. Each decoded line → `logger.info`. Lines starting
  with `§` → split `§<FRAME>{json}`, parse, `logger.info` the telemetry dict (tagged with
  `_frame`). Empty lines / decode errors skipped. On `SerialException`/`OSError` (unplug):
  publish `Heater/signals/disconnected` and exit. **RX is log-only for now** (no topic
  publish — that's a deliberate next step).
- `send_command(text)` — newline-terminate, encode, `write()`, with small retry
  (mirrors `Board._send_command_serial`).
- `terminate()` — stop reader thread, close port.
- `transaction_lock` (`threading.Lock`) — serializes writes (proxy convention).

### `HeaterControllerBase(PeripheralDeviceControllerBase)`
`_device_name="Heater"`, `proxy = Instance(HeaterSerialProxy)`. No preferences.

### `HeaterMonitorMixinService(PeripheralDeviceMonitorMixinService)`
`_default_hwids=["VID:PID=2E8A:0005"]`, `_make_proxy` → `HeaterSerialProxy(port=...)`,
`_find_port` matching VID:PID directly.

### `HeaterCommandSetterService`
One exposed method `on_send_command_request(message)` → under `transaction_lock`,
`self.proxy.send_command(message.content)`. Generic raw-command channel; typed
convenience commands are a later addition.

### `consts.py`
```
DEVICE_NAME = "Heater"
HEATER_HWID = "VID:PID=2E8A:0005"
CONNECTED  = "Heater/signals/connected"
DISCONNECTED = "Heater/signals/disconnected"
START_DEVICE_MONITORING = "Heater/requests/start_device_monitoring"
RETRY_CONNECTION = "Heater/requests/retry_connection"
SEND_COMMAND = "Heater/requests/send_command"
ACTOR_TOPIC_DICT = {"heater_controller_listener": ["Heater/requests/#", CONNECTED, DISCONNECTED]}
```

## Integration & activation

- Register `HeaterControllerPlugin` in `examples/plugin_consts.py` →
  `DROPBOT_BACKEND_PLUGINS`.
- The magnet's monitoring is kicked off by `peripherals_ui` publishing
  `START_DEVICE_MONITORING`. The heater has no UI yet, so for now add a small
  `examples/demos/run_heater_controller_demo.py` that starts the backend, publishes
  `Heater/requests/start_device_monitoring`, and lets the reader thread log incoming
  lines. Optionally sends a `whoami` after connect to demonstrate the command path.

## Out of scope (explicitly deferred)

- Publishing RX lines/telemetry to dramatiq topics (log-only for now).
- Typed convenience command topics (setpoint, pwm, fan, stream).
- BLE transport.
- Heater preferences and any heater UI plugin.

## Testing

- `peripheral_controller/tests` (magnet) must pass unchanged — proves the refactor is
  behavior-preserving.
- Unit test for `HeaterSerialProxy` line routing (plain vs `§`-telemetry) against a fake
  serial object, runnable without hardware.
- Hardware-dependent connect/print verified manually via the demo script.
