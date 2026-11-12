# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Drives protocol AutoSave (#966): change events in, debounced writes out.

Owned by ``ProtocolTreePane`` so the demo windows and the full-app dock
pane get the same behaviour. Every protocol change restarts a single-shot
timer; when it fires, ``ProtocolAutosaveModel`` decides whether the write
is due and the injected ``write_protocol`` performs it through the pane's
ordinary save path. The toggle state is persisted in the protocol
preferences.
"""

# Standard library imports.
import time

# Enthought library imports.
from pyface.qt.QtCore import QTimer
from traits.api import Callable, HasTraits, Instance, observe

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import warning
from pluggable_protocol_tree.models.protocol_autosave import ProtocolAutosaveModel
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.preferences import ProtocolPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class ProtocolAutosaveController(HasTraits):
    #: Decision rules and toggle state; the toolbar toggle binds to it.
    model = Instance(ProtocolAutosaveModel)

    #: The protocol whose cell and structure changes trigger a write.
    manager = Instance(RowManager)

    #: Persists the toggle state across sessions.
    preferences = Instance(ProtocolPreferences)

    #: Writes the protocol to its current file; raises on failure.
    write_protocol = Callable()

    #: Monotonic clock source; overridable in tests.
    clock = Callable(time.monotonic)

    #: Single-shot debounce timer, restarted on every change.
    _timer = Instance(QTimer)

    def traits_init(self):
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer_timeout)

        self.model.enabled = self.preferences.protocol_autosave_enabled

    def flush(self):
        """Write pending changes now instead of waiting for the debounce."""
        self._timer.stop()

        if self.model.claim_flush_save():
            self._save()

    # --- change sources ----------------------------------------------

    @observe("manager:cell_changed, manager:rows_changed", dispatch="ui")
    def _on_protocol_changed(self, event):
        self.model.note_change(self.clock())
        self._arm_timer()

    @observe("model:enabled", dispatch="ui")
    def _on_enabled_changed(self, event):
        self.preferences.protocol_autosave_enabled = event.new
        logger.info(f"Protocol AutoSave turned {'on' if event.new else 'off'}")

        # Turning AutoSave on over unsaved edits saves them like a fresh edit.
        self.model.note_change(self.clock())
        self._arm_timer()

    @observe("model:tracker:is_active", dispatch="ui")
    def _on_run_state_changed(self, event):
        if not event.new:
            self.model.note_run_ended(self.clock())
            self._arm_timer()

    # --- timer + write -----------------------------------------------

    def _arm_timer(self):
        wait_s = self.model.seconds_until_due(self.clock())

        if wait_s is None:
            self._timer.stop()
            return

        self._timer.start(int(wait_s * 1000))

    def _on_timer_timeout(self):
        if self.model.claim_due_save(self.clock()):
            self._save()

    def _save(self):
        path = self.model.tracker.loaded_protocol_path

        try:
            self.write_protocol()

        except (OSError, TypeError, ValueError) as e:
            # The tracker is left dirty, so the next change retries the write
            # and the unsaved-changes prompts still guard the edits.
            logger.error(f"Protocol AutoSave to {path} failed: {e}")

            if self.model.record_save_failed(str(e)):
                warning(
                    None,
                    f"AutoSave could not write the protocol to\n{path}\n\n{e}\n\n"
                    f"Your changes are kept but not saved. AutoSave retries on "
                    f"the next change; use Save As to pick another location.",
                    title="AutoSave Failed",
                    cancel=False,
                )

            return

        logger.debug(f"Protocol AutoSaved to {path}")
