# Microdrop Project

## What is MicroDrop?

MicroDrop is an open-source digital microfluidics (DMF) control system built by [Sci-Bots](https://sci-bots.com/). DMF uses electric fields to manipulate tiny droplets on a chip — lab-on-a-chip for biology, chemistry, and diagnostics.

### Supported Hardware
- **[DropBot](https://sci-bots.com/products/dropbot)** — Sci-Bots' DMF platform. Teensy 3.x-based, USB serial RPC. Full capacitance sensing, short detection, multi-channel actuation.
- **[OpenDrop](https://www.gaudi.ch/OpenDrop/)** — Open-source DMF platform by GaudiLabs. Simpler hardware, community-driven.

## Project Structure
- Outer repo: `pixi-microdrop/microdrop-py` (uses pixi for env management)
- Inner submodule: `microdrop-py/src/` — the actual Microdrop source (Pyface/Envisage GUI app)
- The source code submodule remote is `https://github.com/Blue-Ocean-Technologies-Inc/Microdrop.git`
- Main branch in the submodule is `main`

## Software Architecture

Three-layer, message-driven system:

1. **Frontend** (PySide6/Qt6 GUI) — Interactive SVG device viewer + protocol grid. Built on [Envisage](https://docs.enthought.com/envisage/) plugin framework.
2. **Message Server** (Redis + Dramatiq) — Pub/sub message router with MQTT-style topic matching. Can run on localhost, LAN, or cloud (enables remote hardware control).
3. **Backend** (DropBot Controller) — Receives messages via Dramatiq workers, translates to hardware commands via `SerialProxy` (auto-generated Python RPC from C++ firmware via `arduino-rpc` + protobuf), sends over USB serial.

**Data flow**: User clicks electrode → frontend publishes `electrodes_state_change` (toggles on/off state, does NOT apply voltage) → Redis routes to backend worker → backend calls `proxy.state_of_channels = [...]` → SerialProxy sends RPC over USB → firmware applies high voltage → capacitance feedback flows back → GUI updates.

## DropBot Python API

```python
import dropbot as db
proxy = db.SerialProxy()  # auto-detects connected DropBot

# Read state
proxy.voltage, proxy.frequency, proxy.state_of_channels, proxy.number_of_channels

# Set state
proxy.voltage = 100
proxy.frequency = 1e4
proxy.hv_output_enabled = True
proxy.state_of_channels = channel_array  # 1D numpy array, 0/1

# Convenience
proxy.update_state(hv_output_enabled=True, hv_output_selected=True, voltage=100, frequency=10e3)

# Measurements
proxy.measure_voltage(), proxy.measure_capacitance(), proxy.measure_temperature(), proxy.detect_shorts()

# Signals (event-driven)
proxy.signals.signal('capacitance-updated').connect(callback_fn)
# Available: connected, disconnected, no-power, halted, shorts-detected,
#   capacitance-updated, capacitance-exceeded, channels-updated,
#   drops-detected, output_enabled, output_disabled

# Thread safety
with proxy.transaction_lock:
    pass
```

## Key Repos
- **MicroDrop**: https://github.com/Blue-Ocean-Technologies-Inc/Microdrop
- **dropbot.py**: https://github.com/Blue-Ocean-Technologies-Inc/dropbot.py

## Issue Tracking
- Issues: https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/

## Git & PR Workflow
- Commit early, commit frequently — make multiple small, incremental commits for each iterative change (e.g., add constant, then add listener, then add dialog, then wire it up). Each commit should have a clear, descriptive message.
- Always create a new branch for resolving issues (never commit directly to main/master)
- Always submit a PR for reviewing changes after pushing the branch

## Presentation (`microdrop-architecture.html`)
- Self-contained HTML presentation about MicroDrop architecture and DropBot hardware communication
- See `PRESENTATION-GUIDE.md` (in this same `docs/` folder) for full details: slide structure, brand/design system, CSS architecture, SVG logos, and layout conventions
- Key corrections (do not revert): `electrodes_state_change` toggles state only (not voltage), architecture is three-way decoupled (Frontend/Backend/Server), DropBot API slides reflect actual Python API

# Below is from a document that provides more guidance to Claude Code (claude.ai/code) when working with code in this repository:

## Project Overview

MicroDrop-Next-Gen is a GUI for the DropBot Digital Microfluidics control system. It uses a plugin-based architecture (Envisage) with async message passing (Dramatiq + Redis) between decoupled components.

## Running the Application

Redis must be running before launching. Start it via `redis-server` or `python examples/start_redis_server.py`.

```bash
# Full application (frontend + backend)
python examples/run_device_viewer_pluggable.py

# Frontend only (needs redis + backend running separately)
python examples/run_device_viewer_pluggable_frontend.py

# Backend only
python examples/run_device_viewer_pluggable_backend.py
```

## Running Tests

Tests are in `examples/tests/` and `electrode_controller/tests/`. Some test subdirectories have external requirements:
- `tests_with_redis_server_need/` — requires a running Redis server
- `tests_with_dropbot_connection_need/` — requires physical DropBot hardware

```bash
pytest examples/tests/
pytest electrode_controller/tests/
```

## Architecture

### Plugin System (Envisage)

Every major component is an Envisage plugin. Plugins are instantiated in run scripts via `plugin_consts.py`, and **load order matters** — earlier plugins' service contributions take priority.

Three plugin categories:
- **Required:** `CorePlugin`, `MessageRouterPlugin`, `LoggerPlugin`
- **Frontend (UI):** `MicrodropPlugin`, `DeviceViewerPlugin`, `ManualControlsPlugin`, `DropbotStatusPlugin`, `ProtocolGridControllerUIPlugin`, etc.
- **Backend (hardware):** `DropbotControllerPlugin`, `ElectrodeControllerPlugin`, `PeripheralControllerPlugin`

Standard plugin layout:
```
<plugin_name>/
├── plugin.py       # Envisage Plugin class
├── consts.py       # Constants, ACTOR_TOPIC_DICT
├── MVC.py          # Model-View-Controller (UI plugins)
└── services/       # Service implementations
```

### Message Passing (Dramatiq + Redis)

All inter-plugin communication goes through a pub/sub message router — plugins never call each other directly.

- `publish_message(topic, message)` from `microdrop_utils/dramatiq_pub_sub_helpers.py` sends messages
- `MessageRouterActor` in the same file receives and fans out messages to subscribers
- Topics follow MQTT-style naming: `dropbot/requests/set_voltage`, `dropbot/signals/connected`
- MQTT wildcards supported: `+` (single level), `#` (multi-level)
- See `MESSAGES.md` for the full topic map of which plugins send/receive what

### Message Handler Conventions

**Frontend handlers** (`DramatiqControllerBase` in `microdrop_utils/dramatiq_controller_base.py`):
- Methods named `_on_{topic}_triggered()` are called reflectively when a matching topic arrives
- Used for UI state updates

**Backend handlers** (`DropbotControllerBase` in `dropbot_controller/dropbot_controller_base.py`):
- Methods named `on_{specific_sub_topic}_request()` or `on_{specific_sub_topic}_signal()`
- `_request` handlers only run when a DropBot is connected
- The different naming convention distinguishes frontend "triggers" from backend "requests"

### Service Mixin Pattern

`DropbotControllerPlugin` composes multiple mixin services implementing `IDropbotControlMixinService`:
- `DropbotMonitorMixinService`, `DropbotStatesSettingMixinService`, `DropbotSelfTestsMixinService`, `DropletDetectionMixinService`, `DropbotChangeSettingsService`

### SVG Device Handling

Electrode layouts are defined in SVG files. Metadata is parsed from SVG path elements (`data-channels` attribute). Centers are computed from path vertices and neighbors from distance calculations. Only simple path commands (M, H, V, Z) are supported — no curves. See `device_viewer/utils/dmf_utils.py`.

## Coding Conventions

- Every plugin has a `consts.py` with `PKG = '.'.join(__name__.split('.')[:-1])` and `ACTOR_TOPIC_DICT`
- Logging: `from logger.logger_service import get_logger; logger = get_logger(__name__)`
- Styling: use `microdrop_style/` helpers (`colors`, `button_styles`, `icons`)
- Traits/TraitsUI for models and data binding; PySide6/Qt for widgets
- `ValidatedTopicPublisher` (in `microdrop_utils/dramatiq_pub_sub_helpers.py`) provides Pydantic-validated message publishing

## Useful Environment Variables

- `USE_CV2=1` — force OpenCV camera backend instead of QMultimedia
- `DEBUG_QT_PLUGINS=1` — Qt plugin debug logs
- `QT_LOGGING_RULES="*=true"` — maximal Qt debug logging
- `QT_FFMPEG_DECODING_HW_DEVICE_TYPES=` / `QT_FFMPEG_ENCODING_HW_DEVICE_TYPES=` — force software encoding/decoding

## Key Documentation Files

- `src/README.md` — documentation guide & tech-selection rationale (why Envisage/Redis/Dramatiq)
- `ENVISAGE_TRAITS_GUIDE.md` (in this same `docs/` folder) — Envisage/Traits/TraitsUI framework guide + how this repo uses them
- `src/MESSAGES.md` — complete pub/sub topic map (who sends/receives what)
- `src/DRAMATIQ_DOCS.md` — Dramatiq broker/encoder/actor API notes
