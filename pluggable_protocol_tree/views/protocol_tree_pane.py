"""Reusable host widget for the pluggable protocol tree's full UX.

Owns the RowManager + ProtocolTreeWidget + ProtocolExecutor + the
NavigationBar / StatusBar / experiment-bar trio. Mounted by both the
demo window (BasePluggableProtocolDemoWindow) and the full-app dock
pane (PluggableProtocolDockPane).

Service injection (``application``, ``experiment_manager``,
``sticky_manager``) is optional. When None, the corresponding
experiment-bar buttons stay log-only stubs (matches today's demo UX).
When supplied, the pane connects the real handlers — see Task 6 of
PPT-10.1 for the full wiring rules.
"""

from __future__ import annotations

import threading
import time

from pyface.qt.QtCore import Qt, QTimer, Signal
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import (
    QLabel, QToolButton, QVBoxLayout, QWidget,
)

from microdrop_application.dialogs.pyface_wrapper import error as error_dialog
from microdrop_style.button_styles import ICON_FONT_FAMILY

from pluggable_protocol_tree.consts import ELECTRODES_STATE_APPLIED
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
from pluggable_protocol_tree.views.navigation_bar import (
    NavigationBar, StatusBar, make_separator,
)
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

from logger.logger_service import get_logger

logger = get_logger(__name__)


