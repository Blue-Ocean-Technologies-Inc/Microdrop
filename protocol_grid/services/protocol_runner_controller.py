import dramatiq
import time
import uuid
import json
from typing import List, Dict, Any
import threading

from PySide6.QtCore import QObject, Signal, QTimer

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from protocol_grid.services.path_execution_service import PathExecutionService
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE
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

        # throttling
        self._last_pause_resume_time = 0.0
        self._pause_resume_throttle_delay = 0.7

    def set_preview_mode(self, preview_mode):
        self._preview_mode = preview_mode

    def start(self):
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

    def pause(self):
        current_time = time.time()        
        # check if enough time has passed since last pause/resume
        if current_time - self._last_pause_resume_time < self._pause_resume_throttle_delay:
            return
        
        self._last_pause_resume_time = current_time
        
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
        
        self.signals.protocol_paused.emit()

    def resume(self):
        current_time = time.time()        
        # check if enough time has passed since last pause/resume
        if current_time - self._last_pause_resume_time < self._pause_resume_throttle_delay:
            return
        
        self._last_pause_resume_time = current_time
        
        if not self._is_running or not self._is_paused:
            return
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
        
        # check if navigated during pause (execution plan exists but no phases completed)
        if (self._current_execution_plan and 
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

    def stop(self):
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
            
            logger.info(f"Published final stop message to device viewer: {msg_model.serialize()}")
            
            if not self._preview_mode:
                deactivated_hardware_message = PathExecutionService.create_deactivated_hardware_electrode_message(device_state)
                
                publish_message(topic=ELECTRODES_STATE_CHANGE, message=deactivated_hardware_message)
            
            # select the current step that was being executed
            if step_uid:
                self.signals.select_step.emit(step_uid)
        
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
        
        try:
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            path = step_info["path"]
            
            self.signals.highlight_step.emit(path)
            
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            logger.info(f"Executing step {step.parameters.get('ID', 'Unknown')} with device state: {device_state}")
            
            # recalculate execution plan if it doesn't exist (new step or first time)
            if not self._current_execution_plan:
                self._current_execution_plan = PathExecutionService.calculate_step_execution_plan(step, device_state)
                self._current_phase_index = 0
                self._total_step_phases_completed = 0
                
                self._step_repetition_info = PathExecutionService.calculate_step_repetition_info(step, device_state)
            
            current_time = time.time()
            
            # if first step, synchronize total timer and step timer
            if self._start_time is None:
                self._start_time = current_time
                logger.info("Starting total timer synchronized with first step")
            
            self._step_start_time = current_time
            self._step_phase_start_time = current_time
            self._step_elapsed_time = 0.0
            self._phase_start_time = None
            self._phase_elapsed_time = 0.0
            self._remaining_step_time = 0.0
            self._remaining_phase_time = 0.0
            self._was_in_phase = False
            self._paused_phase_index = 0

            step_timeout = PathExecutionService.calculate_step_execution_time(step, device_state)
            
            self._timer.timeout.disconnect()
            self._timer.timeout.connect(self._on_step_timeout)
            self._timer.start(int(step_timeout * 1000))
                        
            self._execute_next_phase()
            
        except Exception as e:
            logger.error(f"Error executing step: {e}")
            self.signals.protocol_error.emit(str(e))
            self.stop()

    def _execute_next_phase(self):
        if self._is_paused or not self._is_running:
            return
            
        if self._current_phase_index >= len(self._current_execution_plan):
            self._on_step_completed_by_phases()
            return
            
        try:
            plan_item = self._current_execution_plan[self._current_phase_index]
            
            logger.info(f"Executing phase {self._current_phase_index + 1}/{len(self._current_execution_plan)}: {plan_item['activated_electrodes']}")
            
            step_info = self._run_order[self._current_index]
            step = step_info["step"]
            device_state = step.device_state if hasattr(step, 'device_state') and step.device_state else None
            if not device_state:
                device_state = PathExecutionService.get_empty_device_state()
            
            # create and publish message immediately
            msg_model = PathExecutionService.create_dynamic_device_state_message(
                device_state, 
                plan_item["activated_electrodes"], 
                plan_item["step_uid"],
                plan_item["step_description"],
                plan_item["step_id"]
            )
            
            publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
            
            logger.info(f"Published electrode state to device viewer: {msg_model.serialize()}")
            
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
            self._phase_timer.start(duration_ms)
                           
        except Exception as e:
            logger.error(f"Error in phase execution: {e}")
            self.signals.protocol_error.emit(str(e))

    def jump_to_step_by_path(self, step_path):
        if not self._is_running or not self._run_order:
            return False
        
        target_index = self.get_run_order_index_by_path(step_path)
        if target_index == -1:
            logger.warning(f"Could not find step with path {step_path} in run_order")
            return False
        
        logger.info(f"Jumping from step {self._current_index} to step {target_index}")
        
        self._timer.stop()
        self._phase_timer.stop()
        
        current_time = time.time()
        if self._step_start_time:
            self._step_elapsed_time = current_time - self._step_start_time
        if self._start_time:
            self._elapsed_time = current_time - self._start_time
        
        self._current_index = target_index
        
        self._current_execution_plan = []
        self._current_phase_index = 0
        self._total_step_phases_completed = 0
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0
        
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
                
                msg_model.editable = False
                
                publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
                
                logger.info(f"Published paused navigation preview to device viewer: {msg_model.serialize()}")
            
            logger.info(f"Navigated to step during pause, ready to resume from beginning of step")
        
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

    def get_protocol_state(self):
        return {
            "is_running": self._is_running,
            "is_paused": self._is_paused,
            "current_index": self._current_index,
            "total_steps": len(self._run_order),
            "current_step_path": self.get_current_step_path()
        }

    def _on_phase_timeout(self):
        if not self._is_running or self._is_paused:
            return
        
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
        
        # Reset phase tracking
        self._current_execution_plan = []
        self._current_phase_index = 0
        self._total_step_phases_completed = 0
        self._phase_start_time = None
        self._phase_elapsed_time = 0.0
        self._remaining_phase_time = 0.0
        self._remaining_step_time = 0.0
        self._was_in_phase = False
        self._paused_phase_index = 0
        
        self._current_index += 1
        
        if self._current_index >= len(self._run_order):
            self._on_protocol_finished()
        else:
            self._execute_next_step()

    def _on_step_timeout(self):
        if not self._is_running or self._is_paused:
            return
                
        if self._current_phase_index < len(self._current_execution_plan):
            # force completion of remaining phases
            self._current_phase_index = len(self._current_execution_plan)
            self._execute_next_phase()
        else:
            self._on_step_completed_by_phases()

    def _on_protocol_error(self, error_message):
        self.signals.protocol_error.emit(error_message)
        self.stop()

    def _on_protocol_finished(self):
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
            
            logger.info(f"Published final protocol message to device viewer: {msg_model.serialize()}")
            
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
            step_time = self._step_elapsed_time
        else:
            if self._start_time and self._step_start_time:
                total_time = current_time - self._start_time
                step_time = current_time - self._step_start_time
            else:
                total_time = 0.0
                step_time = 0.0
        
        # current repetition based on cycle of largest loop in the step
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

    def is_running(self):
        return self._is_running and not self._is_paused

    def is_paused(self):
        return self._is_paused