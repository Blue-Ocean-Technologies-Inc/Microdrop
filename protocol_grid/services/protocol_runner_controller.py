import dramatiq
import time
import uuid
from typing import List, Dict, Any
import threading

from PySide6.QtCore import QObject, Signal, QTimer

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from protocol_grid.services.protocol_execution_actors import execute_step_actor
from protocol_grid.services.path_execution_service import PathExecutionService
from protocol_grid.consts import PROTOCOL_GRID_DISPLAY_STATE
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)

class ProtocolRunnerSignals(QObject):
    highlight_step = Signal(object) # path (list of ints)
    update_status = Signal(dict)
    protocol_finished = Signal()
    protocol_paused = Signal()
    protocol_error = Signal(str)

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

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_step_timeout)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(100)
        self._status_timer.timeout.connect(self._emit_status_update)

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
        self._start_time = time.time()
        self._elapsed_time = 0.0
        self._step_elapsed_time = 0.0
        self._step_start_time = time.time()
        if not self._run_order:
            self.signals.protocol_finished.emit()
            return
        
        # Start executing the protocol
        self._execute_next_step()

    def pause(self):
        if not self._is_running or self._is_paused:
            return
        self._is_paused = True
        self._status_timer.stop()
        self._timer.stop()
        self._elapsed_time += time.time() - self._start_time
        self._step_elapsed_time += time.time() - self._step_start_time
        self.signals.protocol_paused.emit()

    def resume(self):
        if not self._is_running or not self._is_paused:
            return
        self._is_paused = False
        self._status_timer.start()
        self._start_time = time.time()
        self._step_start_time = time.time()
        
        # Continue from current step
        self._execute_next_step()

    def stop(self):
        self._is_running = False
        self._is_paused = False
        self._status_timer.stop()
        self._timer.stop()
        self._current_index = 0
        self._run_order = []
        self._start_time = None
        self._step_start_time = None
        self._elapsed_time = 0.0
        self._step_elapsed_time = 0.0
        self._current_step_timer = None

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
            
            self._execute_step_with_immediate_messages(step, device_state)
            
            self._step_start_time = time.time()
            self._step_elapsed_time = 0.0

            step_timeout = PathExecutionService.calculate_step_execution_time(step, device_state)
            
            self._timer.timeout.disconnect()
            self._timer.timeout.connect(lambda: self._on_step_completed(step.parameters.get("UID", "")))
            self._timer.start(int(step_timeout * 1000))
            
        except Exception as e:
            logger.error(f"Error executing step: {e}")
            self.signals.protocol_error.emit(str(e))
            self.stop()

    def _execute_step_with_immediate_messages(self, step, device_state):
        try:
            execution_plan = PathExecutionService.calculate_step_execution_plan(step, device_state)
            
            logger.info(f"Execution plan has {len(execution_plan)} phases")
            
            for i, plan_item in enumerate(execution_plan):
                logger.info(f"Executing phase {i+1}/{len(execution_plan)}: {plan_item['activated_electrodes']}")
                
                msg_model = PathExecutionService.create_dynamic_device_state_message(
                    device_state, 
                    plan_item["activated_electrodes"], 
                    plan_item["step_uid"],
                    plan_item["step_description"],
                    plan_item["step_id"]
                )
                
                publish_message(
                    topic=PROTOCOL_GRID_DISPLAY_STATE,
                    message=msg_model.serialize()
                )
                
                logger.info(f"Published electrode state immediately: {msg_model.serialize()}")
                
                # Wait for the duration if not the last phase
                if i < len(execution_plan) - 1:
                    logger.info(f"Waiting {plan_item['duration']} seconds")
                    time.sleep(plan_item["duration"])
                else:
                    # For the last phase, schedule completion callback
                    def schedule_completion():
                        time.sleep(plan_item["duration"])
                        if self._is_running and not self._is_paused:
                            QTimer.singleShot(0, lambda: self._on_step_completed(step.parameters.get("UID", "")))
                    
                    # Use a separate thread for the final sleep to avoid blocking
                    completion_thread = threading.Thread(target=schedule_completion)
                    completion_thread.daemon = True
                    completion_thread.start()
                    
        except Exception as e:
            logger.error(f"Error in step execution: {e}")
            self.signals.protocol_error.emit(str(e))

    def _on_step_completed(self, step_uid):
        if not self._is_running or self._is_paused:
            return
        
        logger.info(f"Step {step_uid} completed")

        self._timer.stop()
        
        self._current_index += 1
        
        if self._current_index >= len(self._run_order):
            self._on_protocol_finished()
        else:
            self._execute_next_step()

    def _on_protocol_error(self, error_message):
        logger.error(f"Protocol error: {error_message}")
        self.signals.protocol_error.emit(error_message)
        self.stop()

    def _on_protocol_finished(self):
        self._is_running = False
        self._status_timer.stop()
        self.signals.protocol_finished.emit()

    def _emit_status_update(self):
        if not self._is_running or self._is_paused or not self._run_order:
            return
        step_info = self._run_order[self._current_index]
        step = step_info["step"]
        rep_idx, rep_total = step_info["rep_idx"], step_info["rep_total"]
        step_total = len(self._run_order)
        step_idx = self._current_index + 1
        status = {
            "total_time": self._elapsed_time + (time.time() - self._start_time
                                                 if self._is_running and not self._is_paused else 0),
            "step_time": time.time() - self._step_start_time if not self._is_paused else self._step_elapsed_time,
            "step_idx": step_idx,
            "step_total": step_total,
            "step_rep_idx": rep_idx,
            "step_rep_total": rep_total,
            "recent_step": self._run_order[self._current_index - 1]["step"].parameters.get("Description", "-") if self._current_index > 0 else "-",
            "next_step": self._run_order[self._current_index + 1]["step"].parameters.get("Description", "-") if self._current_index + 1 < len(self._run_order) else "-",
            "protocol_repeat_idx": self._current_protocol_repeat,
            "protocol_repeat_total": self._repeat_protocol_n
        }
        self.signals.update_status.emit(status)

    def _on_step_timeout(self):
        """Handle step timeout (fallback)."""
        if self._is_running and not self._is_paused:
            logger.warning("Step timed out, moving to next step")
            self._on_step_completed("timeout")

    def is_running(self):
        return self._is_running and not self._is_paused

    def is_paused(self):
        return self._is_paused