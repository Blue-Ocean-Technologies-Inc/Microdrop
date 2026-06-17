"""Pyface TaskPane hosting ProtocolTreePane.

Receives its column set from the plugin on construction and constructs
the experiment + sticky-note services from the live Envisage
application so the experiment-bar buttons drive real handlers."""
import html as _html
import json
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING, STATE_STOPPED
from apscheduler.triggers.interval import IntervalTrigger

from microdrop_application.dialogs.pyface_wrapper import (
    confirm, NO, YES, error as error_dialog, escape_html_multiline,
    format_traceback_detail, information,
)
from microdrop_style.colors import DIALOG_ERROR_TEXT_COLOR
from microdrop_utils.decorators import attempt_func_execution_with_error_dialog
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from device_viewer.consts import PROTOCOL_RUNNING
from pluggable_protocol_tree.consts import (
    REPEAT_DURATION_RECALC_TRIGGERS, ACK_WAIT_FOREVER, ELECTRODES_STATE_CHANGE,
)
from pluggable_protocol_tree.execution.events import PauseEvent
from pluggable_protocol_tree.execution.exceptions import StepExecutionError
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.execution.lifecycle.logging import LoggingHandler
from pluggable_protocol_tree.execution.lifecycle.realtime_mode import (
    RealtimeModeHandler,
)
from pluggable_protocol_tree.execution.signals import ExecutorSignals
from pluggable_protocol_tree.services.logging.controller import (
    ProtocolLoggingController,
)
from pluggable_protocol_tree.services.phase_math import effective_repetitions_for_duration, estimate_repeat_duration_s
from pluggable_protocol_tree.services.protocol_state_tracker import PluggableProtocolStateTracker
from pluggable_protocol_tree.services.protocol_status_controller import ProtocolStatusController
from pyface.tasks.api import TraitsDockPane
from traits.api import Any, Bool, Event, Float, Instance, List, Str, observe

from logger.logger_service import get_logger
from microdrop_utils.sticky_notes import StickyWindowManager
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import DeviceViewerSyncController
from pluggable_protocol_tree.views.protocol_tree_pane import (
    ProtocolTreePane, REPEAT_DURATION_TOLERANCE_S, REPEAT_DURATION_DECIMALS,
    RUN_OUTCOME_FINISHED, RUN_OUTCOME_ABORTED, RUN_OUTCOME_ERROR,
    PREVIEW_COMPLETE_TOAST_MS,
)
from pluggable_protocol_tree.views.navigation_bar import STATUS_POLL_INTERVAL_MS
from protocol_grid.services.experiment_manager import ExperimentManager

from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.services.preferences import (
    ProtocolPreferences
)

logger = get_logger(__name__)

# The status-time poll job runs at 10 Hz; silence APScheduler's per-execution
# logs so it doesn't flood the log.
get_logger('apscheduler.executors.default').setLevel(level="WARNING")


