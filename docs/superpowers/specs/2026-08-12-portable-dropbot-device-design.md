# Portable Dropbot device type (design)

Date: 2026-08-12
Branches: `feat/portable-dropbot-device` (Microdrop),
`feat/package-as-portable-dropbot` (python-driver)

## Problem

Microdrop drives two device types — DropBot and OpenDrop. The
Portable Dropbot (GitLab `dropbot-portable/python-driver`) is a
third: same electrode-actuation job, plus six motors (tray, pmt,
magnet, filter, pogo_left, pogo_right), heaters, a PMT, and a
streamed status/alarm protocol. Nothing wires it into Microdrop.

## Decision

Add it in-tree as a first-class device type, mirroring OpenDrop's
architecture: a backend controller package selected with
`--device portable`, and a frontend package contributing TWO dock
panes — the standard status-and-controls pane and a motor panel.
The device viewer needs no changes: it already publishes
`hardware/requests/electrodes_state_change`, and any backend that
implements `on_electrodes_state_change_request` receives it.

## Components

### A. Driver packaging (python-driver repo)

The repo is not installable (flat modules, hyphenated folder, no
pyproject). Restructure: core modules (`__init__`, `session`,
`portable_dropbot_service`, `commands`, `commands_generated`,
`proxy`, `utils`) move into a `portable_dropbot/` package; scripts
and `full_test_ui/` stay at the root importing it; a
`pyproject.toml` names the distribution `portable-dropbot`
(import `portable_dropbot`). Driver logic unchanged.

Microdrop imports the package lazily and reports a clear error if
missing; for development it is installed editable into the pixi env
(`pixi run pip install -e ...`). Pinning it as a pixi dependency
waits until the packaging branch is merged.

### B. Backend — `portable_dropbot_controller/`

Mirror of `opendrop_controller/`:

- `consts.py` — topics under `portable_dropbot/…` plus the shared
  `hardware/…` strings; `ACTOR_TOPIC_DICT` subscribing to
  `portable_dropbot/requests/#`, `hardware/requests/#`, and the
  shared connected/disconnected signals.
- `interfaces/` — `IPortableDropbotControllerBase`,
  `IPortableDropbotControlMixinService`.
- `portable_dropbot_controller_base.py` — HasTraits base owning the
  `DropletBotSession` proxy and the standard topic-tree
  `listener_actor_routine` dispatch (`portable_dropbot` and
  `hardware` head topics).
- `services/` mixins, composed by `plugin.py` exactly as OpenDrop
  composes its own:
  - **monitor** — port scan probing the driver's login handshake
    (the hardware has no VID/PID identity), preferred port first
    (preference hint). On connect: publish
    `hardware/signals/connected`, start the driver's event
    streaming, and bridge its callbacks into dramatiq signals
    (status, chip detect, alarms). On loss: disconnected signal,
    resume scanning.
  - **electrodes** — `on_electrodes_state_change_request` →
    `session.actuate_channels(channels)`. Channel count comes from
    the driver's own board detection (120/200).
  - **states** — voltage/frequency requests →
    `set_actuation(voltage, frequency)`; both are Int end-to-end;
    realtime mode handling as the other backends do.
  - **motors** — mechanism requests (`move_tray` in/out,
    `move_magnet` engage/disengage/press/release, `set_filter`
    0-4, `set_pogo`, `home_all`) and advanced per-motor requests
    (absolute, relative, stop, home — steps, Int). Every action
    ends by publishing `portable_dropbot/signals/motors_updated`
    carrying positions, homed flags, and mechanism states.
- `preferences.py` — port hint, baud, defaults.

Driver calls follow the magnet plugin's guard pattern (transaction
lock + error handling); failures publish an error signal, alarms
surface as the driver's decoded strings, never tracebacks.

### C. Frontend — `portable_dropbot_status_and_controls/`

Subclasses `template_status_and_controls` (`BaseStatusPlugin` /
`BaseStatusDockPane`), implementing the same hooks the DropBot and
OpenDrop panes do. Listens to `portable_dropbot/signals/#` +
`hardware/signals/#`.

**Status pane** (UnifiedView): device icon, connection text,
chip-detect, realtime toggle, editable voltage/frequency,
capacitance — plus portable extras: temperature, a one-line
mechanism summary (tray/magnet/filter/pogo), the last alarm text.

**Motor panel** — second dock pane contributed via
`_get_extra_dock_pane_classes()`. House MVC: Qt-free HasTraits
model mutated only on the GUI thread by the message handler; view
observes the model; controller publishes request topics.
- *Mechanisms section*: tray in/out, magnet
  engage/disengage/press/release, filter position dropdown (0-4),
  pogo up/down, Home All.
- *Advanced section* (collapsible): per motor — position readout,
  absolute/relative move spinners (steps), move, stop, home.

### D. Wiring

`PORTABLE_DROPBOT_BACKEND_PLUGINS` / `_FRONTEND_PLUGINS` in
`examples/plugin_consts.py`; `--device portable` added to
`examples/run_device_viewer_pluggable*.py` and `microdrop.py`'s
`resolve_run_config()`.

## Testing

User verifies with hardware through the GUI. The backend mixins
keep the driver behind one proxy attribute, so they can be
exercised against a stub session later if wanted.