class ProtocolTreePane(QWidget):
    """Hosts the pluggable protocol tree with full UX scaffolding.

    Layered top-to-bottom:
      NavigationBar  (playback + step nav + experiment bar in left slot)
      StatusBar      (step/phase elapsed, repetition counter, recent/next labels)
      separator
      ProtocolTreeWidget
    """

    phase_acked = Signal()

    def __init__(
        self,
        columns_or_manager,
        *,
        application=None,
        experiment_manager=None,
        sticky_manager=None,
        phase_ack_topic=ELECTRODES_STATE_APPLIED,
        executor_factory=None,
        parent=None,
    ):
        super().__init__(parent)

        if isinstance(columns_or_manager, RowManager):
            self.manager = columns_or_manager
        else:
            self.manager = RowManager(columns=list(columns_or_manager))

        self.application = application
        self.experiment_manager = experiment_manager
        self.sticky_manager = sticky_manager
        self.phase_ack_topic = phase_ack_topic

        self.widget = ProtocolTreeWidget(self.manager, parent=self)

        self._build_status_bar()
        self._build_navigation_bar()
        self._build_experiment_bar()
        self._build_layout()

        self.executor = self._build_executor(executor_factory)

        self._step_index = 0
        self._step_total = 0
        self._step_started_at: float | None = None
        self._phase_started_at: float | None = None
        self._phase_target: float | None = None
        self._current_row = None
        self._repeats_total = 1
        self._repeats_completed = 0
        self._current_run_preview_mode = False

        self._status_step_label = self.status_bar.lbl_step_progress
        self._status_step_time_label = self.status_bar.lbl_step_time
        self._status_reps_label = self.status_bar.lbl_step_repetition
        self._status_phase_time_label = (
            self.status_bar.lbl_phase_time if self.phase_ack_topic is not None
            else None
        )

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)
        self._tick_timer.timeout.connect(self._refresh_status)

        self._wire_executor_signals()
        self._wire_button_state_machine()
        self._wire_navigation_buttons()
        self._set_idle_button_state()

    def _build_status_bar(self):
        self.status_bar = StatusBar()
        phase_enabled = self.phase_ack_topic is not None
        self.status_bar.lbl_phase_time.setVisible(phase_enabled)

    def _build_navigation_bar(self):
        self.navigation_bar = NavigationBar()

    def _build_experiment_bar(self):
        icon_font = QFont(ICON_FONT_FAMILY)
        icon_font.setPixelSize(20)

        self.btn_new_exp = QToolButton()
        self.btn_new_exp.setText("note_add")
        self.btn_new_exp.setFont(icon_font)
        self.btn_new_exp.setToolTip("New Experiment")
        self.btn_new_exp.setCursor(Qt.PointingHandCursor)
        self.btn_new_exp.clicked.connect(self._on_new_experiment)

        self.experiment_label = ExperimentLabel()

        self.btn_new_note = QToolButton()
        self.btn_new_note.setText("sticky_note")
        self.btn_new_note.setFont(icon_font)
        self.btn_new_note.setToolTip("New Note")
        self.btn_new_note.setCursor(Qt.PointingHandCursor)
        self.btn_new_note.clicked.connect(self._on_new_note)

        self.experiment_label.clicked.connect(self._on_experiment_label_clicked)

        self.navigation_bar.add_widget_to_left_slot(self.btn_new_exp)
        self.navigation_bar.add_widget_to_left_slot(self.experiment_label)
        self.navigation_bar.add_widget_to_left_slot(self.btn_new_note)

    def _build_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation_bar)
        layout.addWidget(self.status_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self.widget)

    def _build_executor(self, executor_factory):
        factory = executor_factory or self._default_executor_factory
        return factory(
            row_manager=self.manager,
            qsignals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

    @staticmethod
    def _default_executor_factory(row_manager, qsignals, pause_event, stop_event):
        return ProtocolExecutor(
            row_manager=row_manager,
            qsignals=qsignals,
            pause_event=pause_event,
            stop_event=stop_event,
        )

    def _wire_executor_signals(self):
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row,
        )
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.step_finished.connect(self._on_step_finished)
        self.executor.qsignals.step_repetition.connect(self._on_step_repetition)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        self.executor.qsignals.protocol_error.connect(self._on_error)
        if self.phase_ack_topic is not None:
            self.phase_acked.connect(self._on_phase_ack)

    def _wire_button_state_machine(self):
        self.executor.qsignals.protocol_started.connect(
            self._set_running_button_state,
        )
        self.executor.qsignals.protocol_paused.connect(self._on_protocol_paused)
        self.executor.qsignals.protocol_resumed.connect(self._on_protocol_resumed)
        self.executor.qsignals.protocol_finished.connect(self._on_protocol_finished)
        self.executor.qsignals.protocol_aborted.connect(self._on_protocol_aborted)

    def _wire_navigation_buttons(self):
        nb = self.navigation_bar
        nb.btn_play.clicked.connect(self._on_play_clicked)
        nb.btn_resume.clicked.connect(self._toggle_pause)
        nb.btn_stop.clicked.connect(self.executor.stop)

    # --- step lifecycle handlers --------------------------------------

    def _on_protocol_started(self):
        try:
            self._step_total = sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            self._step_total = 0
        self._step_index = 0
        self._status_step_label.setText(f"Step 0 / {self._step_total}")

    def _on_step_started(self, row):
        self._step_index += 1
        self._current_row = row
        self._step_started_at = time.monotonic()
        self._phase_started_at = None
        try:
            self._phase_target = float(getattr(row, "duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._phase_target = None
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        self.status_bar.lbl_recent_step.setText(f"Most Recent Step: {row.name}")
        self.status_bar.lbl_next_step.setText(
            f"Next Step: {self._next_step_name(row)}"
        )
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    def _next_step_name(self, current):
        steps = self.manager.iter_execution_steps()
        cur_path = tuple(current.path)
        for row in steps:
            if tuple(row.path) == cur_path:
                next_row = next(steps, None)
                return next_row.name if next_row is not None else "-"
        return "-"

    def _on_phase_ack(self):
        if self._current_row is None:
            return
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now

    def _on_step_repetition(self, rep_chain):
        if not rep_chain:
            self._status_reps_label.setText("")
            self._status_reps_label.setVisible(False)
            return
        parts = [
            f"rep {idx}/{total} of '{name}'" for name, idx, total in rep_chain
        ]
        self._status_reps_label.setText(" · ".join(parts))
        self._status_reps_label.setVisible(True)

    def _on_step_finished(self, _row):
        self._refresh_status()

    def _on_error(self, msg):
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._tick_timer.stop()
        self._set_idle_button_state()
        error_dialog(parent=self, title="Protocol error", message=str(msg))

    def _refresh_status(self):
        if self._step_started_at is None:
            return
        step_elapsed = time.monotonic() - self._step_started_at
        self._status_step_time_label.setText(f"Step {step_elapsed:5.2f}s")
        if self._status_phase_time_label is not None:
            phase_elapsed = (
                0.0 if self._phase_started_at is None
                else time.monotonic() - self._phase_started_at
            )
            target = self._phase_target if self._phase_target is not None else 0.0
            self._status_phase_time_label.setText(
                f"Phase {phase_elapsed:5.2f}s / {target:.2f}s"
            )

    # --- button state machine ----------------------------------------

    def _set_idle_button_state(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_play_state()
        nb.btn_stop.setEnabled(False)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)
        nb.action_preview.setEnabled(True)

    def _set_running_button_state(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_pause_state()
        nb.btn_stop.setEnabled(True)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)
        nb.action_preview.setEnabled(False)

    def _on_play_clicked(self):
        if self._is_protocol_active():
            self._toggle_pause()
            return
        self._start_protocol_run(
            preview_mode=self.navigation_bar.is_preview_mode(),
        )

    def _start_protocol_run(self, preview_mode):
        self._repeats_total = self.status_bar.edit_repeat_protocol.value()
        self._repeats_completed = 0
        self._current_run_preview_mode = preview_mode
        self._update_repeat_status_label()
        self.executor.start(
            start_step_path=self._selected_step_path(),
            preview_mode=preview_mode,
        )

    def _update_repeat_status_label(self):
        self.status_bar.lbl_repeat_protocol_status.setText(
            f"{self._repeats_completed}/"
        )

    def _selected_step_path(self):
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget._index_to_path(idx)
        for row in self.manager.iter_execution_steps():
            if tuple(row.path) == path:
                return path
        return None

    def _is_protocol_active(self):
        return self.navigation_bar.btn_stop.isEnabled()

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
        else:
            self.executor.pause()

    def _on_protocol_paused(self):
        self.navigation_bar.show_resume_state()
        self._tick_timer.stop()

    def _on_protocol_resumed(self):
        self.navigation_bar.show_pause_state()
        if self._current_row is not None:
            self._tick_timer.start()

    def _on_protocol_finished(self):
        self._repeats_completed += 1
        self._update_repeat_status_label()
        if self._repeats_completed < self._repeats_total:
            QTimer.singleShot(50, self._restart_for_next_rep)
            return
        self._on_protocol_terminated()

    def _restart_for_next_rep(self):
        self.executor.start(preview_mode=self._current_run_preview_mode)

    def _on_protocol_aborted(self):
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._on_protocol_terminated()

    def _on_protocol_terminated(self):
        self._set_idle_button_state()
        self._tick_timer.stop()

    # --- experiment-bar stubs (Task 6 wires real services) -------------

    def _on_new_experiment(self):
        logger.info("New Experiment requested")

    def _on_new_note(self):
        logger.info("New Note requested")

    def _on_experiment_label_clicked(self):
        logger.info("Experiment label clicked")
