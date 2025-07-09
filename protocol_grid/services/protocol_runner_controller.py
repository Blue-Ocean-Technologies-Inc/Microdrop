import dramatiq
import time

from PySide6.QtCore import QObject, Signal, QTimer

class ProtocolRunnerSignals(QObject):
    highlight_step = Signal(object) # path (list of ints)
    update_status = Signal(dict)
    protocol_finished = Signal()
    protocol_paused = Signal()

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
        self._run_order = self.flatten_func(self.protocol_state)
        self._start_time = time.time()
        self._elapsed_time = 0.0
        self._step_elapsed_time = 0.0
        self._step_start_time = time.time()
        if not self._run_order:
            self.signals.protocol_finished.emit()
            return 
        self._run_next_step()

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
        self._run_next_step(resume=True)

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

    def set_repeat_protocol_n(self, n):
        self._repeat_protocol_n = max(1, int(n))

    def _run_next_step(self, resume=False):
        if self._current_index >= len(self._run_order):
            self._is_running = False
            self._status_timer.stop()
            self.signals.protocol_finished.emit()
            return
        step_info = self._run_order[self._current_index]
        step, path = step_info["step"], step_info["path"]
        rep_idx, rep_total = step_info["rep_idx"], step_info["rep_total"]
        self.signals.highlight_step.emit(path)
        self._emit_status_update()
        run_time = float(step.parameters.get("Run Time", "1.0") or "1.0")
        self._step_start_time = time.time()
        self._step_elapsed_time = 0.0
        self._timer.start(int(run_time * 1000))

    def _emit_status_update(self):
        if not self._is_running or self._is_paused or not self._run_order:
            return
        step_info = self._run_order[self._current_index]
        step, path = step_info["step"], step_info["path"]
        rep_idx, rep_total = step_info["rep_idx"], step_info["rep_total"]
        step_total = len(self._run_order) * self._repeat_protocol_n
        step_idx = (self._current_protocol_repeat - 1) * len(self._run_order) + self._current_index + 1
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
        if not self._is_running or self._is_paused:
            return
        self._current_index += 1
        if self._current_index >= len(self._run_order):
            if self._current_protocol_repeat < self._repeat_protocol_n:
                self._current_protocol_repeat += 1
                self._current_index = 0
                self._run_next_step()
                return
            else:
                self._is_running = False
                self._status_timer.stop()
                self.signals.protocol_finished.emit()
                return
        self._run_next_step()

    def is_running(self):
        return self._is_running and not self._is_paused

    def is_paused(self):
        return self._is_paused