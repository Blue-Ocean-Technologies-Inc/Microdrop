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

Sending: (Via publish_method)
- ELECTRODES_STATE_CHANGE "dropbot/requests/electrodes_state_change"
- START_DEVICE_MONITORING "dropbot/requests/start_device_monitoring"
- DEVICE_VIEWER_STATE_CHANGED "ui/device_viewer/state_changed"
- STEP_PARAMS_COMMIT "ui/device_viewer/step_params_commit"

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

