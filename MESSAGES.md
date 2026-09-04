Plugins do not communicate with each other, all updates are dispatched by the message broker, so we only need to list the interactions between each component and the broker, namely what they send and what they receive.

Messages are sent via publish_message() from microdrop_utils/dramatiq_pub_sub_helpers.py.

They are received/handled using _on_{topic}_triggered (or similar) handlers, which made functional by microdrop_utils/dramatiq_controller_base.py. 

I used ** and !! to indicate that a plugin is listening to a signal that they are sending. We were having positive feedback loops when the dropbot isnt detected (like 7 logs a seconds) so this may contribute to it. Loop may of course also occur between two plugins. 

## Backend

### dropbot_controller

Sending: (Via proxy)
- proxy.digital_read(OUTPUT_ENABLE_PIN)
- proxy.update_state()
- proxy.turn_off_all_channels()
- proxy.terminate()
- self.proxy.voltage
- self.proxy.frequency

Receiving: (Via proxy)
- proxy.signals.signal('output_enabled') (dropbot_controller_base.py:164)
- proxy.signals.signal('output_disabled')
- proxy.signals.signal('halted')
- proxy.signals.signal('capacitance-updated')
- proxy.signals.signal('shorts-detected')

Sending: (Via publish_message)
- CAPACITANCE_UPDATED "dropbot/signals/capacitance_updated"
- SHORTS_DETECTED "dropbot/signals/shorts_detected"
- HALTED "dropbot/signals/halted"
- !! HALT "dropbot/requests/halt"
- CHIP_NOT_INSERTED "dropbot/signals/chip_not_inserted"
- CHIP_INSERTED "dropbot/signals/chip_inserted"
- NO_DROPBOT_AVAILABLE "dropbot/signals/warnings/no_dropbot_available"
- NO_POWER "dropbot/signals/warnings/no_power"
- "dropbot/error"
- DROPBOT_SETUP_SUCCESS "dropbot/signals/setup_success"
- SELF_TESTS_PROGRESS "dropbot/signals/self_tests_progress"
- SELF_TESTS_RESULTS "dropbot/signals/self_tests_results"
- CONNECTED "dropbot/signals/connected"
- ** DISCONNECTED "dropbot/signals/connected"

Receiving: (Via handlers)
- START_DEVICE_MONITORING "dropbot/requests/start_device_monitoring"
- DETECT_SHORTS "dropbot/requests/detect_shorts"
- RETRY_CONNECTION "dropbot/requests/retry_connection"
- !! HALT "dropbot/requests/halt"
- ** DISCONNECTED "dropbot/signals/disconnected"

### electrode_controller

Sending: (Via proxy)
- proxy.state_of_channels (electrode_state_change_service.py:38)

Receiving: (Via handlers)
- ELECTRODES_STATE_CHANGE "dropbot/requests/electrodes_state_change"

## Frontend

### dropbot_status_plot

Receiving:
- CAPACITANCE_UPDATED "dropbot/signals/capacitance_updated" (via microdrop_utils/base_dropbot_status_plot_qwidget.py)

### dropbot_tools_menu

Receiving: (Via handlers)
- SELF_TESTS_PROGRESS "dropbot/signals/self_tests_progress"
- SELF_TESTS_RESULTS "dropbot/signals/self_tests_results" (handled in `microdrop_application/task.py`, not this plugin — see Detailed Flows)

Sending: (Via publish_message)
- TEST_VOLTAGE "dropbot/requests/test_voltage" (menus.py:78)
- TEST_ON_BOARD_FEEDBACK_CALIBRATION "dropbot/requests/test_on_board_feedback_calibration"
- TEST_SHORTS "dropbot/requests/test_shorts"
- TEST_CHANNELS "dropbot/requests/test_channels"
- RUN_ALL_TESTS "dropbot/requests/run_all_tests"
- START_DEVICE_MONITORING "dropbot/requests/start_device_monitoring" 

### manual_controls

Sending: (Via publish_message)
- SET_VOLTAGE "dropbot/requests/set_voltage"
- SET_FREQUENCY "dropbot/requests/set_frequency"

