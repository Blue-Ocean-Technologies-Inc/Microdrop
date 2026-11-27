# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pre-flight check inside the protocol dock pane: the controller, the
pill and its card, the run gate, and what makes the report stale."""

# Enthought library imports.
from envisage.ui.tasks.api import TaskWindow
from traits.api import (
    Bool,
    Callable,
    HasTraits,
    Instance,
    List,
    Property,
    Tuple,
    Union,
    observe,
)

# Microdrop package imports.
from microdrop_status_bar.consts import LEFT_PRIORITY_READINESS, STATUS_BAR_SIDE_LEFT
from pluggable_protocol_tree.models.protocol_status import ProtocolStatusModel
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController,
)
from pluggable_protocol_tree.services.preferences import ProtocolPreferences

# Local imports.
from .context import build_preflight_context
from .controller import PreflightController
from .models import RunInfo
from .settings import open_protocol_settings
from .views.panel import PreflightPanel
from .views.pill import PillController, ReadinessPill

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PreflightHost(HasTraits):
    """Owns the pre-flight controller, the run shown while a protocol runs,
    the pill (contributed to the status bar's left) and its card.

    Every change that can alter the verdict invalidates the report, which
    is evaluated once the changes settle; ``gate`` evaluates a run's scope
    on the spot instead. All of it runs on the GUI thread: the sync
    controller's traits are set on a Dramatiq worker, so its observers
    dispatch to the UI.
    """

    #: The protocol, the loaded device and the protocol preferences.
    manager = Instance(RowManager)
    sync = Instance(DeviceViewerSyncController)
    preferences = Instance(ProtocolPreferences)

    #: The executor's status; no re-checks while it runs.
    status_model = Instance(ProtocolStatusModel)

    #: The main window: its control is the card's parent, its application
    #: serves the Settings dialog.
    window = Instance(TaskWindow)

    #: Starts a run: ``start_run(preview_mode, run_paths, anyway)``, gated
    #: again here. The card's Run calls it on ``last_scope``.
    start_run = Callable

    #: The scope the pill reflects: whether the next run is a preview, and
    #: the run last asked for (``run_paths`` None: the whole protocol;
    #: ``start_path`` None: from its first step) until the protocol
    #: changes or a run ends, which reset it to what Play would run.
    preview_mode = Bool(False)
    run_paths = Union(None, List(Tuple))
    start_path = Union(None, Tuple)

    #: ``(preview_mode, run_paths)``: the card's Run starts this scope.
    last_scope = Property(observe="preview_mode, run_paths")

    #: Evaluates the checks and owns the report and the mutes.
    controller = Instance(PreflightController)

    #: The run in progress, shown in place of the checks.
    run_info = Instance(RunInfo, ())

    #: The pill in the status bar and its card; both None once withdrawn.
    pill = Instance(ReadinessPill)
    panel = Instance(PreflightPanel)

    #: Keeps the pill's face in step with the report and the run.
    _pill_controller = Instance(PillController)

    def traits_init(self):
        self.controller = PreflightController(
            context_provider=self.current_context,
            preferences=self.preferences,
            column_handlers=[column.handler for column in self.manager.columns],
        )

        self.pill = ReadinessPill()
        self.pill.setVisible(self.preferences.preflight_enabled)
        self.pill.clicked.connect(self.toggle_panel)
        self._pill_controller = PillController(
            report=self.controller.report,
            run_info=self.run_info,
            pill=self.pill,
            controller=self.controller,
        )

        self.panel = PreflightPanel(
            self.controller, self.run_info, parent=self.window.control
        )
        self.panel.run_requested.connect(
            lambda anyway: self.start_run(*self.last_scope, anyway)
        )
        self.panel.settings_requested.connect(
            lambda: open_protocol_settings(self.window.application, self.window.control)
        )

        self.invalidate()

    def _get_last_scope(self):
        return self.preview_mode, self.run_paths

    # ------------------------------------------------------------------
    # Checking
    # ------------------------------------------------------------------

    def current_context(self):
        """A fresh ``PreflightContext`` of the scope the pill reflects."""
        return build_preflight_context(
            self.manager,
            self.sync,
            self.preferences,
            self.run_paths,
            self.preview_mode,
            self.start_path,
        )

    def invalidate(self):
        """Re-check once changes settle; never while a protocol runs (its
        end re-checks), nor once withdrawn."""
        if (
            self.pill is not None
            and self.preferences.preflight_enabled
            and not self.status_model.running
        ):
            self.controller.invalidate()

    def gate(self, preview_mode, run_paths=None, start_path=None, anyway=False):
        """Whether a run over ``run_paths`` from ``start_path`` may start:
        evaluated now over a fresh snapshot, never the idle report. All
        clear flashes the pill; warnings pass only ``anyway``; otherwise the
        card opens on the verdict and the run does not start. Fails open: a
        failing check never stops an experiment."""
        try:
            if not self.preferences.preflight_enabled or self.pill is None:
                return True

            self.trait_set(
                preview_mode=preview_mode,
                run_paths=run_paths,
                start_path=None if start_path is None else tuple(start_path),
            )
            report = self.controller.evaluate(self.current_context())

            if report.overall == "pass":
                self.pill.flash_all_clear()

                return True

            if anyway and report.overall == "warn":
                return True

            self.panel.show_above(self.pill)

            return False

        except Exception:
            logger.exception("Pre-flight gate failed; the run starts unchecked")

            return True

    def on_preview_toggled(self, checked):
        """The navigation bar's Preview Mode: the next run's kind."""
        self.preview_mode = checked
        self.invalidate()

    @observe("manager:[rows_changed, cell_changed]", dispatch="ui")
    @observe(
        "sync:[connected, electrode_ids_channels_map, hardware_state_changed]",
        dispatch="ui",
    )
    @observe(
        "preferences:[suppress_unused_column_hooks_information, preflight_enabled]",
        dispatch="ui",
    )
    @observe("preferences:protocol_tree_ack_times.items", dispatch="ui")
    @observe("controller:column_handlers", dispatch="ui")
    def _invalidate_on_change(self, event):
        self.invalidate()

    @observe("manager:rows_changed", dispatch="ui")
    def _reset_scope_on_edit(self, event):
        self.reset_scope()

    @observe("manager:columns", dispatch="ui")
    def _follow_columns(self, event):
        # Columns change on a hot-loaded plugin or a protocol load.
        self.controller.column_handlers = [
            column.handler for column in self.manager.columns
        ]

    @observe("preferences:preflight_enabled", dispatch="ui")
    def _show_pill(self, event):
        if self.pill is not None:
            self.pill.setVisible(event.new)

    @observe("status_model:[running, paused, step_index, step_total]", dispatch="ui")
    def _follow_run(self, event):
        model = self.status_model
        self.run_info.trait_set(
            active=model.running,
            paused=model.paused,
            step=model.step_index,
            step_total=model.step_total,
        )

        if event.name != "running":
            return

        if model.running:
            # "This run" mutes last until the run they let through starts.
            self.controller.clear_run_mutes()

        else:
            # Nothing was re-checked while the protocol ran.
            self.reset_scope()
            self.invalidate()

    def reset_scope(self):
        """Judge what Play would run: the whole protocol from its start."""
        self.trait_set(run_paths=None, start_path=None)

    # ------------------------------------------------------------------
    # The pill
    # ------------------------------------------------------------------

    def toggle_panel(self):
        """The pill's click: close the open card, else open it."""
        if self.panel.isVisible():
            self.panel.close()

        else:
            self.panel.show_above(self.pill)

    def contribute(self, status_bar_icons):
        """Put the pill first on the status bar's left
        (``status_bar_icons``: the status-bar plugin's extension point)."""
        self.pill.status_bar_side = STATUS_BAR_SIDE_LEFT
        self.pill.status_bar_left_priority = LEFT_PRIORITY_READINESS
        status_bar_icons.append(self.pill)

    def withdraw(self, status_bar_icons):
        """Stop checking, take the pill out of the status bar, which deletes
        it, once nothing drives it any more, and delete the card once it
        stops following the report and the window. The host drops both."""
        self.controller.cancel_pending()
        pill, panel = self.pill, self.panel

        if pill is None:
            return

        self._pill_controller.trait_set(
            pill=None, report=None, run_info=None, controller=None
        )
        self.trait_set(pill=None, panel=None, _pill_controller=None)

        pill.stop_ring()
        panel.detach()
        panel.deleteLater()

        if pill in status_bar_icons:
            status_bar_icons.remove(pill)

        else:
            # Never placed on a bar, so nothing else deletes it.
            pill.deleteLater()
