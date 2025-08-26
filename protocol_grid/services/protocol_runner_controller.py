import time
import json
from typing import Optional, Dict

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QDialog, QApplication

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from protocol_grid.services.path_execution_service import PathExecutionService
from protocol_grid.services.voltage_frequency_service import VoltageFrequencyService
from protocol_grid.services.volume_threshold_service import VolumeThresholdService
from protocol_grid.extra_ui_elements import DropletDetectionFailureDialogAction
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE
from dropbot_controller.consts import (ELECTRODES_STATE_CHANGE, DETECT_DROPLETS,
                                       SET_REALTIME_MODE)
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class ProtocolRunnerSignals(QObject):
    highlight_step = Signal(object) # path (list of ints)
    update_status = Signal(dict)
    protocol_finished = Signal()
    protocol_paused = Signal()
    protocol_error = Signal(str)
    select_step = Signal(str)  # step_uid

class ProtocolRunnerController(QObject):
    """
    runs the protocol VISUALLY
    using Dramatiq actors for logic
    emits signals for UI updates.
    """
    def __init__(self, protocol_state, flatten_func, parent=None):
        super().__init__(parent)
        self.protocol_state = protocol_state
        self.flatten_func = flatten_func
        self.signals = ProtocolRunnerSignals()
        self._is_running = False
        self._is_paused = False
        self._current_index = 0
        self._run_order = []
        self._start_time = None
        self._step_start_time = None
        self._elapsed_time = 0.0
        self._step_elapsed_time = 0.0
        self._repeat_protocol_n = 1
        self._current_protocol_repeat = 1
        self._current_step_timer = None
        self._current_execution_plan = []
        self._current_phase_index = 0
        self._preview_mode = False
        self._step_repetition_info = {}

        # new phase tracking
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._total_step_phases_completed = 0
        self._step_phase_start_time = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_step_timeout)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(100)
        self._status_timer.timeout.connect(self._emit_status_update)
        
        self._phase_timer = QTimer(self)
        self._phase_timer.setSingleShot(True)
        self._phase_timer.timeout.connect(self._on_phase_timeout)

        self._pause_time = None
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0

        self._unique_step_count = 0

        # debounce setup for Qt thread
        self._pause_resume_debounce_timer = QTimer()
        self._pause_resume_debounce_timer.setSingleShot(True)
        self._pause_resume_debounce_timer.timeout.connect(self._execute_debounced_pause_resume)
        self._pending_pause_resume_action = None
        self._debounce_delay_ms = 250

        # Advanced mode direct hardware control state tracking
        self._paused_original_electrodes = {}
        self._is_advanced_hardware_control = False
        # Advanced mode editability state
        self._advanced_mode_editable_state = False

        # Message dialog pause state
        self._pause_for_message_display = False
        # message dialog response state
        self._message_waiting_for_response = False
        self._message_rejected_pause = False

        # phase navigation state
        self._phase_navigation_mode = False
        self._original_pause_phase_index = 0
        self._navigated_phase_index = 0
        self._phase_navigation_step_elapsed = 0.0
        self._original_step_time_remaining = 0.0

        self._was_advanced_hardware_mode = False

        # droplet detection state
        self._droplet_check_enabled = False
        self._waiting_for_droplet_check = False
        self._droplet_check_failed = False
        self._expected_electrodes_for_check = []

        # track droplet detection attempts per step
        self._droplet_check_attempted_for_step = {}  # {step_index: True/False}
        self._droplet_check_skipped_until_phase_nav = False  # skip droplet check unless phase navigation occurs

        # volume threshold service
        self._volume_threshold_service = VolumeThresholdService(self)
        self._volume_threshold_service.threshold_reached.connect(self._on_volume_threshold_reached)
        self._volume_threshold_mode_active = False
        self._current_phase_volume_threshold = 0.0
        self._current_phase_target_capacitance = None

    # --------- data logging ----------
    def set_data_logger(self, data_logger):
        """Set reference to data logger for context updates."""
        self._data_logger = data_logger

    def _get_current_logging_context(self) -> Optional[Dict]:
        """Get current execution context for data logging."""
        if not self._is_running or self._preview_mode or self._current_index >= len(self._run_order):
            return None
        
        try:
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            
            if not device_state:
                return None
            
            # get current phase electrodes
            phase_electrodes = self._get_current_phase_electrodes()
            
            # convert electrode IDs to channel numbers
            actuated_channels = []
            for electrode_id, is_active in phase_electrodes.items():
                if is_active and electrode_id in device_state.id_to_channel:
                    channel = device_state.id_to_channel[electrode_id]
                    actuated_channels.append(channel)
            
            # calculate actuated area
            actuated_area = 0.0
            if hasattr(step, 'device_state') and step.device_state:
                # get calibration data from protocol state for electrode areas
                if hasattr(self, 'protocol_state') and hasattr(self.protocol_state, 'get_calibration_data'):
                    try:
                        calibration_data = self.protocol_state.get_calibration_data()
                        electrode_areas = calibration_data.get('electrode_areas', {})
                        
                        for electrode_id in phase_electrodes:
                            if phase_electrodes[electrode_id] and electrode_id in electrode_areas:
                                actuated_area += electrode_areas[electrode_id]
                    except Exception as e:
                        logger.debug(f"Could not get electrode areas for data logging: {e}")
                        # Area remains 0 if calibration data not available
            
            return {
                'step_id': step.parameters.get("ID", ""),
                'actuated_channels': sorted(actuated_channels),
                'actuated_area': actuated_area
            }
            
        except Exception as e:
            logger.error(f"Error getting logging context: {e}")
            return None
    # ---------------------------------

    def connect_droplet_detection_listener(self, message_listener):
        """Connect to droplet detection response signals."""
        if message_listener and hasattr(message_listener, 'signal_emitter'):
            message_listener.signal_emitter.droplets_detected.connect(
                self._on_droplets_detected_response
            )
            message_listener.signal_emitter.capacitance_updated.connect(
                self._volume_threshold_service.update_capacitance
            )
            logger.info("Connected to droplet detection signals")

    def set_droplet_check_enabled(self, enabled):
        self._droplet_check_enabled = enabled

    def _should_perform_droplet_check(self):
        if not self._droplet_check_enabled:
            logger.debug("Skipping droplet check: droplet check not enabled")
            return False

        if self._preview_mode:
            logger.debug("Skipping droplet check: preview mode")
            return False
        
        # skip if current step has no electrodes/paths/loops
        if self._current_index >= len(self._run_order):
            logger.debug("Skipping droplet check: no current step")
            return False
        
        # check if droplet detection was already attempted for this step
        if self._droplet_check_attempted_for_step.get(self._current_index, False):
            # if skipping until phase navigation, do not check
            if self._droplet_check_skipped_until_phase_nav:
                logger.debug(f"Skipping droplet check for step {self._current_index} - already attempted and skipped until phase nav")
                return False
            else:
                # phase navigation occurred, allow re-check
                logger.debug(f"Allowing droplet check for step {self._current_index} - phase navigation reset")
                # do not return

        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
    
        if not device_state:
            logger.debug("Skipping droplet check: no device state")
            return False
        
        # check if step has any electrodes to check
        has_individual_electrodes = any(device_state.activated_electrodes.values())
        has_paths = device_state.has_paths()
        
        should_check = has_individual_electrodes or has_paths
        logger.debug(f"Droplet check decision: has_individual={has_individual_electrodes}, has_paths={has_paths}, should_check={should_check}")
        
        return should_check
    
    def _perform_droplet_detection_check(self):
        """perform droplet detection check at the end of a step."""
        try:
            if not self._should_perform_droplet_check():
                self._proceed_to_next_step()
                return
            
            # mark attempted droplet detection for this step
            self._droplet_check_attempted_for_step[self._current_index] = True

            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            
            if not device_state:
                self._proceed_to_next_step()
                return
            
            # get expected channels for droplet detection
            expected_channels = self._get_expected_droplet_channels(step, device_state)
            self._expected_electrodes_for_check = expected_channels
            
            if not expected_channels:
                logger.info("No channels to check for droplets")
                self._proceed_to_next_step()
                return
                        
            # flag to indicate waiting for droplet check
            logger.info(f"Starting droplet detection for specific channels")
            self._waiting_for_droplet_check = True
            
            # create message with expected channels
            message = json.dumps(expected_channels)
            
            # send droplet detection request
            publish_message(topic=DETECT_DROPLETS, message=message)
            
        except Exception as e:
            logger.error(f"Error during droplet detection request: {e}")
            self._handle_droplet_detection_failure([], [])

    def _on_droplets_detected_response(self, response_json):
        if not self._waiting_for_droplet_check:
            return
        
        try:
            response = json.loads(response_json)
            
            self._waiting_for_droplet_check = False
            
            success = response.get("success", False)
            detected_channels = response.get("detected_channels", [])
            error = response.get("error", None)
            
            if not success:
                logger.error(f"Droplet detection failed: {error}")
                self._waiting_for_droplet_check = False
                self._proceed_to_next_step()
                return
            
            # convert to integers for consistent comparison
            detected_channels = [int(ch) for ch in detected_channels]
            expected_channels = [int(ch) for ch in self._expected_electrodes_for_check]
            
            # check if all expected channels have droplets
            missing_channels = set(expected_channels) - set(detected_channels)
            
            if missing_channels:
                logger.warning(f"Missing droplets on channels: {list(missing_channels)}")
                self._handle_droplet_detection_failure(expected_channels, detected_channels)
            else:
                logger.info("All expected droplets detected successfully")
                self._waiting_for_droplet_check = False
                self._proceed_to_next_step()
                
        except Exception as e:
            logger.error(f"Error processing droplet detection response: {e}")
            self._handle_droplet_detection_failure(self._expected_electrodes_for_check, [])

    def _handle_droplet_detection_failure(self, expected_channels, detected_channels):
        """show dialog and pause."""
        self._waiting_for_droplet_check = False
        self._droplet_check_failed = True

        # Ensure all channels are integers for consistent handling
        expected_channels = [int(ch) for ch in expected_channels]
        expected_channels.sort()
        detected_channels = [int(ch) for ch in detected_channels]
        missing_channels = set(expected_channels) - set(detected_channels)
        
        # convert channels back to electrode IDs for display
        expected_electrodes = [str(ch) for ch in expected_channels]
        detected_electrodes = [str(ch) for ch in detected_channels]
        missing_electrodes = [str(ch) for ch in missing_channels]
        
        # step is completed, we are just paused at the end of it
        if not self._is_paused:
            self._is_paused = True
            import time
            self._pause_time = time.time()
            self._status_timer.stop()
            
            # set up pause state as if step just completed normally
            current_time = self._pause_time
            if self._start_time:
                self._elapsed_time = current_time - self._start_time
            if self._step_start_time:
                self._step_elapsed_time = current_time - self._step_start_time
            
            # no remaining time since step is technically complete
            self._remaining_phase_time = 0.0
            self._remaining_step_time = 0.0
            self._was_in_phase = False
            
            # set phase navigation to last phase of the step
            if self._current_execution_plan:
                self._paused_phase_index = len(self._current_execution_plan) - 1
                self._original_pause_phase_index = self._paused_phase_index
                self._navigated_phase_index = self._paused_phase_index
                self._phase_navigation_step_elapsed = self._step_elapsed_time
                self._original_step_time_remaining = 0.0
            else:
                self._paused_phase_index = 0
                self._original_pause_phase_index = 0
                self._navigated_phase_index = 0
                self._phase_navigation_step_elapsed = self._step_elapsed_time
                self._original_step_time_remaining = 0.0
                
        else:
            # already paused - preserve existing pause state but ensure navigation is set correctly
            # this means we were paused at step completion and droplet detection failed
            if self._current_execution_plan:
                # ensure we are navigated to the last phase
                self._navigated_phase_index = len(self._current_execution_plan) - 1
                self._paused_phase_index = self._navigated_phase_index
        
        # show dialog on main thread
        QTimer.singleShot(50, lambda: self._show_droplet_detection_failure_dialog(
            expected_electrodes, detected_electrodes, missing_electrodes
        ))
        
        # emit pause signal
        self.signals.protocol_paused.emit()

    def _show_droplet_detection_failure_dialog(self, expected_electrodes, detected_electrodes, missing_electrodes):
        try:            
            dialog_action = DropletDetectionFailureDialogAction()
            
            parent_widget = self.parent()
            if not parent_widget:                
                parent_widget = QApplication.activeWindow()
            
            # Show dialog and get result
            result = dialog_action.perform(
                expected_electrodes, detected_electrodes, missing_electrodes, parent_widget
            )
            
            if result == QDialog.Accepted:
                # User chose to continue
                logger.info("User chose to continue despite droplet detection failure")
                # self._droplet_check_failed = False
                self._resume_after_droplet_dialog()
            else:
                logger.info("User chose to stay paused due to droplet detection failure")
                # stay paused - user can manually resume or stop
                self._remain_paused_after_droplet_dialog()
                
        except Exception as e:
            logger.error(f"Error showing droplet detection failure dialog: {e}")
            # if error, resume automatically to avoid getting stuck
            self._resume_after_droplet_dialog()

    def _remain_paused_after_droplet_dialog(self):
        self._droplet_check_failed = False

        # mark that we should skip droplet detection until phase navigation occurs
        self._droplet_check_skipped_until_phase_nav = True
        
        # remain paused
        self._status_timer.stop()
        
        logger.info("Remaining paused at step end - phase navigation enabled")

    def _resume_after_droplet_dialog(self):
        if not self._is_paused:
            return
        
        self._is_paused = False
        self._droplet_check_failed = False
        
        current_time = time.time()
        if self._pause_time:
            pause_duration = current_time - self._pause_time
            if self._start_time:
                self._start_time += pause_duration
            if self._step_start_time:
                self._step_start_time += pause_duration
        
        self._pause_time = None
        
        self._status_timer.start()

        # clear the skip flag since we are continuing from same phase
        self._droplet_check_skipped_until_phase_nav = False
        
        self._proceed_to_next_step()

    def _proceed_to_next_step(self):
        # reset step tracking
        self._current_execution_plan = []
        self._current_phase_index = 0
        self._total_step_phases_completed = 0
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0
        
        # clear droplet detection state
        self._waiting_for_droplet_check = False
        self._droplet_check_failed = False
        self._expected_electrodes_for_check = []
        
        self._current_index += 1
        
        if self._current_index >= len(self._run_order):
            self._on_protocol_finished()
        else:
            self._execute_next_step()

    def set_preview_mode(self, preview_mode):
        self._preview_mode = preview_mode

    def start(self):
        publish_message(topic=SET_REALTIME_MODE, message=str(True))
        
        if self._is_running:
            return
        self._is_running = True
        self._is_paused = False
        self._status_timer.start()
        self._current_index = 0
        self._current_protocol_repeat = 1
        if not hasattr(self, "_run_order") or not self._run_order:
            self._run_order = self.flatten_func(self.protocol_state)
        
        self._start_time = None
        self._elapsed_time = 0.0
        self._step_elapsed_time = 0.0
        self._step_start_time = None

        self._pause_time = None
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0
        self._total_step_phases_completed = 0
        self._step_phase_start_time = None
        
        total_steps = 0
        for entry in self._run_order:
            if entry["rep_idx"] == 1:
                total_steps += 1
        self._unique_step_count = total_steps

        if not self._run_order:
            self.signals.protocol_finished.emit()
            return
        
        # Start executing the protocol
        self._execute_next_step()

    def _qt_debounce_pause_resume(self, action_func):
        # store the action
        self._pending_pause_resume_action = action_func
        
        # reset timer - cancels any pending execution
        self._pause_resume_debounce_timer.stop()
        self._pause_resume_debounce_timer.start(self._debounce_delay_ms)

    def _execute_debounced_pause_resume(self):
        if self._pending_pause_resume_action:
            try:
                self._pending_pause_resume_action()
            except Exception as e:
                logger.error(f"Error in debounced pause/resume action: {e}")
            finally:
                self._pending_pause_resume_action = None

    def _internal_pause(self):
        if not self._is_running or self._is_paused:
            return
        self._is_paused = True
        current_time = time.time()
        self._pause_time = current_time
        self._status_timer.stop()
        self._timer.stop()
        self._phase_timer.stop()
        
        # store elapsed times at the moment of pause
        if self._start_time:
            self._elapsed_time = current_time - self._start_time
        if self._step_start_time:
            self._step_elapsed_time = current_time - self._step_start_time
        if self._phase_start_time:
            self._phase_elapsed_time = current_time - self._phase_start_time
        
        if self._current_phase_index > 0 and self._current_phase_index <= len(self._current_execution_plan):
            current_phase_item = self._current_execution_plan[self._current_phase_index - 1]
            phase_duration = current_phase_item["duration"]
            self._remaining_phase_time = max(0, phase_duration - self._phase_elapsed_time)
            self._was_in_phase = True
            self._paused_phase_index = self._current_phase_index - 1
        else:
            self._remaining_phase_time = 0.0
            self._was_in_phase = False
            self._paused_phase_index = self._current_phase_index
        
        # remaining step time
        if self._current_index < len(self._run_order):
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            total_step_time = PathExecutionService.calculate_step_execution_time(step, device_state)
            self._remaining_step_time = max(0, total_step_time - self._step_elapsed_time)
            logger.info(f"Paused with {self._remaining_step_time:.2f}s remaining for step (elapsed: {self._step_elapsed_time:.2f}s)")
        
        # track whether to maintain editability for advanced mode
        self._advanced_mode_editable_state = self._is_advanced_hardware_control
        
        # initialize phase navigation state
        self._original_pause_phase_index = max(0, self._current_phase_index - 1)
        self._navigated_phase_index = self._original_pause_phase_index
        self._phase_navigation_step_elapsed = self._step_elapsed_time
        self._original_step_time_remaining = self._remaining_step_time
        
        self.signals.protocol_paused.emit()

    def _internal_resume(self):
        if not self._is_running or not self._is_paused:
            return
        
        # check if we need to restore hardware state from advanced mode control
        if self._is_advanced_hardware_control:
            self._restore_hardware_state_on_resume()
        
        self._is_paused = False
        self._status_timer.start()
        
        current_time = time.time()
        
        if self._pause_time:
            pause_duration = current_time - self._pause_time
            
            if self._start_time:
                self._start_time += pause_duration
            if self._step_start_time:
                self._step_start_time += pause_duration
            if self._phase_start_time:
                self._phase_start_time += pause_duration

        if self._droplet_check_failed:
            self._droplet_check_failed = False
            
            # clear skip flag since we are continuing to next step
            self._droplet_check_skipped_until_phase_nav = False
            
            self._proceed_to_next_step()
            return
        
        # handle resuming from message rejection pause
        if hasattr(self, '_message_rejected_pause') and self._message_rejected_pause:
            self._message_rejected_pause = False
            
            # reset phase index to start from beginning of step
            self._current_phase_index = 0
            self._phase_start_time = None
            self._phase_elapsed_time = 0.0
            
            self._execute_next_phase()
            
            # restart step timer with full remaining time
            if self._remaining_step_time > 0:
                self._timer.start(int(self._remaining_step_time * 1000))
            
            self._pause_time = None
            self._was_in_phase = False
            
            # clear advanced mode editability state
            self._advanced_mode_editable_state = False
            
            # clear advanced hardware control state
            self._is_advanced_hardware_control = False
            self._paused_original_electrodes = {}
            
            return
        
        # handle phase navigation resume
        if self._phase_navigation_mode:
            # resume from navigated phase
            self._current_phase_index = self._navigated_phase_index
            
            # calculate remaining time based on phases left from navigated position
            if self._current_execution_plan:
                phases_remaining = len(self._current_execution_plan) - self._navigated_phase_index
                phase_duration = self._current_execution_plan[0]["duration"]  # all phases in a step have same duration
                new_remaining_time = phases_remaining * phase_duration                
            else:
                new_remaining_time = self._original_step_time_remaining
            
            # reset phase navigation state
            self._phase_navigation_mode = False
            self._original_pause_phase_index = 0
            self._navigated_phase_index = 0
            
            self._phase_start_time = None
            self._phase_elapsed_time = 0.0
            self._execute_next_phase()
            
            # restart step timer with adjusted time
            if new_remaining_time > 0:
                self._timer.start(int(new_remaining_time * 1000))
                logger.info(f"Resuming step from navigated phase with {new_remaining_time:.2f}s remaining")
            
        # check if navigated during pause (execution plan exists but no phases completed)
        elif (self._current_execution_plan and 
            self._current_phase_index == 0 and 
            self._total_step_phases_completed == 0 and
            not self._was_in_phase):
            
            # navigated during pause, start fresh from the beginning of this step
            logger.info("Resuming from navigated step - starting fresh execution")
            self._execute_next_step()
            
        elif self._was_in_phase and self._remaining_phase_time > 0:
            # Resume in the middle of a phase
            self._phase_start_time = current_time
            self._phase_elapsed_time = 0.0
            self._phase_timer.start(int(self._remaining_phase_time * 1000))
            logger.info(f"Resuming phase {self._paused_phase_index + 1} with {self._remaining_phase_time:.2f}s remaining")
            
            if self._remaining_step_time > 0:
                self._timer.start(int(self._remaining_step_time * 1000))
                logger.info(f"Resuming step with {self._remaining_step_time:.2f}s remaining")
                
        else:
            self._phase_start_time = None
            self._phase_elapsed_time = 0.0
            self._execute_next_phase()
            
            # restart step timer with remaining time
            if self._remaining_step_time > 0:
                self._timer.start(int(self._remaining_step_time * 1000))
                logger.info(f"Resuming step with {self._remaining_step_time:.2f}s remaining")
        
        self._pause_time = None
        self._was_in_phase = False
        
        # clear advanced mode editability state
        self._advanced_mode_editable_state = False
        
        # clear advanced hardware control state
        self._is_advanced_hardware_control = False
        self._paused_original_electrodes = {}

    def _restore_hardware_state_on_resume(self):
        if not self._paused_original_electrodes or self._preview_mode:
            return
        
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
        if not device_state:
            device_state = PathExecutionService.get_empty_device_state()
        
        # hardware correction message to restore expected electrode state
        hardware_message = PathExecutionService.create_hardware_electrode_message(
            device_state, 
            self._paused_original_electrodes
        )
        
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=hardware_message)
        
    def pause(self, advanced_mode=False, preview_mode=False):
        
        # store advanced mode state for pause handling
        self._is_advanced_hardware_control = advanced_mode and not preview_mode
        
        # store original electrode state if advanced hardware control is enabled
        if self._is_advanced_hardware_control:
            self._paused_original_electrodes = self._get_current_phase_electrodes()
        
        # execute pause
        self._qt_debounce_pause_resume(self._internal_pause)
        
        # publish advanced mode message after pause if conditions are met
        if self._is_advanced_hardware_control:
            # QTimer to ensure it happens after the pause is processed
            QTimer.singleShot(100, self._publish_advanced_pause_message)

    def resume(self, advanced_mode=False, preview_mode=False):
        self._qt_debounce_pause_resume(self._internal_resume)

    def stop(self):
        publish_message(topic=SET_REALTIME_MODE, message=str(False))

        if hasattr(self, '_current_message_dialog'):
            self._current_message_dialog.close()
            delattr(self, '_current_message_dialog')
        
        if hasattr(self, '_current_completion_dialog'):
            self._current_completion_dialog.close()
            delattr(self, '_current_completion_dialog')
        
        self._pause_for_message_display = False
        self._message_waiting_for_response = False
        self._message_rejected_pause = False
        if hasattr(self, '_message_dialog_step_info'):
            delattr(self, '_message_dialog_step_info')
        
        self._cleanup_message_dialog_timing()
        
        # clear advanced mode editability state
        self._advanced_mode_editable_state = False
        
        self._was_advanced_hardware_mode = False
        
        # send final message of the step that was being executed before stopped
        if self._is_running and self._current_index < len(self._run_order):
            current_step_info = self._run_order[self._current_index]
            current_step = current_step_info["step"]
            
            device_state = current_step.device_state if hasattr(current_step, 'device_state') and current_step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            step_uid = current_step.parameters.get("UID", "")
            step_description = current_step.parameters.get("Description", "Step")
            step_id = current_step.parameters.get("ID", "")
            
            msg_model = PathExecutionService.create_dynamic_device_state_message(
                device_state, 
                device_state.activated_electrodes,
                step_uid,
                step_description,
                step_id
            )
            
            msg_model.editable = True
            
            publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
                        
            if not self._preview_mode:
                deactivated_hardware_message = PathExecutionService.create_deactivated_hardware_electrode_message(device_state)
                
                publish_message(topic=ELECTRODES_STATE_CHANGE, message=deactivated_hardware_message)
            
            # select the current step that was being executed
            if step_uid:
                self.signals.select_step.emit(step_uid)

        # VoltageFrequencyService.publish_default_voltage_frequency(self._preview_mode)
        
        self._is_running = False
        self._is_paused = False
        self._status_timer.stop()
        self._timer.stop()
        self._phase_timer.stop()
        
        self._current_index = 0
        self._run_order = []
        self._start_time = None
        self._step_start_time = None
        self._elapsed_time = 0.0
        self._step_elapsed_time = 0.0
        self._current_step_timer = None
        self._current_execution_plan = []
        self._current_phase_index = 0
        self._step_repetition_info = {}

        self._pause_time = None
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0
        self._total_step_phases_completed = 0
        self._step_phase_start_time = None
        self._unique_step_count = 0
        
        # clear advanced mode state
        self._is_advanced_hardware_control = False
        self._paused_original_electrodes = {}

        # clear phase navigation state
        self._phase_navigation_mode = False
        self._original_pause_phase_index = 0
        self._navigated_phase_index = 0
        self._phase_navigation_step_elapsed = 0.0
        self._original_step_time_remaining = 0.0

        # clear droplet detection state
        self._droplet_check_enabled = False
        self._waiting_for_droplet_check = False
        self._droplet_check_failed = False
        self._expected_electrodes_for_check = []

        # clear droplet detection tracking
        self._droplet_check_attempted_for_step = {}
        self._droplet_check_skipped_until_phase_nav = False

        # stop volume threshold monitoring
        self._volume_threshold_service.stop_monitoring()
        self._volume_threshold_mode_active = False
        self._current_phase_volume_threshold = 0.0
        self._current_phase_target_capacitance = None

    def set_repeat_protocol_n(self, n):
        self._repeat_protocol_n = max(1, int(n))

    def set_run_order(self, run_order):
        self._run_order = run_order

    def _execute_next_step(self):
        if self._is_paused or not self._is_running:
            return
        
        if self._current_index >= len(self._run_order):
            self._on_protocol_finished()
            return
        
        # update data logger context
        if hasattr(self, '_data_logger') and self._data_logger:
            context = self._get_current_logging_context()
            if context:
                self._data_logger.set_protocol_context(context)

        try:
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            path = step_info["path"]
            rep_idx, rep_total = step_info["rep_idx"], step_info["rep_total"]

            logger.info(f"Executing step {self._current_index + 1}/{len(self._run_order)}: "
                        f"{step.parameters.get('Description', 'Step')} (rep {rep_idx}/{rep_total})")
            
            self.signals.highlight_step.emit(path)
            
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            logger.info(f"Executing step {self._current_index + 1} with device state: {device_state}")
            
            self._current_execution_plan = PathExecutionService.calculate_step_execution_plan(step, device_state)
            self._current_phase_index = 0
            self._total_step_phases_completed = 0
            self._step_repetition_info = PathExecutionService.calculate_step_repetition_info(step, device_state)
            
            current_time = time.time()
            
            # if first step, synchronize total timer and step timer
            if self._start_time is None:
                self._start_time = current_time
            
            self._step_start_time = current_time
            self._step_phase_start_time = current_time
            self._step_elapsed_time = 0.0
            self._phase_start_time = None
            self._phase_elapsed_time = 0.0
            self._remaining_step_time = 0.0
            self._remaining_phase_time = 0.0
            self._was_in_phase = False
            self._paused_phase_index = 0

            VoltageFrequencyService.publish_step_voltage_frequency(step, self._preview_mode)
            step_timeout = PathExecutionService.calculate_step_execution_time(step, device_state)
            
            self._timer.timeout.disconnect()
            self._timer.timeout.connect(self._on_step_timeout)
            self._timer.start(int(step_timeout * 1000))
            
            logger.info(f"Started step timer for {step_timeout:.2f} seconds with {len(self._current_execution_plan)} phases")
            
            # check for Message first BEFORE any phase execution
            message = step.parameters.get("Message", "")
            if message and message.strip():
                # publish individual electrodes first, then message pop-up
                self._show_individual_electrodes_and_message(step, device_state)
            else:
                self._execute_next_phase()
            
        except Exception as e:
            logger.error(f"Error executing step: {e}")
            self.signals.protocol_error.emit(str(e))
            self.stop()

    def _execute_next_phase(self):
        if self._is_paused or not self._is_running:
            return
        
        if hasattr(self, '_pause_for_message_display') and self._pause_for_message_display:
            return
        
        if hasattr(self, '_message_waiting_for_response') and self._message_waiting_for_response:
            return
            
        if self._current_phase_index >= len(self._current_execution_plan):
            self._on_step_completed_by_phases()
            return
        
        # update data logger context for current phase
        if hasattr(self, '_data_logger') and self._data_logger:
            context = self._get_current_logging_context()
            if context:
                self._data_logger.set_protocol_context(context)
            
        try:
            plan_item = self._current_execution_plan[self._current_phase_index]
            
            logger.info(f"Executing phase {self._current_phase_index + 1}/{len(self._current_execution_plan)}: {plan_item['activated_electrodes']}")
            
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()

            # check for volume threshold mode
            try:
                volume_threshold = float(step.parameters.get("Volume Threshold", "0.0"))
            except (ValueError, TypeError):
                volume_threshold = 0.0
            
            self._current_phase_volume_threshold = volume_threshold
            self._volume_threshold_mode_active = volume_threshold > 0.0
            
            # create and publish message immediately
            msg_model = PathExecutionService.create_dynamic_device_state_message(
                device_state, 
                plan_item["activated_electrodes"], 
                plan_item["step_uid"],
                plan_item["step_description"],
                plan_item["step_id"]
            )
            
            if self._advanced_mode_editable_state:
                msg_model.step_info["free_mode"] = True
                msg_model.editable = True
            
            publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
                        
            if not self._preview_mode:
                hardware_message = PathExecutionService.create_hardware_electrode_message(
                    device_state, 
                    plan_item["activated_electrodes"]
                )
                
                publish_message(topic=ELECTRODES_STATE_CHANGE, message=hardware_message)

            # track phase timing
            current_time = time.time()
            self._phase_start_time = current_time
            self._phase_elapsed_time = 0.0
            self._current_phase_index += 1
            
            duration_ms = int(plan_item["duration"] * 1000)

            # start volume threshold monitoring if enabled
            if self._volume_threshold_mode_active and not self._preview_mode:
                target_capacitance = self._volume_threshold_service.calculate_target_capacitance(
                    volume_threshold,
                    plan_item["activated_electrodes"],
                    self.protocol_state
                )
                
                if target_capacitance is not None:
                    self._current_phase_target_capacitance = target_capacitance
                    monitoring_started = self._volume_threshold_service.start_monitoring(
                        target_capacitance, 
                        plan_item["duration"]
                    )
                    if monitoring_started:
                        logger.info(f"Volume threshold mode active for phase: {volume_threshold}, "
                                f"target capacitance: {target_capacitance}pF")
                    else:
                        logger.warning("Failed to start volume threshold monitoring")
                        self._volume_threshold_mode_active = False
                else:
                    logger.warning("Could not calculate target capacitance, disabling volume threshold mode for this phase")
                    self._volume_threshold_mode_active = False

            self._phase_timer.start(duration_ms)
                           
        except Exception as e:
            logger.error(f"Error in phase execution: {e}")
            self.signals.protocol_error.emit(str(e))

    def _on_volume_threshold_reached(self):
        """Handle early phase completion when volume threshold is reached."""
        if not self._is_running or self._is_paused:
            return
            
        if not self._volume_threshold_mode_active:
            return
        
        logger.info(f"Volume threshold reached, advancing phase early")
        
        # since we are advancing early
        self._phase_timer.stop()
        
        # Update phase timing for early completion
        current_time = time.time()
        if self._phase_start_time:
            self._phase_elapsed_time = current_time - self._phase_start_time
        
        self._total_step_phases_completed += 1
        
        # Reset threshold monitoring state
        self._volume_threshold_mode_active = False
        self._current_phase_target_capacitance = None
        
        # Continue to next phase
        self._execute_next_phase()

    def jump_to_step_by_path(self, step_path):
        if not self._is_running or not self._run_order:
            return False
        
        target_index = self.get_run_order_index_by_path(step_path)
        if target_index == -1:
            logger.warning(f"Could not find step with path {step_path} in run_order")
            return False
                
        self._timer.stop()
        self._phase_timer.stop()
        
        current_time = time.time()
        if self._step_start_time:
            self._step_elapsed_time = current_time - self._step_start_time
        if self._start_time:
            self._elapsed_time = current_time - self._start_time
        
        self._current_index = target_index

        # clear droplet detection tracking for navigation
        self._droplet_check_skipped_until_phase_nav = False
        
        self._current_execution_plan = []
        self._current_phase_index = 0
        self._total_step_phases_completed = 0
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0
        
        # clear advanced mode state when jumping
        self._is_advanced_hardware_control = False
        self._paused_original_electrodes = {}
        
        if not self._is_paused:
            self._execute_next_step()
        else:
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            path = step_info["path"]
            self.signals.highlight_step.emit(path)
            
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            self._current_execution_plan = PathExecutionService.calculate_step_execution_plan(step, device_state)
            self._step_repetition_info = PathExecutionService.calculate_step_repetition_info(step, device_state)
            
            if self._current_execution_plan:
                first_phase = self._current_execution_plan[0]
                
                msg_model = PathExecutionService.create_dynamic_device_state_message(
                    device_state, 
                    first_phase["activated_electrodes"], 
                    first_phase["step_uid"],
                    first_phase["step_description"],
                    first_phase["step_id"]
                )
                
                msg_model.editable = True
                
                publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
                                    
        return True
    
    def get_current_step_path(self):
        if not self._is_running or self._current_index >= len(self._run_order):
            return None
        
        step_info = self._run_order[self._current_index]
        return step_info["path"]

    def get_run_order_index_by_path(self, step_path):
        for i, step_info in enumerate(self._run_order):
            if step_info["path"] == step_path:
                return i
        return -1
    
    def _get_current_phase_electrodes(self):
        if not self._is_running or self._current_index >= len(self._run_order):
            return {}
        
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
        if not device_state:
            device_state = PathExecutionService.get_empty_device_state()
        
        if not self._current_execution_plan:
            self._current_execution_plan = PathExecutionService.calculate_step_execution_plan(step, device_state)
        
        current_phase_electrodes = {}
        
        if self._current_phase_index > 0 and self._current_phase_index <= len(self._current_execution_plan):
            # middle of executing a phase
            current_phase_item = self._current_execution_plan[self._current_phase_index - 1]
            current_phase_electrodes = current_phase_item["activated_electrodes"].copy()
        elif self._current_execution_plan:
            # havent started any phases yet, use the first phase
            first_phase = self._current_execution_plan[0]
            current_phase_electrodes = first_phase["activated_electrodes"].copy()
        else:
            # no execution plan, use individual electrodes only
            current_phase_electrodes = device_state.activated_electrodes.copy()
        
        return current_phase_electrodes
    
    def _get_final_phase_electrodes(self, step, device_state):
        """get electrodes that should be active in the final phase of the step."""
        target_electrodes = {}
        
        # individual electrodes
        target_electrodes.update(device_state.activated_electrodes)
        
        # electrodes from the last phase of paths/loops if any
        if device_state.has_paths() and self._current_execution_plan:
            last_phase = self._current_execution_plan[-1]
            last_phase_electrodes = last_phase["activated_electrodes"]
            target_electrodes.update(last_phase_electrodes)
        
        return target_electrodes
    
    def _get_expected_droplet_channels(self, step, device_state):
        """Get the channels where droplets are expected to be detected."""
        expected_channels = set()
        
        # individually activated electrodes
        for electrode_id, activated in device_state.activated_electrodes.items():
            if activated and electrode_id in device_state.id_to_channel:
                channel = device_state.id_to_channel[electrode_id]
                expected_channels.add(channel)
        
        # include electrodes from the final phase of all paths/loops
        if device_state.has_paths() and self._current_execution_plan:
            from protocol_grid.services.path_execution_service import PathExecutionService
            
            # channels from the final overall phase
            if self._current_execution_plan:
                final_phase = self._current_execution_plan[-1]
                final_phase_electrodes = final_phase.get("activated_electrodes", {})
                
                for electrode_id, activated in final_phase_electrodes.items():
                    if activated and electrode_id in device_state.id_to_channel:
                        channel = device_state.id_to_channel[electrode_id]
                        expected_channels.add(channel)
            
            # also include electrodes from the last phase of each individual path/loop
            # in case some paths finished earlier than others
            last_phase_electrodes = self._get_individual_path_last_phase_electrodes(step, device_state)
            
            for electrode_id in last_phase_electrodes:
                if electrode_id in device_state.id_to_channel:
                    channel = device_state.id_to_channel[electrode_id]
                    expected_channels.add(channel)
        
        return list(expected_channels)
    
    def _get_individual_path_last_phase_electrodes(self, step, device_state):
        """Get electrodes that are active in the last phase of each individual path/loop."""
        last_phase_electrodes = set()
        
        if not device_state.has_paths():
            return last_phase_electrodes
        
        # get required step parameters
        trail_length = int(step.parameters.get("Trail Length", "1"))
        trail_overlay = int(step.parameters.get("Trail Overlay", "0"))
        
        # calculate effective repetitions and phases for each path
        for i, path in enumerate(device_state.paths):
            is_loop = PathExecutionService.is_loop_path(path)
            
            if is_loop:
                cycle_phases = PathExecutionService.calculate_loop_cycle_phases(path, trail_length, trail_overlay)
                cycle_length = len(cycle_phases)
                
                if cycle_length > 0:
                    # loop path: first phase will always be the same as last phase
                    electrode_indices = cycle_phases[0]
            else:
                # for open paths: get electrodes from the final phase
                cycle_phases = PathExecutionService.calculate_trail_phases_for_path(path, trail_length, trail_overlay)
                
                if cycle_phases:
                    # last phase
                    electrode_indices = cycle_phases[-1]
                    
            # convert electrode indices to electrode IDs
            for electrode_idx in electrode_indices:
                if electrode_idx < len(path):
                    electrode_id = path[electrode_idx]
                    last_phase_electrodes.add(electrode_id)
        
        return last_phase_electrodes
    
    def _publish_advanced_pause_message(self):
        if not self._is_running or self._current_index >= len(self._run_order):
            return
        
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
        if not device_state:
            device_state = PathExecutionService.get_empty_device_state()
        
        step_uid = step.parameters.get("UID", "")
        step_description = step.parameters.get("Description", "Step")
        step_id = step.parameters.get("ID", "")
        
        current_electrodes = self._get_current_phase_electrodes()
        
        msg_model = PathExecutionService.create_dynamic_device_state_message(
            device_state, 
            current_electrodes,
            step_uid,
            step_description,
            step_id
        )
        
        msg_model.step_info["free_mode"] = True
        msg_model.editable = True
        
        # re-set the advanced mode editability state, for safety
        self._advanced_mode_editable_state = True
        
        publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
        
    def _on_phase_timeout(self):
        if not self._is_running or self._is_paused:
            return
        
        # if we were in volume threshold mode, warn if threshold not met
        if self._volume_threshold_mode_active:
            logger.info(f"Phase completed by duration timeout - volume threshold not reached "
                    f"(target: {self._current_phase_target_capacitance}pF)")
            # Stop monitoring since phase completed by timeout
            self._volume_threshold_service.stop_monitoring()
            self._volume_threshold_mode_active = False
            self._current_phase_target_capacitance = None
            
        self._total_step_phases_completed += 1
        
        # reset phase timing
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        
        self._execute_next_phase()

    def _on_step_completed_by_phases(self):
        if not self._is_running or self._is_paused:
            return
        
        logger.info(f"Step completed by phases - all {self._total_step_phases_completed} phases finished")
        
        self._timer.stop()
        self._phase_timer.stop()
        
        if self._step_start_time:
            current_time = time.time()
            self._step_elapsed_time = current_time - self._step_start_time
            
            if self._start_time:
                self._elapsed_time = current_time - self._start_time

        # perform droplet detection 
        logger.info(f"should perform droplet check? {self._should_perform_droplet_check()}")
        if self._should_perform_droplet_check():
            self._perform_droplet_detection_check()
        else:
            self._proceed_to_next_step() 

    def _on_step_timeout(self):
        if not self._is_running or self._is_paused:
            return
                
        if self._current_phase_index < len(self._current_execution_plan):
            # force completion of remaining phases
            self._current_phase_index = len(self._current_execution_plan)
            self._execute_next_phase()
        else:
            self._on_step_completed_by_phases()

    def _on_protocol_finished(self):
        publish_message(topic=SET_REALTIME_MODE, message=str(False))

        # message with last executed step
        if self._current_index > 0 and self._current_index <= len(self._run_order):
            last_step_info = self._run_order[self._current_index - 1]
            last_step = last_step_info["step"]
            
            device_state = last_step.device_state if hasattr(last_step, 'device_state') and last_step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            step_uid = last_step.parameters.get("UID", "")
            step_description = last_step.parameters.get("Description", "Step")
            step_id = last_step.parameters.get("ID", "")
            
            msg_model = PathExecutionService.create_dynamic_device_state_message(
                device_state, 
                device_state.activated_electrodes,
                step_uid,
                step_description,
                step_id
            )
            
            msg_model.editable = True
            
            publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
                        
            if not self._preview_mode:
                deactivated_hardware_message = PathExecutionService.create_deactivated_hardware_electrode_message(device_state)
                
                publish_message(topic=ELECTRODES_STATE_CHANGE, message=deactivated_hardware_message)
            
            # select the last executed step
            if step_uid:
                self.signals.select_step.emit(step_uid)
        
        self._is_running = False
        self._status_timer.stop()
        self._timer.stop()
        self._phase_timer.stop()
        
        # if self._should_show_completion_dialog():
        #     self._show_experiment_complete_dialog()
        
        self.signals.protocol_finished.emit()

    def _emit_status_update(self):
        if not self._is_running or not self._run_order:
            return
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        rep_idx, rep_total = step_info["rep_idx"], step_info["rep_total"]
        
        current_step_position = 0
        for i, entry in enumerate(self._run_order):
            if entry["rep_idx"] == 1:
                current_step_position += 1
                if i >= self._current_index:
                    break
        
        step_total = self._unique_step_count
        step_idx = current_step_position
        
        current_time = time.time()
        
        if self._is_paused:
            total_time = self._elapsed_time
            if self._phase_navigation_mode:
                # calculate time to reach the navigated phase
                phases_moved = self._navigated_phase_index - self._original_pause_phase_index
                if self._current_execution_plan:
                    phase_duration = self._current_execution_plan[0]["duration"]
                    step_time = self._phase_navigation_step_elapsed + (phases_moved * phase_duration)
                else:
                    step_time = self._step_elapsed_time
            else:
                step_time = self._step_elapsed_time
        else:
            if self._start_time and self._step_start_time:
                total_time = current_time - self._start_time
                step_time = current_time - self._step_start_time
            else:
                total_time = 0.0
                step_time = 0.0
        
        if self._phase_navigation_mode:
            # calculate repetition based on navigated phase
            current_repetition, total_repetitions = self._calculate_repetition_for_phase(self._navigated_phase_index)
        else:
            current_repetition, total_repetitions = self._calculate_current_repetition()
        
        status = {
            "total_time": total_time,
            "step_time": step_time,
            "step_idx": step_idx,
            "step_total": step_total,
            "step_rep_idx": current_repetition,
            "step_rep_total": total_repetitions,
            "recent_step": self._run_order[self._current_index - 1]["step"].parameters.get("Description", "-")
                if self._current_index > 0 else "-",
            "next_step": self._run_order[self._current_index + 1]["step"].parameters.get("Description", "-")
                if self._current_index + 1 < len(self._run_order) else "-",
            "protocol_repeat_idx": self._current_protocol_repeat,
            "protocol_repeat_total": self._repeat_protocol_n
        }
        self.signals.update_status.emit(status)

    def _calculate_current_repetition(self):
        """calculate current repetition based on largest loop cycle."""
        if not hasattr(self, '_step_repetition_info') or not self._step_repetition_info:
            return 1, 1
        
        max_cycle_length = self._step_repetition_info.get('max_cycle_length', 1)
        max_effective_repetitions = self._step_repetition_info.get('max_effective_repetitions', 1)
        
        if max_cycle_length <= 0 or max_effective_repetitions <= 1:
            return 1, 1
        
        current_phase = max(0, self._current_phase_index - 1)
        
        if max_effective_repetitions > 1:
            if current_phase < (max_effective_repetitions - 1) * max_cycle_length:
                current_repetition = (current_phase // max_cycle_length) + 1
            else: # last repetition
                current_repetition = max_effective_repetitions
        else:
            current_repetition = 1
        
        return current_repetition, max_effective_repetitions
    
    def _calculate_repetition_for_phase(self, phase_index):
        if not hasattr(self, '_step_repetition_info') or not self._step_repetition_info:
            return 1, 1
        
        max_cycle_length = self._step_repetition_info.get('max_cycle_length', 1)
        max_effective_repetitions = self._step_repetition_info.get('max_effective_repetitions', 1)
        
        if max_cycle_length <= 0 or max_effective_repetitions <= 1:
            return 1, 1
        
        if max_effective_repetitions > 1:
            if phase_index < (max_effective_repetitions - 1) * max_cycle_length:
                current_repetition = (phase_index // max_cycle_length) + 1
            else: # last repetition
                current_repetition = max_effective_repetitions
        else:
            current_repetition = 1
        
        return current_repetition, max_effective_repetitions

    def is_running(self):
        return self._is_running and not self._is_paused

    def is_paused(self):
        return self._is_paused

    def _show_individual_electrodes_and_message(self, step, device_state):
        step_uid = step.parameters.get("UID", "")
        step_description = step.parameters.get("Description", "Step")
        step_id = step.parameters.get("ID", "")
        
        # publish message with ONLY individual electrodes (no paths/loops)
        msg_model = PathExecutionService.create_dynamic_device_state_message(
            device_state, 
            device_state.activated_electrodes,
            step_uid,
            step_description,
            step_id
        )
        
        publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
        
        if not self._preview_mode:
            hardware_message = PathExecutionService.create_hardware_electrode_message(
                device_state, 
                device_state.activated_electrodes
            )
            publish_message(topic=ELECTRODES_STATE_CHANGE, message=hardware_message)
                
        self._pause_for_message_display = True
        self._message_waiting_for_response = True
        self._pause_timers_for_message()
        
        message_text = step.parameters.get("Message", "").strip()
        if step_description and step_description != "Step":
            step_info = f"Step: {step_description} (ID: {step_id})"
        else:
            step_info = f"Step ID: {step_id}" if step_id else "Step"
        
        self._message_dialog_step_info = (message_text, step_info)
        
        # QTimer to create dialog on main thread
        QTimer.singleShot(50, self._create_and_show_message_dialog)

    def _pause_timers_for_message(self):
        current_time = time.time()
        
        # store current elapsed times
        if self._start_time:
            self._message_dialog_total_elapsed = current_time - self._start_time
        else:
            self._message_dialog_total_elapsed = 0.0
            
        if self._step_start_time:
            self._message_dialog_step_elapsed = current_time - self._step_start_time
        else:
            self._message_dialog_step_elapsed = 0.0
            
        if self._phase_start_time:
            self._message_dialog_phase_elapsed = current_time - self._phase_start_time
        else:
            self._message_dialog_phase_elapsed = 0.0
        
        # store remaining times from active timers
        if self._timer.isActive():
            self._message_dialog_step_remaining = self._timer.remainingTime() / 1000.0
            self._timer.stop()
        else:
            self._message_dialog_step_remaining = 0.0
            
        if self._phase_timer.isActive():
            self._message_dialog_phase_remaining = self._phase_timer.remainingTime() / 1000.0
            self._phase_timer.stop()
        else:
            self._message_dialog_phase_remaining = 0.0
        
        # stop status timer to freeze status bar
        self._status_timer.stop()
        
    def _resume_timers_for_message(self):
        current_time = time.time()
        
        # adjust times to account for the message dialog pause duration
        if hasattr(self, '_message_dialog_total_elapsed'):
            if self._start_time:
                self._start_time = current_time - self._message_dialog_total_elapsed
            
        if hasattr(self, '_message_dialog_step_elapsed'):
            if self._step_start_time:
                self._step_start_time = current_time - self._message_dialog_step_elapsed
                
        if hasattr(self, '_message_dialog_phase_elapsed'):
            if self._phase_start_time:
                self._phase_start_time = current_time - self._message_dialog_phase_elapsed
        
        # resume step timer if it was active
        if hasattr(self, '_message_dialog_step_remaining') and self._message_dialog_step_remaining > 0:
            self._timer.start(int(self._message_dialog_step_remaining * 1000))
            
        # resume phase timer if it was active
        if hasattr(self, '_message_dialog_phase_remaining') and self._message_dialog_phase_remaining > 0:
            self._phase_timer.start(int(self._message_dialog_phase_remaining * 1000))
        
        # resume status timer
        self._status_timer.start()
        
        self._cleanup_message_dialog_timing()
        
    def _create_and_show_message_dialog(self):
        if not hasattr(self, '_message_dialog_step_info') or not self._message_dialog_step_info:
            return
        
        try:
            # importing here to avoid circular imports
            from protocol_grid.extra_ui_elements import StepMessageDialog
            
            message, step_info = self._message_dialog_step_info
            
            # set the main widget as parent
            parent_widget = self.parent()
            
            # create dialog with YES/NO buttons and connect to response method
            self._current_message_dialog = StepMessageDialog(message, step_info, parent_widget)
            self._current_message_dialog.finished.connect(self._on_message_dialog_response)
            self._current_message_dialog.show_message()
                        
        except Exception as e:
            logger.error(f"Failed to show step message dialog: {e}")
            self._pause_for_message_display = False
            self._message_waiting_for_response = False
            self._resume_timers_for_message()
            self._execute_next_phase()

    def _cleanup_message_dialog_timing(self):
        for attr in ['_message_dialog_total_elapsed', '_message_dialog_step_elapsed', 
                    '_message_dialog_phase_elapsed', '_message_dialog_step_remaining', 
                    '_message_dialog_phase_remaining']:
            if hasattr(self, attr):
                delattr(self, attr)

    def _cleanup_message_dialog_state(self):
        if hasattr(self, '_current_message_dialog'):
            delattr(self, '_current_message_dialog')
        if hasattr(self, '_message_dialog_step_info'):
            delattr(self, '_message_dialog_step_info')

    def _on_message_dialog_response(self, result):               
        self._pause_for_message_display = False
        
        if result == QDialog.Accepted: # YES button pressed
            self._message_waiting_for_response = False
            
            self._resume_timers_for_message()
            
            self._cleanup_message_dialog_state()
            
            # continue phase execution if protocol still running and NOT manually paused
            if self._is_running and not self._is_paused:
                QTimer.singleShot(10, self._execute_next_phase)
        else:  # NO button pressed or dialog closed            
            self._resume_timers_for_message()
            
            # set pause state manually
            self._is_paused = True
            self._pause_time = time.time()
            
            # flags to wait for manual resume after message rejection
            self._message_waiting_for_response = False
            self._message_rejected_pause = True
            
            self._cleanup_message_dialog_state()
            
            # emit paused signal to update UI
            self.signals.protocol_paused.emit()

    def can_navigate_phases(self):
        if not self._is_running or self._current_index >= len(self._run_order):
            return False
        
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
        
        if not device_state:
            return False
        
        return device_state.has_paths()

    def get_phase_navigation_info(self):
        if not self._current_execution_plan:
            return {"current_phase": 1, "total_phases": 1, "can_navigate": False}
        
        return {
            "current_phase": self._navigated_phase_index + 1 if self._phase_navigation_mode else self._current_phase_index,
            "total_phases": len(self._current_execution_plan),
            "can_navigate": self.can_navigate_phases()
        }
    
    def navigate_to_previous_phase(self):
        if not self._is_paused or not self._current_execution_plan:
            return False
        
        if self._navigated_phase_index > 0:
            self._navigated_phase_index -= 1
            self._phase_navigation_mode = True

            # clear droplet check skip flag - phase navigation resets droplet detection
            if self._droplet_check_skipped_until_phase_nav:
                self._droplet_check_skipped_until_phase_nav = False

            self._publish_phase_navigation_state()
            logger.info(f"Navigated to previous phase: {self._navigated_phase_index + 1}/{len(self._current_execution_plan)}")
            return True
        
        return False

    def navigate_to_next_phase(self):
        if not self._is_paused or not self._current_execution_plan:
            return False
        
        if self._navigated_phase_index < len(self._current_execution_plan) - 1:
            if self._message_rejected_pause:
                self._navigated_phase_index = 0
                self._message_rejected_pause = False
            else:
                self._navigated_phase_index += 1
            self._phase_navigation_mode = True
            self._publish_phase_navigation_state()
            logger.info(f"Navigated to next phase: {self._navigated_phase_index + 1}/{len(self._current_execution_plan)}")
            return True
        
        return False

    def _publish_phase_navigation_state(self):
        if not self._current_execution_plan or not self._is_paused:
            return
        
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
        if not device_state:
            device_state = PathExecutionService.get_empty_device_state()
        
        plan_item = self._current_execution_plan[self._navigated_phase_index]
        
        msg_model = PathExecutionService.create_dynamic_device_state_message(
            device_state, 
            plan_item["activated_electrodes"], 
            plan_item["step_uid"],
            plan_item["step_description"],
            plan_item["step_id"]
        )
        
        # editable if in advanced mode
        if self._advanced_mode_editable_state:
            msg_model.step_info["free_mode"] = True
            msg_model.editable = True
        
        publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
        
        # hardware message if not in preview mode
        if not self._preview_mode:
            hardware_message = PathExecutionService.create_hardware_electrode_message(
                device_state, 
                plan_item["activated_electrodes"]
            )
            publish_message(topic=ELECTRODES_STATE_CHANGE, message=hardware_message)
        
    def set_advanced_hardware_mode(self, advanced_mode, preview_mode):
        self._was_advanced_hardware_mode = advanced_mode and not preview_mode

    def update_step_voltage_frequency_in_plan(self, step_uid, new_voltage, new_frequency):
        if not self._is_running or not self._run_order:
            return False
        
        target_step_index = -1
        for i, step_info in enumerate(self._run_order):
            step = step_info["step"]
            if step.parameters.get("UID", "") == step_uid:
                target_step_index = i
                break
        
        if target_step_index == -1:
            return False
        
        # update the step parameters
        target_step = self._run_order[target_step_index]["step"]
        target_step.parameters["Voltage"] = str(new_voltage)
        target_step.parameters["Frequency"] = str(new_frequency)
        
        # if its the currently running step, publish immediately
        if target_step_index == self._current_index:
            VoltageFrequencyService.publish_immediate_voltage_frequency(
                str(new_voltage), str(new_frequency), self._preview_mode
            )
            logger.info(f"Updated voltage/frequency for currently running step: {new_voltage}V, {new_frequency}Hz")
        else:
            logger.info(f"Updated voltage/frequency for upcoming step: {new_voltage}V, {new_frequency}Hz")
        
        return True
