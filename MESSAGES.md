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
- `DEVICE_VIEWER_MEDIA_CAPTURED` (`device_viewer/consts.py`) → media bucket for the report's Media Captures section. Since #695 the camera capture path publishes this topic live on every capture (carrying the requester's `request_id`, if any), closing the earlier gap where only `app_globals["media_captures"]` was written; `_flush` still drains that bucket at run end for anything captured outside a run, and `LoggingIngestion.log_media` dedupes by path so a capture is never listed twice.
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

### Portable DropBot PMT capture, live stream, ADC query, buffered acquire (#601)

The PMT Capture pane (`portable_dropbot_status_and_controls`) and the PMT mixin (`portable_dropbot_controller/services/portable_dropbot_pmt_mixin_service.py`) talk over validated topics; the Pydantic contracts and publishers live in `portable_dropbot_controller/consts.py`. Three sessions — the multi-spot capture, the live stream, and the buffered acquire — share the tube and the ADC and so share one claim in the backend: `_pmt_claim` guards the check-and-set of `_pmt_capturing` / `_pmt_streaming` / `_pmt_acquiring`, and a request for a different session while one is running is refused with a reason naming which one ("a PMT capture is running", "the live stream is running", "a buffered acquire is running"). A `PMT_STREAM_START` received while the stream is already running is not a new session — it is a live avg/osr/gain update, handled before the claim is even consulted, so it never restarts the stream or drops a sample.

