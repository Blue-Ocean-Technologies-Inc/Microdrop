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

from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.decorators import attempt_func_execution_with_error_dialog
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.pyside_helpers import LoadingOverlay

from device_viewer.consts import DEVICE_SVG_PATH_KEY, PROTOCOL_RUNNING
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED,
    ELECTRODES_STATE_CHANGE, PROTOCOL_FILE_DIALOG_FILTER)
from pluggable_protocol_tree.execution.exceptions import StepExecutionError
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.services.persistence import (
    _RESERVED_ROW_METADATA_FIELDS,
)
from pluggable_protocol_tree.services.logging.controller import (
    ProtocolLoggingController,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)
from pluggable_protocol_tree.services.protocol_validator import validate_protocol
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.lifecycle.logging import LoggingHandler
from pluggable_protocol_tree.execution.lifecycle.realtime_mode import (
    RealtimeModeHandler,
)
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
from pluggable_protocol_tree.views.protocol_validator_presenter import (
    confirm_report,
)
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

# Auto-dismiss timeout for the preview-complete toast.
PREVIEW_COMPLETE_TOAST_MS = 3000
# app_globals value used when no device SVG path has been published
# (legacy protocol_grid sentinel — saves then land in a "Null" subfolder).
NO_DEVICE_SVG_SENTINEL = "Null"
# Run-outcome sentinels threaded from the terminal handlers through
# _on_protocol_terminated into _run_completion_flow.
RUN_OUTCOME_FINISHED = "finished"
RUN_OUTCOME_ABORTED = "aborted"
RUN_OUTCOME_ERROR = "error"
# Route-Reps-Dur auto-recalc: display rounding + write-back tolerance
# that stops estimate jitter from dirtying the cell.
REPEAT_DURATION_DECIMALS = 2
REPEAT_DURATION_TOLERANCE_S = 0.01


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
    # Emitted (from the flush worker thread) with the error message when a
    # report the user asked for fails to generate; QueuedConnection marshals
    # it to the GUI thread so the error dialog runs there.
    _report_failed = Signal(str)
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
        preferences=None,
        quick_actions=None,
        protocol_state_tracker=None,
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
        # Protocol preferences model, passed down from the dock pane in the
        # full app (bound to the application's preferences there). Demos and
        # headless tests get a standalone instance against the global default
        # preferences node, so every consumer can rely on it being present.
        self.preferences = preferences or ProtocolPreferences()

        self.protocol_state_tracker = protocol_state_tracker or PluggableProtocolStateTracker()

        self.widget = ProtocolTreeWidget(
            self.manager, preferences=self.preferences, parent=self)

        # Loading screen shown over the tree during the executor's pre-protocol
        # wait (realtime settle, etc.). Same widget the old protocol_grid used.
        self.loading_overlay = LoadingOverlay(self.widget.tree)

        self.device_viewer_sync = device_viewer_sync
        if self.device_viewer_sync is not None:
            self.device_viewer_sync.attach(self.widget)

        # Re-emit the tree's selectionChanged as a parameterless signal so
        # the QuickActionsController doesn't have to know about Qt selection
        # models. The pane already constructed self.widget above.
        self.widget.tree.selectionModel().selectionChanged.connect(
            lambda *_: self.selection_changed.emit()
        )

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
        self._report_failed.connect(
            self._on_report_failed, Qt.QueuedConnection)
        self.logging_controller = ProtocolLoggingController(
            completion_callback=self._logging_complete.emit,
            report_failure_callback=self._report_failed.emit,
            flush_scheduler=self._schedule_flush_with_progress,
            settling_provider=self._logs_settling_time_s,
        )
        self.logging_controller.attach(self.executor.qsignals)

        # Execution lifecycle policy lives in handlers, not the view. These
        # run once per run (on_pre_protocol_start / on_post_protocol_end) at
        # high priority so they trail every column's start hooks: realtime
        # mode is enabled + settled (900), then logging starts (1000) right
        # before the first step. The view only wires them (composition root).
        self.executor.lifecycle_handlers = [
            RealtimeModeHandler(preferences=self.preferences),
            LoggingHandler(
                controller=self.logging_controller,
                experiment_dir_provider=(
                    lambda: self.experiment_manager.get_experiment_directory()
                ),
                n_steps_provider=(
                    lambda: sum(1 for _ in self.manager.iter_execution_frames())
                ),
            ),
        ]

        # Status-bar timing/counting now lives in ProtocolStatusModel, driven
        # by ProtocolStatusController and bound to the StatusBar by the
        # composition root (dock pane / demo window). The pane keeps only the
        # nav-relevant current row + pause-phase cursor below.
        self._current_row = None
        self._current_run_preview_mode = False
        self.status_controller = None  # set by the composition root (#471)
        # Guards the window between play-click and the protocol_started
        # signal (the executor's on_pre_protocol_start realtime settle runs
        # in there) so a second play-click can't start a duplicate run.
        self._start_pending = False
        # True while the pre-protocol wait loading screen is up, so pause/resume
        # know to freeze/restart its countdown.
        self._wait_active = False

        self._wire_executor_signals()
        self._wire_button_state_machine()
        self._wire_navigation_buttons()
        self._set_idle_button_state()

        # Set the initial experiment label (application is None in
        # standalone demos/tests — the label just stays blank there).
        if self.application is not None:
            cur = self.application.current_experiment_directory
            if cur is not None:
                self.experiment_label.update_experiment_id(cur.stem)

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
        # Pane keeps the nav-relevant current row; status counters/timers are
        # owned by ProtocolStatusController.
        self.executor.qsignals.step_started.connect(self._on_step_started)
        self.executor.qsignals.protocol_wait_started.connect(
            self._on_protocol_wait_started)
        self.executor.qsignals.protocol_wait_finished.connect(
            self._on_protocol_wait_finished)
        self.executor.qsignals.protocol_started.connect(self._on_protocol_started)
        self.executor.qsignals.protocol_error.connect(self._on_error)
        if self.phase_ack_topic is not None:
            self.phase_acked.connect(self._on_phase_ack)

    def _wire_button_state_machine(self):
        self.executor.qsignals.protocol_started.connect(
            self._set_running_button_state,
        )
        # During the pre-protocol wait, go to the running button state too —
        # pause + stop stay live, everything else is disabled.
        self.executor.qsignals.protocol_wait_started.connect(
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
        self._start_pending = False
        self.protocol_running_changed.emit(True)
        self._publish_protocol_running("True")
        logger.info("Protocol started")

    def _on_step_started(self, row):
        # The pane keeps only the nav-relevant current row; the status
        # counters/timers/labels are owned by ProtocolStatusController +
        # ProtocolStatusModel and bound to the StatusBar by the
        # composition root.
        self._current_row = row

        # NOTE: we deliberately do NOT publish the static step view to the
        # DV here. RoutesHandler publishes a per-phase display for every
        # phase (carrying step_id/label/routes + the phase's active
        # electrodes, editable=False), which is the authoritative source
        # while a protocol runs. Publishing _publish_for_row(row) here too
        # raced with phase 1: the worker publishes phase 1 to the broker
        # before this queued slot runs, so the static view (electrodes=[],
        # editable=True) consistently landed AFTER phase 1 and cleared it,
        # making the animation appear to begin at the second position.

    def _on_phase_ack(self):
        # Phase boundary now comes from the executor's phase_started
        # signal (independent of hardware ack). Kept as a no-op so
        # external code emitting phase_acked doesn't fight anything.
        return

    def _on_error(self, msg):
        logger.error(f"Protocol error: {msg}")
        self._publish_protocol_running("False")
        # Immediate teardown only; the completion flow is deferred so the
        # error dialog is shown before the "Generate Run Summary?" prompt.
        self._on_protocol_terminated(RUN_OUTCOME_ERROR)
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
        self._run_completion_flow(RUN_OUTCOME_ERROR)

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
            col_label = exc.col_label
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

    # --- button state machine ----------------------------------------

    def _set_idle_button_state(self):
        self.protocol_state_tracker.is_active = False
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_play_state()
        nb.btn_stop.setEnabled(False)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)
        nb.action_preview.setEnabled(True)

    def _set_running_button_state(self):
        self.protocol_state_tracker.is_active = True
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
        repeats = self.status_bar.edit_repeat_protocol.value()
        self._current_run_preview_mode = preview_mode
        start_path = self._selected_step_path()
        logger.info(
            f"Protocol run starting: {repeats} rep(s), "
            f"preview={preview_mode}, start_step={start_path}"
        )
        # Realtime-mode prep + settle and logging start are once-per-run
        # executor lifecycle hooks (RealtimeModeHandler / LoggingHandler,
        # wired in _build_executor); the executor owns the repeat loop, so
        # the whole run (all repetitions) is a single start() call.
        # _start_pending guards the play button until protocol_started
        # fires (after the realtime settle, which now runs on the worker).
        self._start_pending = True
        self.executor.start(
            start_step_path=start_path,
            preview_mode=preview_mode,
            repeats=repeats,
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
        # One source of truth shared with non-view collaborators (the
        # dock pane observes the same tracker) — kept in lockstep with
        # the button state machine above, which sets it.
        return self.protocol_state_tracker.is_active

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
        else:
            self.executor.pause()

    def _on_protocol_wait_started(self, total_ms):
        # The run is on its way; clear the start guard and show the loading
        # screen countdown over the tree. auto_stop=False — the executor
        # dismisses it via protocol_wait_finished (it owns the wait clock).
        self._start_pending = False
        self._wait_active = True
        self.loading_overlay.show_loading(
            "Preparing protocol run…", duration_ms=total_ms, auto_stop=False)

    def _on_protocol_wait_finished(self):
        self._wait_active = False
        self.loading_overlay.stop_loading()

    def _on_protocol_paused(self):
        logger.info("Protocol paused")
        self.navigation_bar.show_resume_state()
        if self._wait_active:
            # Freeze the loading-screen countdown in lockstep with the
            # executor's frozen pre-protocol wait.
            self.loading_overlay.pause()
        nb = self.navigation_bar
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)
        if self._current_row is not None:
            nb.split_play_button_to_phase_controls()
            self._update_phase_nav_buttons()

    def _on_protocol_resumed(self):
        logger.info("Protocol resumed")
        self.navigation_bar.show_pause_state()
        if self._wait_active:
            self.loading_overlay.resume()
        nb = self.navigation_bar
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)
        nb.merge_phase_controls_to_play_button()

    def _on_protocol_finished(self):
        # The executor owns the repeat loop now, so protocol_finished fires
        # once at the end of the whole run; the per-rep label is updated by
        # _on_protocol_repetition_finished during the run.
        self._publish_protocol_running("False")
        logger.info("Protocol finished")
        self._on_protocol_terminated(RUN_OUTCOME_FINISHED)

    def _on_protocol_aborted(self):
        logger.info("Protocol aborted by user")
        self._publish_protocol_running("False")
        self._on_protocol_terminated(RUN_OUTCOME_ABORTED)

    def _on_protocol_terminated(self, outcome=RUN_OUTCOME_FINISHED):
        self.protocol_running_changed.emit(False)
        logger.info("Protocol terminated --> free mode")
        # Defensive: the executor normally dismisses the loading screen via
        # protocol_wait_finished, but make sure it's never left up. Also clear
        # the start guard in case the run was stopped before protocol_started
        # fired (which is what normally clears it).
        self._wait_active = False
        self._start_pending = False
        self.loading_overlay.stop_loading()
        self.clear_highlights()
        self._set_idle_button_state()
        self.navigation_bar.merge_phase_controls_to_play_button()
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
        # Realtime-mode restore is owned by RealtimeModeHandler's
        # on_post_protocol_end hook (runs once per run on the executor).
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
        if outcome != RUN_OUTCOME_ERROR:
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
                            title="Preview Complete",
                            timeout=PREVIEW_COMPLETE_TOAST_MS)
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

        # Only offer / build a report if the run actually logged step data.
        # A run stopped before any step ran (e.g. Stop on the loading screen)
        # has nothing meaningful — skip the prompt and generate no report.
        generate_report = self.logging_controller.has_data()
        if generate_report and outcome in (RUN_OUTCOME_ABORTED, RUN_OUTCOME_ERROR) and have_exp:
            try:
                if confirm(parent=None,
                           message=("Protocol was stopped before completion."
                                    "<br><br>Press <b>YES</b> to create run "
                                    "summary."),
                           title="Generate Run Summary?", cancel=False) == NO:
                    generate_report = False
            except Exception as e:
                logger.warning(f"run-summary confirm failed: {e}")
        elif outcome == RUN_OUTCOME_FINISHED and have_exp:
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

    def _on_prev_phase(self):
        self._seek_relative_phase(-1)

    def _on_next_phase(self):
        self._seek_relative_phase(+1)

    def _seek_relative_phase(self, delta):
        sc = self.status_controller
        if sc is None or self._current_row is None:
            return
        target0 = (sc.model.phase_index - 1) + delta   # model phase_index is 1-based
        path = tuple(self._current_row.path)
        sc.seek_to(path, target0)
        sc.preview_phase(path, target0, self._current_run_preview_mode)
        self._update_phase_nav_buttons()

    def _update_phase_nav_buttons(self):
        m = self.status_controller.model if self.status_controller else None
        if m is None:
            self.navigation_bar.set_phase_navigation_enabled(False, False)
            return
        prev_enabled = m.phase_index > 1
        next_enabled = 0 < m.phase_index < m.phase_total
        self.navigation_bar.set_phase_navigation_enabled(prev_enabled, next_enabled)

    # --- step-cursor navigation -------------------------------------
    @attempt_func_execution_with_error_dialog
    def navigate_to_first_step(self):
        steps = self._navigable_steps()
        if steps:
            logger.info(f"Nav: first step [{steps[0].dotted_path()}]")
            self._select_step(steps[0])

    @attempt_func_execution_with_error_dialog
    def navigate_to_last_step(self):
        steps = self._navigable_steps()
        if steps:
            logger.info(f"Nav: last step [{steps[-1].dotted_path()}]")
            self._select_step(steps[-1])

    @attempt_func_execution_with_error_dialog
    def navigate_to_previous_step(self):
        steps = self._navigable_steps()
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
        steps = self._navigable_steps()
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
        if self.status_controller is not None and self.status_controller.model.paused:
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

    def _navigable_steps(self):
        """Distinct steps in execution order for the step cursor.

        iter_execution_steps() expands repetitions — a Reps=N step (or a
        step nested under a Reps=N group) is yielded N times as the *same*
        row. The cursor navigates structural steps, so collapse those
        repeats to one entry per row; otherwise next/prev would re-select
        the same row and the cursor would never advance past a repeated step.
        """
        seen = set()
        steps = []
        for row in self.manager.iter_execution_steps():
            if row.uuid in seen:
                continue
            seen.add(row.uuid)
            steps.append(row)
        return steps

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
        sc = self.status_controller
        if sc is not None and sc.model.paused:
            self._current_row = row
            path = tuple(row.path)
            sc.seek_to(path, 0)
            sc.preview_phase(path, 0, self._current_run_preview_mode)
            self._update_phase_nav_buttons()

    @attempt_func_execution_with_error_dialog
    def clear_highlights(self):
        """Reset the tree's selection + active-row highlight to the idle
        visual state. Status-bar fields are owned by ProtocolStatusModel and
        reset on the next run (on_protocol_start)."""
        with self._suppress_sync_publish():
            self.widget.highlight_active_row(None)
            self.widget.tree.clearSelection()
            self.widget.tree.setCurrentIndex(QModelIndex())

        self._current_row = None

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
            device = Path(
                app_globals.get(DEVICE_SVG_PATH_KEY, NO_DEVICE_SVG_SENTINEL)
            ).stem
            default_dir = Path(self.preferences.PROTOCOL_REPO_DIR) / device
            default_dir.mkdir(parents=True, exist_ok=True)
            return str(default_dir)
        except Exception as e:
            logger.debug(f"default protocol save dir unavailable: {e}")
            return ""

    def _write_protocol_json(self, path, parent=None) -> bool:
        """Persist the manager's JSON state to ``path``. Returns True on
        success; shows the save-error dialog and returns False on failure."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.manager.to_json(), f, indent=2)
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Save error", message=str(e))
            return False
        return True

    @attempt_func_execution_with_error_dialog
    def save_to_dialog(self, parent=None):
        """Open a file dialog and persist the manager's JSON state.

        Returns the saved path on success, ``None`` if the user cancels
        or the write fails.
        """
        path, _ = QFileDialog.getSaveFileName(
            parent or self, "Save Protocol", self._default_save_dir(),
            PROTOCOL_FILE_DIALOG_FILTER,
        )
        if not path:
            return None
        if not self._write_protocol_json(path, parent=parent):
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
            parent or self, "Load Protocol", "", PROTOCOL_FILE_DIALOG_FILTER,
        )
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            columns = columns_factory()
            # Device's current electrode->channel map (from DEVICE_VIEWER_GEOMETRY_CHANGED);
            # None when no device/sync is wired -> validator skips device-dependent checks.
            device_map = None
            if self.device_viewer_sync is not None:
                device_map = dict(self.device_viewer_sync.electrode_ids_channels_map)
            report = validate_protocol(data, columns, device_map)
            if not report.is_empty:
                if confirm_report(report, parent=parent or self) != YES:
                    return None
            # report already shown in the dialog -> don't re-log it
            self.manager.set_state_from_json(
                data, columns=columns, report_findings=False,
            )
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Load error", message=str(e))
            return None
        return path

    # --- file menu actions ------------------------------------------
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
        if not self._write_protocol_json(known_path):
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
        report was generated; silent when it was skipped (a requested report
        that fails is reported separately via _on_report_failed)."""
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
    def _on_report_failed(self, message):
        """Surface a requested run-summary that failed to generate, so the
        user isn't left with the same silence as an intentional skip. The
        run's data files were still written."""
        error_dialog(
            parent=None,
            message="The run summary could not be generated.<br><br>"
                    "The run's data files were still saved to the experiment "
                    "directory.",
            title="Run Summary Failed",
            detail=message,
        )

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
    def _on_experiment_changed(self):
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
            self, "Import Protocol", "", PROTOCOL_FILE_DIALOG_FILTER)
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
