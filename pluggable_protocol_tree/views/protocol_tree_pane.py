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

import json
import threading
import time
from pathlib import Path
import html as _html

from pyface.qt.QtCore import (
    Qt, QEventLoop, QModelIndex, QThread, QTimer, Signal, QUrl,
)
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import (
    QApplication, QFileDialog, QProgressDialog, QToolButton, QVBoxLayout,
    QWidget,
)

from microdrop_application.dialogs.pyface_wrapper import (
    NO, YES, confirm, error as error_dialog, escape_html_multiline,
    format_traceback_detail, information, success,
)
from microdrop_style.button_styles import ICON_FONT_FAMILY
from microdrop_style.colors import DIALOG_ERROR_TEXT_COLOR

from microdrop_application.dialogs.decorators import (
    attempt_func_execution_with_error_dialog,
)
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from device_viewer.consts import DEVICE_SVG_PATH_KEY, PROTOCOL_RUNNING
from dropbot_controller.consts import REALTIME_MODE_KEY, SET_REALTIME_MODE
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, ELECTRODES_STATE_CHANGE,
    PROTOCOL_TREE_DISPLAY_STATE, REPEAT_DURATION_RECALC_TRIGGERS,
)
from pluggable_protocol_tree.execution.exceptions import StepExecutionError
from pluggable_protocol_tree.models.display_state import ProtocolTreeDisplayMessage
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.services.persistence import (
    _RESERVED_ROW_METADATA_FIELDS,
)
from pluggable_protocol_tree.services.logging.controller import (
    ProtocolLoggingController,
)
from pluggable_protocol_tree.services.phase_math import (
    effective_repetitions_for_duration, estimate_repeat_duration_s,
    iter_phases,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
from pluggable_protocol_tree.views.navigation_bar import (
    NavigationBar, StatusBar, make_separator,
)
from pluggable_protocol_tree.views.quick_action_bar import (
    QuickActionBar, QuickActionsController,
)
from pluggable_protocol_tree.views.tree_widget import ProtocolTreeWidget

from logger.logger_service import get_logger
logger = get_logger(__name__)

# Shared Redis-backed state (device SVG path published by the device viewer,
# realtime mode mirrored by the status panel). The proxy connects lazily;
# reads are wrapped in try/except where no-Redis must be tolerated.
app_globals = get_microdrop_redis_globals_manager()

class ProtocolTreePane(QWidget):
    """Hosts the pluggable protocol tree with full UX scaffolding.

    Layered top-to-bottom:
      NavigationBar  (playback + step nav + experiment bar in left slot)
      StatusBar      (step/phase elapsed, repetition counter, recent/next labels)
      separator
      ProtocolTreeWidget
    """

    phase_acked = Signal()
    # Emitted by the logging controller from a worker thread when the
    # deferred flush completes; QueuedConnection in __init__ marshals it
    # back to the GUI thread so the success dialog runs there.
    _logging_complete = Signal(object)
    # Quick-actions toolbar feed: emit True/False on protocol start/end,
    # parameterless selection_changed on each tree selection move.
    # QuickActionsController listens to both to drive button enabled state.
    protocol_running_changed = Signal(bool)
    selection_changed = Signal()

    def __init__(
        self,
        columns_or_manager,
        *,
        application=None,
        experiment_manager=None,
        sticky_manager=None,
        device_viewer_sync=None,
        phase_ack_topic=ELECTRODES_STATE_APPLIED,
        executor_factory=None,
        logging_device_context_provider=None,
        preferences=None,
        quick_actions=None,
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
        self._logging_device_context_provider = logging_device_context_provider
        # Protocol preferences model, passed down from the dock pane in the
        # full app (bound to the application's preferences there). Demos and
        # headless tests get a standalone instance against the global default
        # preferences node, so every consumer can rely on it being present.
        self.preferences = ProtocolPreferences.ensure(preferences)

        self.widget = ProtocolTreeWidget(
            self.manager, preferences=self.preferences, parent=self)

        self.device_viewer_sync = device_viewer_sync
        if self.device_viewer_sync is not None:
            self.device_viewer_sync.attach(self.widget)

        # Re-emit the tree's selectionChanged as a parameterless signal so
        # the QuickActionsController doesn't have to know about Qt selection
        # models. The pane already constructed self.widget above.
        self.widget.tree.selectionModel().selectionChanged.connect(
            lambda *_: self.selection_changed.emit()
        )

        self.protocol_state_tracker = PluggableProtocolStateTracker()
        # Structural mutations (add/remove/move/paste/new) re-check the
        # baseline path set and rescan if paths re-aligned (insert+
        # delete, move+undo).
        self.manager.observe(self._on_manager_rows_changed, "rows_changed")
        # Cell edits go through cell_changed (carries path + col_id)
        # so the tracker can update its diff in O(1).
        self.manager.observe(self._on_manager_cell_changed, "cell_changed")

        self._build_status_bar()
        self._build_navigation_bar()
        self._build_experiment_bar()

        # Quick-actions toolbar (bar + controller). Both are None when no
        # contributions exist (demo / headless test environments) so the
        # pane stays usable with no chrome below the tree. Constructed
        # before _build_layout() so it can be inserted in the layout.
        if quick_actions:
            self.quick_action_bar = QuickActionBar(
                actions=list(quick_actions), parent=self)
            self.quick_actions_controller = QuickActionsController(
                bar=self.quick_action_bar, pane=self,
                actions=list(quick_actions))
        else:
            self.quick_action_bar = None
            self.quick_actions_controller = None

        self._build_layout()

        self.executor = self._build_executor(executor_factory)

        # The flush_scheduler shows a "Generating Run Report..." progress
        # dialog around the report build (legacy parity, mirrors
        # protocol_grid's with_loading_screen("Generating Run Report...")).
        # The flush runs in a QThread to keep the GUI responsive while
        # plotly renders charts; the controller's completion_callback is
        # routed through a Qt signal so the success dialog ends up back on
        # the GUI thread.
        self._logging_complete.connect(
            self._on_logging_complete, Qt.QueuedConnection)
        self.logging_controller = ProtocolLoggingController(
            completion_callback=self._logging_complete.emit,
            flush_scheduler=self._schedule_flush_with_progress,
            settling_provider=self._logs_settling_time_s,
        )
        self.logging_controller.attach(self.executor.qsignals)

        self._step_index = 0
        self._step_total = 0
        self._step_started_at: float | None = None
        self._phase_started_at: float | None = None
        self._phase_target: float | None = None
        self._phase_index = 0
        self._phase_total = 0
        self._current_row = None
        self._repeats_total = 1
        self._repeats_completed = 0
        self._current_run_preview_mode = False
        self._pause_phases: list = []
        self._pause_phase_idx: int = 0
        # Realtime-mode bookkeeping (legacy protocol_grid parity). True =
        # leave realtime mode on after the run; default True so a terminal
        # without a pre-run prep (preview, tests) never turns it off.
        self._restore_realtime_mode = True
        # Guards the settling window between play-click and executor.start
        # so a second play-click can't start a duplicate run.
        self._start_pending = False

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

        if self.application is not None:
            self.application.observe(
                self._on_experiment_changed, "experiment_changed",
            )
            try:
                self.application.observe(
                    self._on_application_exiting, "application_exiting",
                )
            except ValueError as e:
                # Bare HasTraits test stubs may not declare the trait;
                # production Envisage apps always do.
                logger.debug(f"application_exiting observer skipped: {e}")
            try:
                cur = self.application.current_experiment_directory
                if cur is not None:
                    self.experiment_label.update_experiment_id(cur.stem)
            except Exception as e:
                logger.warning(f"could not read initial experiment dir: {e}")

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
        if self.quick_action_bar is not None:
            layout.addWidget(self.quick_action_bar)

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
        # highlight_active_row is pure visual decoration — no setCurrentIndex,
        # so it doesn't fire currentChanged and needs no suppress wrap.
        self.executor.qsignals.step_started.connect(
            self.widget.highlight_active_row,
        )
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.step_finished.connect(self._on_step_finished)
        self.executor.qsignals.step_repetition.connect(self._on_step_repetition)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        self.executor.qsignals.protocol_error.connect(self._on_error)
        self.executor.qsignals.phase_started.connect(self._on_phase_started)
        self.executor.qsignals.phase_extended.connect(self._on_phase_extended)
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
        nb.btn_first.clicked.connect(self.navigate_to_first_step)
        nb.btn_prev.clicked.connect(self.navigate_to_previous_step)
        nb.btn_next.clicked.connect(self.navigate_to_next_step)
        nb.btn_last.clicked.connect(self.navigate_to_last_step)
        nb.btn_prev_phase.clicked.connect(self._on_prev_phase)
        nb.btn_next_phase.clicked.connect(self._on_next_phase)
        nb.set_phase_navigation_enabled(False, False)

    # --- step lifecycle handlers --------------------------------------

    def _publish_protocol_running(self, value: str) -> None:
        logger.info("Protocol Tree: Publishing Protocol Running")
        publish_message(topic=PROTOCOL_RUNNING, message=value)

    def _on_protocol_started(self):
        self.protocol_running_changed.emit(True)
        self._publish_protocol_running("True")
        try:
            self._step_total = sum(1 for _ in self.manager.iter_execution_steps())
        except Exception:
            self._step_total = 0
        self._step_index = 0
        self._status_step_label.setText(f"Step 0 / {self._step_total}")
        logger.info(f"Protocol started ({self._step_total} steps)")

    def _on_step_started(self, row):
        self._step_index += 1
        self._current_row = row
        self._step_started_at = time.monotonic()
        self._phase_started_at = None
        self._phase_index = 0
        self._phase_total = 0
        try:
            self._phase_target = float(getattr(row, "duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._phase_target = None
        logger.info(
            f"Step started: {self._step_index}/{self._step_total} "
            f"[{row.dotted_path()}] {row.name!r}"
        )
        self._status_step_label.setText(
            f"Step {self._step_index} / {self._step_total}"
        )
        self.status_bar.lbl_recent_step.setText(f"Most Recent Step: {row.name}")
        self.status_bar.lbl_next_step.setText(
            f"Next Step: {self._next_step_name(row)}"
        )
        if not self._tick_timer.isActive():
            self._tick_timer.start()

        # NOTE: we deliberately do NOT publish the static step view to the
        # DV here. RoutesHandler publishes a per-phase display for every
        # phase (carrying step_id/label/routes + the phase's active
        # electrodes, editable=False), which is the authoritative source
        # while a protocol runs. Publishing _publish_for_row(row) here too
        # raced with phase 1: the worker publishes phase 1 to the broker
        # before this queued slot runs, so the static view (electrodes=[],
        # editable=True) consistently landed AFTER phase 1 and cleared it,
        # making the animation appear to begin at the second position.

    def _next_step_name(self, current):
        steps = self.manager.iter_execution_steps()
        cur_path = tuple(current.path)
        for row in steps:
            if tuple(row.path) == cur_path:
                next_row = next(steps, None)
                return next_row.name if next_row is not None else "-"
        return "-"

    def _on_phase_ack(self):
        # Phase boundary now comes from the executor's phase_started
        # signal (independent of hardware ack). Kept as a no-op so
        # external code emitting phase_acked doesn't fight the timer.
        return

    def _on_phase_started(self, phase_index, phase_total, phase_duration_s):
        """Executor signal: a new phase has begun. Reset the elapsed
        clock and update the Phase x/y label so the status bar tracks
        the executor regardless of whether a hardware ack arrives."""
        if self._current_row is None:
            return
        now = time.monotonic()
        if self._step_started_at is None:
            self._step_started_at = now
        self._phase_started_at = now
        self._phase_index = int(phase_index)
        self._phase_total = int(phase_total)
        try:
            self._phase_target = float(phase_duration_s)
        except (TypeError, ValueError):
            self._phase_target = None
        self._refresh_status()

    def _on_phase_extended(self, extra_s):
        """A handler extended the current phase (e.g. volume threshold
        holding for more wetting time). Grow the displayed target so the
        'elapsed / target' readout stays honest while the phase is held."""
        if self._current_row is None:
            return
        try:
            self._phase_target = (self._phase_target or 0.0) + float(extra_s)
        except (TypeError, ValueError):
            return
        self._refresh_status()

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
        logger.error(f"Protocol error: {msg}")
        self._publish_protocol_running("False")
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        # Immediate teardown only; the completion flow is deferred so the
        # error dialog is shown before the "Generate Run Summary?" prompt.
        self._on_protocol_terminated("error")
        # Present a nicely-formatted HTML body (rendered via the dialog's
        # `informative` slot) built from the structured StepExecutionError
        # fields, with the full traceback as collapsible detail. `message`
        # stays the plain summary as a fallback.
        exc = getattr(self.executor, "_error", None)
        informative = self._format_error_html(exc, str(msg))
        detail = format_traceback_detail(exc) if exc is not None else None
        error_dialog(parent=None, title="Protocol error",
                     message=str(msg), informative=informative, detail=detail)
        # Now prompt for a run summary (error is treated like a force-stop).
        self._run_completion_flow("error")

    @staticmethod
    def _format_error_html(exc, fallback_msg: str) -> str:
        """Build the HTML body shown in the protocol-error dialog. Uses the
        structured StepExecutionError fields (step / column / hook / cause)
        when available, else falls back to the plain message text."""
        red = DIALOG_ERROR_TEXT_COLOR
        if isinstance(exc, StepExecutionError):
            row = exc.row
            if row is not None:
                dotted = row.dotted_path()
                name = getattr(row, "name", "") or ""
                where = f"Step {dotted}"
                if name:
                    where += f" &mdash; &ldquo;{_html.escape(name)}&rdquo;"
            else:
                where = "Protocol"
            col_label = (
                getattr(getattr(exc.col, "model", None), "col_name", "")
                or getattr(getattr(exc.col, "model", None), "col_id", "")
                or "column"
            )
            cause = escape_html_multiline(str(exc.cause))
            return (
                f"<p style='margin:0 0 6px 0;'><b>{where}</b></p>"
                f"<p style='margin:0 0 10px 0;color:#555;'>The "
                f"<b>{_html.escape(col_label)}</b> column failed during "
                f"<code>{_html.escape(exc.hook_name)}</code>.</p>"
                f"<p style='margin:0;color:{red};'>{cause}</p>"
            )
        # Generic fallback (non-annotated errors, or signal emitted directly).
        safe = escape_html_multiline(fallback_msg)
        return f"<p style='margin:0;color:{red};'>{safe}</p>"

    @attempt_func_execution_with_error_dialog
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
            if self._phase_total > 0:
                self._status_phase_time_label.setText(
                    f"Phase {self._phase_index}/{self._phase_total}  "
                    f"{phase_elapsed:4.2f}s / {target:.2f}s"
                )
            elif self._phase_index > 0:
                # Dynamic duration loop: total is unknown while looping, so
                # show the running phase number with no misleading denominator.
                self._status_phase_time_label.setText(
                    f"Phase {self._phase_index}  "
                    f"{phase_elapsed:4.2f}s / {target:.2f}s"
                )
            else:
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
        if self._start_pending:
            # Realtime-mode settling window — the run is already on its way.
            return
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
        start_path = self._selected_step_path()
        logger.info(
            f"Protocol run starting: {self._repeats_total} rep(s), "
            f"preview={preview_mode}, start_step={start_path}"
        )
        # Protocol logging starts once here (run start) and stops once in
        # _on_protocol_terminated — the single terminal point reached only
        # after the LAST repetition (whole-protocol repeats restart the
        # executor via _restart_for_next_rep, which returns before the
        # terminal). So one log spans all repetitions. capacitance_per_unit_area
        # is not seeded here; it arrives live via the controller's
        # on_calibration (CALIBRATION_DATA) so the Force column populates.
        if self._logging_device_context_provider is not None:
            try:
                _log_ctx = self._logging_device_context_provider()
                if _log_ctx is not None:
                    _n_steps = sum(1 for _ in self.manager.iter_execution_frames())
                    self.logging_controller.start_logging(_log_ctx, _n_steps, preview_mode)
            except Exception as e:
                logger.warning(f"could not start protocol logging: {e}")
        if preview_mode:
            # Preview runs never touch hardware — no realtime-mode prep.
            self.executor.start(
                start_step_path=start_path,
                preview_mode=preview_mode,
            )
            return
        # Legacy protocol_grid parity: turn realtime mode on (deciding
        # whether to restore the previous state after the run) and let the
        # hardware settle for realtime_mode_settling_time_s before the
        # first step. Repeats (_restart_for_next_rep) skip this — realtime
        # mode is already on mid-run.
        settle_ms = self._prepare_realtime_mode()
        self._start_pending = True

        def _start_after_settling():
            self._start_pending = False
            self.executor.start(
                start_step_path=start_path,
                preview_mode=preview_mode,
            )

        QTimer.singleShot(settle_ms, _start_after_settling)

    def _prepare_realtime_mode(self) -> int:
        """Pre-run realtime-mode handling, ported from legacy
        protocol_grid's protocol_runner_controller:

        - realtime mode OFF: turn it on for the run and turn it back off
          at the end (restore = False).
        - realtime mode ON, prompt enabled: ask whether to keep it after
          the run; the "don't ask again" checkbox persists the answer to
          the preferences.
        - realtime mode ON, prompt disabled: follow the saved
          keep_realtime_mode_after_protocol preference.

        Returns the settling delay (ms) to wait before the first step.
        """
        restore = False
        try:
            realtime_on = bool(app_globals.get(REALTIME_MODE_KEY, False))
        except Exception as e:
            logger.debug(f"realtime-mode state unavailable: {e}")
            realtime_on = False
        if not realtime_on:
            logger.info("Realtime mode off before protocol start; "
                        "turning it on...")
            try:
                publish_message(topic=SET_REALTIME_MODE, message=str(True))
            except Exception as e:
                logger.warning(f"could not enable realtime mode: {e}")
        elif self.preferences.prompt_to_restore_realtime_mode:
            user_choice, remember = confirm(
                None,
                title="Keep Realtime Mode Enabled Post-Protocol?",
                message="<b>Realtime mode is currently ON.</b><br><br>"
                        "Would you like to keep it enabled after the "
                        "protocol finishes?",
                cancel=False,
                checkbox_text="Don't ask again (can be changed in "
                              "preferences)",
            )
            restore = user_choice == YES
            if remember:
                self.preferences.prompt_to_restore_realtime_mode = False
                self.preferences.keep_realtime_mode_after_protocol = restore
        else:
            restore = self.preferences.keep_realtime_mode_after_protocol
            logger.info(f"Realtime mode post-protocol (per preference): "
                        f"{'keep' if restore else 'disable'}")
        self._restore_realtime_mode = restore
        return int(self.preferences.realtime_mode_settling_time_s * 1000)

    def _update_repeat_status_label(self):
        self.status_bar.lbl_repeat_protocol_status.setText(
            f"{self._repeats_completed}/"
        )

    def _selected_step_path(self):
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget.index_to_path(idx)
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
        logger.info("Protocol paused")
        self.navigation_bar.show_resume_state()
        self._tick_timer.stop()
        if self._current_row is not None:
            self._compute_pause_phase_state(self._current_row)
            self.navigation_bar.split_play_button_to_phase_controls()
            self._update_phase_nav_buttons()

    def _on_protocol_resumed(self):
        logger.info("Protocol resumed")
        self.navigation_bar.show_pause_state()
        if self._current_row is not None:
            self._tick_timer.start()
        self.navigation_bar.merge_phase_controls_to_play_button()

    def _on_protocol_finished(self):
        self._publish_protocol_running("False")
        self._repeats_completed += 1
        logger.info(
            f"Protocol finished (rep {self._repeats_completed}/"
            f"{self._repeats_total})"
        )
        self._update_repeat_status_label()
        if self._repeats_completed < self._repeats_total:
            QTimer.singleShot(50, self._restart_for_next_rep)
            return
        self._on_protocol_terminated("finished")

    def _restart_for_next_rep(self):
        self.executor.start(preview_mode=self._current_run_preview_mode)

    def _on_protocol_aborted(self):
        logger.info("Protocol aborted by user")
        self._publish_protocol_running("False")
        self._repeats_total = 0
        self._repeats_completed = 0
        self._update_repeat_status_label()
        self._on_protocol_terminated("aborted")

    def _on_protocol_terminated(self, outcome="finished"):
        self.protocol_running_changed.emit(False)
        logger.info("Protocol terminated --> free mode")
        self.clear_highlights()
        self._set_idle_button_state()
        self._tick_timer.stop()
        self.navigation_bar.merge_phase_controls_to_play_button()
        self._pause_phases = []
        self._pause_phase_idx = 0
        # Clear hardware actuation: independent of the DV's free-mode
        # publish below, which can race with PROTOCOL_RUNNING and leave
        # the last step's channels energized after abort/error.
        try:
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps({"electrodes": [], "channels": []}),
            )
        except Exception as e:
            logger.warning(f"protocol-terminated electrode clear failed: {e}")
        # Restore realtime mode (legacy parity): turn it back off unless the
        # user chose / prefers to keep it on. Preview runs never touched it.
        if not self._current_run_preview_mode and not self._restore_realtime_mode:
            try:
                publish_message(topic=SET_REALTIME_MODE, message=str(False))
            except Exception as e:
                logger.warning(f"realtime-mode restore failed: {e}")
        # Push free-mode payload to DV: clear_highlights cleared the
        # tree selection but did so with _suppress_publish active, so
        # the controller's currentChanged slot was gated. Explicit
        # publish here puts the DV back in free mode after the run.
        if self.device_viewer_sync is not None:
            try:
                self.device_viewer_sync._publish_for_row(None)
            except Exception as e:
                logger.warning(f"protocol-terminated DV publish failed: {e}")
        # Logging stop + end-of-run dialogs run last, after immediate teardown
        # (hardware clear / idle UI) so electrodes de-energize before any modal
        # dialog blocks. For "error", the caller (_on_error) runs the flow after
        # showing the error dialog, so we skip it here.
        if outcome != "error":
            self._run_completion_flow(outcome)

    def _run_completion_flow(self, outcome):
        """End-of-run UX: auto-save the protocol, prompt per outcome, and
        stop logging (which schedules the deferred flush). ``outcome`` is one
        of "finished", "aborted", "error". Every dialog is best-effort —
        failures are logged, never raised, so terminal cleanup is unaffected."""
        # Preview runs produce no artifacts; just confirm completion.
        if self._current_run_preview_mode:
            try:
                self.logging_controller.stop_logging()
            except Exception as e:
                logger.warning(f"stop_logging (preview) failed: {e}")
            try:
                information(parent=None,
                            message="Preview run completed successfully.",
                            title="Preview Complete", timeout=3000)
            except Exception as e:
                logger.warning(f"preview-complete dialog failed: {e}")
            return

        have_exp = (self.experiment_manager is not None
                    and self.application is not None)

        # Auto-save the protocol + record its path into the report metadata,
        # before stop_logging so the metadata is present when _flush builds
        # the report.
        if have_exp:
            try:
                saved = self.experiment_manager.auto_save_protocol(
                    self.manager.to_json())
                if saved:
                    self.logging_controller.log_metadata(
                        {"Protocol Path": str(saved)})
            except Exception as e:
                logger.warning(f"protocol auto-save failed: {e}")

        generate_report = True
        if outcome in ("aborted", "error") and have_exp:
            try:
                if confirm(parent=None,
                           message=("Protocol was stopped before completion."
                                    "<br><br>Press <b>YES</b> to create run "
                                    "summary."),
                           title="Generate Run Summary?", cancel=False) == NO:
                    generate_report = False
            except Exception as e:
                logger.warning(f"run-summary confirm failed: {e}")
        elif outcome == "finished" and have_exp:
            try:
                if confirm(parent=None,
                           message="Would you like to start a new experiment?",
                           title="Create New Experiment?",
                           cancel=False) == YES:
                    self._on_new_experiment()
            except Exception as e:
                logger.warning(f"new-experiment confirm failed: {e}")

        try:
            self.logging_controller.stop_logging(generate_report=generate_report)
        except Exception as e:
            logger.warning(f"stop_logging failed: {e}")

    # --- pause-time phase navigation ---------------------------------

    def _compute_pause_phase_state(self, row):
        try:
            self._pause_phases = list(iter_phases(
                static_electrodes=list(getattr(row, "electrodes", []) or []),
                routes=list(getattr(row, "routes", []) or []),
                trail_length=int(getattr(row, "trail_length", 1)),
                trail_overlay=int(getattr(row, "trail_overlay", 0)),
                soft_start=bool(getattr(row, "soft_start", False)),
                soft_end=bool(getattr(row, "soft_end", False)),
                repeat_duration_s=float(getattr(row, "repeat_duration", 0.0)),
                linear_repeats=bool(getattr(row, "linear_repeats", False)),
                n_repeats=int(getattr(row, "route_repetitions", 1)),
                step_duration_s=float(getattr(row, "duration_s", 1.0)),
            ))
        except Exception as e:
            logger.warning(f"phase navigation: iter_phases failed: {e}")
            self._pause_phases = []
        self._pause_phase_idx = 0

    def _on_prev_phase(self):
        if self._pause_phases and self._pause_phase_idx > 0:
            self._pause_phase_idx -= 1
            self._publish_paused_phase()
            self._update_phase_nav_buttons()

    def _on_next_phase(self):
        if (self._pause_phases
                and self._pause_phase_idx < len(self._pause_phases) - 1):
            self._pause_phase_idx += 1
            self._publish_paused_phase()
            self._update_phase_nav_buttons()

    def _publish_paused_phase(self):
        if not self._pause_phases:
            return
        phase = self._pause_phases[self._pause_phase_idx]
        mapping = self.manager.protocol_metadata.get(
            "electrode_to_channel", {},
        )
        electrodes = sorted(phase)
        channels = sorted(mapping[e] for e in electrodes if e in mapping)

        # Display path: always publishes to PROTOCOL_TREE_DISPLAY_STATE
        # so the DV's overlay tracks Prev/Next phase clicks instantly,
        # even in preview mode. Cached step metadata from _current_row.
        row = self._current_row
        if row is not None:
            dotted_id = row.dotted_path()
            display_msg = ProtocolTreeDisplayMessage(
                electrodes=electrodes,
                routes=list(getattr(row, "routes", []) or []),
                step_id=getattr(row, "uuid", "") or "",
                step_label=f"Step {dotted_id}",
                free_mode=False,
                editable=False,
            )
            try:
                publish_message(
                    topic=PROTOCOL_TREE_DISPLAY_STATE,
                    message=display_msg.serialize(),
                )
            except Exception as e:
                logger.warning(f"phase navigation display publish failed: {e}")

        # Hardware path: gated on preview. Matches RoutesHandler — the
        # backend has no preview awareness, we just don't publish.
        if not self._current_run_preview_mode:
            payload = {"electrodes": electrodes, "channels": channels}
            try:
                publish_message(
                    topic=ELECTRODES_STATE_CHANGE,
                    message=json.dumps(payload),
                )
            except Exception as e:
                logger.warning(f"phase navigation hardware publish failed: {e}")

    def _update_phase_nav_buttons(self):
        prev_enabled = self._pause_phase_idx > 0
        next_enabled = (
            bool(self._pause_phases)
            and self._pause_phase_idx < len(self._pause_phases) - 1
        )
        self.navigation_bar.set_phase_navigation_enabled(
            prev_enabled, next_enabled,
        )

    # --- step-cursor navigation -------------------------------------
    @attempt_func_execution_with_error_dialog
    def navigate_to_first_step(self):
        steps = list(self.manager.iter_execution_steps())
        if steps:
            logger.info(f"Nav: first step [{steps[0].dotted_path()}]")
            self._select_step(steps[0])

    @attempt_func_execution_with_error_dialog
    def navigate_to_last_step(self):
        steps = list(self.manager.iter_execution_steps())
        if steps:
            logger.info(f"Nav: last step [{steps[-1].dotted_path()}]")
            self._select_step(steps[-1])

    @attempt_func_execution_with_error_dialog
    def navigate_to_previous_step(self):
        steps = list(self.manager.iter_execution_steps())
        if not steps:
            return
        cur = self._current_step_in(steps)
        if cur is None:
            logger.info(f"Nav: previous (no current) --> [{steps[0].dotted_path()}]")
            self._select_step(steps[0])
            return
        if cur > 0:
            logger.info(f"Nav: previous step --> [{steps[cur - 1].dotted_path()}]")
            self._select_step(steps[cur - 1])

    @attempt_func_execution_with_error_dialog
    def navigate_to_next_step(self):
        steps = list(self.manager.iter_execution_steps())
        if not steps:
            return
        cur = self._current_step_in(steps)
        if cur is None:
            logger.info(f"Nav: next (no current) --> [{steps[0].dotted_path()}]")
            self._select_step(steps[0])
            return
        if cur < len(steps) - 1:
            logger.info(f"Nav: next step --> [{steps[cur + 1].dotted_path()}]")
            self._select_step(steps[cur + 1])
            return
        logger.info(f"Nav: next at end — duplicating [{steps[cur].dotted_path()}]")
        self._duplicate_step_after(steps[cur])

    def _duplicate_step_after(self, row):
        path = tuple(row.path)
        parent_path = path[:-1]
        insert_idx = path[-1] + 1
        values = {}
        for col in self.manager.columns:
            cid = col.model.col_id
            if hasattr(row, cid):
                values[cid] = getattr(row, cid)
        new_path = self.manager.add_step(
            parent_path=parent_path, index=insert_idx, values=values,
        )
        new_row = self.manager.get_row(new_path)
        self._select_step(new_row)

    def _current_step_in(self, steps):
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget.index_to_path(idx)
        for i, row in enumerate(steps):
            if tuple(row.path) == path:
                return i
        return None

    def _suppress_sync_publish(self):
        """Context manager wrapping a programmatic selection move so the
        sync controller's currentChanged slot does not trigger a publish."""
        pane = self
        class _Guard:
            def __enter__(self_):
                if pane.device_viewer_sync is not None:
                    pane.device_viewer_sync._suppress_publish = True
            def __exit__(self_, *exc):
                if pane.device_viewer_sync is not None:
                    pane.device_viewer_sync._suppress_publish = False
        return _Guard()

    @attempt_func_execution_with_error_dialog
    def _select_step(self, row):
        # No suppress wrap: nav buttons (next/prev/first/last) call this
        # path, and the user expects the DV to update on those clicks
        # just as on a direct row click. Only clear_highlights (transient
        # state reset) needs to suppress.
        self.widget.set_current_row(row)

    @attempt_func_execution_with_error_dialog
    def clear_highlights(self):
        """Reset the tree's selection + active-row highlight + per-step
        labels to the idle visual state."""
        with self._suppress_sync_publish():
            self.widget.highlight_active_row(None)
            self.widget.tree.clearSelection()
            self.widget.tree.setCurrentIndex(QModelIndex())

        self._step_index = 0
        self._step_total = 0
        self._step_started_at = None
        self._phase_started_at = None
        self._phase_target = None
        self._phase_index = 0
        self._phase_total = 0
        self._current_row = None

        self._status_step_label.setText("Step 0/0")
        self._status_step_time_label.setText("Step Time: 0 s")
        self._status_reps_label.setText("Repetition 0/0")
        self._status_reps_label.setVisible(True)
        self.status_bar.lbl_recent_step.setText("Most Recent Step: -")
        self.status_bar.lbl_next_step.setText("Next Step: -")
        if self._status_phase_time_label is not None:
            self._status_phase_time_label.setText("Phase 0/0  0.00s / 0.00s")

    def _logs_settling_time_s(self) -> float:
        """Settling provider injected into the logging controller. Reads
        the preference at flush-schedule time, so live preference edits
        take effect on the next run without re-wiring."""
        return float(self.preferences.logs_settling_time_s)

    # --- save / load -----------------------------------------------
    def _default_save_dir(self) -> str:
        """Default directory for the save dialog: PROTOCOL_REPO_DIR with a
        per-device subfolder named after the active SVG's stem (legacy
        protocol_grid parity). Best-effort — falls back to "" (last-used
        dir) when prefs/app_globals are unavailable (headless, no Redis)."""
        try:
            device = Path(app_globals.get(DEVICE_SVG_PATH_KEY, "Null")).stem
            default_dir = Path(self.preferences.PROTOCOL_REPO_DIR) / device
            default_dir.mkdir(parents=True, exist_ok=True)
            return str(default_dir)
        except Exception as e:
            logger.debug(f"default protocol save dir unavailable: {e}")
            return ""

    @attempt_func_execution_with_error_dialog
    def save_to_dialog(self, parent=None):
        """Open a file dialog and persist the manager's JSON state.

        Returns the saved path on success, ``None`` if the user cancels
        or the write fails.
        """
        path, _ = QFileDialog.getSaveFileName(
            parent or self, "Save Protocol", self._default_save_dir(),
            "Protocol JSON (*.json)",
        )
        if not path:
            return None
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.manager.to_json(), f, indent=2)
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Save error", message=str(e))
            return None
        return path

    @attempt_func_execution_with_error_dialog
    def load_from_dialog(self, columns_factory, parent=None):
        """Open a file dialog and replace the manager's state from JSON.

        ``columns_factory`` rebuilds the column list (consumed by
        ``set_state_from_json``); the dock pane and demo window each
        own a different source of truth for it. Returns the loaded path
        on success, ``None`` otherwise.
        """
        path, _ = QFileDialog.getOpenFileName(
            parent or self, "Load Protocol", "", "Protocol JSON (*.json)",
        )
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.manager.set_state_from_json(data, columns=columns_factory())
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Load error", message=str(e))
            return None
        return path

    @attempt_func_execution_with_error_dialog
    def closeEvent(self, event):
        """Detach Traits observers before the underlying QWidget is
        destroyed. Without this, application.experiment_changed firing
        after pane destruction dispatches to a deleted Qt object."""
        if self.application is not None:
            try:
                self.application.observe(
                    self._on_experiment_changed,
                    "experiment_changed",
                    remove=True,
                )
            except Exception as e:
                logger.warning(f"failed to detach experiment_changed observer: {e}")
            try:
                self.application.observe(
                    self._on_application_exiting,
                    "application_exiting",
                    remove=True,
                )
            except Exception as e:
                logger.warning(f"failed to detach application_exiting observer: {e}")
        try:
            self.manager.observe(
                self._on_manager_rows_changed, "rows_changed", remove=True,
            )
        except Exception as e:
            logger.warning(f"failed to detach rows_changed observer: {e}")
        try:
            self.manager.observe(
                self._on_manager_cell_changed, "cell_changed", remove=True,
            )
        except Exception as e:
            logger.warning(f"failed to detach cell_changed observer: {e}")
        if self.device_viewer_sync is not None:
            try:
                self.device_viewer_sync.detach()
            except Exception as e:
                logger.warning(f"failed to detach device_viewer_sync: {e}")
        super().closeEvent(event)

    # --- file menu actions ------------------------------------------

    def _on_manager_rows_changed(self, event):
        """Structural mutation — re-check the baseline path set."""
        self.protocol_state_tracker.on_structure_changed(self.manager)

    def _on_manager_cell_changed(self, event):
        """Cell value edit — incremental dirty update for the one cell."""
        payload = event.new
        if not isinstance(payload, dict):
            return
        path = payload.get("path")
        col_id = payload.get("col_id")
        if path is None or col_id is None:
            return
        self.protocol_state_tracker.on_cell_changed(
            path, col_id, self.manager,
        )
        self._reconcile_repeat_duration_for_row(path, col_id)

    def _reconcile_repeat_duration_for_row(self, path, col_id):
        """Mirror the legacy auto-recalc / effective-reps coupling:

          * In Route-Reps-controlled mode (``repeat_duration_controls``
            False): edits to any geometry/timing knob refresh the
            Route Reps Dur cell with the new estimate.
          * In Route-Reps-Dur-controlled mode (flag True): edits to
            Route Reps Dur refresh the Route Reps cell with the effective
            number of full cycles that fit.

        Programmatic writes here go via ``setattr`` directly (NOT
        ``model.set_value`` and NOT through ``on_interact``) so the
        mode-switch dialog only ever fires for genuine user clicks,
        never for these reconciliation passes.
        """
        if self._is_protocol_active():
            return
        try:
            row = self.manager.get_row(tuple(path))
        except (IndexError, AttributeError):
            return
        routes = list(getattr(row, "routes", []) or [])
        if not routes:
            return
        controls = bool(getattr(row, "repeat_duration_controls", False))
        duration_s = float(getattr(row, "duration_s", 1.0) or 0.0)
        trail_length = int(getattr(row, "trail_length", 1) or 1)
        trail_overlay = int(getattr(row, "trail_overlay", 0) or 0)
        linear_repeats = bool(getattr(row, "linear_repeats", False))
        soft_start = bool(getattr(row, "soft_start", False))
        soft_end = bool(getattr(row, "soft_end", False))

        if not controls and col_id in REPEAT_DURATION_RECALC_TRIGGERS:
            n_repeats = int(getattr(row, "route_repetitions", 1) or 1)
            estimated = estimate_repeat_duration_s(
                routes=routes,
                trail_length=trail_length, trail_overlay=trail_overlay,
                n_repeats=n_repeats, step_duration_s=duration_s,
                linear_repeats=linear_repeats,
                soft_start=soft_start, soft_end=soft_end,
            )
            estimated = round(estimated, 2)
            if abs(float(getattr(row, "repeat_duration", 0.0)) - estimated) >= 0.01:
                row.repeat_duration = estimated
                # Re-entrancy is bounded: see the
                # REPEAT_DURATION_RECALC_TRIGGERS guard + mode-check above;
                # "repeat_duration" is not a trigger in
                # route-reps-controlled mode so the next pass exits cleanly.
                self.manager.cell_changed = {
                    "path": tuple(path), "col_id": "repeat_duration",
                }
        elif controls and col_id == "repeat_duration":
            effective = effective_repetitions_for_duration(
                routes=routes,
                trail_length=trail_length, trail_overlay=trail_overlay,
                step_duration_s=duration_s,
                repeat_duration_s=float(getattr(row, "repeat_duration", 0.0) or 0.0),
            )
            if int(getattr(row, "route_repetitions", 1) or 1) != int(effective):
                row.route_repetitions = int(effective)
                self.manager.cell_changed = {
                    "path": tuple(path), "col_id": "route_repetitions",
                }

    def _confirm_proceed_or_abort(self) -> bool:
        """Returns True if the action should proceed.

        Shows a confirm dialog when the protocol is dirty, or when the
        loaded file no longer exists on disk. Returns False if the user
        picks NO.
        """
        tracker = self.protocol_state_tracker
        if tracker.is_modified:
            logger.warning("Attempting to overwrite unsaved protocol.")
            user_choice = confirm(
                self,
                "Current protocol has unsaved changes.\n"
                "Proceed without saving?",
                title="Unsaved Protocol Changes",
                cancel=False,
            )
            if user_choice == NO:
                logger.info("Action cancelled due to unsaved changes.")
                return False
        elif (tracker.loaded_protocol_path
              and not Path(tracker.loaded_protocol_path).exists()):
            logger.warning("Loaded protocol file no longer exists on disk.")
            user_choice = confirm(
                self,
                "Current protocol file has been deleted.\n"
                "Proceed without saving?",
                title="Protocol File Not Found",
                cancel=False,
            )
            if user_choice == NO:
                logger.info("Action cancelled due to missing protocol file.")
                return False
        return True

    @attempt_func_execution_with_error_dialog
    def new_protocol(self):
        if not self._confirm_proceed_or_abort():
            return
        self.manager.root = GroupRow(name="Root")
        self.manager.protocol_metadata = {}
        self.manager.selection = []
        self.manager.rows_changed = True
        self.protocol_state_tracker.reset()
        # Legacy protocol_grid parity: a new protocol starts with one
        # default step. Seed before reseeding so it's the clean baseline.
        self.manager.seed_default_step_if_empty()
        self.protocol_state_tracker.reseed_baseline(self.manager)

    def _seed_default_step_if_empty(self) -> None:
        """When no protocol is loaded, start with one default step (legacy
        protocol_grid parity) and treat it as the clean baseline so it
        isn't flagged as unsaved. No-op if the tree already has rows.
        Used by the full-app dock pane on startup."""
        if self.manager.seed_default_step_if_empty():
            self.protocol_state_tracker.reseed_baseline(self.manager)

    @attempt_func_execution_with_error_dialog
    def save_protocol_dialog(self):
        known_path = self.protocol_state_tracker.loaded_protocol_path
        if not known_path:
            self.save_as_protocol_dialog()
            return
        try:
            with open(known_path, "w", encoding="utf-8") as f:
                json.dump(self.manager.to_json(), f, indent=2)
        except Exception as e:
            error_dialog(parent=self, title="Save error", message=str(e))
            return
        self.protocol_state_tracker.set_saved(known_path)
        self.protocol_state_tracker.reseed_baseline(self.manager)

    @attempt_func_execution_with_error_dialog
    def save_as_protocol_dialog(self):
        path = self.save_to_dialog(parent=self)
        if path:
            self.protocol_state_tracker.set_saved(path)
            self.protocol_state_tracker.reseed_baseline(self.manager)

    @attempt_func_execution_with_error_dialog
    def load_protocol_dialog(self, columns_factory=None):
        if not self._confirm_proceed_or_abort():
            return
        factory = (columns_factory
                   if columns_factory is not None
                   else (lambda: list(self.manager.columns)))
        path = self.load_from_dialog(factory, parent=self)
        if path:
            self.protocol_state_tracker.set_loaded(path)
            self.protocol_state_tracker.reseed_baseline(self.manager)

    def _on_application_exiting(self, event):
        """Veto application exit when the protocol is dirty and the user
        elects to keep it open.

        ``event`` is a Pyface Vetoable event — setting ``event.veto = True``
        cancels the exit. Falls back to a non-fatal log if veto plumbing
        isn't available.
        """
        if not self.protocol_state_tracker.is_modified:
            return
        user_choice = confirm(
            self,
            "Current protocol has unsaved changes.\n"
            "Exit without saving?",
            title="Unsaved Protocol Changes",
            cancel=False,
        )
        if user_choice == NO:
            try:
                event.veto = True
            except Exception as e:
                logger.warning(f"could not veto application exit: {e}")

    # --- experiment-bar handlers ------------------------------------
    @attempt_func_execution_with_error_dialog
    def _schedule_flush_with_progress(self, controller):
        """Custom flush scheduler: pop the "Generating Run Report..." dialog
        immediately, then sit through the settling delay (so in-flight
        capacitance is captured) before running ``controller._flush()`` in
        a background QThread. Legacy parity with protocol_grid's
        ``@with_loading_screen("Generating Run Report...")``.

        Showing the dialog *before* the settling timer (not after) is the
        UX point: ``stop_logging`` is called the moment the user dismisses
        the new-experiment / summary confirm, so any latency between that
        click and the dialog reads as the GUI freezing. With this order
        the user sees feedback instantly, the settling delay (and the
        plotly chart build) happens under the dialog, and the worker
        thread keeps the GUI responsive while charts render.

        When the run skipped the report (force-stop -> NO), the flush is
        just a quick data-file write — no dialog, no worker thread, fast
        path mirrors the original ``QTimer.singleShot`` scheduler.
        """
        settling_ms = int(controller.settling_provider() * 1000)
        if not controller._generate_report:
            QTimer.singleShot(settling_ms, controller._flush)
            return

        progress = QProgressDialog(
            "Generating Run Report...", None, 0, 0, self)
        progress.setWindowTitle("Please Wait")
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        def _start_worker():
            worker_holder = {}

            class _FlushWorker(QThread):
                def run(self_inner):
                    try:
                        controller._flush()
                    except Exception as e:
                        logger.warning(f"deferred flush failed: {e}")

            worker = _FlushWorker(self)
            worker_holder["w"] = worker          # keep reference alive
            loop = QEventLoop()
            worker.finished.connect(loop.quit)
            worker.finished.connect(progress.close)
            worker.start()
            loop.exec()

        QTimer.singleShot(settling_ms, _start_worker)

    @attempt_func_execution_with_error_dialog
    def _on_logging_complete(self, report_path):
        """Controller completion callback (runs on the GUI thread via the
        QTimer-scheduled flush). Shows the report-link success dialog when a
        report was generated; silent when it was skipped or the flush failed."""
        if report_path is None:
            return
        try:
            file_url = QUrl.fromLocalFile(str(report_path)).toString(QUrl.FullyEncoded)
            success(
                parent=None,
                message=(f"Report file saved to:<br>"
                         f"<a href='{file_url}'>{Path(report_path).name}</a>"),
                title="Run Summary Generated",
            )
        except Exception as e:
            logger.warning(f"run-summary success dialog failed: {e}")

    @attempt_func_execution_with_error_dialog
    def _on_new_experiment(self):
        if self.experiment_manager is None or self.application is None:
            logger.info("New Experiment requested (stub: no services injected)")
            return
        new_dir = self.experiment_manager.initialize_new_experiment()
        if new_dir is None:
            logger.warning("initialize_new_experiment returned None; label unchanged")
            return
        # The setter fires application.experiment_changed; the
        # _on_experiment_changed observer updates the label.
        self.application.current_experiment_directory = new_dir
        logger.info(f"Started new experiment: {new_dir.stem}")

    @attempt_func_execution_with_error_dialog
    def _on_new_note(self):
        if self.sticky_manager is None or self.experiment_manager is None:
            logger.info("New Note requested (stub: no services injected)")
            return
        base_dir = self.experiment_manager.get_experiment_directory()
        experiment_name = base_dir.stem
        self.sticky_manager.request_new_note(base_dir, experiment_name)

    @attempt_func_execution_with_error_dialog
    def _on_experiment_label_clicked(self):
        if self.experiment_manager is None:
            logger.info("Experiment label clicked (stub: no service injected)")
            return
        self.experiment_manager.open_experiment_directory()

    @attempt_func_execution_with_error_dialog
    def _on_experiment_changed(self, _event):
        if self.experiment_label is None:
            return
        try:
            cur = self.application.current_experiment_directory
        except Exception as e:
            logger.warning(f"experiment_changed: failed to read dir: {e}")
            return
        if cur is None:
            return
        self.experiment_label.update_experiment_id(cur.stem)

    # --- quick-actions helpers --------------------------------------
    @attempt_func_execution_with_error_dialog
    def _insert_position_after_selection(self):
        """Return ``(parent_path, index)`` for "insert after current
        selection". Rules:

        * No selection  -> ``((), None)``  (append at root).
        * Single GroupRow selected  -> ``(group_path, None)``  (append
          INSIDE the group as its last child).
        * Single step (or last of multi-selection)  -> ``(parent_path,
          step_index + 1)``  (insert immediately after).
        """
        sel = list(self.manager.selection or [])
        if not sel:
            return ((), None)
        last = tuple(sel[-1])
        # Single-group selection -> append inside the group.
        if len(sel) == 1:
            try:
                row = self.manager.get_row(last)
            except (IndexError, AttributeError):
                row = None
            if isinstance(row, GroupRow):
                return (last, None)
        # Step (or fallback for multi-selection): insert after at parent.
        return (last[:-1], last[-1] + 1)

    @attempt_func_execution_with_error_dialog
    def add_step_after_selection(self):
        parent_path, index = self._insert_position_after_selection()
        self.manager.add_step(parent_path=parent_path, index=index)

    @attempt_func_execution_with_error_dialog
    def add_group_after_selection(self):
        parent_path, index = self._insert_position_after_selection()
        self.manager.add_group(parent_path=parent_path, index=index)

    @attempt_func_execution_with_error_dialog
    def delete_selected_rows(self):
        sel = list(self.manager.selection or [])
        if not sel:
            return
        self.manager.remove(sel)

    @attempt_func_execution_with_error_dialog
    def delete_last_step(self):
        """Delete the last meaningful element at the end of the protocol.

        Walks down the rightmost path through groups:
          * Empty trailing group  -> delete the group.
          * Non-empty group       -> descend, then re-check.
          * Step                  -> delete the step.

        No-op when the tree is empty. The primary case (the user's
        common click) is "delete the deepest-rightmost step"; the
        empty-trailing-group case keeps the action from silently
        no-op'ing when the user has lingering empty groups."""
        parent = self.manager.root
        if not parent.children:
            return
        while True:
            last = parent.children[-1]
            if isinstance(last, GroupRow):
                if not last.children:
                    self.manager.remove([tuple(last.path)])
                    return
                parent = last
                continue
            self.manager.remove([tuple(last.path)])
            return

    @attempt_func_execution_with_error_dialog
    def import_into_selected_group(self):
        """Open a file picker, load the JSON protocol, and merge every
        top-level row from the loaded protocol under the selected group.

        No-op when the selection isn't exactly one row OR the selected
        row isn't a GroupRow.
        """
        sel = list(self.manager.selection or [])
        if len(sel) != 1:
            return
        target_path = tuple(sel[0])
        try:
            target = self.manager.get_row(target_path)
        except (IndexError, AttributeError):
            return
        if not isinstance(target, GroupRow):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Protocol", "", "Protocol JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"import_into_selected_group: read failed: {e}")
            return
        # Look up positions by name so we stay correct if the
        # persistence schema reorders or adds fixed metadata.
        fields = data.get("fields") or []
        try:
            depth_idx = fields.index("depth")
            type_idx = fields.index("type")
            name_idx = fields.index("name")
        except ValueError:
            return            # malformed file — no fixed metadata
        # (index, col_id) pairs for the column-value positions:
        # everything except the reserved row-metadata fields.
        col_field_positions = [
            (i, fid) for i, fid in enumerate(fields)
            if fid not in _RESERVED_ROW_METADATA_FIELDS
        ]
        # Build once — same across all rows; keyed by col_id for O(1)
        # lookup inside the loop.
        live_by_col_id = {
            c.model.col_id: c for c in self.manager.columns
        }

        for row in (data.get("rows") or []):
            # Top-level only — nested rows are not recursively
            # imported (deep-import out of scope; legacy parity).
            if int(row[depth_idx]) != 0:
                continue
            if row[type_idx] == "group":
                self.manager.add_group(
                    parent_path=target_path, name=row[name_idx])
            else:
                # Resolve each saved column id against the LIVE column
                # set. Skip:
                #   * column ids unknown to this tree (different plugin
                #     set) — would otherwise set orphan attributes.
                #   * None saved values — strict-typed traits (Float,
                #     Int, ...) reject None; skipping lets the trait's
                #     default apply.
                # Use the live column's model.deserialize so custom
                # serializations round-trip correctly (matches
                # services/persistence.deserialize_tree).
                values = {}
                for i, fid in col_field_positions:
                    live = live_by_col_id.get(fid)
                    if live is None:
                        continue
                    raw = row[i]
                    if raw is None:
                        continue
                    values[fid] = live.model.deserialize(raw)
                # Name was filtered from col_field_positions by the
                # persistence dedup — inject it explicitly from the
                # fixed metadata position.
                values["name"] = row[name_idx]
                self.manager.add_step(
                    parent_path=target_path, values=values,
                )
