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
- SELF_TESTS_RESULTS "dropbot/signals/self_tests_results" (see Detailed Flows)

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
- DEVICE_VIEWER_VOLUME_ESTIMATE "ui/device_viewer/volume_estimate" (see the droplet readouts flow below)

There is also a handler for "dropbot/signals/warnings/*" called _on_show_warning_triggered (in widget.py) that is assigned in dramatiq_dropbot_status_controller.py

### device_viewer

Receiving: (Via handlers)
- SETUP_SUCCESS "dropbot/signals/setup_success"
- PHASE_NAVIGATION_MODE "ui/phase_navigation_mode" (** also self-published)
- PHASE_NAVIGATION_REQUEST "ui/device_viewer/phase_navigation_request"
- DEVICE_VIEWER_CAMERA_SELECT_SOURCE "ui/device_viewer/camera/select_source" (see the camera source selection flow below)
- DEVICE_VIEWER_CAMERA_APPLY_SETTINGS "ui/device_viewer/camera/apply_settings" (a step's capture setup; see the per-step capture camera settings flow below)
- DISABLED_CHANNELS_CHANGED "hardware/signals/disabled_channels_changed" (replaces the hardware-disabled set only; see the disabled channels flow below)

Sending: (Via publish_method)
- ELECTRODES_STATE_CHANGE "dropbot/requests/electrodes_state_change"
- DETECT_DROPLETS "dropbot/requests/detect_droplets" (Find Liquid: the device's channels minus every disabled one; nothing when all are disabled)
- START_DEVICE_MONITORING "dropbot/requests/start_device_monitoring"
- SET_REALTIME_MODE "hardware/requests/set_realtime_mode" (T shortcut, via keyboard_shortcut_service)
- DEVICE_VIEWER_STATE_CHANGED "ui/device_viewer/state_changed"
- STEP_PARAMS_COMMIT "ui/device_viewer/step_params_commit"
- ** PHASE_NAVIGATION_MODE "ui/phase_navigation_mode"
- PHASE_NAVIGATION_STATE "ui/device_viewer/phase_navigation_state" (via route_execution_service)
- DEVICE_VIEWER_CAMERA_SOURCE_SELECTED "ui/device_viewer/camera/source_selected" (reply to select_source)
- DEVICE_VIEWER_CAMERA_STATE "ui/device_viewer/camera/state" (camera selection / on-off, on every change)
- DEVICE_VIEWER_CAMERA_SETTINGS "ui/device_viewer/camera/settings" (capture setup snapshot, on user edits and source selection)
- DEVICE_VIEWER_CAMERA_SETTINGS_APPLIED "ui/device_viewer/camera/settings_applied" (reply to apply_settings)
- DEVICE_VIEWER_VOLUME_ESTIMATE "ui/device_viewer/volume_estimate" (live volume readout, on changes above reading noise)

### image_viewer

Receiving: (Via handlers, image_viewer/message_handler.py)
- PROTOCOL_RUNNING "microdrop/protocol_running" — sets the ROI analysis model's `protocol_running` on the GUI thread: Calculate/Export/AI Detect/Track ask before starting, the ROI batch computes at most 2 images at once, and a draw/edit holds the view (no auto-follow, no refit)

### notifications

Receiving: (Via handlers, notifications/controllers/message_handler.py)
- NOTIFICATION_POST "ui/notifications/post" — any plugin posts a notification (`NotificationMessage`, via `notification_publisher`); see the notifications flow below
- NOTIFICATIONS_SHOW_PANEL "ui/notifications/show_panel" — open the notifications drawer (floating, bottom right, over the panes), expanding a section if `section_id` names one, the drawer's own `notifications.attention` / `notifications.history` included (`ShowNotificationsPanelRequest`, via `show_notifications_panel_publisher`)
- NOTIFICATION_RESOLVE "ui/notifications/resolve" — the condition behind Needs attention cards cleared: every card whose `condition_id` matches leaves Needs attention, read, its buttons replaced by `resolution` (`NotificationResolveRequest`, via `notification_resolve_publisher`)

Sending: (Via a card's buttons)
- the topic and message of a notification's `PublishAction`, as the poster defined them; a `HelpAction` publishes nothing (it opens help in-process, and is disabled while nothing can)

### plugin_management

Sending:
- NOTIFICATIONS_SHOW_PANEL "ui/notifications/show_panel" (`section_id` = `plugin_management.load_status`) when the status-bar plugin loading indicator is clicked and the notifications plugin is loaded; otherwise the indicator opens its own load-status panel

---

## Detailed Flows

Deeper references for message flows whose payloads or plumbing are non-obvious from the topic list alone. Add a new subsection here whenever you find yourself reverse-engineering a flow.

### Device Viewer → Protocol Grid: routes / state sync

The device viewer pushes its full UI state (routes, free-mode electrode state, colors) to the protocol grid so the grid can turn user-drawn electrode paths into protocol steps. One topic carries the whole serialized model.

**Topic**
- `DEVICE_VIEWER_STATE_CHANGED = "ui/device_viewer/state_changed"` — defined in `protocol_grid/consts.py:25`.

**Publisher side (device_viewer)**
- `device_viewer/controllers/device_viewer_publish_controller.py` — `publish_model_message`, `@observe("message_buffer")`, sends `publish_message(topic=DEVICE_VIEWER_STATE_CHANGED, message=self.message_buffer)`.
- Triggered reactively by `model_change_handler_with_message` (`@observe("model.routes.layers.items.route.route.items")` among others, same file), which serializes the UI model into `message_buffer`.
- Payload is assembled in `device_viewer/utils/message_utils.py:4-20` via `gui_models_to_message_model()` — routes are extracted as `[(layer.route.route, layer.color) for layer in model.routes.layers]`.

**Payload schema**
- Pydantic `DeviceViewerMessageModel` at `device_viewer/models/messages.py:5-61`.
- Key field: `routes: list[tuple[list[str], str]]` — each entry is `(electrode_id_list, color_string)`.
- Serialized with `.serialize()` (JSON) and rebuilt with `.deserialize()` on the receiving side.

**Subscriber side (protocol_grid)**
- `protocol_grid/services/message_listener.py:52-54` — `_on_device_viewer_message_received()` handles the topic, deserializes, and re-emits a Qt signal `device_viewer_message_received` for UI consumption.
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_on_dv_state` writes a step-scoped message's electrodes/routes back to the step; when that step is the current row of a multi-selection, the columns it changed are written to every selected step (`write_back_targets`, groups expanded one level), and an unchanged echo writes nothing.

### Device Viewer → protocol widgets: step execution params commit

Separate topic used only when the user explicitly commits the sidebar
execution parameters back to the selected protocol step. Distinct from the
live route sync so step cells only mutate on deliberate user action.

**Topic**
- `STEP_PARAMS_COMMIT = "ui/device_viewer/step_params_commit"` — canonical home `device_viewer/consts.py` (the DV publishes it); `protocol_grid/consts.py` keeps a duplicated literal until PPT-9.

**Publisher side (device_viewer)**
- `device_viewer/views/device_view_dock_pane.py` — `_commit_sidebar_params(step_id)` builds a `StepParamsCommitMessage` and publishes it on `STEP_PARAMS_COMMIT`. Three callers share it: the commit button (`_on_commit_requested`), auto-commit (`_auto_commit_sidebar_params`), and the step-transition Commit/Discard prompt (`_check_unsaved_execution_params`) on "Commit".
- Triggered by the Traits Button `commit_to_step_btn` on `RouteLayerManager`. `DeviceViewMainModel.commit_button_state` decides what a press does: `auto` turns auto-commit off, `pending` (sidebar diverges from the baseline over every field in `STEP_PARAM_NAMES`, `device_viewer/consts.py`) fires `commit_requested`, `idle` turns auto-commit on, and `unavailable` (no step) is disabled.
- Auto-commit (#969, on by default, preference `auto_commit_to_step`): while `DeviceViewMainModel.auto_commit_due` is true (toggle on, step selected, no protocol running, sidebar dirty) a `AUTO_COMMIT_DEBOUNCE_MS` timer restarts on each edit and publishes once edits settle. On a step change, pending edits are committed to the step being left before the new step's values load; loading a step re-baselines and is never committed.

**Payload schema**
- Pydantic `StepParamsCommitMessage` at `device_viewer/models/step_params_commit.py` (canonical; `protocol_grid/models/step_params_commit.py` is the legacy copy).
- Fields: `step_id, duration, repetitions, repeat_duration, trail_length, trail_overlay, soft_start, soft_terminate, linear_repeats`, plus the slug shape (#682) `lane_left, lane_right, lanes_in_out, rotation_lock, recentre` — defaulted (0, 0, True, True, True) so messages from older senders still parse; on the tree side they are the hidden columns of the same ids.

**Subscriber side (protocol_grid, legacy)**
- `protocol_grid/services/message_listener.py` — `listener_actor_routine` branches on `STEP_PARAMS_COMMIT`, deserializes, emits `step_params_commit_received`.
- `protocol_grid/widget.py` — `_on_step_params_commit` finds the step by UID and writes the cell values.

**Subscriber side (pluggable_protocol_tree)**
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_on_step_params_commit_qt` finds the row by uuid and writes the mapped columns (`repetitions` → `route_repetitions`, `soft_terminate` → `soft_end`, rest 1:1), firing `cell_changed` per column for dirty tracking. Of the Route Reps / Route Reps Dur pair only the row's controlling knob (per `repeat_duration_controls`) is written — the pane reconciliation derives the other. It then re-publishes `PROTOCOL_TREE_DISPLAY_STATE` for the selected row so the DV rebaselines on the post-reconciliation values.
- Multi-selection: when the committed step is the current row of a multi-selection, the params the commit changed are written to every selected step (`write_back_targets`), still with one display publish at the end.

**Companion addition (pull direction)**
- The grid → DV publish on `PROTOCOL_GRID_DISPLAY_STATE` carries the target step's params in `DeviceViewerMessageModel.execution_params`; the tree → DV publish on `PROTOCOL_TREE_DISPLAY_STATE` carries the same dict in `ProtocolTreeDisplayMessage.execution_params` (None in free mode → commit button disabled). The DV applies them on `step_id` transition (`device_view_dock_pane._apply_step_transition`), then baselines the sidebar for dirty tracking; a same-step refresh carrying params re-applies + rebaselines silently when no protocol is running.
- The tree publishes that same-step refresh in two cases: the post-commit echo (above), and any tree-originated edit to an execution-param cell on the selected step (`_republish_on_param_cell_change`, gated on `DV_EXECUTION_PARAM_COL_IDS`) — protocol values supersede the sidebar, including uncommitted sidebar edits.

### Device Viewer → Protocol Tree: device geometry for wide paths (#682)

The plan builder lays a slug wider than one electrode out on the device's
lattice, so the tree needs the electrode centroids and the neighbour graph
that only the device viewer has.

**Topic**
- `DEVICE_VIEWER_GEOMETRY_CHANGED` — published once per device change (chip insert, SVG load), change-gated on the electrode-to-channel mapping.

**Payload schema**
- Pydantic `GeometryChangedMessage` at `device_viewer/models/messages.py`.
- Fields: `id_to_channel` (as before) plus optional `centroids` (`id -> (x, y)`) and `neighbours` (`id -> [ids]`), None from publishers that predate the shape.

**Publisher side (device_viewer)**
- `device_viewer/controllers/device_viewer_publish_controller.py` — `_publish_geometry_if_changed` fills the two lattice fields from `Electrodes.svg_model` when a device is loaded.

**Subscriber side (pluggable_protocol_tree)**
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_on_geometry_changed` keeps them on `electrode_centroids` / `electrode_neighbours` and hands them to `services.phase_math.set_device_lattice`, the module-level lattice every phase-math caller reads. A step asking for a wide slug before any lattice is known runs one electrode wide and logs an error.

### Device Viewer → DropBot / Portable DropBot status: droplet readouts

The device viewer turns the live capacitance into a droplet volume, fill and
covered area (`VolumeEstimateModel`); the DropBot and Portable DropBot status
panes show them.

**Capacitance source**
- `CAPACITANCE_UPDATED = "dropbot/signals/capacitance_updated"` feeds `VolumeEstimateModel` (via `DeviceViewerMessageController._on_capacitance_updated_triggered` → `calibration.last_capacitance`). The DropBot publishes it per proxy reading; the Portable DropBot publishes it with every status sample (`PortableDropbotControllerBase._publish_capacitance`: each status poll, every `MONITOR_INTERVAL_S`, or each event-merged status on MCU 1.0.1.33+), with the signal board's `chip_cap` — the actuated electrodes' summed capacitance — and `hv_vol`, and a host monotonic µs counter (mod 2³²) as `instrument_time_us`.

**Topic**
- `DEVICE_VIEWER_VOLUME_ESTIMATE = "ui/device_viewer/volume_estimate"` — defined in `device_viewer/consts.py`; publish through `volume_estimate_publisher`.

**Payload schema**
- Pydantic `VolumeEstimateMessage` at `device_viewer/models/messages.py`: `status_message` ("" when there is an estimate), `volume_ul`, `fill_fraction`, `covered_area_mm2`.

**Publisher side (device_viewer)**
- `device_viewer/controllers/device_viewer_publish_controller.py` — `_publish_volume_estimate` fires on `VolumeEstimateModel.shown_values_updated`: once per readout change, never for capacitance noise under `VOLUME_READOUT_NOISE_UL`.

**Subscriber side (dropbot_status_and_controls, portable_dropbot_status_and_controls)**
- Each pane's message handler — `_on_volume_estimate_triggered` stores the message on `model.volume_estimate`. The readout traits, grid row, dialog and the controller that opens it are shared from `template_status_and_controls/droplet_readouts.py`: the dropdown picks which readout shows, its tooltip and the Droplet Readouts dialog list them all (the DropBot pane adds c_device).

### Device Viewer ↔ Protocol Tree: idle phase navigation (#493)

Opt-in mode letting the user step through a route's phases without running the protocol. Three topics: a shared mode toggle synced between both UIs, a request the tree sends to move the DV's position, and a state echo the DV sends back to drive the tree's own controls.

**Topics**
- `PHASE_NAVIGATION_MODE = "ui/phase_navigation_mode"` — defined in `device_viewer/consts.py`. Payload `"True"`/`"False"`.
- `PHASE_NAVIGATION_REQUEST = "ui/device_viewer/phase_navigation_request"` — defined in `device_viewer/consts.py`. JSON `{"action": "prev" | "next" | "goto", "index": <int, goto only>}`.
- `PHASE_NAVIGATION_STATE = "ui/device_viewer/phase_navigation_state"` — defined in `device_viewer/consts.py`. JSON `{"phase_index": <0-based int>, "phase_total": <int>}` (`phase_total` 0 = no plan).

**Publisher/subscriber side (device_viewer)**
- `device_viewer/controllers/device_viewer_publish_controller.py` — `_publish_phase_navigation_mode` sends `PHASE_NAVIGATION_MODE` when the sidebar checkbox is toggled.
- `device_viewer/controllers/device_viewer_message_controller.py` — `_on_phase_navigation_mode_triggered` applies the tree's toggle (and any external `"False"`, e.g. force-exit on protocol run start) via the pane's `apply_phase_navigation_mode`; `_on_phase_navigation_request_triggered` applies an incoming `PHASE_NAVIGATION_REQUEST` via `RouteExecutionService`. Both handlers are registered on the DV's `ACTOR_TOPIC_DICT` listener.
- `device_viewer/services/route_execution_service.py` — `_publish_phase_nav_state` sends `PHASE_NAVIGATION_STATE` whenever the idle-nav position or plan size changes (including the no-plan `phase_total=0` case).

**Publisher/subscriber side (pluggable_protocol_tree)**
- `pluggable_protocol_tree/views/dock_pane.py` — `_on_phase_nav_check_toggled` publishes `PHASE_NAVIGATION_MODE` when the tree's "Phase navigation" checkbox is ticked; `_publish_phase_nav_request` sends `PHASE_NAVIGATION_REQUEST` from the nav-bar Prev/Next buttons and the timeline's phase track.
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_listener_routine` branches on `PHASE_NAVIGATION_MODE` (mirrors the checkbox) and `PHASE_NAVIGATION_STATE` (drives the timeline/button enablement); subscriptions declared in `pluggable_protocol_tree/consts.py` alongside `device_viewer/consts.py`'s `ACTOR_TOPIC_DICT` entries.

**Notes**
- `PHASE_NAVIGATION_MODE` is published by whichever UI the user toggled and consumed by both (applying an equal value is a trait no-op, so the echo is harmless).
- Mode is force-exited (`PHASE_NAVIGATION_MODE` published `"False"`) when a protocol run starts; the paused-run phase-seeking flow (#471) is untouched and gated separately.

### Protocol Tree → column-owning panes: row selection + cell write-back

Plugin panes that author a protocol column (fluorescence capture chain, PMT, magnet, ...) live-track the tree's selection and write their cell back without reaching into the tree.

**Topics**
- `PROTOCOL_TREE_ROW_SELECTED = "ui/protocol_tree/row_selected"` — defined in `pluggable_protocol_tree/consts.py`; publish through `protocol_tree_row_selected_publisher`.
- `PROTOCOL_TREE_SET_CELL = "ui/protocol_tree/set_cell"` — request; publish through `protocol_tree_set_cell_publisher`.

**Payload schema**
- Pydantic `ProtocolTreeRowSelectedMessage` / `ProtocolTreeSetCellMessage` at `pluggable_protocol_tree/models/cell_sync.py`.
- row_selected: `step_id` (the tree's current row; None for a group or no selection), `group_id`, `cells` (every column's serialized value for `step_id`), and `selected_step_ids` — every selected step row's uuid in tree order, groups excluded. It need not contain `step_id` (Ctrl-click can deselect the current row) and is `[]` from senders that predate the field.
- set_cell: `step_id`, `col_id`, `value` (the column's serialized form), `only_if_set`.

**Publisher side (pluggable_protocol_tree)**
- `pluggable_protocol_tree/services/device_viewer_sync.py` — `_publish_row_selected` broadcasts immediately on any cell edit of the current step (`_republish_on_param_cell_change`) and on a step-params commit; selection changes go through `_schedule_row_selected`, ONE coalesced broadcast one event-loop turn later (a mouse click moves the current index before it updates the selection, so an immediate broadcast would carry the previous selection). A current-row change (`_on_current_changed`, which still publishes `PROTOCOL_TREE_DISPLAY_STATE` immediately) always broadcasts; a selection-only change (`_on_selection_changed`: Ctrl+A, Ctrl-click deselect) is publish-only — no device-viewer redisplay — and skipped when `(step_id, group_id, selected_step_ids)` repeats the last broadcast.
- `_on_set_cell_request` writes one cell (equality-skipped, ignored during a run) through `RowManager.set_value`, so the edit rebroadcasts row_selected only when it targets the current step.

**Subscriber side**
- Column-owning plugin panes (e.g. the fluorescence plugin's `fluorescence_controls_ui`) — load their editor from `cells`; a pane writing to several steps (`selected_step_ids`) sends one set_cell per step and sees one echo, for the current step.

### Disabled channels: user vs hardware

The device viewer keeps two disabled sets on `Electrodes`; `disabled_channels` is their read-only union (click blocking, Find Liquid, the recording overlay). Hardware-disabled channels are drawn red (`ELECTRODE_DISABLED`), user-disabled ones grey (`ELECTRODE_USER_DISABLED`); a channel in both is red, and the electrode tooltip names the kind.

**Hardware-disabled (`hardware_disabled_channels`)**
- `DISABLED_CHANNELS_CHANGED` — `{"channels": [...]}` from the DropBot backend (halt, actuation discrepancy) or `microdrop_application/task.py` (shorts the user declined to keep). `_on_disabled_channels_changed_triggered` replaces the hardware set only (when the `allow_hardware_disables` advanced preference is on); the user set is untouched. The firmware's `disabled_channels_mask` enforces these, so the electrode menu cannot re-enable them (it shows a disabled "Electrode Disabled by Hardware" item).

**User-disabled (`user_disabled_channels`)**
- Set from the electrode context menu: Disable/Enable Electrode, Disable All, and Enable All (clears the user set only). Undoable like other edits.
- `USER_DISABLED_CHANNELS_KEY` (app_globals, owned by `device_viewer`) — sorted channel list, written by the `Electrodes` model at construction, on every device load and on every change of the user set (`user_disabled_channels_mirror` in `device_viewer/consts.py`), so a previous session's list never lingers.
- Every `ELECTRODES_STATE_CHANGE` handler drops these channels before actuating, logging what it dropped: the DropBot (`electrode_controller`; its actuation-discrepancy check compares against the filtered request), the portable, the mock and OpenDrop. Protocol phases and replays of the last request are covered, not only clicks.
- A change of the user set republishes `ELECTRODES_STATE_CHANGE` through `publish_electrode_update` (same realtime/connected/mode gating as a click), after the app_globals write, so a newly disabled actuated channel stops being driven at once and a re-enabled one resumes.
- `DETECT_DROPLETS` — the DropBot and portable backends drop user-disabled channels (the DropBot also its `disabled_channels_mask`); an empty request means "every channel minus the disabled", and a request left empty by the filter replies `{"success": true, "detected_channels": []}` without scanning. The mock answers with its (already filtered) actuated channels.

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

### Backend → DropBot tools menu: self-test results dialog (#611)

`dropbot_self_tests_mixin_service` (backend, must stay Qt-free) used to
import `ResultsDialogAction` from `dropbot_tools_menu` directly and show the
dialog itself, later rendering a plot to a PNG on disk instead. It now
writes the test's *raw* results to a JSON file and publishes only the file
path; the frontend (`dropbot_tools_menu`, the same place that already owns
the progress dialog) subscribes, loads the file, and renders it
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

**Subscriber side (dropbot_tools_menu)**
- `dropbot_tools_menu/consts.py` routes `SELF_TESTS_PROGRESS` and `SELF_TESTS_RESULTS` to the plugin's own `dropbot_tools_menu_listener`; the core `microdrop_application` task no longer knows about self-tests (#674).
- `plugin.py` forwards both topics to `self_test_dialogs_controller.SelfTestDialogsController`: progress drives the `WaitForTestDialogAction`; `on_self_tests_results` validates the payload (`SelfTestResultsSignal`, imported from `dropbot_controller.consts`) and, via `GUI.invoke_later`, builds a `ResultsDialogAction` parented to the active task window and calls `.perform(task, title=..., test_name=..., results_path=..., failed_channels=...)`.
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

**app_globals (read at run start)**
- `DIELECTRIC_MATERIAL_KEY = "dropbot.dielectric_material"` (`dropbot_status_and_controls/consts.py`) — written by `dropbot_status_and_controls/controller.py:_publish_dielectric_material` at startup and on every dielectric pick; read by `LoggingDeviceContext` (`services/logging/models.py`), which looks the name up in `DIELECTRIC_MATERIALS` for the report's Dielectric Material / Dielectric Constant metadata and the per-row `Dielectric Thickness (um)` column.
- `FILLER_CAPACITANCE_KEY = "filler_capacitance_over_area"` (`device_viewer/consts.py`, pF/mm^2) — written by `device_viewer/models/calibration.py`; read by `LoggingDeviceContext` as the run-start filler that `Dielectric Thickness (um)` subtracts, and shown as the Filler Capacitance Over Area metadata row. Live changes arrive through `CALIBRATION_DATA` (`controller.on_calibration`).

**Contribution topics (any plugin → report)**
- `PROTOCOL_LOGGING_METADATA_CONTRIBUTION = "microdrop/protocol_tree/logging/metadata"` and `PROTOCOL_LOGGING_DATA_CONTRIBUTION = "microdrop/protocol_tree/logging/data"` — defined in `pluggable_protocol_tree/consts.py`.
- Payloads are flat scalar-valued JSON objects. Publish through `protocol_logging_metadata_contribution_publisher` / `protocol_logging_data_contribution_publisher` in `pluggable_protocol_tree/consts.py` (RootModel contracts in `pluggable_protocol_tree/models/report_contributions.py` — validated publishers that serialize to the bare object). Subscribers stay lenient: malformed / non-object payloads are ignored, matching the other listener handlers.
- Metadata → `controller.on_metadata_contribution` merges the object into the report's Metadata table (`LoggingIngestion.log_metadata`).
- Data → `controller.on_data_contribution` appends the object as a data row (`LoggingIngestion.log_contributed_data`); `step_idx`/`step_id` are stamped from the currently running step unless the payload carries its own. Numeric columns automatically get a Data Summary row and a per-step Data Trends chart in the report, and every column lands in the persisted `data_<t>.json`/`.csv`.
- Timing: contributions are accepted from `start_logging` until the post-`stop_logging` settling flush, so messages published shortly after the run ends still make the report.
- Demo: `examples/demos/protocol_report_contribution_demo.py` runs the whole pipeline headlessly over redis and prints the generated report path.


### Portable DropBot chip tray: tray-only move vs the pogo pushpad macro

Two ways to move the chip tray, one topic. The firmware's eject/insert macro releases the pogo pushpads before the tray moves and presses them after; the tray-only move leaves the pushpads where they are (the firmware still drops the magnet out of the way, as a safety interlock, either way).

**Topic (`portable_dropbot_controller/consts/`)**
- `MOVE_TRAY = "portable_dropbot/requests/move_tray"` — `MoveTrayRequest {direction: "in" | "out" | "toggle", actuate_pogos: bool = true}`, published through `move_tray_publisher`. A legacy bare string `"in"` / `"out"` / `"toggle"` is still accepted and means `actuate_pogos: true`. `"toggle"` moves the tray opposite to the cabin state the motor STATUS reports (byte 1: 0 = in, 1 = out).

**Senders (`portable_dropbot_status_and_controls`)**
- Status pane tray glyph (`tray_out` toggle under the device picture) → `{direction: "in" | "out", actuate_pogos: false}`.
- Status pane device picture click (`tray_toggle_clicked`, only while connected) → `{direction: "toggle", actuate_pogos: true}`.
- Motors pane tray In/Out macros → `{direction: "in" | "out", actuate_pogos: not tray_only}`; the `tray_only` checkbox shows only while the target motor is the tray, and is not persisted.

**Backend (`portable_dropbot_controller/services/portable_dropbot_motors_mixin_service.py`)**
- `on_move_tray_request` parses the message (`parse_move_tray_request`; an unknown direction is logged and ignored), resolves `"toggle"` from the motor STATUS cabin byte (0 in → out, 1 out → in; the magnet view position, moving and FAULT are logged and ignored), then sends one `proxy.motor.chip_cabin_ctrl(TRAY_ACTION_CODES[direction], flags)` as the vendor UI does (action 0 = in, 1 = out; flags `CHIP_CABIN_WITH_POGOS_FLAG` 0 = pogo pushpad macro, `CHIP_CABIN_TRAY_ONLY_FLAG` 1 = tray only). The reply is judged like the driver's `setTray` (`motion_replies.mechanism_failure`): the state byte of the 1-byte or legacy 12-byte reply, 0xFF (FAULT), an empty reply (refused by an interlock or an un-homed tray) and no reply all fail and go out on `ERROR_RAISED` with the driver's reason. Either way it republishes the status snapshot.

**Traced flow (tray glyph)**
glyph click → `MOVE_TRAY {direction, actuate_pogos: false}` → `on_move_tray_request` → `motor.chip_cabin_ctrl(action, 1)` → `_publish_status_snapshot()` → `STATUS_UPDATED` + `MOTORS_UPDATED` → status pane `_on_motors_updated_triggered` sets `tray_out_reported` from `mechanisms["cabin"]`, which re-syncs the glyph.

### Portable DropBot motors: Home All, Stop motion, E-STOP

Aligned with the vendor UI (dropbot-portable 1.7.0): Home All is its host plan, not the board's HW_RESET; the stops follow its vocabulary ("Stop motion" = one axis's `MOTOR_CONTROL` STOP, "EMERGENCY STOP — MOTORS" = `MOTOR_ESTOP` 0x11B6).

**Topics (`portable_dropbot_controller/consts/`)**
- `HOME_ALL = "portable_dropbot/requests/home_all"` — any message.
- `MOTOR_STOP = "portable_dropbot/requests/motor_stop"` — the motor name.
- `MOTOR_ESTOP = "portable_dropbot/requests/motor_estop"` — empty message (raw `publish_message`). Motors only: HV, the PMT supply, heaters and the rails are untouched.
- `MOTORS_UPDATED` also carries `moving: {motor: bool}` and `faults: {motor: [fault names]}` (`drv-err`, `chip-bad`, `last-err`, `busy`, `estopped`, `drv-off`) on motor firmware with `MOTOR_SNAPSHOT`; `{}` otherwise.

**Senders (`portable_dropbot_status_and_controls`, Motors pane)**
- Home All → `pyface_wrapper.confirm` (the vendor's "confirm the deck is actually clear") → `HOME_ALL`.
- E-STOP Motors (beside the target motor selector, no confirmation, as the vendor's) → `MOTOR_ESTOP`.

**Backend (`portable_dropbot_controller/motion_safety.py`, composed into the motors mixin)**
- `on_home_all_request`: refused while one runs; `_leave_realtime_mode()` first (HV off, electrodes cleared); reads the board's `_dp_home_seq` (`motor.get_params`; an empty or unanswered table = the compiled default) and refuses a table the vendor UI would (firmware rules, then its enforced safe order). As in the vendor's Home All, the empty-table rule (`HOME_SEQ_EMPTY_PROBLEM`, dropbot-portable 1.8.0) refuses only a write, never Home All. The plan is the vendor's `home_all_plan` (default `pmt_reset`, `mag_reset`, `pushpad_reset`, `tray_reset`, `flu_reset`; a PARK row or a magnet / pad home + park adds `motor_control(id, 6, 0)`); `tray_reset` falls back to `cabin_mag_reset` on firmware without TRAY_RESET, like the vendor's `tray_reset_job`. Each step runs outside the proxy lock and is judged like the vendor's job outcome (no reply / False → the driver's `last_result`; an answered error status → `ui.device_status.device_status_error`); a failed step → `ERROR_RAISED` (`home all: <step>`) and the later steps still run. A successful `pushpad_reset` clears `pads_smart_engaged`. Ends with the status snapshot.
- `on_motor_estop_request`: first calls the base's `_on_motor_estop()` hook (the self-test mixin halts a running self-test there), then `motor.motor_estop()` outside the proxy lock, on a thread marked urgent (`mark_urgent_thread`, cleared after) so the driver's link supervisor never runs inline on it; marks every motor stopped and ends a running Home All after its current step (no error for the aborted step). An unanswered E-STOP → `ERROR_RAISED`. Republishes the motor picture.
- `on_motor_stop_request`: `uart.motorStop(id)` outside the proxy lock, marked urgent like the E-STOP; the move it interrupts logs its failed reply instead of publishing an error.
- Every motion (`_motion_call`, in `MotionSafetyMixin`: tray, magnet, pogo, filter, per-motor move / home, PMT_RESET) runs outside the proxy lock: the driver matches every reply to its request and serialises only param writes and firmware upgrades itself, and the firmware refuses conflicting motion with BUSY. The status poll therefore keeps running during a long move. Skipping the lock takes and releases nothing, so a caller that already holds it keeps it across the motion: the self-test hub's HV off → pad press / release (`_set_pogo`, which returns whether the board accepted the move, judged by `mechanism_failure`) → read-back stays one locked span.

**Traced flow (E-STOP during Home All)**
E-STOP click → `MOTOR_ESTOP` → `on_motor_estop_request` (its own Dramatiq worker, no lock) → `motor_estop()` → the running reset answers aborted → Home All logs it and sends no further step → status snapshot.

### Portable DropBot chip lock: classic vs smart pad engage

Chip lock is the pogo pads pressing the chip. The Portable DropBot Settings preference "Chip engage mode" (`chip_engage_mode`, `CHIP_ENGAGE_MODE_KEY`, default classic) picks how a lock presses: classic is the motor board's fixed-position press (`PUSHPAD_CTRL`), smart is the signal board's `PAD_ENGAGE` (0x1250), where each pad descends until its own contact sensor trips, then overdrives. Smart runs at the vendor UI's fixed defaults (`PAD_ENGAGE_STEP_UM` 200, `PAD_ENGAGE_MAX_STEPS` 18, `PAD_ENGAGE_OVERDRIVE_UM` 300) and needs both pads homed.

**Topics (`portable_dropbot_controller/consts/`)**
- `LOCK_CHIP = "portable_dropbot/requests/lock_chip"` — `"True"` locks, `"False"` unlocks (unchanged wire format; the backend reads the mode from its own preferences).
- `CHIP_LOCK_FAILED = "portable_dropbot/signals/chip_lock_failed"` — `ChipLockFailed {action: "lock" | "unlock", error: str, pads_may_be_pressed: bool}`, published through `chip_lock_failed_publisher` when a smart lock or a pad retract does not finish.
- `MOTORS_UPDATED` carries `pads_smart_engaged: bool` beside `mechanisms`.

**Senders (`portable_dropbot_status_and_controls`)**
- Status pane lock toggle (`chip_locked`, only a click contradicting `chip_locked_reported`) and the Motors pane pogo Press/Release macros publish `LOCK_CHIP`.

**Backend (`portable_dropbot_controller/services/portable_dropbot_motors_mixin_service.py`)**
- `on_lock_chip_request`: lock in smart mode → `sig.pad_engage(1, 1, step, max_steps, overdrive)`; unlock while the mode is smart **or** `pads_smart_engaged` is set → `sig.pad_engage(0, 0, ...)`, the vendor UI's Retract (its way out of any engage, classic or smart), so changing the mode between lock and unlock never strands the pads; anything else → `on_set_pogo_request` (`uart.setPogo`, classic, exactly as before).
- The `PAD_ENGAGE` reply's status: 0 sets `pads_smart_engaged` to the action (engaged / retracted); 1 no contact, 2 motor error, 3 busy publish `CHIP_LOCK_FAILED` (a lock's motor error, or a call that got no reply, adds that smart engage needs both pads homed); 4 retract failed and 5 E-stopped set `pads_smart_engaged` and publish `CHIP_LOCK_FAILED` with `pads_may_be_pressed`. A call answering `None` is described through `uart.last_result(PAD_ENGAGE_CMD)`; a raised error carries its message. Every failed unlock sets `pads_may_be_pressed`. The handler always republishes the status snapshot.
- `PAD_ENGAGE` runs outside the proxy lock, under its own pad engage lock, as on the vendor UI's slow lane: a second lock while one is in flight is refused at once (`CHIP_LOCK_FAILED` "a pad engage is already in flight"), and a retract waits for the engage to finish.

**Frontend (`portable_dropbot_status_and_controls/message_handlers/message_handler.py`)**
- `_on_motors_updated_triggered`: `chip_locked_reported = pads_smart_engaged or (lpush == 1 and rpush == 1)`.
- `_on_chip_lock_failed_triggered`: logs the failure to the Alarms box, puts the toggle back on `chip_locked_reported`, and raises a `pyface_wrapper` dialog on the GUI thread (`GUI.invoke_later`): a warning that the pads may still be pressed when `pads_may_be_pressed`, an error otherwise.

**Traced flow (smart lock)**
toggle click → `LOCK_CHIP "True"` → `on_lock_chip_request` → `sig.pad_engage(1, 1, 200, 18, 300)` (the pad engage lock held up to 45 s, not the proxy lock) → status 0: `pads_smart_engaged = True` → `_publish_status_snapshot()` → `MOTORS_UPDATED {pads_smart_engaged: true}` → `chip_locked_reported = True`; status 1–5 / no reply: `CHIP_LOCK_FAILED` → dialog + toggle back to unlocked (locked after 4/5, so the next click retracts).

### Portable DropBot board health: firmware, port lease, alarms, halt latch

Aligned with dropbot-portable 1.7.0 (#1050). MicroDrop reads and reports the firmware but never flashes it — that is the vendor UI's Firmware tab.

**Topics (`portable_dropbot_controller/consts/`)**
- `FIRMWARE_VERSIONS_UPDATED = "portable_dropbot/signals/firmware_versions_updated"` — `FirmwareVersionsUpdated {mcu: str, motor: str, outdated: list[str]}`, published once per connect through `firmware_versions_publisher`. `mcu` / `motor` are the running tags (`""` unknown); `outdated` has one line per board below the driver bindings' minimum (`proxy.MCU_MIN_COMPATIBLE_FW` / `DRV_MIN_COMPATIBLE_FW`, MCU 1.0.1.31 / motor 1.0.0.26 in 1.7.0).
- `ALARM_RAISED = "portable_dropbot/signals/alarm"` — now `AlarmRaised {command: str, alarms: list[str], reports: list[AlarmReportEntry]}` through `alarm_raised_publisher`; `AlarmReportEntry {text, code?, title, detail, active?, level?}` carries the driver's `AlarmReport` fields, one per frame. `active` 0 is the board clearing the alarm. `alarms` keeps the legacy display strings, and a payload without `reports` is still read.
- `CLEAR_HALT = "portable_dropbot/requests/clear_halt"` — empty message (raw `publish_message`, like the capture aborts).
- `CLEAR_ALARMS = "portable_dropbot/requests/clear_alarms"` — `ClearAlarmsRequest {boards: list["motor" | "signal"] = both, codes: list[str] = []}` through `clear_alarms_publisher`; empty `codes` = every active alarm, codes are 5 digits (`04012`). An empty message means the defaults.
- `ALARMS_CLEARED = "portable_dropbot/signals/alarms_cleared"` — `AlarmsCleared {results: list[BoardAlarmsCleared]}` through `alarms_cleared_publisher`; `BoardAlarmsCleared {board, cleared: list[str], failed: list[str], still_active: dict[code, title], error: str}`, one per board asked. `cleared` codes are gone on the re-read; `failed` ones were refused or are still active (condition persists); `error` says the alarms could not be read or the board did not answer.
- `STATUS_UPDATED` gains `halted` (STATUS `hv_state` bit3, `HV_STATE_HALTED_BIT`) and, from MCU 1.0.1.30 (the driver's `uart.last_status_tail`, None on older firmware), `hv_setpoint` (V), `fault_flags` and `faults` (names). The board's `chip_on_pad` is judged by the chip-detect preference, now defaulting to `presence` (bit0 only, the vendor's rule and the HV interlock's); the pogo rules stay as opt-ins.
- `ERROR_RAISED` also carries refused `HV_ENABLE` replies (`HV enable` / `HV disable` context), refused halt clears, and the port-lease yield.

**Backend (`portable_dropbot_controller`)**
- Monitor mixin `_attempt_connect`: claims the port with `port_lease.acquire_use` before opening it (`PortLeaseGuard.claim`; refused while a firmware update holds priority), reads `session.check_versions(ignore=True)` into `board_firmware_versions` (`{"mcu": (1, 0, 1, 31), "motor": ...}`; `_mcu_firmware_at_least` / `_motor_firmware_at_least` answer False while unknown), retried once after `FIRMWARE_READ_RETRY_DELAY_S` when a board answers no version (still homing), then publishes `FIRMWARE_VERSIONS_UPDATED` after `connected`. Every connect sends `hv_enable(0, 0)` before the connection goes active: HV comes on only through a realtime-on request after that. Every disconnect path releases the claim (after closing the port), forgets the versions, and ends realtime mode (`REALTIME_MODE_UPDATED False` — the frontend's own realtime-off request is refused while disconnected). The user Disconnect, the firmware-update yield and app exit first de-energize like the vendor UI (`session_shutdown.deenergize_session`: `hv_enable(0, 0)`, electrodes cleared, `pmt_power(0)`, each bounded to `SHUTDOWN_TIMEOUT_S`); a lost link closes without them.
- `_monitor_tick` checks `port_lease.holder` on our port before each status poll: another process holding priority (the vendor flash tool) → `ERROR_RAISED`, disconnect, and scanning returns no ports until the holder is gone plus `PORT_LEASE_RELEASE_DELAY_S`. Scan probes skip any port a holder owns. A user connect / retry ends the yield.
- Base `_publish_alarm` (the driver's `on_alarm`) publishes `AlarmRaised` with each report's fields; it runs on the driver's RX thread, so a frame that fails validation is logged with its traceback instead of vanishing.
- States mixin `on_set_realtime_mode_request` judges the `HV_ENABLE` status byte the vendor's way (0 HV on answers an enable, 1 HV off a disable; 2 no device, 3 busy, 4 24 V off, 5 halt latched are refusals → `ERROR_RAISED`). A refused or failed enable sets realtime mode back off and republishes `REALTIME_MODE_UPDATED False`. Leaving realtime mode (`_leave_realtime_mode`, also run by Home All) sends `hv_enable(0, 0)` then clears every electrode, both outside the proxy lock so they never queue behind a long call. `on_clear_halt_request` → `proxy.clear_halt()` (`HALT_CLEAR`): a refusal → `ERROR_RAISED` with the blocking types; then the status snapshot republishes. HV stays off.
- States mixin `on_clear_alarms_request` → per board, one `_proxy_call` (proxy lock) running `board_alarms.clear_board_alarms`: `uart.get_alarms(board)` (GET_ALARMS, active only), `session.clear_alarm(board, code)` (CLEAR_ALARM) for each requested or active code, `get_alarms` again. The re-read is the verdict, since the signal board replies to a refused `failure`-level clear all the same. Publishes `ALARMS_CLEARED` and logs one summary line; an invalid request → `ERROR_RAISED`.

**Frontend (`portable_dropbot_status_and_controls`)**
- `_on_firmware_versions_updated_triggered`: Board Status "Firmware"; outdated firmware also logs to the Alarms box and raises a `pyface_wrapper.warning` (once per connect) pointing at the vendor UI's Firmware tab.
- `_on_alarm_triggered`: a raise adds `code -> title` to `active_alarms` (the Alarms box "Active" line) and logs; a clear removes the code and logs `Cleared: ...` without replacing `last_alarm`.
- `_on_status_updated_triggered`: `halted` drives the model's `halted` (red status icon, realtime off, the "HV halt latched" row with **Clear Halt**); Board Status shows HV Setpoint and Faults ("n/a" before MCU 1.0.1.30); dev temp/humidity 0xFFFF reads "n/a"; `fan_duty` is shown as the fans commanded on (bit0 fan 1, bit1 fan 2). The dead `pmt` key is gone.
- Clear Halt → `pyface_wrapper.confirm` → `CLEAR_HALT`.
- Clear Alarms (Alarms box, next to "Active"; no confirm) → `CLEAR_ALARMS {}`. `_on_alarms_cleared_triggered` drops the `cleared` codes from `active_alarms` and adds `still_active` (the motor board pushes no clear report), logs the cleared codes, and records the `failed` ones as still active.

**Traced flow (halt)**
board latches a halt → STATUS `hv_state` bit3 → `STATUS_UPDATED {halted: true}` → `model.halted` → icon red + `realtime_mode = False` → `SET_REALTIME_MODE False` (HV off, always honoured) → user removes the cause, Clear Halt → confirm → `CLEAR_HALT` → `clear_halt()` → snapshot `{halted: false}` → icon back to the chip colour; realtime on re-enables HV.

**Traced flow (latched alarm)**
an E-STOP during a tray move latches 04012 → `ALARM_RAISED` → Alarms box "Active: [04012] ..." → Home All re-homes but the alarm stays → Clear Alarms → `CLEAR_ALARMS {}` → `get_alarms("motor")` → `clear_alarm("motor", "04012")` → re-read → `ALARMS_CLEARED {results: [{board: "motor", cleared: ["04012"]}, {board: "signal"}]}` → code dropped from "Active", "Cleared motor: 04012" logged.

### Portable DropBot status: change-only events, poll fallback (#1051, #1082)

MCU firmware 1.0.1.33 (dropbot-portable 1.8.0) pushes change-only status events: `DATA_REPORT 0x1205` EVT_FIELDS frames (event mask bit `0x40`), `[0x40][seq][n][n × {field id, u16}]`. Each frame carries every subscribed STATUS field that moved past its deadband (`evt_db`). All fields are resent when the subscription changes and every 5 s, and a gap in `seq` means a lost frame. The topic and payload are unchanged: `STATUS_UPDATED` keeps its keys whether a STATUS read or a merged event produced it.

**Topics (`portable_dropbot_controller/consts/`)**
- `STATUS_UPDATED` gains heater channel 1 from the STATUS tail (MCU 1.0.1.33+, absent before): `cur_temp1`, `target_temp1` (°C) and `out_power1` (%), next to the head's channel-0 `cur_temp` / `target_temp` / `out_power`. `faults` always follows the sample's `fault_flags` (`data_report.fault_names`).
- Tuning lives in `consts/hardware.py`: `STATUS_EVENTS_MIN_MCU_FIRMWARE` (1, 0, 1, 33), `STATUS_EVENTS_REPORT_INTERVAL_MS` 1000, `STATUS_EVENTS_PUBLISH_INTERVAL_S` 0.5, `STATUS_EVENTS_RESYNC_INTERVAL_S` 30 and `STATUS_EVENTS_STALE_S` 12.

**Backend (`portable_dropbot_controller`)**
- `status_events.status_sample(signal, tail)`: one full STATUS sample is the head (`session.status["signal"]`) plus the driver's `uart.last_status_tail` (`evt_fields.tail_from_sample`). Base `_publish_status_snapshot` builds it, hands it to `_note_status_sample` (the events' merge base) and publishes it through `_publish_board_signal`, which applies the chip-detect rule and `halted` and also publishes `CAPACITANCE_UPDATED`.
- Monitor `_attempt_connect` → `_start_status_events(session)` just before the first snapshot. It is gated on `_mcu_firmware_at_least(STATUS_EVENTS_MIN_MCU_FIRMWARE)`, because older firmware accepts bit `0x40` and sends nothing. `StatusEventStream.start` subscribes to `0x1205` (`uart.subscribe`), then sends `set_report_interval(1000)` and `set_event_mask(EVT_FIELDS)` in the vendor hub's order. If the board does not echo the bit, it unsubscribes and the poll stays.
- Frames arrive on the driver's reader thread (`on_data_report`). That thread only decodes (`data_report.decode_fields_event`) and merges into the vendor `FieldsStatusModel` under the stream's own lock: no driver call, no `_proxy_lock`, no publish. A daemon publisher thread (`portable-status-events`) publishes the latest merged sample through `_publish_board_signal`, at most once per `STATUS_EVENTS_PUBLISH_INTERVAL_S`. Frames before a base publish nothing.
- `_monitor_tick` → `_refresh_status` (proxy lock held):
  - Without events (older firmware, refused), it runs the full STATUS poll every `MONITOR_INTERVAL_S` as before.
  - With events, it runs the full read only when `status_read_due()`: a seq gap or a frame without a base asked for a resync, the last read is older than `STATUS_EVENTS_RESYNC_INTERVAL_S`, or no frame arrived for `STATUS_EVENTS_STALE_S`. A stale stream is also re-subscribed (`rearm_if_stale`), at most once per resync interval, because a board reset drops its RAM mask.
  - Otherwise it reads only `motor.status()`, since the events cover the signal board alone, and publishes `MOTORS_UPDATED` as the poll did.
  - The full read stays the link check. An unanswered motor read (`request_status_read`) makes the next tick a full read, so a dead link reaches `STATUS_FAILURE_DISCONNECT_LIMIT` one tick later than the plain poll would.
- Deliberate closes (user Disconnect, firmware-update yield, app exit) turn the board's stream off (`set_event_mask(0)`) after de-energizing. Every disconnect path unsubscribes and resets the model (`_forget_connection`), and the next connect subscribes again.

**Frontend (`portable_dropbot_status_and_controls`)**
- `_on_status_updated_triggered`: the Environment group shows Heater 1 Temp / Power (channel 0, the head fields) and Heater 2 Temp / Power (channel 1, the tail; "n/a" before MCU 1.0.1.33). "Heaters" decodes `temp_onoff` as the per-loop bitmask (`HEATER_ONOFF_BITS`: bit0 Heater 1, bit1 Heater 2).

**Traced flow (event)**
heater 2 warms past its deadband → board EVT_FIELDS `{cur_temp1}` → reader thread `on_data_report` → `FieldsStatusModel.apply` → publisher thread (≤ 2/s) → `_publish_board_signal` → `STATUS_UPDATED {…, cur_temp1}` → Heater 2 Temp. A lost frame (seq gap) → next tick's full STATUS read → `adopt_status` → resync done.

### Portable DropBot magnet engage height: read / RAM write / flash preset

The magnet's engage height is `z_up` (µm), the first int32 of the motor board's `magnet_defaults` device-defaults struct (flash key `_dp_magnet`: `z_up, z_down, y_0, y_space`, big-endian, `MAGNET_DEFAULTS_FIELDS`/`MAGNET_DEFAULTS_FORMAT`). The workflow mirrors the vendor debug UI: Write = RAM only (used from the next engage, lost on reboot); Preset = persists what is in RAM to flash. No motor-board reboot is needed.

**Topics (`portable_dropbot_controller/consts/`)**
- `MAGNET_ENGAGE_READ = "portable_dropbot/requests/magnet_engage_read"` — empty message.
- `MAGNET_ENGAGE_WRITE = "portable_dropbot/requests/magnet_engage_write"` — `MagnetEngageWriteRequest {engage_mm: float >= 0}`, published through `magnet_engage_write_publisher`.
- `MAGNET_ENGAGE_PRESET = "portable_dropbot/requests/magnet_engage_preset"` — empty message.
- `MAGNET_ENGAGE_UPDATED = "portable_dropbot/signals/magnet_engage_updated"` — `MagnetEngageUpdated {action: "read" | "write" | "preset", engage_mm: float | null, error: str}`, published through `magnet_engage_updated_publisher`; `error` empty means the request succeeded, and `engage_mm` is the height a read returned or a write sent.

**Backend (`portable_dropbot_controller/services/portable_dropbot_system_mixin_service.py`)**
- `on_magnet_engage_read_request` reads the struct (`uart.getBoardParameter("motor", "magnet_defaults")`) and publishes `z_up / 1000`.
- `on_magnet_engage_write_request` reads the struct back, refuses a height above the magnet-Z motor's positive soft limit (`pl_pos` of the `magnet_motor` mechanical params — above it the firmware rejects every engage), replaces only `z_up` with `round(engage_mm * 1000)`, and writes all four fields with `uart.setParams("motor", "_dp_magnet", ...)`.
- `on_magnet_engage_preset_request` calls `uart.presetParams("motor", "_dp_magnet")`.

**Frontend (`portable_dropbot_status_and_controls`, Preferences > Portable DropBot Settings > Magnet)**
- Read / Write / Preset to flash buttons on `PortableDropbotSettingsPreferencesPane` publish the three requests; Write sends the field's unapplied value, and Preset asks for confirmation first.
- The plugin owns `MAGNET_ENGAGE_LISTENER` (subscribed to `MAGNET_ENGAGE_UPDATED`) for the whole session: `PortableDropbotMagnetEngageMessageHandler`, made in `start()` and torn down in `stop()`, applies each reply to the plugin's `MagnetEngageModel` on the GUI thread. The plugin hands that model to every pane it contributes, so the status line updates live and a successful read fills the pane's detached copy of `magnet_engage_mm` (an unapplied edit until Apply, never the preferences node).

### Portable DropBot droplet detection: the driver's find_drops

The portable answers `DETECT_DROPLETS` with the driver's own drop finder, `DropBotSession.find_drops()`: a per-channel capacitance scan (CHANNEL_CAPACITANCES, pF, at the current V/F) whose channels reading at least their threshold count as holding liquid. The default threshold is the Portable DropBot Settings preference `droplet_detection_threshold_pf` (`DROPLET_DETECTION_THRESHOLD_PF`, 5 pF); per channel, the driver's saved overrides and a fresh chip baseline replace it and the active chip's electrode weights scale it.

**Topics**
- `DETECT_DROPLETS` / `DROPLETS_DETECTED` — the DropBot's shared topics (`dropbot_controller/consts.py`), so Find liquid and the droplet-check / volume-threshold columns work unchanged. Request: JSON list of channels (empty = the session's used channels, all of them without a chip definition), less the user-disabled channels (see the disabled channels flow); reply `{"success", "detected_channels", "error"}`.

**Frontend (`portable_dropbot_status_and_controls`, Preferences > Portable DropBot Settings)**
- "Droplet detection threshold (pF)" mirrors applied changes to the `DROPLET_DETECTION_THRESHOLD_PF_KEY` app_globals key; the backend's `PortableDropbotPreferences` seeds it at start.

**Backend (`portable_dropbot_controller/services/portable_dropbot_droplet_detection_mixin_service.py`)**
- `on_detect_droplets_request` reads the threshold key, sets it as the session's default drop threshold, runs `find_drops` through `_proxy_call` and replies with its sorted liquid channels. User-disabled channels are dropped first; when that leaves none, nothing is scanned and the reply is a success with no channels.
- `find_drops` never actuates an electrode and leaves V/F alone; it switches HV on for the scan only when HV is off and the pads are engaged, and back off afterwards. With HV off and no device on the pads it refuses, and the reply's `error` carries the driver's reason; a scan with no readings at all also replies with an error.

### Protocol Zone Target column: first zone region with / without a droplet (#965)

A step whose Zone Target cell names a zone type resolves, at step start, the first region of that type meeting the step's Zone Criterion (Has Droplet / No Droplet) and actuates its electrodes with the step's own. No new topics: it reuses the shared droplet-detection round trip, so the DropBot, the portable and the mock answer it unchanged.

**Inputs**
- `ZONES_KEY` (app_globals, owned by `device_viewer`) — the zones snapshot `{zone_id: {"name", "color", "regions": [{"id", "electrode_ids", "channels"}]}}`; region order (the zone manager's stored order) is the check order, listed in the Zone Target cell's tooltip.
- `electrode_to_channel` (protocol metadata, `ctx.protocol.scratch`) — the same map RoutesHandler actuates through.

**Flow (`zone_protocol_controls/protocol_columns/zone_target_column.py`, `ZoneTargetHandler.on_pre_step`, priority 25)**
- `DETECT_DROPLETS` — JSON list: the union of the zone type's region channels. Reply awaited on `DROPLETS_DETECTED` (`ctx.wait_for`, Protocol Settings ack wait, default 12 s).
- The first region with a detected channel (Has Droplet) or with none (No Droplet) wins (`zone_selection.select_zone_region`); its electrode ids go into the step scratch under `EXTRA_STATIC_ELECTRODES_KEY`, which RoutesHandler unions into every phase's static electrodes — so they reach `ELECTRODES_STATE_CHANGE` and `PROTOCOL_TREE_DISPLAY_STATE` like the step's own electrodes. The row is not modified.
- `PROTOCOL_LOGGING_DATA_CONTRIBUTION` — `{"Zone Target", "Zone Target Criterion", "Zone Target Region"}` (strings, stored in the report's data files, not charted).
- A missing zone type, a failed or timed-out detection, or no matching region raises, failing the step through the executor's protocol-error path. A step with an empty Zone Target publishes nothing; preview mode skips the column.

### Portable DropBot settings: motor params, heater, calibration macro

Aligned with dropbot-portable 1.7.0 (#1050).

**Motor mechanical params (advanced controls pane ↔ system mixin)**
- `MOTOR_PARAMS_READ` (motor name) → `MOTOR_PARAMS_UPDATED {motor, fields, blob_size, speed_units}`: `fields` are the ones the board's firmware serves (a wire-order prefix of `MOTOR_PARAM_FIELDS`: 56 / 64 / 68 / 72 B), bspd / rspd in real µm/s (converted with `uart.motor_speed_units()`).
- `MOTOR_PARAMS_WRITE` — `MotorParamsWriteRequest {motor, fields}` through `motor_params_write_publisher`. The backend re-reads the board's blob, puts the edits in place (`motor_params.encode_motor_params`: an unchanged speed keeps the board's own number, `param_layout.motor_blob_problem` refusals reported) and writes it back at the served length; refused while the speed units are unconfirmed. Outcome: `MOTOR_PARAMS_UPDATED {motor, written}` or `{motor, error}`. The write is live on the motor's next idle moment.
- `REBOOT_MOTOR_BOARD` → `{motor_board_rebooted}`; the MCU re-runs the motor boot homing after it and motor commands answer BUSY until it finishes.

**Heater (more controls pane ↔ temp mixin)**
- `TEMP_SET_TARGET` — `TempSetTargetRequest {channel 0..1, target_c}`; a target at or above the board's max_temp_c − 5 °C → `ERROR_RAISED`, nothing sent.
- `TEMP_SET_PID` — `TempSetPidRequest {channel, kp, ki, kd 0..100, period_ms 1..65535}` (Kp = Ki = 0 on the wire refused) through `temp_set_pid_publisher`; outcome `TEMP_UPDATED {channel, pid_applied, pid_error}`. The pane reads the PID (`TEMP_READ_PID`) on connect and on a channel switch. Both go through the generated proxy (`sig.temp_set_params` / `sig.temp_read_params`: uint16 fields, rounded gains), as the vendor UI does.

**Calibration macro (calibration pane ↔ calibration mixin)**
- `CALIBRATION_UPDATED {stage, ok, error}` per step, then `{stage: "done", ok, error, retry}`: HV_ENABLE must answer HV on / HV off, CAP_CALIBRATE_ML status 1; a BUSY fit sets `retry`. A failed setup step skips to the teardown (HV off, restore V/F, press pogos), which always runs.

### Portable DropBot heater auto-tune (#1081)

The vendor's `dropbot_portable.heater_tune` (1.8.0) behind the More Controls pane's Auto-tune group (`portable_dropbot_status_and_controls`, live plot in `models/heater_tune_plot_model.py`) and the backend's heater-tune and heater-tune verify mixins (`portable_dropbot_controller/services/portable_dropbot_heater_tune_mixin_service.py` and `..._heater_tune_verify_mixin_service.py`; the shared run loop in `heater_tune_capture.py`, the verify run in `heater_tune_verify.py`, the board adapter in `heater_tune_board.py`). Contracts in `portable_dropbot_controller/consts/heater_tune.py`.

**Requests (pane controller → backend)**
- `HEATER_TUNE_START = "portable_dropbot/requests/heater_tune_start"` — `HeaterTuneStartRequest {channel 0..1, duty_pct 1..100, max_temp_c 30..90, max_duration_s 30..3600}` via `heater_tune_start_publisher`. Refused (answered on `HEATER_TUNE_DONE {ok: false, reason}`) while a tune runs, a protocol step holds a heater target, either heater is on (STATUS `temp_onoff`), the cap is at or above the board's max_temp_c − 5 °C, or `heater_tune.capture_problem` objects (no reading, too close to the cap).
- `HEATER_TUNE_CANCEL = "portable_dropbot/requests/heater_tune_cancel"` — raw `publish_message`, empty message; the running capture or verify run aborts and sends heater OFF.
- `HEATER_TUNE_APPLY = "portable_dropbot/requests/heater_tune_apply"` — `HeaterTuneApplyRequest {channel, kp, ki, kd (TempSetPidRequest limits), period_ms 1000, smith_model (gain, tau, dead), persist}` via `heater_tune_apply_publisher`, sent only after the pane's confirm. Refused while a tune runs, a protocol step holds a target, a heater is on (a `temp_smith` write re-initialises both loops), or the model row is outside `param_layout.temp_smith_problem`'s ranges. Runs `heater_tune.apply_tuning` (TEMP_SET_PARAMS, then this channel's `temp_smith` row, PRESET both with `persist`).
- `HEATER_TUNE_VERIFY_START = "portable_dropbot/requests/heater_tune_verify_start"` — `HeaterTuneVerifyStartRequest {channel 0..1, setpoint_c 20..88.5 (default 40), max_temp_c 30..90, max_duration_s 30..3600, band_c 0.1..5 (default 0.5), hold_s 0..600 (default 60)}` via `heater_tune_verify_start_publisher` (the pane sends the capture's cap and time limit). Same start rules as `HEATER_TUNE_START` under the same claim, then `heater_tune.verify_problem` (no reading, set point not 1 °C above the reading or above the cap minus 1.5 °C); refusals answered on `HEATER_TUNE_VERIFY_DONE {ok: false, reason}`.

**Signals (backend → `MORE_CONTROLS_LISTENER`)**
- `HEATER_TUNE_PROGRESS = "portable_dropbot/signals/heater_tune_progress"` — `HeaterTuneProgress {channel, phase (baseline | step | cooldown | fitting | verify), elapsed_s, current_c, duty_pct, setpoint_c}`, one per reading (1 Hz); during a verify run `duty_pct` is the loop output the board reports and `setpoint_c` is set. The pane's first progress of a run starts a fresh live plot (temperature, output, set point).
- `HEATER_TUNE_DONE = "portable_dropbot/signals/heater_tune_done"` — `HeaterTuneDone {channel, ok, reason, off_confirmed, fit {gain, tau_s, dead_time_s, r2, rmse_c, reached, y0_c}, proposals {smooth | default | fast: {kp, ki, kd, lambda_s, notes}}, smith_model, notes}`; closes every start request (refusal or outcome).
- `HEATER_TUNE_APPLIED = "portable_dropbot/signals/heater_tune_applied"` — `HeaterTuneApplied {channel, gains, smith ("ok" | "not served" | a write failure), gains_persisted, error}`; the pane re-reads the PID (`TEMP_READ_PID`) after a gains write on the selected channel.
- `HEATER_TUNE_VERIFY_DONE = "portable_dropbot/signals/heater_tune_verify_done"` — `HeaterTuneVerifyDone {channel, ok, reason, off_confirmed, setpoint_c, band_c, metrics {dead_time_s, rise_s, peak_c, overshoot_pct, settle_s, sse_c, settled, duration_s}}`; closes every verify request. `ok` once the run reached its end (settled or the time limit); an aborted run still carries the metrics of what it recorded.

**Heater ownership while a tune or verify runs** (the tune mixin's `_exclusive_owner_reason`, chained before the self-test mixin's; a verify run holds the same `_heater_tune_cancel` claim): the listener refuses `TEMP_SET_TARGET`, `TEMP_CONTROL`, `TEMP_SET_PID`, `HEATER_TUNE_APPLY`, `SELF_TEST_RUN` (answered by the hub's own refusal) and `PROTOCOL_SET_TEMPERATURE` (failed at once on `TEMPERATURE_REACHED {error}`); a refused `DISCONNECT` cancels the tune instead, so the port never closes under a driven heater. A running self-test refuses `HEATER_TUNE_START` and `HEATER_TUNE_VERIFY_START` the same way, and either run refuses to start while the other runs.

**Traced flow: a tune**
1. Pane Start → `HEATER_TUNE_START` → `on_heater_tune_start_request` checks the rules under `_heater_tune_claim` (STATUS, heat_fs max_temp_c, a TEMP_READ_INFO), then starts the `heater-tune` daemon thread.
2. The thread reads `sig.temp_read_info(ch)` once a second, each call under `_proxy_lock` (never the whole run), feeds `StepCapture` and publishes `HEATER_TUNE_PROGRESS`: 10 s baseline at 0 %, then `sig.temp_heat_pwm` at the step duty until a plateau, the cap minus 1.5 °C (or its 10 s trend) or the time limit, then `sig.temp_start_stop(ch, 0)` (sent without the lock, resent up to 3 times until acknowledged) and a 30 s cool-down log.
3. Phase `fitting`: `fit_fopdt` on the whole record, `tune_pid` per style, `smith_model`; the claim is released and `HEATER_TUNE_DONE` published.
4. Pane Apply → confirm → `HEATER_TUNE_APPLY` → `apply_tuning` under `_proxy_lock` → `HEATER_TUNE_APPLIED` → pane `TEMP_READ_PID` → `TEMP_UPDATED {pid}`.
- Cancel, an E-STOP (`_on_motor_estop`), a heater failsafe alarm (0900x) on the tuned channel (`on_alarm_signal`, which still chains to the temp mixin's), plugin stop (`cleanup` joins the thread before the port closes) and any exception end the run with heater OFF; `off_confirmed` false in `HEATER_TUNE_DONE` means OFF was never acknowledged. A lost link sends nothing: the firmware's host-silence failsafe (alarm 09004) cuts the heater.
5. The pane overlays the fitted FOPDT response (a numpy simulation from `fit`, starting at `y0_c`) on the captured trace and suggests a verify set point: the last reading + 10 °C, held below the cap minus 1.5 °C.

**Traced flow: a verify run**
1. Pane Verify → `HEATER_TUNE_VERIFY_START` → `on_heater_tune_verify_start_request` checks the tune's start rules plus `verify_problem` under `_heater_tune_claim`, then starts the `heater-tune-verify` daemon thread.
2. The thread sends `sig.temp_set_target(ch, setpoint)` then `sig.temp_start_stop(ch, 1)` (the board's own loop on the gains it holds; a refusal of either aborts with heater OFF), reads `sig.temp_read_info(ch)` once a second, feeds `VerifyRun` and publishes `HEATER_TUNE_PROGRESS {phase: verify, setpoint_c}`.
3. The run ends once the reading held ±band for hold_s, at the time limit, at the cap or on a sensor outage: `sig.temp_start_stop(ch, 0)` (resent until acknowledged), `step_metrics`, the claim released, `HEATER_TUNE_VERIFY_DONE` published; the pane shows the figures on its Verify line.
- Every end of a capture listed above (cancel, E-STOP, failsafe alarm, disconnect, plugin stop, exception, lost link) ends a verify run the same way.

### Portable DropBot protocol columns: magnet + heater step execution

The portable's built-in magnet and heater join a protocol through `portable_dropbot_protocol_controls` (one plugin for every portable peripheral, since they all sit behind the one backend). Each column is a PPT-11 compound column: a "set" checkbox gates the step, and a checked step publishes one request and blocks on one ack, mirroring the standalone magnet/heater plugins.

**Topics (all in `portable_dropbot_controller/consts/`)**
- `PROTOCOL_SET_MAGNET = "portable_dropbot/requests/protocol_set_magnet"` — JSON `{"on": bool, "height_mm": float}`. Ack: `MAGNET_APPLIED = "portable_dropbot/signals/magnet_applied"`.
- `PROTOCOL_SET_TEMPERATURE = "portable_dropbot/requests/protocol_set_temperature"` — JSON `{"channel": int, "target_c": float, "tolerance_c": float}` (`ProtocolSetTemperatureRequest`, validated by the backend). Ack: `TEMPERATURE_REACHED = "portable_dropbot/signals/temperature_reached"` — `TemperatureReached {channel: int, current_c: float?, error: str}` through `temperature_reached_publisher`; a non-empty `error` fails the step (`TemperatureHandler` raises).
- `TEMP_CONTROL` (existing) — the temperature handler's `on_post_protocol_end` publishes `{"channel": DEFAULT_TEMP_CHANNEL, "on": False}` after every run so nothing keeps heating unattended.

**Frontend (handlers in `portable_dropbot_protocol_controls/protocol_columns/`)**
- `MagnetHandler` / `TemperatureHandler` run at priority 20 (with voltage/frequency, before routes). Unchecked steps and preview mode publish nothing and wait for nothing. `ctx.wait_for(<ack>, timeout=self.ack_time_s)` uses the Protocol Settings ack-wait grid value (0 = fire-and-forget); provider defaults are 40 s for the magnet (the driver's engage/disengage blocks up to 30 s) and 120 s for the heater.
- A magnet height below `MAGNET_HEIGHT_MM_BOUNDS[0]` is the "Default" sentinel: the spinbox shows "Default" and the backend runs the firmware engage macro; any other height is an absolute position on the magnet Z motor.

**Backend (`portable_dropbot_controller/services/`)**
- `on_protocol_set_magnet_request` (motors mixin) — disengage / engage macro / `motorAbsoluteMove` on the magnet motor (mm × 1000 µm), then publishes `MAGNET_APPLIED` only when the reply confirms the move (a mechanism state that is not FAULT, or the final position of the absolute move); a refusal, FAULT or timeout goes out on `ERROR_RAISED` instead and leaves the step to time out. It republishes the status snapshot.
- `on_protocol_set_temperature_request` (temp mixin) — sets the channel target and turns control on, then arms a watcher thread that polls the channel every `TEMP_REACHED_POLL_INTERVAL_S` (republishing `TEMP_UPDATED` so the pane keeps tracking) and publishes `TEMPERATURE_REACHED` once `|current - target| <= tolerance`; after `TEMP_REACHED_TIMEOUT_S` it publishes a failure. A new request cancels the previous watcher. A target at or above the board's `heat_fs` max_temp_c − 5 °C (`uart.heater_failsafe()`, 120 °C default), or a setpoint the board does not accept, fails the step at once with the reason.
- `on_alarm_signal` (temp mixin) — the backend listener also subscribes to its own `ALARM_RAISED`: a raised heater failsafe alarm (`HEATER_FAILSAFE_ALARM_CODES` 09001 / 09002 / 09004 / 09005; clears skipped, an alarm naming the other loop `htrN` ignored) cancels the watcher and publishes `TEMPERATURE_REACHED` with the alarm as `error`. Once the setpoint was reached the watcher does not end: it holds the loop armed until a `TEMP_CONTROL` off for that channel (the handler's end-of-run one, or the pane) or a newer setpoint, and an alarm in that hold phase is republished on `TEMPERATURE_REACHED` every `TEMP_REACHED_POLL_INTERVAL_S` (so a pause between steps cannot drop it). `TemperatureHandler` marks the run as heater-armed in the protocol scratch when a step drives the heater, and from then on its `on_pre_step` / `on_post_step` drain any error on that topic and raise, which the executor surfaces as the protocol error.

### Portable DropBot PMT capture, live stream, ADC query, buffered acquire (#601)

The PMT Capture pane (`portable_dropbot_status_and_controls`) and the PMT mixin (`portable_dropbot_controller/services/portable_dropbot_pmt_mixin_service.py`) talk over validated topics; the Pydantic contracts and publishers live in `portable_dropbot_controller/consts/pmt.py`, re-exported from the `consts` package. Three sessions — the multi-spot capture, the live stream, and the buffered acquire — share the tube and the ADC and so share one claim in the backend: `_pmt_claim` guards the check-and-set of `_pmt_capturing` / `_pmt_streaming` / `_pmt_acquiring`, and a request for a different session while one is running is refused with a reason naming which one ("a PMT capture is running", "the live stream is running", "a buffered acquire is running"). A `PMT_STREAM_START` received while the stream is already running is not a new session — it is a live avg/osr/gain update, handled before the claim is even consulted, so it never restarts the stream or drops a sample.

**Spot table**
- On `PORTABLE_DROPBOT_CONNECTED` (and the pane's Refresh button) the pane publishes `PMT_SPOTS_READ = "portable_dropbot/requests/pmt_spots_read"` (empty message).
- Live stream & acquire's **Move to** dropdown (Park = spot 0, then the board's configured spots) publishes `PMT_MOVE_TO_SPOT = "portable_dropbot/requests/pmt_move_to_spot"` (the spot number as text) as soon as it changes; the backend moves via `motor.pmt_ctrl(location)` for the spot's motor location (below) and parks with `MOTOR_CONTROL` action `MOTOR_ACTION_PARK` on motor firmware `PMT_PRESET_PARK_MOTOR_FIRMWARE` (DroDri_1.0.0.25) and newer, `pmt_ctrl(PMT_LEGACY_PARK_LOCATION)` before it; refusing (logged) while a PMT capture runs — a live stream or acquire keeps running. **Home PMT** publishes the Motors pane's `MOTOR_HOME` with `"pmt"` and resets the dropdown to Park without a second move.
- The backend reads the motor board's `pmt_defaults` flash parameter (one int32 Y position in µm per motor location 1–6). **The spot numbering depends on the motor firmware:** from DroDri_1.0.0.25 all six locations are spots and spot n is location n (park is the separate `_dp_park`); before it location 1 was park and never offered, so spot n is location n + 1. A saved PMT protocol step's spot numbers therefore point at a different location after the motor board is upgraded across .25 — re-check them. While the motor firmware version is unknown (re-read once on demand, and retried once at connect for a board still homing) the spot read and every PMT move are refused with that reason rather than guessing. On .25+, a location 1 that reads 0 µm or the PMT's `_dp_park` position is reported once per connection as an `ERROR_RAISED` (context "PMT spot table check"): the sign of a board upgraded from older firmware whose table was never re-taught and publishes `PMT_SPOTS_UPDATED = "portable_dropbot/signals/pmt_spots_updated"` — `PmtSpotsUpdated {spots: [{slot, position_um}]}`, non-zero slots only. The pane merges it into its rows by slot, keeping the operator's tick/gain/exposure and order. A future add/remove-spot feature only has to republish this topic.

**ADC query**
- The pane publishes `PMT_ADC_QUERY = "portable_dropbot/requests/pmt_adc_query"` (empty message) on connect, so the pane's conversion (counts -> volts -> amps) has a real full scale before the operator does anything.
- The backend calls `SignalBoardProxy.spi_adc_diag()`, which shares the ADC bus with every session, so the request is refused (an error `PmtAdcUpdated` with `full_scale: 0`) while a capture/stream/acquire is running. On a reply it publishes `PMT_ADC_UPDATED = "portable_dropbot/signals/pmt_adc_updated"` — `PmtAdcUpdated {adc_type, name, full_scale, error}` — `adc_type` 0 is "none" (`full_scale: 0`), an unrecognized code is `"unknown (N)"` (`full_scale: 0`), and a code the backend knows (1 = ADC128S052/4096, 2 = ADS7076/65536) updates the backend's remembered full scale; an unknown/none reading never overwrites it. Each of the three sessions calls the same query for itself at its own start, before power-on, and stamps its own CSV meta with whatever full scale that answered.

**Capture routine**
- Start publishes `PMT_CAPTURE = "portable_dropbot/requests/pmt_capture"` — `PmtCaptureRequest {entries: [{slot, gain, exposure_s}], avg, osr, rf_ohms}` (the last three inherited from `PmtStreamSettings`, defaulting to `PMT_STREAM_AVG`/`PMT_STREAM_OSR`/`PMT_RF_OHMS`), ticked rows in table order.
- The backend runs the routine on a daemon thread (the actor's time limit would otherwise interrupt a long capture): ADC query, fluorescence LED off, PMT power on, then per entry move (`MotorBoardProxy.pmt_ctrl`), gain, `SignalBoardProxy.pmt_stream(1, request.avg, request.osr)` for `exposure_s` while a `uart.subscribe(PMT_STREAM_DATA_CMD)` callback assembles the frames, stream stop, CSV to `<experiment>/captures/pmt/pmt_spot<slot>_<stamp>_gain<g>.csv` (the queried `adc_full_scale`, `request.avg`/`osr`/`rf_ohms` in its meta). Each stage publishes `PMT_CAPTURE_PROGRESS = "portable_dropbot/signals/pmt_capture_progress"` (`PmtCaptureProgress {index, total, slot, stage, detail, exposure_s}`; stages move/gain/stream/saved/failed; `exposure_s` is set on the stream stage so the pane counts the exposure down on its status line and highlights that spot's row). The proxy lock is taken per command so `STATUS_UPDATED` keeps flowing during a long exposure.
- Teardown always runs: stream stop, power off (an unanswered power-off is logged at error level), light setpoint restored. Then `PMT_CAPTURE_DONE = "portable_dropbot/signals/pmt_capture_done"` — `PmtCaptureDone {ok, aborted, directory, results: [PmtSpotResult], adc_full_scale, rf_ohms, request_id, label, error}` (`adc_full_scale`/`rf_ohms` are what the CSVs were actually written with, so the pane shows the same current the files carry); a refused request (another session running, nothing ticked) publishes it immediately with `error` set so the pane's Start never sticks.
- `PMT_CAPTURE_ABORT = "portable_dropbot/requests/pmt_capture_abort"` sets an event the routine polls every 50 ms; it finishes the current spot's teardown and reports `aborted=true`.
- `PMT_UPDATED {acquiring: true/false}` brackets the routine so the pane greys the controls that must not run concurrently with it, as for the buffered acquire below.

**Protocol-step captures (#601 increment 2, `portable_dropbot_protocol_controls`'s `pmt_capture` column)** — `PmtCaptureRequest` carries three more optional fields, all defaulted so a pane-initiated request is unaffected:
  - `request_id` (default `""`) is echoed back verbatim on `PmtCaptureDone`, on success AND on every refusal (`_refuse_pmt_capture` takes it as a parameter; a request that fails Pydantic validation still gets it read best-effort off the raw JSON, so even a malformed request's ack can be matched, or `""` if the payload wasn't even readable as JSON). A protocol step's `PmtCaptureHandler` sets it to `f"{row.uuid}:{phase}"` (`phase` is `start` or `end`) and waits on `PMT_CAPTURE_DONE` with a `predicate=` matching that value, so a pane-initiated capture or a stale done from an earlier step can never satisfy its wait — the same pattern the droplet-check column uses with `step_uuid`.
  - `label` (default `""`, filename-safe per `PMT_CAPTURE_LABEL_PATTERN`, max 64 chars) is prefixed onto that request's spot CSVs — `pmt_<label>_spot<n>_<stamp>_gain<g>.csv` instead of `pmt_spot<n>_..._gain<g>.csv` — and written into each CSV's meta alongside `request_id`. A step sets it to a tag like `step1.2-end`.
  - `stop_live_stream` (default `False`): when set AND the running live stream is the ONLY reason the claim would be refused, the backend stops the stream instead of refusing — it sets the stream's stop event and joins its teardown thread (bounded by `PMT_STREAM_PREEMPT_TIMEOUT_S`), logs that the protocol stopped the stream, then retries the claim once. If the stream doesn't finish tearing down in time, or the blocker is a capture/acquire already running (never preempted, only the stream is), the request is refused as usual. A pane's Start leaves this `False`, so a running stream still refuses it exactly as before.

**Live stream**
- Start (or update) publishes `PMT_STREAM_START = "portable_dropbot/requests/pmt_stream_start"` — `PmtStreamRequest {gain, avg, osr, rf_ohms}`. The pane sends this again whenever avg/osr/gain change while already streaming, not just on the first Start — the backend's live-update path applies the new values with no restart and no sample gap.
- A first start claims the session and runs it on a daemon thread with the same opening as the capture routine (ADC query, LED off, power on, `_publish_pmt(power=True)`, gain, `uart.subscribe(PMT_STREAM_DATA_CMD)` before `pmt_stream(1, avg, osr)`), then acks `PMT_STREAM_UPDATED = "portable_dropbot/signals/pmt_stream_updated"` — `PmtStreamUpdated {streaming: true, avg, osr}` — and loops publishing a batch (`{streaming: true, avg, osr, samples, packets}`) every `PMT_STREAM_PUBLISH_INTERVAL_S` (0.25 s) while there is anything to report, until `PMT_STREAM_STOP = "portable_dropbot/requests/pmt_stream_stop"` sets the loop's stop event (a stop with nothing running is a no-op, logged at debug).
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

**Topics (`portable_dropbot_controller/consts/`)**
- `FLUORESCENCE_CAPTURE = "portable_dropbot/requests/fluorescence_capture"` — `FluorescenceCaptureRequest {entries: [{filter_position, led_percent, exposure_ms, focus_distance}], request_id, label, directory}` (`exposure_ms` `null` = the camera's auto exposure, settled `FLUORESCENCE_AUTO_EXPOSURE_SETTLE_S` before the grab instead of `FLUORESCENCE_SETTLE_S`; `directory` empty = current experiment directory; `label` filename-safe per the PMT capture's `PMT_CAPTURE_LABEL_PATTERN`).
- `FLUORESCENCE_CAPTURE_ABORT = "portable_dropbot/requests/fluorescence_capture_abort"` — stops the routine after the current entry's teardown.
- `FLUORESCENCE_CAPTURE_PROGRESS = "portable_dropbot/signals/fluorescence_capture_progress"` — `FluorescenceCaptureProgress {request_id, index, total, filter_position, stage, detail}` (stages `filter`/`led`/`camera`/`frame`/`teardown`).
- `FLUORESCENCE_CAPTURE_DONE = "portable_dropbot/signals/fluorescence_capture_done"` — `FluorescenceCaptureDone {request_id, ok, label, directory, frames, error}`; `frames` are the saved PNGs as `FluorescenceCapturedFrame {filter_position, path}`, capture order.

**Camera seam (`device_viewer/consts.py`)** — the only new cross-plugin surface, since the routine runs in the backend but the camera is a frontend `QCamera`:
- `DEVICE_VIEWER_CAMERA_SET_CONTROLS = "ui/device_viewer/camera/set_controls"` — `CameraControlsRequest {request_id, exposure_ms, hold_auto_exposure, focus_distance}`; either value `None` means auto exposure / continuous auto focus; `hold_auto_exposure=true` leaves auto for manual at the exposure auto last chose (`exposure_ms` ignored). Under GStreamer (Pi) Qt's auto exposure is a no-op, so the camera widget also flips v4l2 `auto_exposure` (3 auto / 1 manual). The device viewer validates the payload against `CameraControlsRequest` before touching the camera (#703): malformed JSON or an out-of-range/mistyped value is answered `CameraControlsApplied {request_id, ok=False, error}` directly (the `request_id` recovered from the raw payload when possible) without reaching the camera widget, so a waiting requester fails fast instead of timing out.
- `DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED = "ui/device_viewer/camera/controls_applied"` — `CameraControlsApplied {request_id, ok, exposure_ms, exposure_auto, focus_distance, error}` (`exposure_ms` is the exposure in effect — auto's current pick while `exposure_auto`, when the Qt backend reports it — or `None` when unreported; the Pi's DH Camera never reports auto's pick, its v4l2 `exposure_time_absolute` keeps the last manual value), the camera's readback after applying; a provider feed (no `QCamera`) or an unsupported mode answers `ok=False` with why, rather than raising.
- `DEVICE_VIEWER_MEDIA_CAPTURED` (existing topic, see the Protocol tree run logging section above) is now published live from the capture path itself, carrying the saving request's `request_id` on `MediaCaptureMessageModel`, so the fluorescence routine can match a saved frame to the request that asked for it.

**Backend routine (`portable_dropbot_controller/services/portable_dropbot_fluorescence_mixin_service.py`)**
- Refuses a concurrent request (`ok=False, error="busy"`) while a capture thread is alive; no guard against a concurrent PMT capture — the firmware itself darkens the fluorescence LED for PMT reads and restores it, and both panes grey out while a protocol runs.
- Per entry, in order, each stage publishing `FLUORESCENCE_CAPTURE_PROGRESS` and checking an abort `Event` first: **filter** (`proxy.motor.fluorescence_ctrl(pos)`, up to 60 s), **led** (`proxy.sig.fluorescence_ctrl(raw)`), **camera** (publish a `CameraControlsRequest` tagged `f"{request_id}:{index}"` and wait up to `FLUORESCENCE_CAMERA_CONTROLS_TIMEOUT_S` for the matching `CameraControlsApplied`, then settle `FLUORESCENCE_SETTLE_S`), **frame** (publish `DEVICE_VIEWER_SCREEN_CAPTURE` with the same request id and wait up to `FLUORESCENCE_FRAME_TIMEOUT_S` for the matching `DEVICE_VIEWER_MEDIA_CAPTURED`, appending its path with the entry's filter position as a frame).
- Teardown always runs two independent steps: restore the LED to the controller's current light intensity, and reset the camera to auto exposure/focus (fire-and-forget, no wait). Then `FLUORESCENCE_CAPTURE_DONE` with the frames collected so far — `ok=False` and `error` set on a filter alarm, a camera refusal, a wait timeout, or an abort (`error="aborted"`).
- `FLUORESCENCE_CAPTURE_ABORT` and `PORTABLE_DROPBOT_DISCONNECTED` both set the routine's abort event; every wait returns early on it.

**Pane (`portable_dropbot_status_and_controls`, "Fluorescence Capture" dock pane)** — one row per `FILTER_POSITIONS` entry (capture tick, LED %, auto exposure, exposure ms, start/end ticks; no focus control — the Pi's camera has no software focus, so entries always carry `focus_distance: null`). Start publishes `FLUORESCENCE_CAPTURE` with `request_id=uuid4()`, `label="manual"`; Abort publishes `FLUORESCENCE_CAPTURE_ABORT`. Attaching to the selected protocol row writes the step's cell over `PROTOCOL_TREE_SET_CELL`, mirroring the PMT Capture pane.

**Filter names** — positions stay numbers in every message and step cell; `FILTER_NAMES` (1 HEX, 2 CY5, 3 White, 4 FAM, 5 Empty — confirmed against the vendor UI) is display-only: the pane shows `filter_label()` (the dye alone, "FAM") in its tables, Filter pick and status line, and `frame_description()` puts the dye in each frame's `step_description`, so files read `flu_<label>_f4_FAM_<timestamp>.png`.

**Park PMT / Park Filter (the capture panes)** — a pane-level checkbox (off by default) beside Abort (fluorescence) / Refresh spots (PMT). It rides on `PMT_CAPTURE` / `FLUORESCENCE_CAPTURE` as `park_motor` (`CaptureParkOption`), and on an attached step's `pmt_capture` / `fluorescence_capture` cell the same way (the protocol columns pass `step.park_motor` through, adding one per-entry overhead to the step timeout). When set, the capture's guaranteed teardown also moves its motor to its parking position — the PMT to park (spot 0, `PMT_PARK_LOCATION`), the filter wheel to `FLUORESCENCE_PARK_FILTER` (3) — whether the run finished, failed or was aborted (best effort, logged on failure).

**PMT / fluorescence exclusivity (per step)** — a step sets only one of `pmt_capture` / `fluorescence_capture`. Each capture pane reads the other column from the `PROTOCOL_TREE_ROW_SELECTED` cells: while the selected step carries the other capture and its own cell is empty, its Start/End table is locked with a note (a step carrying both stays editable so one can be cleared). Since a set-cell rebroadcasts `PROTOCOL_TREE_ROW_SELECTED`, ticking in one pane locks the other live. At run time both columns call `check_single_capture` (`portable_dropbot_protocol_controls/capture_exclusivity.py`) at the start of each phase, so a step with both raises before any hardware moves.

**Pane Manual controls (same pane, collapsible group)** — each edit applies live (the LED is left to the status pane's Light control): a filter pick publishes `SET_FILTER` (the position as text); **Home filter** publishes `MOTOR_HOME` with `"filter"` and resets the pick to position 1 without a second move; an exposure change (while not on auto) or ticking Auto exposure publishes a `CameraControlsRequest` on `DEVICE_VIEWER_CAMERA_SET_CONTROLS` with `request_id="manual"` (`exposure_ms` `None` = auto; `focus_distance` always `None`); unticking it publishes `hold_auto_exposure=true` with `request_id="manual-hold-exposure"` only when the last readback reported auto's pick (that readback's `exposure_ms` then moves the Exposure slider there), else a plain manual request at the slider's value. Capture frame publishes `DEVICE_VIEWER_SCREEN_CAPTURE` `{directory: <experiment dir>, step_description: "flu_manual_f<n>", show_status_message: false, request_id: "manual-<uuid4>"}`. The pane's listener subscribes to `DEVICE_VIEWER_CAMERA_CONTROLS_APPLIED` (any readback, manual or a capture's, shown on its Camera line) and `DEVICE_VIEWER_MEDIA_CAPTURED` (only the file echoing its in-flight `manual-` request id becomes a Results run).

**Protocol-step captures (`portable_dropbot_protocol_controls`'s `fluorescence_capture` column, `FluorescenceCaptureHandler`)** — the same `step_uuid`-style correlation pattern as `pmt_capture`: `on_pre_step` runs entries ticked `at_start`, `on_post_step` those ticked `at_end`, each phase publishing one `FLUORESCENCE_CAPTURE` with `request_id=f"{row.uuid}:{phase}"` and `label` sanitised to `PMT_CAPTURE_LABEL_PATTERN` (e.g. `step1.2-end`), then waiting on `FLUORESCENCE_CAPTURE_DONE` with a `predicate=` matching that `request_id` — a pane-initiated capture or a stale done from an earlier step can never satisfy it. Timeout is `len(entries) * FLUORESCENCE_STEP_PER_ENTRY_OVERHEAD_S + FLUORESCENCE_STEP_TIMEOUT_MARGIN_S` (no per-entry exposure sum like the PMT column's — the per-entry overhead already covers the filter's up-to-60 s move plus both camera stages); `ack_time_s == 0` on the Protocol Settings grid means fire-and-forget, as for magnet/heater/PMT. `done.ok == False` raises `RuntimeError(done.error)`; an `AbortError` publishes `FLUORESCENCE_CAPTURE_ABORT` before re-raising, and `on_post_protocol_end` publishes it unconditionally (including in preview mode) so an interrupted run never leaves a capture going. The captures folder lands in the report as one metadata row (`{"Fluorescence Captures Folder": done.directory}`); the PNGs themselves reach the report's Media Captures section on their own through the now-live `DEVICE_VIEWER_MEDIA_CAPTURED`, so there is no per-image contribution.

### Portable DropBot self-tests

The self-test hub (`portable_dropbot_self_tests`, Tools > Self Tests...) runs the vendor's `dropbot_portable.self_test` catalogue on the portable backend (`portable_dropbot_controller`'s self-test mixin service). The whole contract (topics, Pydantic models, publishers) lives in `portable_dropbot_self_tests/consts.py`, which the backend imports (consts-only).

**Requests (frontend hub panel -> backend; handlers `on_<segment>_request`)**
- `SELF_TEST_RUN = "portable_dropbot/requests/self_test_run"` — `SelfTestRunRequest {run_id, tests, test_kwargs, chip_absent_acknowledged}` via `self_test_run_publisher`; handler `on_self_test_run_request`.
- `SELF_TEST_ABORT = "portable_dropbot/requests/self_test_abort"` — `SelfTestAbortRequest {run_id}` (empty aborts any run) via `self_test_abort_publisher`; stops at the next step, the restore still runs.
- `SELF_TEST_PREFLIGHT_READ = "portable_dropbot/requests/self_test_preflight_read"` — empty message; answered on `SELF_TEST_PREFLIGHT_UPDATED`.
- `SELF_TEST_SAVE_CALIBRATION = "portable_dropbot/requests/self_test_save_calibration"` — `SelfTestSaveCalibrationRequest {calibration, tare}` via `self_test_save_calibration_publisher`; answered on `SELF_TEST_CALIBRATION_SAVED`.
- `SELF_TEST_DIAG_INFO_READ = "portable_dropbot/requests/self_test_diag_info_read"` — empty message (the panel's Board diagnostics button); answered on `SELF_TEST_DIAG_INFO_UPDATED`; handler `on_self_test_diag_info_read_request` (state mixin).

**Signals (backend -> hub's plugin-lifetime listener `SELF_TEST_LISTENER`, so the model survives the panel closing)**
- `SELF_TEST_PREFLIGHT_UPDATED = "portable_dropbot/signals/self_test_preflight_updated"` — `SelfTestPreflight {tray_in, pads_pressed, chip_on_pad_mask, chip_res, board_detected, running, run_id, unsaved, error}` via `self_test_preflight_publisher` (also lets a reopened panel resync).
- `SELF_TEST_PROGRESS = "portable_dropbot/signals/self_test_progress"` — `SelfTestProgress {run_id, phase, index, total, name, step, steps, text, error, cancelled}`; `phase` is `choreography` (HV-off / pad moves / restore between tests) or the vendor's `start`/`step`/`done`.
- `SELF_TEST_RESULT = "portable_dropbot/signals/self_test_result"` — `SelfTestResult {run_id, name, title, verdict, duration, utc_timestamp, error, cancelled, restore_errors, result, results_path}`.
- `SELF_TEST_FINISHED = "portable_dropbot/signals/self_test_finished"` — `SelfTestFinished {run_id, refused_reason, cancelled, error, restore_note, verdicts, unsaved, directory}`.
- `SELF_TEST_CALIBRATION_SAVED = "portable_dropbot/signals/self_test_calibration_saved"` — `SelfTestCalibrationSaved {calibration_status, calibration_text, tare_ok, unsaved, error}`.
- `SELF_TEST_DIAG_INFO_UPDATED = "portable_dropbot/signals/self_test_diag_info_updated"` — `SelfTestDiagInfo {text, stalled_sources, diagnostics, error}` via `self_test_diag_info_publisher`: the vendor's `diag_info.format_diag_info` text, `DiagInfo.stalled_sources()`, the parsed `DiagInfo` as a dict.

Each signal has a matching `self_test_*_publisher` (`ValidatedTopicPublisher`) in the same consts module.

**Behaviour rules**
- The frontend mints a `run_id` per run; every progress/result/finished message carries it and the frontend ignores any other id (a second frontend or stale message cannot corrupt its model).
- Per run request the backend publishes EXACTLY ONE `SELF_TEST_FINISHED`, always last. A refused run publishes only that message with `refused_reason` set; an accepted run publishes per test progress (start, steps, done) then one result, interleaved with `choreography` progress.
- Refusals (before any HV change or pad move): a run already in progress; a PMT or fluorescence session holds the board; realtime mode on or a protocol running; Home All or a smart chip lock / unlock running (neither holds the proxy lock); a test name outside `ALL_TESTS` + `HEALTH_TESTS` or a `test_kwargs` key the hub does not set (`TEST_KWARG_BOUNDS`: the repeat counts, the channels / calibration limits, and the health tests' bool `heat_step` / `moves`); pad state unknown while a selected test needs pads moved; the tray not where the run wants it (IN for Run all and `test_motors`); no board detected by the backend's own chip read and `chip_absent_acknowledged` False. Preflight reads, board diagnostics reads and calibration saves report refusals/failures in the reply's `error`.
- Health tests (`HEALTH_TESTS`: `test_heaters`, `test_motors`, rows after the DropBot tests, Run all included): the frontend confirms a run whose `test_motors` has `moves` on (`pyface_wrapper.confirm`, before the pre-flight). `test_heaters`' heat step switches each heater off on its own paths (cancel, E-STOP, errors); while it runs `SelfTestBoard.run_test` registers both loops in `_self_test_heaters` (the vendor's `worker.shutdown_heaters`), and a disconnect meanwhile (the state mixin's `portable_dropbot_connection_active` observer, which fires before the session closes) or the self-test teardown after a timed-out join sends `TEMP_START_STOP 0` for them through `session_shutdown.switch_heaters_off` (bounded, past the proxy lock). Their results skip the frontend's NaN restore: a None there is a missing reading.
- Board diagnostics: read between runs only — a run refuses `SELF_TEST_DIAG_INFO_READ` like any request outside its allowed list, and a held proxy lock answers `error="board busy"` (`PREFLIGHT_BOARD_BUSY_ERROR`) instead of waiting. Replies are broadcast (no request id), so the model shows them without touching the tracked run.
- Exclusive ownership: while a run is in progress the backend refuses every other `portable_dropbot/requests/*` topic except abort, preflight read and `MOTOR_ESTOP` (connection requests that are no-ops while connected also pass), with a logged warning. A disconnect request during a run becomes an abort, so the port is never closed under a running test.
- E-STOP during a run: `MOTOR_ESTOP` passes the gate and halts the run, as the vendor runner does — the test stops at its next step, the restore switches HV off and sends no pad move (`SelfTestBoard.move_pads` refuses after the halt); `SELF_TEST_FINISHED` has `cancelled` and an `error` naming the E-STOP.
- Unsaved calibration: the feedback-cap calibration and electrode tare live in board RAM until saved. `unsaved` (`calibration` / `tare`) is backend-owned: set when a run leaves either captured-but-unsaved, cleared by a successful save and on disconnect, reported on finished, preflight and save replies.
- Verdicts and titles are computed by the backend so every frontend shows the same judgement. `SelfTestResult.result` is the vendor result made JSON-safe (arrays to lists, NaN to None); the backend also writes each test's JSON under the experiment directory (`results_path` / `directory`, reference only) and the frontend regenerates any Markdown/HTML report locally from the inline results, so a remote frontend works.

**Traced flow (board diagnostics)**
1. Hub panel: Board diagnostics → `SelfTestHubController._read_diagnostics` → `SelfTestHubModel.request_diagnostics()` (Report view, "Reading..." section) → `publish_message(SELF_TEST_DIAG_INFO_READ, "")`.
2. Backend listener: a run in progress → `_exclusive_owner_reason` refuses; disconnected → refused too; either way `PortableDropbotSelfTestStateMixinService._on_request_refused` publishes `SelfTestDiagInfo {error: <reason>}`.
3. Otherwise `on_self_test_diag_info_read_request` → `_read_diag_info`: non-blocking proxy-lock acquire (busy → `error="board busy"`), `_proxy_call` → `proxy.sig.diag_info()` (DIAG_INFO 0x12B0; None on firmware without it) → `self_test_results.diag_info_fields` (vendor `parse_diag_info` / `format_diag_info` / `stalled_sources`) → `self_test_diag_info_publisher`.
4. Hub listener `SelfTestsMessageHandler._on_self_test_diag_info_updated_triggered` validates `SelfTestDiagInfo` → GUI thread → `SelfTestHubModel.apply_diag_info` → `SelfTestRunOutputs.show_diagnostics`; the report view renders `display_markdown` (the run report, then the "Board diagnostics" section). A new run clears it.

### Protocol columns → Device Viewer: camera source selection around a run

Lets a plugin column (the fluorescence plugin's, in its own repo) show a given camera source for a run, learn whether that worked, and put the previous source back afterwards. Payload models live in `device_viewer/models/media.py`, re-exported with the topics and their `ValidatedTopicPublisher`s (`camera_select_source_publisher`, `camera_source_selected_publisher`, `camera_state_publisher`) from `device_viewer/consts.py`.

**Topics (`device_viewer/consts.py`)**
- `DEVICE_VIEWER_CAMERA_SELECT_SOURCE = "ui/device_viewer/camera/select_source"` — `CameraSelectSourceRequest {label, active, request_id}` (extra fields rejected). `label` is the camera dropdown text, e.g. `"ASI: ZWO ASI183MM"`: an exact match wins, else a case-insensitive one; `""` selects `<No Camera>` (what `CameraState` reports for it). `active` `true`/`false` also turns the camera on/off; `null` leaves it.
- `DEVICE_VIEWER_CAMERA_SOURCE_SELECTED = "ui/device_viewer/camera/source_selected"` — `CameraSourceSelected {request_id, label, ok, error, active}`: `label` is the entry selected (the requested one when unknown), `active` the camera's on/off after the request. `ok=false` for malformed JSON or a failed validation (answered by the message controller without reaching the widget, `request_id`/`label` recovered from the raw payload), no camera widget, an unknown label (`error` lists the available labels), a provider feed that failed to open or raised, or `active=true` with `<No Camera>` selected.
- `DEVICE_VIEWER_CAMERA_STATE = "ui/device_viewer/camera/state"` — `CameraState {selected_camera, active, leased}`, published by `CameraController` whenever its model's `selected_camera`, `camera_active` or `camera_leased` changes (so once when the camera panel makes its first selection at startup, and on every dropdown pick, toggle, `camera_active` request or feed error), and again right after every `source_selected` reply.

**Device viewer side**
- `DeviceViewerMessageController._on_select_source_triggered` (Dramatiq worker) validates the payload and emits `CameraControlWidget.camera_select_source_signal`, which runs `apply_select_source` on the GUI thread: `CameraController.find_requested_source` matches the label, `combo_cameras.setCurrentIndex` selects it through the same `on_camera_changed` path as a click (a running camera is restarted on the new source), then `on_camera_active(active)` — the slot `DEVICE_VIEWER_CAMERA_ACTIVE` uses — switches it on/off. `CameraController.source_selected` publishes the reply, then the state.
- A provider feed (`CAMERA_SOURCES`) opens synchronously — an `open()` failure is answered at once with its message — but may start asynchronously (the ASI feed opens the camera on its thread), so a request that starts a new feed holds its reply: the feed's first `error` answers `ok=false` with that message, its optional `started` signal or `CAMERA_FEED_START_TIMEOUT_MS` (3 s) without an error answers `ok=true`. Requesters' reply timeouts must exceed that. A `QCamera`'s start is not waited on: `ok=true` means the selection and the start request went through; a camera failing later shows as `active=false` on `DEVICE_VIEWER_CAMERA_STATE`.
- **Camera lease** — every valid `select_source` sets `CameraModel.camera_leased` in the message controller on receipt: `active=true` takes it, anything else releases it. While leased, `_on_camera_active_triggered` ignores `DEVICE_VIEWER_CAMERA_ACTIVE` `"false"` (info log "Camera kept on: leased by a protocol run"); `"true"` still applies. `PROTOCOL_RUNNING` `"False"` (published by the protocol tree dock pane on finish/abort/error) also releases it, so a crashed run never leaves the camera held.

**Traced flow (run start)**
1. Plugin column `on_pre_protocol_start` publishes `select_source {label, active: true, request_id: <uuid>}`, having kept the latest `DEVICE_VIEWER_CAMERA_STATE` (its listener subscribes to it) to restore later.
2. Device viewer selects + starts the source (above) and publishes `source_selected {request_id, ok, ...}` then `camera/state`.
3. The column waits for the `source_selected` carrying its `request_id`, then returns (run proceeds) or raises `RuntimeError(error)` on `ok=false` / timeout. The executor wraps it in `StepExecutionError` ("protocol — '<column>' failed during on_pre_protocol_start: ..."), aborts before `protocol_started`, runs the `on_protocol_end` / `on_post_protocol_end` teardown, and emits `protocol_error`; the protocol tree dock pane shows it in the "Protocol error" dialog. Note `on_pre_protocol_start` gets a `ProtocolContext`, which has no `wait_for`: the executor's listener only fills the active step's mailboxes, so a run-start wait needs the requester's own subscription.
4. Mid-run: the Video column's `camera_active` `"false"` for a step without video is ignored while the run's lease holds; `"true"` applies (a no-op on the already-running feed).
5. Run end: the column restores the saved state with another `select_source {label: <saved selected_camera>, active: <saved active>}`, which releases the lease; best sent from `on_post_protocol_end`, after the Video column's `on_protocol_end` camera-off (ignored if it arrives first, applied if Dramatiq delivers it after the restore). `PROTOCOL_RUNNING` `"False"` releases the lease if no restore came.

**Ownership** — the Video column stays the only publisher of `DEVICE_VIEWER_CAMERA_ACTIVE` during steps; `select_source` is a run-start/run-end request, and its `active=true` lease outranks the Video column's camera-off (see `video_protocol_controls/protocol_columns/capture_column.py`'s header).

### Protocol Capture column ↔ Device Viewer: per-step capture camera settings

Each capturing step stores the resolution and camera properties it captures with (the Capture compound's display-only `capture_camera_settings` cell, a `CameraSettings` dict or `None`), so they vary from step to step instead of staying whatever the camera panel last had. Payload models live in `device_viewer/models/media.py`, re-exported from `device_viewer/consts.py`.

**Topics (`device_viewer/consts.py`)**
- `DEVICE_VIEWER_CAMERA_SETTINGS = "ui/device_viewer/camera/settings"` — `CameraSettingsSnapshot {camera, resolution, image_controls, focus, user_edit}`: `resolution` is `[w, h]` (`None`, with no controls, unless a QCamera is selected), `image_controls` maps v4l2 control names to `{value, auto}`, `focus` is `{auto, distance}` or `None`. Published by `CameraController` through a 0.3 s throttle (`CAMERA_SETTINGS_PUBLISH_INTERVAL_S`): `user_edit=true` after a resolution pick, an image-control edit, a focus edit or an autofocus sweep; `false` after a source selection, a restored format or an applied request.
- `DEVICE_VIEWER_CAMERA_APPLY_SETTINGS = "ui/device_viewer/camera/apply_settings"` — `CameraSettingsRequest {camera, resolution, image_controls, focus, request_id, context}` (extra fields rejected); `context` names the asker for the user's warnings ("Step 1.2 · Wash").
- `DEVICE_VIEWER_CAMERA_SETTINGS_APPLIED = "ui/device_viewer/camera/settings_applied"` — `CameraSettingsApplied {request_id, ok, warnings, error}`. `ok=false` when nothing applied (no QCamera selected, invalid payload, no camera widget); `warnings` lists what the camera could not take while the rest applied.

**Device viewer side** — `_on_apply_settings_triggered` validates and emits `camera_settings_signal`; `CameraControlWidget.apply_camera_settings` (GUI thread) switches to the best format of the resolution (via the saved-resolution restore, so it shows in the condensed list and skips the high-resolution notice), then `CameraController.apply_settings` sets each image control (a missing one skipped, an out-of-range value clamped, an `auto` without an automatic mode applied manual) and the focus. While the camera is off the request is kept and applied again when it starts (Qt reports focus support only for a started camera, and some cameras reset their controls on open). Each warning is logged and shown once per camera selection in a deferred `pyface_wrapper.warning`, so steps sharing an unsupported setup warn once.

**Protocol side (`video_protocol_controls/services/camera_settings_sync.py`, `CameraSettingsSync` actor)** — subscribes to `DEVICE_VIEWER_CAMERA_SETTINGS`, `PROTOCOL_TREE_ROW_SELECTED` and `PROTOCOL_RUNNING`; idle only:
1. A `user_edit` snapshot is written over `PROTOCOL_TREE_SET_CELL` into the current step when it captures, and into every other selected step with `only_if_set=true` (only those already holding a setup).
2. A capturing step without a setup gets the latest snapshot on selection (or on the next snapshot).
3. Selecting a step holding a setup publishes `apply_settings` for it (skipped when it is the setup last synced, so the tree's rebroadcast of our own write is not applied back); a snapshot naming a different camera re-applies it, so the new camera's warnings show.

**Run time** — `CaptureHandler.on_pre_step` (capture ticked, setup stored) publishes `apply_settings` before the camera lead starts and waits for the `settings_applied` carrying its `request_id` (the Capture ack time; 0 = fire-and-forget). `ok=false` and warnings are logged; the capture always goes ahead.

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

### Any plugin → notifications drawer: posting a notification (#1077, #1137)

**Posting** — import only `notifications.consts` (allowed by `.importlinter`) and publish a `NotificationMessage`:

```python
from notifications.consts import notification_publisher

notification_publisher.publish({
    "title": "Chip removed",                 # one line, required
    "detail": "The protocol is paused.",     # optional; a traceback shows monospace
    "severity": "warning",                   # info | success | warning | error
    "category": "hardware",                  # free text
    "source": "dropbot_status_and_controls", # who posted
    "action": {"kind": "publish", "label": "Retry", "topic": "...", "message": ""},
    "secondary_action": {"kind": "help", "label": "How to insert a chip", "target": "Inserting a chip"},
    "needs_attention": True,                 # listed under Needs attention, toast stays
    "category_id": "dropbot.chip_removed",   # a declared NOTIFICATION_CATEGORIES id
    "thread_id": "dropbot.chip.COM5",        # posts with this id update one entry in place
    "condition_id": "dropbot.chip_missing",  # NOTIFICATION_RESOLVE with this id clears it
    "pop_up": True,                          # False: listed and counted, no toast, no sound
    "priority": 0,                           # within Needs attention, higher sorts first
})
```

Every field after `action` is optional and defaults to "not set", so messages posted before they existed validate unchanged. `action` is data, never a callable: `{"kind": "publish", "label", "topic", "message"}` publishes `message` on `topic`, `{"kind": "open_path", "label", "path"}` opens a file or folder. `secondary_action` is `{"kind": "help", "label", "target"}` (a link; with no `action` the card's one outlined button). Its `target` names a tutorial, `"<tutorial id>"` or `"<tutorial id>#<section id>"` (`help_target` builds it, e.g. `"dropbot_status#part-tools"`); pressing it publishes OPEN_TUTORIAL. It is disabled, with a tooltip, until the help plugin announces on HELP_AVAILABILITY that tutorials can be opened or `{"kind": "snooze", "label"}` ("Later": out of Needs attention, into Activity). Pressing `action` marks the card handled: read, out of Needs attention, its buttons replaced by the label.

**Receiving** — `NotificationsMessageHandler._on_post_triggered` validates on the worker thread and hands the message to `NotificationCenter.post_message` with `GUI.invoke_later`. A notification with the same `(source, category, severity, title)` as a listed one collapses into it (count + 1, latest text and time, moved to the top, unread again); one with a `thread_id` replaces its thread's entry state whole, counted once. A category the user keeps out of the drawer is not recorded, unless it is an error or needs attention. The session keeps `MAX_ENTRIES` (300); the oldest go first; Clear all keeps Needs attention. Nothing persists across launches.

**Arrival** — each new (or newly unread) entry, and each repeat, is offered to the toasts (`ToastStackController.offer`, rule `arrival_outcome`): while the drawer is open it lands there marked new; otherwise it pops up as a toast (three at most, the rest counted on "+N more"), refreshes the toast already showing, or, while quiet (`ToastStackModel.quiet`), is held for one summary toast unless it is an error, needs attention or belongs to the quiet run's own category group. Whatever shows rings the bell and chimes the category's tone (`services/chime.py`); start-up history, read entries, held ones and those posted with `pop_up` False (the sender's per-message choice, e.g. a reminder re-posted at every launch) are silent. Needs attention lists by `priority` (higher first), then newest first. Info and success toasts time out (settings), warnings, errors, Needs attention and ones with a button stay.

**Resolving** — publish `NotificationResolveRequest(condition_id, resolution)` on NOTIFICATION_RESOLVE when the condition clears; `NotificationCenter.resolve` moves its cards out of Needs attention, read, marked with `resolution`. A thread whose next post no longer needs attention leaves Needs attention too, in place.

**Categories** — a plugin declares its kinds of notification as `NotificationCategorySpec`s (id, group, label, description, defaults for drawer / popup / tone, `critical`) in its `consts.py` and contributes them with `List(SPECS, contributes_to=NOTIFICATION_CATEGORIES)`; messages name one in `category_id`. The user's choices (gear button in the drawer header) are saved in `settings.json` in the notifications data folder, with "Open the notifications panel at start-up" (default on; `MICRODROP_NOTIFICATIONS_OPEN_AT_START=0`/`1` overrides it).

**In-process sources** (not topics) — warning-and-above log records from the root logger (`services/log_forwarder.py`: batched every 250 ms, collapsed by logger + level + message template + exception line, minus `LOG_IGNORE_RULES`; category `notifications.log`), and a "failed to load" error for every failed plugin load record (category `notifications.plugin_load_failed`, critical).

**Sections** — the drawer is one scrolling column: Needs attention, the contributed `NOTIFICATION_SECTIONS` (a `NotificationSection`: id, title, summary, order, `factory(parent)`, and its look `glyph` / `accent` / `logo`), then Activity. `plugin_management` contributes the plugin loading list; the indicator click publishes `NOTIFICATIONS_SHOW_PANEL` with that section's id. A section raises alerts for what is new in it (e.g. news posts) by appending `SectionAlert`s to its `alerts`: each pops up, counts on the bell and is marked new until seen in the open drawer with the section expanded, never listed in Activity; the drawer keeps the alert's `unread` / `is_new` current, and a click on its toast asks the section's `alert_widget(contents, alert)` for the widget to scroll to. The drawer opens only from the bell, a toast, or the request; it is no dock pane, so task layouts and the View menu never list it.

### device_viewer → notifications drawer: the calibration reminder (#1133)

```
DeviceViewerDockPane (pane first shown, after the window painted)
  └─ model.load_calibration_data_from_preferences()   # values + calibration.calibrated_on
  └─ CalibrationReminderController.start()             # then hourly, and on every change
       reminder_state(liquid, filler, calibrated_on, today):
         missing      ─► NOTIFICATION_POST  "No calibration saved"       priority 2
         date unknown ─► NOTIFICATION_POST  "Calibration date unknown"   priority 1
         stale (>7 d) ─► NOTIFICATION_POST  "Calibration is N days old"  priority 1
         fresh        ─► NOTIFICATION_RESOLVE "Calibrated" (only after a card this session)
```

Every post: severity warning, `needs_attention`, `pop_up` False (no toast, no sound, counted on the bell), `category_id` `device_viewer.dropbot_maintenance`, `thread_id` `device_viewer.calibration_reminder` (one card, updated in place), `condition_id` `device_viewer.calibration_needed`, help link "How to calibrate" (target "Calibrating the device"). Measuring the filler or liquid capacitance stamps `CalibrationModel.calibrated_on` (ISO day, saved beside the values as `calibration.calibrated_on` in the preferences) before the value, so the card resolves at once.

### device_viewer → notifications drawer: photos and videos (Camera › Captures)

```
camera panel (CameraControlWidget, GUI thread) ─► CaptureNotificationsController
  photo saved (ImageSaver.save_complete)   ─► NOTIFICATION_POST "Photo captured" | "N photos captured"
  no camera frame to grab                  ─► NOTIFICATION_POST "Photo not captured"     (error)
  recording finalized (recording_stopped)  ─► NOTIFICATION_POST "Video saved"
```

Every post: `category_id` `device_viewer.camera_captures` (group Camera, label Captures; drawer and pop-up on, tone Soft), `source` `device_viewer`, `category` `camera`. Photos: success, detail the file name ("Latest: <name>" past the first), action `{"kind": "open_path", "label": "Show folder", "path": <the captures folder>}` (opened by the drawer through `microdrop_utils.file_handler.open_file`, no topic). One card per capture session, `thread_id` `device_viewer.camera_captures.photos.<n>`, updated in place with the count: a session is one folder and one protocol run (counted on the main model's `protocol_running` turning on), and outside a run, photos into the same folder within `CAPTURE_SESSION_WINDOW_S` (5 min) of the previous one (`models/capture_session.py`, `continues_capture_session`). Videos: success, detail `<name> (m:ss)` (start to stop of the recording), "Show folder", `thread_id` `device_viewer.camera_captures.video.<path>`. A capture whose request set `show_status_message` False (the protocol's Capture and Record columns, the fluorescence panes) posts with `pop_up` False; the capture button's pop up. The recording's start shows only as the status-bar recording icon; a recording error keeps its dialog (and its logged error card).

### dropbot_tools_menu → notifications drawer: the self-test reminder (#1133)

```
application.extra_plugins_loaded ─► SelfTestReminderController.start()
  reads <application home>/notifications/self_test.json {"last_full_run_completed": ISO}
  reminder_state(last_run, today):
    never run     ─► NOTIFICATION_POST "Self test has not been run"      priority 2
    stale (>10 d) ─► NOTIFICATION_POST "Self test last run N days ago"   priority 1
    fresh         ─► nothing

dropbot/signals/self_tests_progress  SESSION_START {tests}   ─► full suite = more than one test
dropbot/signals/self_tests_results   {failed_channels}       ─► counts tests that failed channels
dropbot/signals/self_tests_progress  SESSION_END {status}
  completed full suite ─► self_test.json written
                       ─► NOTIFICATION_RESOLVE "Self test passed" | "Self test finished · N failed"
```

Every post: as the calibration reminder (warning, Needs attention, `pop_up` False, the same category), `thread_id` `dropbot_tools_menu.self_test_reminder`, `condition_id` `dropbot_tools_menu.self_test_needed`, help link "What does it check?" (target "DropBot self tests"). While a DropBot is connected (`DropbotToolsMenuPlugin.dropbot_connected`), the card also has the button "Run self test", publishing RUN_SELF_TESTS_REQUEST; without one it is help-only and says to connect a DropBot first. The card is re-posted quietly through its thread whenever the connection changes.

- RUN_SELF_TESTS_REQUEST "ui/dropbot_tools_menu/run_self_tests" — run all the DropBot self tests exactly as Tools › Dropbot › Run all on-board self-tests does (`run_self_tests`: nothing but a "disconnected" dialog without a DropBot; the "insert the test board" dialog first; then RUN_ALL_TESTS with the user data folder for the report). Handled on the frontend by `dropbot_tools_menu` (its listener, then `GUI.invoke_later`). Payload `RunSelfTestsRequest` (no fields; `{}`), via `run_self_tests_request_publisher`. The time is kept once for any board: the frontend has no stable id for the connected DropBot.

### Anyone → user_help_plugin: opening a tutorial by id

- OPEN_TUTORIAL "ui/help/open_tutorial" — open a tutorial as Help › Tutorials does (the same `tutorial_action`), scrolled to a section when `anchor` names one (an `id` in the page). An unknown id logs a warning and opens Getting Started. Payload `OpenTutorialRequest{tutorial_id, anchor=None}`, via `open_tutorial_publisher`. A tutorial's id is its page's file name without `.html` (`tutorial_id(path)`, `TutorialEntry.id`), e.g. `dropbot_status`. Handled on the frontend by `UserHelpPlugin` (its listener `user_help_plugin_listener`, then `GUI.invoke_later`).
- HELP_AVAILABILITY "ui/help/availability" — `HelpAvailability{available}`: True once `UserHelpPlugin` has started (after its listener exists), False when it stops; via `help_availability_publisher`. The notifications drawer follows it: help links are enabled only while it is True. The help plugin is deferred, so links stay disabled for the few seconds after the window paints.

```
card help link ─► NotificationsController.open_help(target)
                 └─ open_tutorial(target): parse_help_target ─► OPEN_TUTORIAL {tutorial_id, anchor}
UserHelpPlugin listener ─► GUI.invoke_later(open_tutorial) ─► tutorial_action(entry, anchor).perform()
                           (QtWebEngine dialog; the system browser where QtWebEngine cannot load)
```