### dropbot_status

Receiving: (Via handlers)
- SHORTS_DETECTED "dropbot/signals/shorts_detected"
- CAPACITANCE_UPDATED "dropbot/signals/capacitance_updated"
- DISCONNECTED "dropbot/signals/disconnected"
- CHIP_NOT_INSERTED "dropbot/signals/chip_not_inserted"
- CHIP_INSERTED "dropbot/signals/chip_inserted"
- NO_POWER "dropbot/signals/warnings/no_power"

There is also a handler for "dropbot/signals/warnings/*" called _on_show_warning_triggered (in widget.py) that is assigned in dramatiq_dropbot_status_controller.py

### device_viewer

Receiving: (Via handlers)
- SETUP_SUCCESS "dropbot/signals/setup_success"
- PHASE_NAVIGATION_MODE "ui/phase_navigation_mode" (** also self-published)
- PHASE_NAVIGATION_REQUEST "ui/device_viewer/phase_navigation_request"

Sending: (Via publish_method)
- ELECTRODES_STATE_CHANGE "dropbot/requests/electrodes_state_change"
- START_DEVICE_MONITORING "dropbot/requests/start_device_monitoring"
- DEVICE_VIEWER_STATE_CHANGED "ui/device_viewer/state_changed"
- STEP_PARAMS_COMMIT "ui/device_viewer/step_params_commit"
- ** PHASE_NAVIGATION_MODE "ui/phase_navigation_mode"
- PHASE_NAVIGATION_STATE "ui/device_viewer/phase_navigation_state" (via route_execution_service)

---

## Detailed Flows

Deeper references for message flows whose payloads or plumbing are non-obvious from the topic list alone. Add a new subsection here whenever you find yourself reverse-engineering a flow.

### Device Viewer → Protocol Grid: routes / state sync

The device viewer pushes its full UI state (routes, free-mode electrode state, colors) to the protocol grid so the grid can turn user-drawn electrode paths into protocol steps. One topic carries the whole serialized model.

**Topic**
- `DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"` — defined in `protocol_grid/consts.py:25`.

**Publisher side (device_viewer)**
- `device_viewer/views/device_view_dock_pane.py:408` — `publish_message.send(topic=DEVICE_VIEWER_STATE_CHANGED, message=self.message_buffer)`.
- Triggered reactively by the Traits observer at `device_view_dock_pane.py:1024-1048` (`@observe("model.routes.layers.items.route.route.items")`), which serializes the UI model and calls `publish_model_message()` at line 1047.
- Payload is assembled in `device_viewer/utils/message_utils.py:4-20` via `gui_models_to_message_model()` — routes are extracted as `[(layer.route.route, layer.color) for layer in model.routes.layers]`.

**Payload schema**
- Pydantic `DeviceViewerMessageModel` at `device_viewer/models/messages.py:5-61`.
- Key field: `routes: list[tuple[list[str], str]]` — each entry is `(electrode_id_list, color_string)`.
- Serialized with `.serialize()` (JSON) and rebuilt with `.deserialize()` on the receiving side.

**Subscriber side (protocol_grid)**
- `protocol_grid/services/message_listener.py:52-54` — `_on_device_viewer_message_received()` handles the topic, deserializes, and re-emits a Qt signal `device_viewer_message_received` for UI consumption.

### Device Viewer → protocol widgets: step execution params commit

Separate topic used only when the user explicitly commits the sidebar
execution parameters back to the selected protocol step. Distinct from the
live route sync so step cells only mutate on deliberate user action.

**Topic**
- `STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"` — canonical home `device_viewer/consts.py` (the DV publishes it); `protocol_grid/consts.py` keeps a duplicated literal until PPT-9.

**Publisher side (device_viewer)**
- `device_viewer/views/device_view_dock_pane.py` — `_on_commit_to_step_btn_fired` builds a `StepParamsCommitMessage` and publishes via `publish_message.send(topic=STEP_PARAMS_COMMIT, ...)`; the step-transition Commit/Discard/Cancel prompt (`_apply_step_transition`) publishes the same message on "Commit".
- Triggered by the Traits Button `commit_to_step_btn` on `RouteLayerManager`; enabled only when the sidebar values diverge from the committed baseline.

