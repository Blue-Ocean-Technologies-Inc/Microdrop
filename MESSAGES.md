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


