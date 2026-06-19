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
from pathlib import Path

from pyface.qt.QtCore import (
    Qt, QEventLoop, QModelIndex, QThread, QTimer, Signal, QUrl,
)
from pyface.qt.QtGui import QFont
from pyface.qt.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QProgressDialog, QToolButton, QVBoxLayout, QWidget,
)

from microdrop_application.dialogs.pyface_wrapper import (
    NO, YES, confirm, error as error_dialog, success,
)
from microdrop_style.button_styles import ICON_FONT_FAMILY

from microdrop_application.helpers import get_microdrop_redis_globals_manager
from microdrop_utils.decorators import attempt_func_execution_with_error_dialog
from microdrop_utils.pyside_helpers import LoadingOverlay

from device_viewer.consts import DEVICE_SVG_PATH_KEY
from pluggable_protocol_tree.consts import (
    ELECTRODES_STATE_APPLIED, PROTOCOL_FILE_DIALOG_FILTER)
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.services.persistence import (
    _RESERVED_ROW_METADATA_FIELDS,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)
from pluggable_protocol_tree.services.protocol_validator import validate_protocol
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.experiment_label import ExperimentLabel
from pluggable_protocol_tree.views.protocol_validator_presenter import (
    confirm_report,
)
from pluggable_protocol_tree.views.navigation_bar import (
    NavigationBar, StatusBar, make_separator,
)
from pluggable_protocol_tree.views.timeline_bar import TimelineBar
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
        self.timeline_bar = TimelineBar()
        self.timeline_controls = self._build_timeline_controls()
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

        # The flush_scheduler shows a "Generating Run Report..." progress
        # dialog around the report build (legacy parity, mirrors
        # protocol_grid's with_loading_screen("Generating Run Report...")).
        # The flush runs in a QThread to keep the GUI responsive while
        # plotly renders charts; the completion_callback is routed through a
        # Qt signal so the success dialog ends up back on the GUI thread.
        # The logging controller + executor lifecycle handlers that drive
        # these signals are owned by the composition root (the dock pane),
        # which constructs the ProtocolLoggingController pointing at the
        # _logging_complete / _report_failed / _schedule_flush_with_progress /
        # _logs_settling_time_s members below — those stay here because they
        # are the GUI-thread bridge + dialog presentation (pure view).
        self._logging_complete.connect(
            self._on_logging_complete, Qt.QueuedConnection)
        self._report_failed.connect(
            self._on_report_failed, Qt.QueuedConnection)

        # The nav cursor (_current_row), preview-mode flag, and run guards
        # now live on the composition root (the dock pane), which owns the
        # executor and all run control. The pane is a pure view.

        # The active-step highlight + the nav cursor follow the status model
        # (current_step_path / running) via observers wired by the dock pane;
        # button state + executor signals are wired there too.

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

    def _build_timeline_controls(self):
        """Step-rep and phase-rep selectors (side by side) + a 'show full
        timeline' toggle, shown beneath the timeline when the current step has
        repetitions. The dock-pane controller populates, shows/hides, wires."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        self.timeline_step_rep_label = QLabel("Step Rep")
        self.timeline_step_rep_combo = QComboBox()
        self.timeline_step_rep_combo.setToolTip("Jump to a step repetition")
        self.timeline_phase_rep_label = QLabel("Phase Rep")
        self.timeline_phase_rep_combo = QComboBox()
        self.timeline_phase_rep_combo.setToolTip("Jump to a phase repetition")
        self.timeline_show_full_check = QCheckBox("Show full timeline")
        self.timeline_show_full_check.setToolTip(
            "Show every phase/step across all repetitions instead of a "
            "collapsed base loop")
        layout.addWidget(self.timeline_step_rep_label)
        layout.addWidget(self.timeline_step_rep_combo)
        layout.addWidget(self.timeline_phase_rep_label)
        layout.addWidget(self.timeline_phase_rep_combo)
        layout.addWidget(self.timeline_show_full_check)
        layout.addStretch()
        row.setVisible(False)
        return row

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
        layout.addWidget(self.timeline_bar)
        layout.addWidget(self.timeline_controls)
        layout.addWidget(self.status_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self.widget)
        if self.quick_action_bar is not None:
            layout.addWidget(self.quick_action_bar)

    # --- thin view ops (driven by the dock-pane controller) ----------
    # The dock pane owns the executor, the status controller, and all run
    # control (issue #471). It drives these pure-view methods; the pane never
    # touches the executor or status controller itself.

    def select_row(self, row):
        """Move the tree's current selection to ``row`` (pure view)."""
        self.widget.set_current_row(row)

    def selected_step_path(self):
        """Path tuple of the tree's currently-selected execution step, or
        None when the selection isn't a step."""
        idx = self.widget.tree.currentIndex()
        if not idx.isValid():
            return None
        path = self.widget.index_to_path(idx)
        for row in self.manager.iter_execution_steps():
            if tuple(row.path) == path:
                return path
        return None

    # --- button state (view) -----------------------------------------

    def enter_idle_buttons(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_play_state()
        nb.btn_stop.setEnabled(False)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)
        nb.action_preview.setEnabled(True)

    def enter_running_buttons(self):
        nb = self.navigation_bar
        nb.btn_play.setEnabled(True)
        nb.show_pause_state()
        nb.btn_stop.setEnabled(True)
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)
        nb.action_preview.setEnabled(False)

    def enter_paused_buttons(self):
        nb = self.navigation_bar
        nb.show_resume_state()
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(True)

    def enter_resumed_buttons(self):
        nb = self.navigation_bar
        nb.show_pause_state()
        for btn in (nb.btn_first, nb.btn_prev, nb.btn_next, nb.btn_last):
            btn.setEnabled(False)
        nb.merge_phase_controls_to_play_button()

    def split_to_phase_controls(self):
        self.navigation_bar.split_play_button_to_phase_controls()

    # --- loading overlay (view) --------------------------------------

    def show_loading(self, msg, ms):
        self.loading_overlay.show_loading(msg, duration_ms=ms, auto_stop=False)

    def stop_loading(self):
        self.loading_overlay.stop_loading()

    def freeze_loading(self):
        self.loading_overlay.pause()

    def resume_loading(self):
        self.loading_overlay.resume()

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
    def clear_highlights(self):
        """Reset the tree's selection + active-row highlight to the idle
        visual state. Status-bar fields are owned by ProtocolStatusModel and
        reset on the next run (on_protocol_start). The nav cursor
        (_current_row) lives on the dock pane, which resets it alongside."""
        with self._suppress_sync_publish():
            self.widget.highlight_active_row(None)
            self.widget.tree.clearSelection()
            self.widget.tree.setCurrentIndex(QModelIndex())

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