class PluggableProtocolDockPane(TraitsDockPane):
    id = "pluggable_protocol_tree.dock_pane"
    name = Str("Protocol (pluggable)")

    columns = List(Instance(IColumn))
    manager = Instance(RowManager)
    sync = Instance(DeviceViewerSyncController)
    sticky_manager = Instance(StickyWindowManager)
    experiment_manager = Instance(ExperimentManager)
    quick_actions = List(desc="Quick actions to mount under the tree.")
    protocol_state_tracker = Instance(PluggableProtocolStateTracker)

    #: Links the executor's Qt signals to the status model and binds the
    #: status bar to it (issue #467). The dock pane is the app's HasTraits
    #: composition root that "sets up the link" between Qt and the model.
    status_controller = Instance(ProtocolStatusController)
    #: 10 Hz background job that ticks the live status-bar time readouts. It
    #: runs on its own thread and only fires ``time_update_event`` — the actual
    #: widget writes happen on the GUI thread via the dispatch="ui" observer.
    _protocol_poll_scheduler = Instance(BackgroundScheduler,
                                        desc="Ticks the status-bar time readouts at 10 Hz")
    #: Fired (carrying time.monotonic()) on each poll tick from the scheduler's
    #: background thread; _update_protocol_time observes it with dispatch="ui".
    protocol_time_update_event = Event(Float)

    #: Protocol preferences model (the "microdrop.protocol" node). Bound to
    #: the live application's preferences in create_contents, then passed
    #: down to ProtocolTreePane, which hands it to whatever needs it (save
    #: dialogs, realtime-mode settling/restore, logging settling, column
    #: visibility).
    preferences = Instance(ProtocolPreferences)

    executor = Instance(ProtocolExecutor)

    #: Logging controller (executor signals -> per-run report). Owned here;
    #: its GUI-thread completion bridge + dialogs live on the pane (view).
    logging_controller = Instance(ProtocolLoggingController)

    # Run state owned by the controller — the pane is a pure view (#471).
    #: The nav cursor: the paused/executing step the cursor tracks; mirrored
    #: from the status model's current_step_path by the highlight observer.
    _current_row = Any()
    #: True while the active run is a preview (no artifacts/report).
    _current_run_preview_mode = Bool(False)
    #: Guards the play button between play-click and protocol_started.
    _start_pending = Bool(False)
    #: True while the pre-protocol wait loading screen is up.
    _wait_active = Bool(False)

    def _executor_default(self):
        return ProtocolExecutor(
            row_manager=self.manager,
            signals=ExecutorSignals(),
            pause_event=PauseEvent(),
            stop_event=threading.Event(),
        )

    def _experiment_manager_default(self):
        return ExperimentManager(self.task.window.application.current_experiment_directory)

    def _sticky_manager_default(self):
        return StickyWindowManager()

    def _protocol_state_tracker_default(self):
        # dock_pane=self binds the tracker's display name ("<name> -
        # <protocol> [modified]") to this pane's title.
        return PluggableProtocolStateTracker(dock_pane=self)

    def _preferences_default(self):
        return ProtocolPreferences(preferences=self.task.window.application.preferences)

    def _sync_default(self):
        return DeviceViewerSyncController(row_manager=self.manager)

    def _manager_default(self):
        return RowManager(columns=list(self.columns))

    def traits_init(self):
        # One ack-wait grid entry per wait-capable column, user-edited
        # values persisted on the node are kept.
        self.preferences.seed_ack_times_from_columns(self.columns)
        # Handlers boot with their provider default and the observer
        # below only sees edits made from here on — push the persisted
        # grid values in once so a user-tuned wait survives a relaunch.
        self._sync_handler_ack_times()

    def create_contents(self, parent):
        self._pane = pane = ProtocolTreePane(
            self.manager,
            application=self.task.window.application,
            experiment_manager=self.experiment_manager,
            sticky_manager=self.sticky_manager,
            device_viewer_sync=self.sync,
            preferences=self.preferences,
            quick_actions=list(self.quick_actions),
            protocol_state_tracker=self.protocol_state_tracker,
            parent=parent,
        )

        # The dock pane is the composition root: it owns the executor, the
        # status controller (executor signals -> status model), the logging
        # controller, and all run control. The pane is a pure view.
        self.status_controller = ProtocolStatusController(
            manager=self.manager,
            executor=self.executor,
        )

        # Logging controller + executor lifecycle handlers. The completion /
        # report-failure callbacks + flush scheduler live on the pane (the
        # QObject GUI-thread bridge + dialog presentation); the controller and
        # handlers that drive them are owned here.
        self.logging_controller = ProtocolLoggingController(
            completion_callback=pane._logging_complete.emit,
            report_failure_callback=pane._report_failed.emit,
            flush_scheduler=pane._schedule_flush_with_progress,
            settling_provider=lambda: float(self.preferences.logs_settling_time_s),
        )
        self.logging_controller.attach(self.executor.signals)
        # Execution lifecycle policy lives in handlers, not the view. These run
        # once per run (on_pre_protocol_start / on_post_protocol_end) at high
        # priority so they trail every column's start hooks: realtime mode is
        # enabled + settled (900), then logging starts (1000) right before the
        # first step.
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

        # Background poll job for the live time readouts. Started paused; the
        # running observer resumes/pauses it. It only fires time_update_event
        # from its worker thread — _update_protocol_time runs on the GUI thread
        # via dispatch="ui".
        self._protocol_poll_scheduler = BackgroundScheduler()
        self._protocol_poll_scheduler.add_job(
            self._emit_time_update_tick,
            trigger=IntervalTrigger(seconds=STATUS_POLL_INTERVAL_MS / 1000.0),
        )
        self._protocol_poll_scheduler.start(paused=True)

        # Phase trackers are always shown in the full app (issue #467); the
        # pane only auto-reveals the phase field when a phase_ack_topic is set
        # (demo path), so make it explicit here.
        pane.status_bar.lbl_phase_time.setVisible(True)

        # initial values for status bar
        self._on_counts_changed()
        self._on_repeats_changed()
        self._on_names_changed()
        self._update_protocol_time()

        # Wire executor lifecycle signals -> dock-pane handlers (the controller
        # role). Each handler drives the model/run-state and calls thin view
        # methods on the pane.
        # These handlers touch widgets, so observe with dispatch="ui" — the
        # executor sets the events from its worker thread and Traits marshals
        # the handler onto the GUI thread.
        q = self.executor.signals
        q.observe(self._on_protocol_wait_started, "protocol_wait_started", dispatch="ui")
        q.observe(self._on_protocol_wait_finished, "protocol_wait_finished", dispatch="ui")
        q.observe(self._on_protocol_started, "protocol_started", dispatch="ui")
        q.observe(self._on_error, "protocol_error", dispatch="ui")
        # Button state machine: running on start AND during the pre-protocol
        # wait (pause + stop stay live, everything else disabled).
        q.observe(self._set_running_button_state, "protocol_started", dispatch="ui")
        q.observe(self._set_running_button_state, "protocol_wait_started", dispatch="ui")
        q.observe(self._on_protocol_paused, "protocol_paused", dispatch="ui")
        q.observe(self._on_protocol_resumed, "protocol_resumed", dispatch="ui")
        q.observe(self._on_protocol_finished, "protocol_finished", dispatch="ui")
        q.observe(self._on_protocol_aborted, "protocol_aborted", dispatch="ui")

        # handle the navigation bar requests
        nb = pane.navigation_bar
        nb.btn_prev.clicked.connect(self.navigate_to_previous_step)
        nb.btn_next.clicked.connect(self.navigate_to_next_step)
        nb.btn_prev_phase.clicked.connect(self._on_prev_phase)
        nb.btn_next_phase.clicked.connect(self._on_next_phase)
        nb.btn_first.clicked.connect(self.navigate_to_first_step)
        nb.btn_last.clicked.connect(self.navigate_to_last_step)

        nb.btn_play.clicked.connect(self._on_play_clicked)
        nb.btn_resume.clicked.connect(self._toggle_pause)
        nb.btn_stop.clicked.connect(self.executor.stop)

        nb.set_phase_navigation_enabled(False, False)
        self._set_idle_button_state()

        # Legacy protocol_grid parity: the full app opens with one default
        # step when no protocol is loaded (no-op once a protocol is loaded).
        pane._seed_default_step_if_empty()

        return pane

    def destroy(self):
        """Tear down the background poll job before the pane goes away so its
        thread doesn't outlive the view (QTimer cleaned up with the widget;
        APScheduler needs an explicit shutdown)."""
        sched = self._protocol_poll_scheduler
        if sched is not None and sched.state != STATE_STOPPED:
            try:
                sched.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"poll scheduler shutdown failed: {e}")
        super().destroy()

    # --- step-cursor navigation -------------------------------------
    @attempt_func_execution_with_error_dialog
    def navigate_to_first_step(self):
        steps = self._pane._navigable_steps()
        if steps:
            logger.info(f"Nav: first step [{steps[0].dotted_path()}]")
            self._select_step(steps[0])

    @attempt_func_execution_with_error_dialog
    def navigate_to_last_step(self):
        steps = self._pane._navigable_steps()
        if steps:
            logger.info(f"Nav: last step [{steps[-1].dotted_path()}]")
            self._select_step(steps[-1])

    @attempt_func_execution_with_error_dialog
    def navigate_to_previous_step(self):
        steps = self._pane._navigable_steps()
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
        steps = self._pane._navigable_steps()
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
            self._pane.navigation_bar.set_phase_navigation_enabled(False, False)
            return
        prev_enabled = m.phase_index > 1
        next_enabled = 0 < m.phase_index < m.phase_total
        self._pane.navigation_bar.set_phase_navigation_enabled(prev_enabled, next_enabled)

    # --- step-cursor selection (drives the view + a paused seek) ------
    @attempt_func_execution_with_error_dialog
    def _select_step(self, row):
        # Move the tree selection (view), then — only while paused — re-seat
        # the model + DV preview to the chosen step. Nav buttons call this; the
        # user expects the DV to follow just as on a direct row click.
        self._pane.select_row(row)
        sc = self.status_controller
        if sc is not None and sc.model.paused:
            self._current_row = row
            path = tuple(row.path)
            sc.seek_to(path, 0)
            sc.preview_phase(path, 0, self._current_run_preview_mode)
            self._update_phase_nav_buttons()

    def _current_step_in(self, steps):
        # During a run the nav cursor follows the model's current step (the
        # paused/executing step, synced into _current_row by the highlight
        # observer) -- NOT the tree's stale selection, which is what made
        # navigation jump to the first step after a pause (issue #471). Only
        # when editing do we fall back to the tree selection.
        sc = self.status_controller
        if sc is not None and sc.model.running and self._current_row is not None:
            cur_path = tuple(self._current_row.path)
            for i, row in enumerate(steps):
                if tuple(row.path) == cur_path:
                    return i
            return None
        idx = self._pane.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self._pane.widget.index_to_path(idx)
        for i, row in enumerate(steps):
            if tuple(row.path) == path:
                return i
        return None

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

    # --- run control -------------------------------------------------
    def _publish_protocol_running(self, value: str) -> None:
        logger.info("Protocol Tree: Publishing Protocol Running")
        publish_message(topic=PROTOCOL_RUNNING, message=value)

    def _is_protocol_active(self):
        # One source of truth shared with non-view collaborators — kept in
        # lockstep with the button state machine, which sets it.
        return self.protocol_state_tracker.is_active

    def _on_play_clicked(self):
        if self._start_pending:
            # Realtime-mode settling window — the run is already on its way.
            return
        if self._is_protocol_active():
            self._toggle_pause()
            return
        self._start_protocol_run(
            preview_mode=self._pane.navigation_bar.is_preview_mode(),
        )

    def _start_protocol_run(self, preview_mode):
        repeats = self._pane.status_bar.edit_repeat_protocol.value()
        self._current_run_preview_mode = preview_mode
        start_path = self._pane.selected_step_path()
        logger.info(
            f"Protocol run starting: {repeats} rep(s), "
            f"preview={preview_mode}, start_step={start_path}"
        )
        # Realtime-mode prep + settle and logging start are once-per-run
        # executor lifecycle hooks (RealtimeModeHandler / LoggingHandler, wired
        # in create_contents); the executor owns the repeat loop, so the whole
        # run (all repetitions) is a single start() call. _start_pending guards
        # the play button until protocol_started fires (after the realtime
        # settle, which runs on the worker).
        self._start_pending = True
        self.executor.start(
            start_step_path=start_path,
            preview_mode=preview_mode,
            repeats=repeats,
        )

    def _toggle_pause(self):
        if self.executor.pause_event.is_set():
            self.executor.resume()
        else:
            self.executor.pause()

    # --- button state machine ----------------------------------------
    def _set_idle_button_state(self):
        self.protocol_state_tracker.is_active = False
        self._pane.enter_idle_buttons()

    def _set_running_button_state(self, event=None):
        self.protocol_state_tracker.is_active = True
        self._pane.enter_running_buttons()

    # --- executor lifecycle handlers ---------------------------------
    def _on_protocol_started(self, event=None):
        self._start_pending = False
        self._pane.protocol_running_changed.emit(True)
        self._publish_protocol_running("True")
        logger.info("Protocol started")

    def _on_error(self, event=None):
        msg = event.new
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

    def _on_protocol_wait_started(self, event=None):
        # The run is on its way; clear the start guard and show the loading
        # screen countdown over the tree. The executor dismisses it via
        # protocol_wait_finished (it owns the wait clock).
        total_ms = event.new
        self._start_pending = False
        self._wait_active = True
        self._pane.show_loading("Preparing protocol run…", total_ms)

    def _on_protocol_wait_finished(self, event=None):
        self._wait_active = False
        self._pane.stop_loading()

    def _on_protocol_paused(self, event=None):
        logger.info("Protocol paused")
        self._pane.enter_paused_buttons()
        if self._wait_active:
            # Freeze the loading-screen countdown in lockstep with the
            # executor's frozen pre-protocol wait.
            self._pane.freeze_loading()
        if self._current_row is not None:
            self._pane.split_to_phase_controls()
            self._update_phase_nav_buttons()

    def _on_protocol_resumed(self, event=None):
        logger.info("Protocol resumed")
        if self._wait_active:
            self._pane.resume_loading()
        self._pane.enter_resumed_buttons()

    def _on_protocol_finished(self, event=None):
        # The executor owns the repeat loop now, so protocol_finished fires
        # once at the end of the whole run; the per-rep label is updated by
        # the repetition-finished signal during the run.
        self._publish_protocol_running("False")
        logger.info("Protocol finished")
        self._on_protocol_terminated(RUN_OUTCOME_FINISHED)

    def _on_protocol_aborted(self, event=None):
        logger.info("Protocol aborted by user")
        self._publish_protocol_running("False")
        self._on_protocol_terminated(RUN_OUTCOME_ABORTED)

    def _on_protocol_terminated(self, outcome=RUN_OUTCOME_FINISHED):
        self._pane.protocol_running_changed.emit(False)
        logger.info("Protocol terminated --> free mode")
        # Defensive: the executor normally dismisses the loading screen via
        # protocol_wait_finished, but make sure it's never left up. Also clear
        # the start guard + nav cursor in case the run was stopped before
        # protocol_started fired (which is what normally clears them).
        self._wait_active = False
        self._start_pending = False
        self._pane.stop_loading()
        self._pane.clear_highlights()
        self._current_row = None
        self._set_idle_button_state()
        self._pane.navigation_bar.merge_phase_controls_to_play_button()
        # Clear hardware actuation: independent of the DV's free-mode publish
        # below, which can race with PROTOCOL_RUNNING and leave the last step's
        # channels energized after abort/error.
        try:
            publish_message(
                topic=ELECTRODES_STATE_CHANGE,
                message=json.dumps({"electrodes": [], "channels": []}),
            )
        except Exception as e:
            logger.warning(f"protocol-terminated electrode clear failed: {e}")
        # Realtime-mode restore is owned by RealtimeModeHandler's
        # on_post_protocol_end hook (runs once per run on the executor).
        # Push free-mode payload to DV: clear_highlights cleared the tree
        # selection but did so with _suppress_publish active, so the
        # controller's currentChanged slot was gated. Explicit publish here
        # puts the DV back in free mode after the run.
        if self.sync is not None:
            try:
                self.sync._publish_for_row(None)
            except Exception as e:
                logger.warning(f"protocol-terminated DV publish failed: {e}")
        # Logging stop + end-of-run dialogs run last, after immediate teardown
        # (hardware clear / idle UI) so electrodes de-energize before any modal
        # dialog blocks. For "error", the caller (_on_error) runs the flow after
        # showing the error dialog, so we skip it here.
        if outcome != RUN_OUTCOME_ERROR:
            self._run_completion_flow(outcome)

    def _run_completion_flow(self, outcome):
        """End-of-run UX: auto-save the protocol, prompt per outcome, and stop
        logging (which schedules the deferred flush). ``outcome`` is one of
        "finished", "aborted", "error". Every dialog is best-effort — failures
        are logged, never raised, so terminal cleanup is unaffected."""
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
                    and self.task.window.application is not None)

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
                    self._pane._on_new_experiment()
            except Exception as e:
                logger.warning(f"new-experiment confirm failed: {e}")

        try:
            self.logging_controller.stop_logging(generate_report=generate_report)
        except Exception as e:
            logger.warning(f"stop_logging failed: {e}")

    # --- &Protocol menu action delegates ----------------------------

    def new_protocol(self):
        self._pane.new_protocol()

    def load_protocol_dialog(self):
        self._pane.load_protocol_dialog()

    def save_protocol_dialog(self):
        self._pane.save_protocol_dialog()

    def save_as_protocol_dialog(self):
        self._pane.save_as_protocol_dialog()

    def setup_new_experiment(self):
        # Reuses the same handler the experiment-bar button drives so
        # the menu and the toolbutton stay consistent.
        self._pane._on_new_experiment()


    ### Trait observers ###########################
    @observe("preferences.protocol_tree_ack_times.items", post_init=True)
    def _sync_handler_ack_times(self, event=None):
        """Push the Protocol Settings ack-wait grid into the column
        handlers — the only bridge from the preference to the running
        columns (handlers read their own ``ack_time_s`` at wait time).
        Idempotent: equal values are skipped, so re-running on every
        grid event is free; the event payload is never inspected (the
        ``.items`` pattern fires for whole-dict reassignment — what grid
        edits and node syncs do — as well as in-place mutation). A
        compound's field cells share one handler, so its push lands
        exactly once.
        post_init: an immediate observer would materialize
        _preferences_default mid-construction (to compute event.old)
        before ``task`` exists; traits_init covers the initial sync."""
        ack_times = self.preferences.protocol_tree_ack_times
        for col in self.columns:
            if col.id not in ack_times:
                continue
            seconds = ack_times[col.id]
            ack_time_s = (float("inf") if seconds == ACK_WAIT_FOREVER
                          else float(seconds))
            if col.handler.ack_time_s != ack_time_s:
                logger.info(f"Protocol Tree: ack wait changed for {col.id} column: "
                            f"{col.handler.ack_time_s}s --> {ack_time_s}s")
                col.handler.ack_time_s = ack_time_s

    @observe("manager.rows_changed")
    def _on_manager_rows_changed(self, event):
        """Structural mutation — re-check the baseline path set."""
        self.protocol_state_tracker.on_structure_changed(self.manager)

    @observe("manager.cell_changed", dispatch="ui")
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

        self._clamp_trail_overlay_for_row(path, col_id)
        self._reconcile_repeat_duration_for_row(path, col_id)

    @observe("task.window.application.experiment_changed", dispatch="ui")
    def _on_experiment_changed(self, event):
        # control is None until create_contents has run (the application
        # can switch experiments before this pane is mounted).
        self._pane._on_experiment_changed()

    @observe("task.window.closing", dispatch="ui")
    def _on_window_closing(self, event):
        """Veto the window close (title-bar X or File->Exit) when the
        protocol is dirty and the user elects to keep it open.

        The window's ``closing`` event is the only vetoable point:
        TasksApplication.exit() fires it per window and aborts when
        vetoed, and the title-bar X routes through the same event.
        (``application_exiting`` is NOT vetoable — it fires from
        _prepare_exit AFTER every closing veto has already passed, so
        vetoing there let the app quit anyway.) ``event.new`` carries
        the Vetoable.
        """
        if not self.protocol_state_tracker.is_modified:
            return
        user_choice = confirm(
            None,  # the dock pane is not a QWidget — no dialog parent
            "Current protocol has unsaved changes.\n"
            "Exit without saving?",
            title="Unsaved Protocol Changes",
            cancel=False,
        )
        # Veto only an explicit "No" — dismissing the dialog via the
        # window X maps to CANCEL and lets the exit proceed, matching
        # the original pane behaviour.
        if user_choice == NO:
            event.new.veto = True

    # Wire the pane to the status model — the single source of truth for
    # the current step (issue #471). The tree's active-step highlight and the
    # nav cursor (_current_row) follow ``model.current_step_path``; tree
    # editability follows ``model.running``. Called by the composition root
    # after the controller is built.
    @observe("status_controller:model:current_step_path", dispatch="ui")
    def _on_current_step_path_changed(self, event):
        path = event.new
        row = None
        if path is not None:
            try:
                row = self._pane.manager.get_row(tuple(path))
            except (IndexError, KeyError):
                row = None
        self._current_row = row
        self._pane.widget.highlight_active_row(row)

    ## Observe status bar model changes and modify view accordingly
    @observe("status_controller:model:[step_index, step_total, phase_index, phase_total]", dispatch="ui", post_init=True)
    def _on_counts_changed(self, event=None):
        model = self.status_controller.model
        self._pane.status_bar._refresh_counts(current=model.step_index, total=model.step_total)

    @observe("status_controller:model:[repeats_completed, repeats_total]", dispatch="ui", post_init=True)
    def _on_repeats_changed(self, event=None):
        self._pane.status_bar._refresh_repeats(self.status_controller.model.repeats_completed)

    @observe("status_controller:model:[recent_step_name, next_step_name, rep_chain_label]", dispatch="ui", post_init=True)
    def _on_names_changed(self, event=None):
        model = self.status_controller.model
        self._pane.status_bar._refresh_names(model.recent_step_name, model.next_step_name, model.rep_chain_label)

    @observe("status_controller:model:running", dispatch="ui", post_init=True)
    def _on_protocol_running_changed(self, event):
        # Lock the tree while a run is in progress (issue #471) and drive the
        # live time-readout poll job off the same running flag.
        self._pane.widget.set_editable(not bool(event.new))
        sched = self._protocol_poll_scheduler
        if sched is None:
            return
        if event.new:
            if sched.state == STATE_PAUSED:
                sched.resume()
            elif sched.state == STATE_STOPPED:
                sched.start()
        else:
            self._update_protocol_time()  # final freeze-frame (GUI thread)
            if sched.state == STATE_RUNNING:
                sched.pause()


    ######### Helpers ###################
    def _clamp_trail_overlay_for_row(self, path, col_id):
        """Mirror the DV sidebar's dynamic bound (trail_overlay can never
        reach trail_length): shrinking Trail Len drags an out-of-range
        Trail Overlay down with it. Runs before the repeat-duration
        reconciliation so the recalc sees the clamped overlay."""
        if col_id != "trail_length":
            return
        try:
            row = self.manager.get_row(tuple(path))
        except (IndexError, AttributeError):
            return
        max_overlay = max(0, int(getattr(row, "trail_length", 1) or 1) - 1)
        if int(getattr(row, "trail_overlay", 0) or 0) > max_overlay:
            row.trail_overlay = max_overlay
            self.manager.cell_changed = {
                "path": tuple(path), "col_id": "trail_overlay",
            }

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
        if self.protocol_state_tracker.is_active:
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
            estimated = round(estimated, REPEAT_DURATION_DECIMALS)
            if (abs(float(getattr(row, "repeat_duration", 0.0)) - estimated)
                    >= REPEAT_DURATION_TOLERANCE_S):
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

    def _emit_time_update_tick(self):
        # Runs on the scheduler's background thread. Setting the Traits event
        # hands the GUI-thread refresh off to _update_protocol_time via its
        # dispatch="ui" observer — no widget access happens here.
        self.protocol_time_update_event = time.monotonic()

    @observe("protocol_time_update_event", dispatch="ui")
    def _update_protocol_time(self, event=None):
        model = self.status_controller.model
        status_view = self._pane.status_bar

        # event.new is the tick's monotonic timestamp; direct calls (initial
        # paint, freeze-frame on stop) pass no event and read the clock here.`
        now = event.new if event is not None else time.monotonic()

        status_view.update_total_time(
            elapsed=model.protocol_clock.elapsed(now),
            active=model.protocol_clock.active(now),
        )

        status_view.update_step_time(
            elapsed=model.step_clock.elapsed(now),
            active=model.step_clock.active(now),
        )

        status_view.update_phase_status(
            elapsed=model.phase_clock.elapsed(now),
            active=model.phase_clock.active(now),
            target=model.phase_target_s,
            current_phase_idx=model.phase_index,
            total_phases=model.phase_total
        )
