# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Evaluates the checks into the report, synchronously on demand (the Run
gate) and debounced after ``invalidate()``, and owns the mutes."""

# Enthought library imports.
from pyface.timer.api import do_after
from traits.api import Any, Bool, Callable, HasTraits, Instance, List, observe

# Microdrop package imports.
from pluggable_protocol_tree.services.preferences import ProtocolPreferences

# Local imports.
from .checks import evaluate_checks, protocol_stats
from .consts import DEBOUNCE_MS, MUTE_ALWAYS, run_mute_key
from .models import PreflightCheck, PreflightReport

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PreflightController(HasTraits):
    """Owns the report; ``evaluate(context)`` fills it with final results.

    Lives on the GUI thread: ``invalidate`` arms a Qt timer, so every path
    into it must already run there.
    """

    #: Builds a fresh ``PreflightContext`` of the current run scope; called
    #: once per debounced evaluation, never per change.
    context_provider = Callable

    #: The protocol's column handlers; each may contribute checks through
    #: ``preflight_checks(context)``.
    column_handlers = List(Any)

    #: The protocol preferences: ``preflight_always_allowed`` is the
    #: persisted ``List(Str)`` of check ids allowed for good.
    preferences = Instance(ProtocolPreferences)

    #: The report the pill and panel show.
    report = Instance(PreflightReport, ())

    #: True from an invalidation until the evaluation it schedules ends:
    #: the window in which the shown report may be stale.
    checking = Bool(False)

    #: The pending debounced evaluation, a pyface single-shot timer.
    _debounce = Any

    @observe("preferences.preflight_always_allowed.items")
    def _copy_always_allowed(self, event):
        if self.preferences is None:
            self.report.always_mutes = []

        else:
            self.report.always_mutes = list(self.preferences.preflight_always_allowed)

    # ------------------------------------------------------------------
    # Evaluating
    # ------------------------------------------------------------------

    def invalidate(self):
        """Mark the report stale and re-evaluate once changes settle."""
        self.cancel_pending()
        self._debounce = do_after(DEBOUNCE_MS, self._evaluate_current)
        self.checking = True

    def evaluate(self, context):
        """Run every check over ``context`` now and return the report, its
        statuses final. Supersedes any pending debounced evaluation; on a
        failure, the report keeps its last results."""
        self.cancel_pending()

        try:
            rows = evaluate_checks(context, self.column_handlers)
            stats = protocol_stats(context)
            checks = [
                PreflightCheck(
                    id=row.id,
                    category=row.category,
                    label=row.label,
                    mutable_always=row.mutable_always,
                    status=row.result.status,
                    detail=row.result.detail,
                    problem=row.result.problem,
                    tooltip=row.result.tooltip,
                )
                for row in rows
            ]

        finally:
            self.checking = False

        report = self.report
        report.step_count, report.duration_s, report.electrode_count = stats
        report.scope_line = _scope_line(context, report.step_count)
        report.checks = checks

        logger.info(f"Pre-flight ({report.scope_line}): {report.overall}")

        return report

    def cancel_pending(self):
        """Drop the pending debounced evaluation, if any."""
        if self._debounce is not None:
            self._debounce.stop()
            self._debounce = None

    def _evaluate_current(self):
        self._debounce = None

        try:
            if self.context_provider is not None:
                self.evaluate(self.context_provider())

        except Exception:
            logger.exception("Pre-flight evaluation failed; the last report stays")

        finally:
            # The ring never outlives a failed evaluation.
            self.checking = False

    # ------------------------------------------------------------------
    # Mutes
    # ------------------------------------------------------------------

    def mute(self, check, scope):
        """Mute warning ``check`` for this run, or allow it for good
        (``MUTE_ALWAYS``, only where the check allows it; else this run)."""
        if check.status != "warn":
            return

        if (
            scope == MUTE_ALWAYS
            and check.mutable_always
            and self.preferences is not None
        ):
            allowed = self.preferences.preflight_always_allowed

            # The preferences helper persists an in-place change too.
            if check.id not in allowed:
                allowed.append(check.id)

            return

        key = run_mute_key(check.id, check.detail)

        if key not in self.report.run_mutes:
            self.report.run_mutes.append(key)

    def unmute(self, check):
        """Bring a muted warning back, whichever way it was muted."""
        key = run_mute_key(check.id, check.detail)

        if key in self.report.run_mutes:
            self.report.run_mutes.remove(key)

        if self.preferences is None:
            return

        allowed = self.preferences.preflight_always_allowed

        if check.id in allowed:
            allowed.remove(check.id)

    def clear_run_mutes(self):
        """Drop the "this run" mutes (once a run starts, or on reset)."""
        self.report.run_mutes = []


def _scope_line(context, step_count):
    """e.g. "Run · 8 steps" or "Preview · 2 steps"."""
    kind = "Preview" if context.preview_mode else "Run"

    return f"{kind} · {step_count} step{'s' if step_count != 1 else ''}"