**Spot table**
- On `PORTABLE_DROPBOT_CONNECTED` (and the pane's Refresh button) the pane publishes `PMT_SPOTS_READ = "portable_dropbot/requests/pmt_spots_read"` (empty message).
- The backend reads the motor board's `pmt_defaults` flash parameter (one int32 Y position in µm per motor location 1–6; location 1 is park and never offered, so spot `slot` n is `pmt_ctrl` location n + 1) and publishes `PMT_SPOTS_UPDATED = "portable_dropbot/signals/pmt_spots_updated"` — `PmtSpotsUpdated {spots: [{slot, position_um}]}`, non-zero slots only. The pane merges it into its rows by slot, keeping the operator's tick/gain/exposure and order. A future add/remove-spot feature only has to republish this topic.

**ADC query**
- The pane publishes `PMT_ADC_QUERY = "portable_dropbot/requests/pmt_adc_query"` (empty message) on connect, so the pane's conversion (counts -> volts -> amps) has a real full scale before the operator does anything.
- The backend calls `SignalBoardProxy.spi_adc_diag()`, which shares the ADC bus with every session, so the request is refused (an error `PmtAdcUpdated` with `full_scale: 0`) while a capture/stream/acquire is running. On a reply it publishes `PMT_ADC_UPDATED = "portable_dropbot/signals/pmt_adc_updated"` — `PmtAdcUpdated {adc_type, name, full_scale, error}` — `adc_type` 0 is "none" (`full_scale: 0`), an unrecognized code is `"unknown (N)"` (`full_scale: 0`), and a code the backend knows (1 = ADC128S052/4096, 2 = ADS7076/65536) updates the backend's remembered full scale; an unknown/none reading never overwrites it. Each of the three sessions calls the same query for itself at its own start, before power-on, and stamps its own CSV meta with whatever full scale that answered.

**Capture routine**
- Start publishes `PMT_CAPTURE = "portable_dropbot/requests/pmt_capture"` — `PmtCaptureRequest {entries: [{slot, gain, exposure_s}], avg, osr, rf_ohms}` (the last three inherited from `PmtStreamSettings`, defaulting to `PMT_STREAM_AVG`/`PMT_STREAM_OSR`/`PMT_RF_OHMS`), ticked rows in table order.
- The backend runs the routine on a daemon thread (the actor's time limit would otherwise interrupt a long capture): ADC query, fluorescence LED off, PMT power on, then per entry move (`MotorBoardProxy.pmt_ctrl`), gain, `SignalBoardProxy.pmt_stream(1, request.avg, request.osr)` for `exposure_s` while a `uart.subscribe(CMD_PMT_STREAM_DATA)` callback assembles the frames, stream stop, CSV to `<experiment>/captures/pmt/pmt_spot<slot>_<stamp>_gain<g>.csv` (the queried `adc_full_scale`, `request.avg`/`osr`/`rf_ohms` in its meta). Each stage publishes `PMT_CAPTURE_PROGRESS = "portable_dropbot/signals/pmt_capture_progress"` (`PmtCaptureProgress {index, total, slot, stage, detail, exposure_s}`; stages move/gain/stream/saved/failed; `exposure_s` is set on the stream stage so the pane counts the exposure down on its status line and highlights that spot's row). The proxy lock is taken per command so `STATUS_UPDATED` keeps flowing during a long exposure.
- Teardown always runs: stream stop, power off (an unanswered power-off is logged at error level), light setpoint restored. Then `PMT_CAPTURE_DONE = "portable_dropbot/signals/pmt_capture_done"` — `PmtCaptureDone {ok, aborted, directory, results: [PmtSpotResult], adc_full_scale, rf_ohms, request_id, label, error}` (`adc_full_scale`/`rf_ohms` are what the CSVs were actually written with, so the pane shows the same current the files carry); a refused request (another session running, nothing ticked) publishes it immediately with `error` set so the pane's Start never sticks.
- `PMT_CAPTURE_ABORT = "portable_dropbot/requests/pmt_capture_abort"` sets an event the routine polls every 50 ms; it finishes the current spot's teardown and reports `aborted=true`.
- `PMT_UPDATED {acquiring: true/false}` brackets the routine so the pane greys the controls that must not run concurrently with it, as for the buffered acquire below.

**Protocol-step captures (#601 increment 2, `portable_dropbot_protocol_controls`'s `pmt_capture` column)** — `PmtCaptureRequest` carries three more optional fields, all defaulted so a pane-initiated request is unaffected:
  - `request_id` (default `""`) is echoed back verbatim on `PmtCaptureDone`, on success AND on every refusal (`_refuse_pmt_capture` takes it as a parameter; a request that fails Pydantic validation still gets it read best-effort off the raw JSON, so even a malformed request's ack can be matched, or `""` if the payload wasn't even readable as JSON). A protocol step's `PmtCaptureHandler` sets it to `f"{row.uuid}:{phase}"` (`phase` is `start` or `end`) and waits on `PMT_CAPTURE_DONE` with a `predicate=` matching that value, so a pane-initiated capture or a stale done from an earlier step can never satisfy its wait — the same pattern the droplet-check column uses with `step_uuid`.
  - `label` (default `""`, filename-safe per `PMT_CAPTURE_LABEL_PATTERN`, max 64 chars) is prefixed onto that request's spot CSVs — `pmt_<label>_spot<n>_<stamp>_gain<g>.csv` instead of `pmt_spot<n>_..._gain<g>.csv` — and written into each CSV's meta alongside `request_id`. A step sets it to a tag like `step1.2-end`.
  - `stop_live_stream` (default `False`): when set AND the running live stream is the ONLY reason the claim would be refused, the backend stops the stream instead of refusing — it sets the stream's stop event and joins its teardown thread (bounded by `PMT_STREAM_PREEMPT_TIMEOUT_S`), logs that the protocol stopped the stream, then retries the claim once. If the stream doesn't finish tearing down in time, or the blocker is a capture/acquire already running (never preempted, only the stream is), the request is refused as usual. A pane's Start leaves this `False`, so a running stream still refuses it exactly as before.

**Live stream**
- Start (or update) publishes `PMT_STREAM_START = "portable_dropbot/requests/pmt_stream_start"` — `PmtStreamRequest {gain, avg, osr, rf_ohms}`. The pane sends this again whenever avg/osr/gain change while already streaming, not just on the first Start — the backend's live-update path applies the new values with no restart and no sample gap.
- A first start claims the session and runs it on a daemon thread with the same opening as the capture routine (ADC query, LED off, power on, `_publish_pmt(power=True)`, gain, `uart.subscribe(CMD_PMT_STREAM_DATA)` before `pmt_stream(1, avg, osr)`), then acks `PMT_STREAM_UPDATED = "portable_dropbot/signals/pmt_stream_updated"` — `PmtStreamUpdated {streaming: true, avg, osr}` — and loops publishing a batch (`{streaming: true, avg, osr, samples, packets}`) every `PMT_STREAM_PUBLISH_INTERVAL_S` (0.25 s) while there is anything to report, until `PMT_STREAM_STOP = "portable_dropbot/requests/pmt_stream_stop"` sets the loop's stop event (a stop with nothing running is a no-op, logged at debug).
- Teardown always runs (stream stop, power off + `_publish_pmt(power=False)`, unsubscribe, light setpoint restored, claim cleared), then a final `PmtStreamUpdated {streaming: false, error}` — `error` is set on a refused start (another session running, or validation failure) or a mid-stream failure (e.g. the proxy disconnecting), empty on a clean stop.

**Buffered acquire**
- Publishes `PMT_ACQUIRE = "portable_dropbot/requests/pmt_acquire"` — `PmtAcquireRequest {gain, rf_ohms}` (the pre-#601 single-acquire payload of just `{"gain": g}` still validates, `rf_ohms` defaulting to `PMT_RF_OHMS`). The pane hosts this button itself now, moved out of More Controls, since the acquire has its own session and CSV rather than sharing the old single-lock macro.
- The backend claims the session and runs it on a daemon thread: ADC query, LED off, power on, gain, then `DropBotUart.pmt_acquire_collect()` — a ~10.3 s onboard buffer fill at 1 kHz followed by ~8 s of packet upload, both blocking. The samples are saved to `<experiment>/captures/pmt/pmt_acquire_<stamp>_gain<g>.csv` (same folder as the capture routine) with meta including `sample_rate_hz`, the queried `adc_type`/`adc_full_scale`, `vref_v`, `rf_ohms`, board UIDs, and the collector's packet/missing/aborted/busy/error fields.
- Teardown always powers off (`_publish_pmt(power=False)`, an unanswered power-off logged at error level) and restores the light setpoint — a deliberate change from the old single-acquire macro, which left the tube powered. Then `PMT_ACQUIRE_DONE = "portable_dropbot/signals/pmt_acquire_done"` — `PmtAcquireDone {ok, gain, n_samples, mean_counts, sd_counts, min_counts, max_counts, packets_received, packets_expected, adc_full_scale, rf_ohms, csv_path, error}`; `ok` requires both a complete collect and a written CSV. A refusal (another session running, or a validation failure) publishes it immediately with `error` set and no CSV.

### Portable DropBot fluorescence capture (#695)

Images a chip under fluorescence: per ticked filter-wheel position, move
the wheel, set the LED, set the camera's exposure/focus, grab a still
frame and save it under the experiment's `captures/` folder. Mirrors the
PMT capture feature above — one request topic, one done topic, a
daemon-thread routine in the backend with abort and guaranteed teardown —
except the two camera stages are delegated to `device_viewer` over a
small request/reply seam rather than done in the backend itself, since
the camera lives in the frontend process.

**Topics (`portable_dropbot_controller/consts.py`)**
- `FLUORESCENCE_CAPTURE = "portable_dropbot/requests/fluorescence_capture"` — `FluorescenceCaptureRequest {entries: [{filter_position, led_percent, exposure_ms, focus_distance}], request_id, label, directory}` (`exposure_ms` `null` = the camera's auto exposure, settled `FLUORESCENCE_AUTO_EXPOSURE_SETTLE_S` before the grab instead of `FLUORESCENCE_SETTLE_S`; `directory` empty = current experiment directory; `label` filename-safe per the PMT capture's `PMT_CAPTURE_LABEL_PATTERN`).
- `FLUORESCENCE_CAPTURE_ABORT = "portable_dropbot/requests/fluorescence_capture_abort"` — stops the routine after the current entry's teardown.
- `FLUORESCENCE_CAPTURE_PROGRESS = "portable_dropbot/signals/fluorescence_capture_progress"` — `FluorescenceCaptureProgress {request_id, index, total, filter_position, stage, detail}` (stages `filter`/`led`/`camera`/`frame`/`teardown`).
- `FLUORESCENCE_CAPTURE_DONE = "portable_dropbot/signals/fluorescence_capture_done"` — `FluorescenceCaptureDone {request_id, ok, label, directory, frames, error}`; `frames` are the saved PNGs as `FluorescenceCapturedFrame {filter_position, path}`, capture order.

**Camera seam (`device_viewer/consts.py`)** — the only new cross-plugin surface, since the routine runs in the backend but the camera is a frontend `QCamera`:
- `DEVICE_VIEWER_CAMERA_SET_CONTROLS = "ui/device_viewer/camera/set_controls"` — `CameraControlsRequest {request_id, exposure_ms, hold_auto_exposure, focus_distance}`; either value `None` means auto exposure / continuous auto focus; `hold_auto_exposure=true` leaves auto for manual at the exposure auto last chose (`exposure_ms` ignored). Under GStreamer (Pi) Qt's auto exposure is a no-op, so the camera widget also flips v4l2 `auto_exposure` (3 auto / 1 manual).
- `DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED = "ui/device_viewer/camera/controls_applied"` — `CameraControlsApplied {request_id, ok, exposure_ms, exposure_auto, focus_distance, error}` (`exposure_ms` is the exposure in effect — auto's current pick while `exposure_auto`, when the Qt backend reports it — or `None` when unreported; the Pi's DH Camera never reports auto's pick, its v4l2 `exposure_time_absolute` keeps the last manual value), the camera's readback after applying; a provider feed (no `QCamera`) or an unsupported mode answers `ok=False` with why, rather than raising.
- `DEVICE_VIEWER_MEDIA_CAPTURED` (existing topic, see the Protocol tree run logging section above) is now published live from the capture path itself, carrying the saving request's `request_id` on `MediaCaptureMessageModel`, so the fluorescence routine can match a saved frame to the request that asked for it.

**Backend routine (`portable_dropbot_controller/services/portable_dropbot_fluorescence_mixin_service.py`)**
- Refuses a concurrent request (`ok=False, error="busy"`) while a capture thread is alive; no guard against a concurrent PMT capture — the firmware itself darkens the fluorescence LED for PMT reads and restores it, and both panes grey out while a protocol runs.
- Per entry, in order, each stage publishing `FLUORESCENCE_CAPTURE_PROGRESS` and checking an abort `Event` first: **filter** (`proxy.motor.fluorescence_ctrl(pos)`, up to 60 s), **led** (`proxy.sig.fluorescence_ctrl(raw)`), **camera** (publish a `CameraControlsRequest` tagged `f"{request_id}:{index}"` and wait up to `FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S` for the matching `CameraControlsApplied`, then settle `FLUORESCENCE_SETTLE_S`), **frame** (publish `DEVICE_VIEWER_SCREEN_CAPTURE` with the same request id and wait up to `FLUORESCENCE_FRAME_TIMEOUT_S` for the matching `DEVICE_VIEWER_MEDIA_CAPTURED`, appending its path with the entry's filter position as a frame).
- Teardown always runs two independent steps: restore the LED to the controller's current light intensity, and reset the camera to auto exposure/focus (fire-and-forget, no wait). Then `FLUORESCENCE_CAPTURE_DONE` with the frames collected so far — `ok=False` and `error` set on a filter alarm, a camera refusal, a wait timeout, or an abort (`error="aborted"`).
- `FLUORESCENCE_CAPTURE_ABORT` and `PORTABLE_DROPBOT_DISCONNECTED` both set the routine's abort event; every wait returns early on it.

**Pane (`portable_dropbot_status_and_controls`, "Fluorescence Capture" dock pane)** — one row per `FILTER_POSITIONS` entry (capture tick, LED %, auto exposure, exposure ms, start/end ticks; no focus control — the Pi's camera has no software focus, so entries always carry `focus_distance: null`). Start publishes `FLUORESCENCE_CAPTURE` with `request_id=uuid4()`, `label="manual"`; Abort publishes `FLUORESCENCE_CAPTURE_ABORT`. Attaching to the selected protocol row writes the step's cell over `PROTOCOL_TREE_SET_CELL`, mirroring the PMT Capture pane.

**Pane Manual controls (same pane, collapsible group)** — each edit applies live (the LED is left to the status pane's Light control): a filter pick publishes `SET_FILTER` (the position as text); an exposure change (while not on auto) or ticking Auto exposure publishes a `CameraControlsRequest` on `DEVICE_VIEWER_CAMERA_SET_CONTROLS` with `request_id="manual"` (`exposure_ms` `None` = auto; `focus_distance` always `None`); unticking it publishes `hold_auto_exposure=true` with `request_id="manual-hold-exposure"` only when the last readback reported auto's pick (that readback's `exposure_ms` then moves the Exposure slider there), else a plain manual request at the slider's value. Capture frame publishes `DEVICE_VIEWER_SCREEN_CAPTURE` `{directory: <experiment dir>, step_description: "flu_manual_f<n>", show_dialog: false, request_id: "manual-<uuid4>"}`. The pane's listener subscribes to `DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED` (any readback, manual or a capture's, shown on its Camera line) and `DEVICE_VIEWER_MEDIA_CAPTURED` (only the file echoing its in-flight `manual-` request id becomes a Results run).

**Protocol-step captures (`portable_dropbot_protocol_controls`'s `fluorescence_capture` column, `FluorescenceCaptureHandler`)** — the same `step_uuid`-style correlation pattern as `pmt_capture`: `on_pre_step` runs entries ticked `at_start`, `on_post_step` those ticked `at_end`, each phase publishing one `FLUORESCENCE_CAPTURE` with `request_id=f"{row.uuid}:{phase}"` and `label` sanitised to `PMT_CAPTURE_LABEL_PATTERN` (e.g. `step1.2-end`), then waiting on `FLUORESCENCE_CAPTURE_DONE` with a `predicate=` matching that `request_id` — a pane-initiated capture or a stale done from an earlier step can never satisfy it. Timeout is `len(entries) * FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S + FLUORESCENCE_STEP_TIMEOUT_MARGIN_S` (no per-entry exposure sum like the PMT column's — the per-entry overhead already covers the filter's up-to-60 s move plus both camera stages); `ack_time_s == 0` on the Protocol Settings grid means fire-and-forget, as for magnet/heater/PMT. `done.ok == False` raises `RuntimeError(done.error)`; an `AbortError` publishes `FLUORESCENCE_CAPTURE_ABORT` before re-raising, and `on_post_protocol_end` publishes it unconditionally (including in preview mode) so an interrupted run never leaves a capture going. The captures folder lands in the report as one metadata row (`{"Fluorescence Captures Folder": done.directory}`); the PNGs themselves reach the report's Media Captures section on their own through the now-live `DEVICE_VIEWER_MEDIA_CAPTURED`, so there is no per-image contribution.

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
