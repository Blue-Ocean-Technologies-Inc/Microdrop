# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Decision rules for protocol AutoSave (#966).

Qt-free and clock-free: every time-dependent method takes ``now`` (a
monotonic timestamp) so the debounce is unit-testable against a fake clock.
The controller owns the timer and the write; this model only decides
*whether* a write is due and what the toggle should tell the user.

A write is allowed only when AutoSave is on, the protocol has a file, no run
is in progress, and the tracker reports unsaved changes — so a clean
protocol is never rewritten and a never-saved one is never written.
"""

# Enthought library imports.
from traits.api import Bool, Float, HasTraits, Instance, Property, Str, Union, observe

# Microdrop package imports.
from pluggable_protocol_tree.consts import PROTOCOL_AUTOSAVE_DEBOUNCE_S
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)


class ProtocolAutosaveModel(HasTraits):
    #: The toggle state, mirrored to the protocol preferences by the controller.
    enabled = Bool(False)

    #: File path, dirty flag and run state of the open protocol.
    tracker = Instance(PluggableProtocolStateTracker, ())

    #: Quiet period after the last change before the write is due.
    debounce_s = Float(PROTOCOL_AUTOSAVE_DEBOUNCE_S)

    #: Monotonic time the pending write is due at; None when nothing is pending.
    due_at = Union(None, Float)

    #: Message of the last failed write; empty once the protocol is clean again.
    last_error = Str()

    #: True once the user has been told about the current run of failures.
    failure_reported = Bool(False)

    #: True when there is a file to write to (the protocol was saved or loaded).
    has_target = Property(Bool, observe="tracker.loaded_protocol_path")

    #: Short state shown on the toolbar toggle.
    label_text = Property(
        Str,
        observe="enabled, last_error, tracker.loaded_protocol_path",
    )

    #: Full state shown as the toggle's tooltip.
    status_text = Property(
        Str,
        observe="enabled, last_error, tracker.[loaded_protocol_path, is_active]",
    )

    # --- scheduling ---------------------------------------------------

    def note_change(self, now):
        """Restart the debounce after a protocol change."""
        if self.enabled:
            self.due_at = now + self.debounce_s

    def note_run_ended(self, now):
        """Make changes held back during a run due immediately."""
        if self.enabled and self.tracker.is_modified:
            self.due_at = now

    def seconds_until_due(self, now):
        """Return the wait before the pending write is due, or None."""
        if self.due_at is None:
            return None

        return max(0.0, self.due_at - now)

    def claim_due_save(self, now):
        """Return whether the debounced write should happen now.

        A write held back by a run stays pending for ``note_run_ended``;
        anything else that cannot be written is dropped.
        """

        if self.due_at is None or now < self.due_at:
            return False

        if self.enabled and self.tracker.is_active:
            return False

        self.due_at = None

        return self._can_write()

    def claim_flush_save(self):
        """Return whether pending changes should be written right away."""
        self.due_at = None

        return self._can_write()

    def _can_write(self):
        return (
            self.enabled
            and self.has_target
            and not self.tracker.is_active
            and self.tracker.is_modified
        )

    # --- failures ----------------------------------------------------

    def record_save_failed(self, message):
        """Record a failed write; return whether the user should be told."""
        should_tell = not self.failure_reported

        self.last_error = message
        self.failure_reported = True

        return should_tell

    @observe("tracker:is_modified")
    def _clear_failure_when_clean(self, event):
        # A clean protocol matches its file again (any save, load or new),
        # so the next failure is news to the user.
        if not event.new:
            self.last_error = ""
            self.failure_reported = False

    # --- display -----------------------------------------------------

    def _get_has_target(self):
        return bool(self.tracker.loaded_protocol_path)

    def _get_label_text(self):
        if not self.enabled:
            return "AutoSave: Off"

        if not self.has_target:
            return "AutoSave: On (no file)"

        if self.last_error:
            return "AutoSave: Failed"

        return "AutoSave: On"

    def _get_status_text(self):
        if not self.enabled:
            return (
                "AutoSave is off. Turn it on to write protocol changes to the "
                "protocol file automatically."
            )

        if not self.has_target:
            return "AutoSave on – save the protocol once to start"

        if self.last_error:
            return (
                f"AutoSave on – the last save failed: {self.last_error}. "
                f"It retries on the next change."
            )

        if self.tracker.is_active:
            return (
                "AutoSave on – paused while the protocol runs; pending changes "
                "are saved when it ends"
            )

        return (
            f"AutoSave on – changes are saved to "
            f"{self.tracker.loaded_protocol_path} automatically"
        )