**Payload schema**
- Pydantic `StepParamsCommitMessage` at `device_viewer/models/step_params_commit.py` (canonical; `protocol_grid/models/step_params_commit.py` is the legacy copy).
- Fields: `step_id, duration, repetitions, repeat_duration, trail_length, trail_overlay, soft_start, soft_terminate, linear_repeats`.

**Subscriber side (protocol_grid, legacy)**
- `protocol_grid/services/message_listener.py` — `listener_actor_routine` branches on `STEP_PARAMS_COMMIT`, deserializes, emits `step_params_commit_received`.
- `protocol_grid/widget.py` — `_on_step_params_commit` finds the step by UID and writes the cell values.

**Subscriber side (pluggable_protocol_tree)**
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_on_step_params_commit_qt` finds the row by uuid and writes the mapped columns (`repetitions` → `route_repetitions`, `soft_terminate` → `soft_end`, rest 1:1), firing `cell_changed` per column for dirty tracking. Of the Route Reps / Route Reps Dur pair only the row's controlling knob (per `repeat_duration_controls`) is written — the pane reconciliation derives the other. It then re-publishes `PROTOCOL_TREE_DISPLAY_STATE` for the selected row so the DV rebaselines on the post-reconciliation values.

**Companion addition (pull direction)**
- The grid → DV publish on `PROTOCOL_GRID_DISPLAY_STATE` carries the target step's params in `DeviceViewerMessageModel.execution_params`; the tree → DV publish on `PROTOCOL_TREE_DISPLAY_STATE` carries the same dict in `ProtocolTreeDisplayMessage.execution_params` (None in free mode → commit button disabled). The DV applies them on `step_id` transition (`device_view_dock_pane._apply_step_transition`), then baselines the sidebar for dirty tracking; a same-step refresh carrying params re-applies + rebaselines silently when no protocol is running.
- The tree publishes that same-step refresh in two cases: the post-commit echo (above), and any tree-originated edit to an execution-param cell on the selected step (`_republish_on_param_cell_change`, gated on `DV_EXECUTION_PARAM_COL_IDS`) — protocol values supersede the sidebar, including uncommitted sidebar edits.

### Device Viewer ↔ Protocol Tree: idle phase navigation (#493)

Opt-in mode letting the user step through a route's phases without running the protocol. Three topics: a shared mode toggle synced between both UIs, a request the tree sends to move the DV's position, and a state echo the DV sends back to drive the tree's own controls.

**Topics**
- `PHASE_NAVIGATION_MODE = "ui/phase_navigation_mode"` — defined in `device_viewer/consts.py`. Payload `"True"`/`"False"`.
- `PHASE_NAVIGATION_REQUEST = "ui/device_viewer/phase_navigation_request"` — defined in `device_viewer/consts.py`. JSON `{"action": "prev" | "next" | "goto", "index": <int, goto only>}`.
- `PHASE_NAVIGATION_STATE = "ui/device_viewer/phase_navigation_state"` — defined in `device_viewer/consts.py`. JSON `{"phase_index": <0-based int>, "phase_total": <int>}` (`phase_total` 0 = no plan).

**Publisher/subscriber side (device_viewer)**
- `device_viewer/views/device_view_dock_pane.py` — `_publish_phase_navigation_mode` sends `PHASE_NAVIGATION_MODE` when the sidebar checkbox is toggled; `_on_phase_navigation_mode_triggered` applies the tree's toggle (and any external `"False"`, e.g. force-exit on protocol run start); `_on_phase_navigation_request_triggered` applies an incoming `PHASE_NAVIGATION_REQUEST` via `RouteExecutionService`. Both handlers are registered on the DV's `ACTOR_TOPIC_DICT` listener.
- `device_viewer/services/route_execution_service.py` — `_publish_phase_nav_state` sends `PHASE_NAVIGATION_STATE` whenever the idle-nav position or plan size changes (including the no-plan `phase_total=0` case).

**Publisher/subscriber side (pluggable_protocol_tree)**
- `pluggable_protocol_tree/views/dock_pane.py` — `_on_phase_nav_check_toggled` publishes `PHASE_NAVIGATION_MODE` when the tree's "Phase navigation" checkbox is ticked; `_publish_phase_nav_request` sends `PHASE_NAVIGATION_REQUEST` from the nav-bar Prev/Next buttons and the timeline's phase track.
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_listener_routine` branches on `PHASE_NAVIGATION_MODE` (mirrors the checkbox) and `PHASE_NAVIGATION_STATE` (drives the timeline/button enablement); subscriptions declared in `pluggable_protocol_tree/consts.py` alongside `device_viewer/consts.py`'s `ACTOR_TOPIC_DICT` entries.

