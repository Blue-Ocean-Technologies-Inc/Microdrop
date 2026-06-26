# Heater Controls UI — Design

**Date:** 2026-06-25
**Status:** Approved (brainstorming)

## Goal

A dock-pane UI for the heater, driven entirely through the heater backend's
dramatiq topics. It offers a **dynamic heater-channel dropdown** (populated from
what the board reports as available), **command fields** (set temperature / PWM,
PID enable/disable/stop, stream start/stop, fan on/off, all-off), and **status
reporters** (connection state + live telemetry: temperature / PWM / board id).

Pattern: the compact TraitsUI `portable_motor_control` dock pane (Model + View +
connection listener + dock-pane controller), split into clean files, with the
file-level MVC separation of `peripherals_ui`.

## Backend change: publish telemetry

Live readouts need the backend to publish what is currently log-only.

- `HeaterSerialProxy._serial_reader`: after parsing a `§<FRAME>{json}` packet,
  publish the dict (JSON) on a new `Heater/signals/telemetry` topic in addition
  to logging it. All frames go on the one topic; the UI routes by `_frame`.
- On connect, also send `whoami` (alongside the existing `dump_config`) so the
  WHOAMI frame populates the board-identity label.
- `heater_controller/consts.py`: add `TELEMETRY = "Heater/signals/telemetry"`.

Telemetry frame shapes (tagged with `_frame`):
- `WHOAMI` → `uid`, `device_id`, `bluetooth_name`
- `INFO` → `event` (`pid_started`, `pid_stopped`, `pid_saved`, ...), `kp`/`ki`/`kd`
- `ERR` → `kind`, `heater`, `message`
- `TEMP` / `PID_<HEATER>` → `temperatures` (dict sensor→°C), `pid_temperature`,
  `pwm_percentage` (PID mode) or `pwm_tec1`/`pwm_tec2`, `current`, `timestamp`

## Frontend package: `heater_controls_ui`

```
heater_controls_ui/
  __init__.py
  consts.py        # PKG, listener_name, ACTOR_TOPIC_DICT (Heater/signals/#)
  model.py         # HeaterControlModel (HasTraits, Qt-free)
  view.py          # TraitsUI View: dynamic EnumEditor + fields + status labels
  listener.py      # HeaterControlListener (dramatiq -> GUI.invoke_later -> model)
  dock_pane.py     # HeaterControlDockPane (TraitsDockPane = controller)
  plugin.py        # HeaterControlsUiPlugin (+ Tools menu action)
  tests/
    test_model_and_listener.py
```

### `model.py` — `HeaterControlModel(HasTraits)` (Qt-free)
- Connection: `connected = Bool`.
- Selection: `available_heaters = List(Str)`, `selected_heater = Str`.
- Inputs: `temperature = Float`, `pwm = Int(0..100)`, `stream_group = Str("all")`.
- Command buttons: `apply_temperature`, `apply_pwm`, `pid_enable`, `pid_disable`,
  `pid_stop`, `stream_start`, `stream_stop`, `fan_on`, `fan_off`, `all_off`,
  `connect`.
- Read-only status strings: `status_text`, `pid_temp_text`, `pwm_text`,
  `temps_text`, `board_id_text`.

### `view.py` — TraitsUI `View`
- Heater dropdown: `Item('selected_heater', editor=EnumEditor(name='object.available_heaters'))`
  — updates live as `available_heaters` changes.
- Set Temperature: float field + Apply button. Set PWM: int field + Apply button.
- PID: enable / disable / stop buttons. Stream: start / stop. Fan: on / off.
  Safety: all-off button.
- Status group: read-only labels bound to the status strings + a Connect control.
- Command groups `enabled_when='connected'`.

### `listener.py` — `HeaterControlListener(HasTraits)`
- A dramatiq listener (via `generate_class_method_dramatiq_listener_actor`) on
  the `heater_controls_ui_listener` name, routing `Heater/signals/...`:
  - `connected` / `disconnected` → `model.connected`
  - `heaters_available` → `model.available_heaters`; if `selected_heater` unset or
    no longer present, default it to the first entry
  - `telemetry` → parse the dict by `_frame`, format the readout strings
    (`pid_temp_text`, `pwm_text`, `temps_text`, `board_id_text`)
- All model writes are marshaled to the GUI thread with
  `pyface.api.GUI.invoke_later` (telemetry streams quickly; TraitsUI editors must
  update on the UI thread).

### `dock_pane.py` — `HeaterControlDockPane(TraitsDockPane)` (controller)
- Holds the `HeaterControlModel`, sets `traits_view`, instantiates the listener.
- `@observe` model command buttons → `publish_message` to the typed topics:
  - `apply_temperature` → `SET_TEMPERATURE` `{"heater": sel, "temperature": t}`
  - `apply_pwm` → `SET_PWM` `{"heater": sel, "pwm": v}`
  - `pid_enable/disable/stop` → `SET_PID_MODE` `{"heater": sel, "mode": ...}`
  - `stream_start/stop` → `SET_STREAM` `{"group": grp | "stop"}`
  - `fan_on/off` → `SET_FAN` `{"on": bool}`
  - `all_off` → `ALL_OFF`
  - `connect` → `START_DEVICE_MONITORING`
- Theme styling mirrors the other dock panes.

### `plugin.py` / `consts.py`
- `HeaterControlsUiPlugin(Plugin)` contributes a `TaskExtension` with the dock
  pane factory + a Tools-menu "Search Heater Connection" `SchemaAddition`, and
  `actor_topic_routing` for `ACTOR_TOPIC_DICT`.
- `ACTOR_TOPIC_DICT = {"heater_controls_ui_listener": ["Heater/signals/#"]}`.

## Integration

- Register `HeaterControlsUiPlugin` in `examples/plugin_consts.py`
  `DROPBOT_FRONTEND_PLUGINS` (heater-specific, like the dropbot status panels).

## Thread-safety

The dramatiq listener fires on worker threads; model writes are pushed to the GUI
thread via `pyface.api.GUI.invoke_later`. Command publishing happens on the GUI
thread (button observers) and is inherently safe.

## Testing

Hardware-free unit tests for the model/listener logic:
- `heaters_available` payload → `available_heaters` + default `selected_heater`,
  and selection preserved/repaired when the list changes.
- telemetry dicts (PID_<HEATER>, WHOAMI) → expected formatted readout strings.

Live UI wiring (dropdown, buttons → topics) verified manually with the backend
demo / a running app.

## Out of scope (deferred)

- PID tunings (kp/ki/kd) + save controls (calibration — later).
- Plotting/history (the old standalone app's matplotlib view).
- Per-sensor configuration UI.