**Notes**
- `PHASE_NAVIGATION_MODE` is published by whichever UI the user toggled and consumed by both (applying an equal value is a trait no-op, so the echo is harmless).
- Mode is force-exited (`PHASE_NAVIGATION_MODE` published `"False"`) when a protocol run starts; the paused-run phase-seeking flow (#471) is untouched and gated separately.

### Backend → Microdrop task: shorts detected

One topic carries both the spontaneous hardware shorts signal and the answer to an explicit user check, so the payload has to say which one it is: an empty channel list means "no shorts", and only the publisher knows whether the user is waiting to hear that.

**Topic**
- `SHORTS_DETECTED = "dropbot/signals/shorts_detected"` — defined in `dropbot_controller/consts.py`.

**Payload schema**
- Pydantic `ShortsDetectedSignal` at `dropbot_controller/models/shorts.py`.
- Fields: `shorted_channels: list[int]` (empty means none found), `show_window: bool` (force a dialog even with no shorts).
- Published through the `shorts_detected_publisher` singleton in `dropbot_controller/consts.py` — never hand-rolled `json.dumps`.

**Publisher side (dropbot_controller)**
- `dropbot_controller_base._shorts_detected_wrapper` — the proxy's `shorts-detected` signal; `show_window=False`, nobody asked, so no shorts means stay silent.
- `dropbot_controller_base.on_detect_shorts_request` and `services/dropbot_self_tests_mixin_service` (the `test_shorts` branch) — both answer an explicit user request, so `show_window=True`.
- `mock_dropbot_controller/mock_controller.py` mirrors both cases (`on_detect_shorts_request`, `simulate_shorts`).

**Subscriber side (microdrop_application)**
- `task._on_shorts_detected_triggered` validates the payload and hands off to the UI thread.
- `task._on_shorts_detected_dialog`: with shorts → a `confirm` offering to keep the channels enabled; declining publishes them via `disabled_channels_changed_publisher`. Without shorts → the "No Shorts Detected" info dialog, unconditionally when `show_window` is set, otherwise only when the `suppress_no_shorts_information` preference is unset (that dialog carries the "do not show again" checkbox which writes the preference).

### Backend → Microdrop task: self-test results dialog (#611)

`dropbot_self_tests_mixin_service` (backend, must stay Qt-free) used to
import `ResultsDialogAction` from `dropbot_tools_menu` directly and show the
dialog itself, later rendering a plot to a PNG on disk instead. It now
writes the test's *raw* results to a JSON file and publishes only the file
path; the frontend (`microdrop_application/task.py`, the same place that
already owns the progress dialog) subscribes, loads the file, and renders it
interactively with the same `dropbot.self_test.plot_*` helpers on a
matplotlib canvas — so the user can zoom, pan, rescale and save. Two of the
three plotted tests carry 2-D capacitance matrices plus scalars, which one
self-describing JSON file holds more naturally than CSV, and keeping the
raw arrays out of the message keeps the payload itself small; the file is
written next to the test's HTML report directory, so it is also available
for later analysis.

**Topic**
- `SELF_TESTS_RESULTS = "dropbot/signals/self_tests_results"` — defined in `dropbot_controller/consts.py`.

**Payload schema**
- Pydantic `SelfTestResultsSignal` at `dropbot_controller/models/self_tests.py`.
- Fields: `test_name: str`, `title: str`, `results_path: str` (absolute path to a JSON file holding the test's raw result dict), `failed_channels: list[int] | None` (only set for `test_channels`).
- Published through the `self_test_results_publisher` singleton in `dropbot_controller/consts.py` — never hand-rolled `json.dumps`.
- `serialise_test_results` / `restore_test_results` (also in `models/self_tests.py`) are the write/read halves of the JSON file format: `numpy` arrays/scalars recursively become JSON-native lists/scalars on write, and list-valued fields become `numpy` arrays again on read. `load_self_test_results(results_path)` combines the read + restore + error handling and is the one function both the results dialog and its tests call.

**Publisher side (dropbot_controller)**
- `services/dropbot_self_tests_mixin_service.py` (`_execute_test_based_on_name`) — after a single test (`test_voltage`, `test_on_board_feedback_calibration`, `test_channels`) finishes, its raw result dict is serialised with `serialise_test_results` and written to a timestamped JSON file next to the test's report directory (`get_timestamped_results_path(...).with_suffix(".json")`); the path (not the data) is published. The backend never calls `dropbot.self_test.plot_*` or imports matplotlib. `test_shorts` and `run_all_tests` never publish this topic — they go through `shorts_detected_publisher` / the full HTML report respectively.

**Subscriber side (microdrop_application, via dropbot_tools_menu's `ACTOR_TOPIC_DICT`)**
- `dropbot_tools_menu/consts.py` routes `SELF_TESTS_RESULTS` to `{microdrop_application_PKG}_listener`, same mechanism already used for `SELF_TESTS_PROGRESS`.
- `task.py` — `_on_self_tests_results_triggered` validates the payload and, via `GUI.invoke_later`, builds a `dropbot_tools_menu.self_test_dialogs.ResultsDialogAction` and calls `.perform(self, title=..., test_name=..., results_path=..., failed_channels=...)`.
- `ResultsDialog` loads the file via `load_self_test_results` and picks the plot function from `PLOT_FUNCTIONS_BY_TEST_NAME[test_name]`, embedding the returned `Figure` in a live `FigureCanvasQTAgg` with a `NavigationToolbar2QT` above it, in a resizable dialog. A missing/unreadable file or unrecognised `test_name` logs and falls back to an empty figure rather than crashing.

### Protocol tree run logging: report data collection + external contributions

Everything a protocol run's HTML report contains flows through one dramatiq listener into a per-run collector. A single active-logger registry gates all of it: `ProtocolLoggingController.start_logging` registers the controller (`listener.set_active_logger`), `stop_logging` clears it, and any message arriving outside a run is dropped silently.

**Listener + routing**
- Actor `protocol_tree_logging_listener` at `pluggable_protocol_tree/services/logging/listener.py` — `route_to_active_logger()` branches on topic and forwards to the active `ProtocolLoggingController` (`services/logging/controller.py`); subscriptions declared in `ACTOR_TOPIC_DICT[LOGGING_LISTENER_NAME]` in `pluggable_protocol_tree/consts.py`.

**Core topics (owned by other plugins, consumed by the logger)**
- `CAPACITANCE_UPDATED` (`dropbot_controller/consts.py`) → one data row per sample, stamped with the current step + actuation phase; capacitance/voltage parsed leniently, force derived from capacitance-per-unit-area.
- `ELECTRODES_STATE_CHANGE` (`electrode_controller/consts.py`) → updates the current actuation context (channels + summed electrode area) stamped onto subsequent capacitance rows.
- `DEVICE_VIEWER_MEDIA_CAPTURED` (`device_viewer/consts.py`) → media bucket for the report's Media Captures section. Note: the camera capture path also caches into `app_globals["media_captures"]` without publishing this topic, so `_flush` additionally drains that bucket.
- `CALIBRATION_DATA` (`device_viewer/consts.py`) → live capacitance-per-unit-area update so the Force column populates mid-run.

**Contribution topics (any plugin → report)**
- `PROTOCOL_LOGGING_METADATA_CONTRIBUTION = "microdrop/protocol_tree/logging/metadata"` and `PROTOCOL_LOGGING_DATA_CONTRIBUTION = "microdrop/protocol_tree/logging/data"` — defined in `pluggable_protocol_tree/consts.py`.
- Payloads are flat scalar-valued JSON objects. Publish through `protocol_logging_metadata_contribution_publisher` / `protocol_logging_data_contribution_publisher` in `pluggable_protocol_tree/consts.py` (RootModel contracts in `pluggable_protocol_tree/models/report_contributions.py` — validated publishers that serialize to the bare object). Subscribers stay lenient: malformed / non-object payloads are ignored, matching the other listener handlers.
- Metadata → `controller.on_metadata_contribution` merges the object into the report's Metadata table (`LoggingIngestion.log_metadata`).
- Data → `controller.on_data_contribution` appends the object as a data row (`LoggingIngestion.log_contributed_data`); `step_idx`/`step_id` are stamped from the currently running step unless the payload carries its own. Numeric columns automatically get a Data Summary row and a per-step Data Trends chart in the report, and every column lands in the persisted `data_<t>.json`/`.csv`.
- Timing: contributions are accepted from `start_logging` until the post-`stop_logging` settling flush, so messages published shortly after the run ends still make the report.
- Demo: `examples/demos/protocol_report_contribution_demo.py` runs the whole pipeline headlessly over redis and prints the generated report path.


### Portable DropBot protocol columns: magnet + heater step execution

The portable's built-in magnet and heater join a protocol through `portable_dropbot_protocol_controls` (one plugin for every portable peripheral, since they all sit behind the one backend). Each column is a PPT-11 compound column: a "set" checkbox gates the step, and a checked step publishes one request and blocks on one ack, mirroring the standalone magnet/heater plugins.

**Topics (all in `portable_dropbot_controller/consts.py`)**
- `PROTOCOL_SET_MAGNET = "portable_dropbot/requests/protocol_set_magnet"` — JSON `{"on": bool, "height_mm": float}`. Ack: `MAGNET_APPLIED = "portable_dropbot/signals/magnet_applied"`.
- `PROTOCOL_SET_TEMPERATURE = "portable_dropbot/requests/protocol_set_temperature"` — JSON `{"channel": int, "target_c": float, "tolerance_c": float}`. Ack: `TEMPERATURE_REACHED = "portable_dropbot/signals/temperature_reached"`.
- `TEMP_CONTROL` (existing) — the temperature handler's `on_post_protocol_end` publishes `{"channel": DEFAULT_TEMP_CHANNEL, "on": False}` after every run so nothing keeps heating unattended.

**Frontend (handlers in `portable_dropbot_protocol_controls/protocol_columns/`)**
- `MagnetHandler` / `TemperatureHandler` run at priority 20 (with voltage/frequency, before routes). Unchecked steps and preview mode publish nothing and wait for nothing. `ctx.wait_for(<ack>, timeout=self.ack_time_s)` uses the Protocol Settings ack-wait grid value (0 = fire-and-forget); provider defaults are 40 s for the magnet (the driver's engage/disengage blocks up to 30 s) and 120 s for the heater.
- A magnet height below `MAGNET_HEIGHT_MM_BOUNDS[0]` is the "Default" sentinel: the spinbox shows "Default" and the backend runs the firmware engage macro; any other height is an absolute position on the magnet Z motor.

**Backend (`portable_dropbot_controller/services/`)**
- `on_protocol_set_magnet_request` (motors mixin) — disengage / engage macro / `motorAbsoluteMove` on the magnet motor (mm × 1000 µm), then publishes `MAGNET_APPLIED` only on success — a failed move leaves the step to time out — and republishes the status snapshot.
- `on_protocol_set_temperature_request` (temp mixin) — sets the channel target and turns control on, then arms a watcher thread that polls the channel every `TEMP_REACHED_POLL_INTERVAL_S` (republishing `TEMP_UPDATED` so the pane keeps tracking) and publishes `TEMPERATURE_REACHED` once `|current - target| <= tolerance`; it gives up after `TEMP_REACHED_TIMEOUT_S`. A new request cancels the previous watcher.

### Voltage/frequency range preferences: app_globals owner-publishes (#610)

`dropbot_status_and_controls` used to reach into `dropbot_preferences_ui` directly (`from dropbot_preferences_ui.models import VoltageFrequencyRangePreferences`) to read the voltage/frequency spinner bounds and to persist the last-applied values. #610 replaced that with the app_globals owner-publishes pattern already used for hardware limits in `dropbot_controller/preferences.py`.

**app_globals keys (constants in `dropbot_preferences_ui/consts.py`)**
- `UI_MIN_VOLTAGE_KEY = "ui_min_voltage"`, `UI_MAX_VOLTAGE_KEY = "ui_max_voltage"`, `UI_DEFAULT_VOLTAGE_KEY = "ui_default_voltage"`
- `UI_MIN_FREQUENCY_KEY = "ui_min_frequency"`, `UI_MAX_FREQUENCY_KEY = "ui_max_frequency"`, `UI_DEFAULT_FREQUENCY_KEY = "ui_default_frequency"`
- Each key name doubles as the corresponding trait name on `VoltageFrequencyRangePreferences`.

**Owner (dropbot_preferences_ui)**
- `VoltageFrequencyRangePreferences.traits_init()` (`models.py`) seeds any key not already in app_globals from its own (ETS-persisted) trait value.
- `VoltageFrequencyRangePreferences._publish_to_app_globals()` — `@observe` on all six range/default traits — mirrors every change (from the preferences pane, or from any ad hoc instance such as `manual_controls/MVC.py`'s) into app_globals as `app_globals[event.name] = event.new`.
- The existing `VOLTAGE_FREQUENCY_RANGE_CHANGED` topic (min/max only) is unchanged — it still drives the live QSpinBox bound updates in `dropbot_status_and_controls/dock_pane.py`.

**Reader (dropbot_status_and_controls)**
- `model.py`'s `voltage`/`frequency` `RangeWithSteppedSpinViewHint` traits read their initial bounds/default from `app_globals.get(<key>, <UI_DEFAULT_* fallback>)` instead of instantiating `VoltageFrequencyRangePreferences`.

**Writer (dropbot_status_and_controls) — persists across restarts**
- `_update_prefs()` does not touch app_globals. It writes the last-applied voltage/frequency straight into the ETS preferences node by path — `get_default_preferences().set(f"{VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH}.ui_default_{voltage|frequency}", value)` — using `VOLTAGE_FREQUENCY_RANGE_PREFERENCES_PATH = "microdrop.ui.voltage_frequency_range"` (a new constant in `dropbot_preferences_ui/consts.py`; `VoltageFrequencyRangePreferences.preferences_path` now reuses the same constant instead of a duplicate literal).
- This works because `envisage.application.Application.__init__` installs the running app's own `ScopedPreferences` node as apptools' package-global default (`set_default_preferences(self.preferences)`) before any plugin constructs a `PreferencesHelper`, and `PreferencesHelper._preferences_default()` returns that same default — so `get_default_preferences()` here and any `VoltageFrequencyRangePreferences()` instance's `self.preferences` are the identical node. Verified interactively: writing by path updates a live `VoltageFrequencyRangePreferences` instance's trait (via its `preferences.add_preferences_listener` callback), which fires `_publish_to_app_globals` and keeps app_globals in sync — `dropbot_status_and_controls` remains the only writer of `ui_default_voltage`/`ui_default_frequency` in app_globals, it just triggers that write indirectly through the ETS node rather than writing app_globals itself. A fresh `VoltageFrequencyRangePreferences()` instance (e.g. after a full app + Redis restart) reads the same persisted value straight from the ETS-backed `preferences.ini`, so the last-applied value survives restarts exactly as it did before #610.
