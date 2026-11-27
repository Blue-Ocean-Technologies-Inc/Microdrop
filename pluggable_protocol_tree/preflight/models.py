# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free models of the pre-flight check: the snapshot the checks read, a
check, the report, and the run shown instead while a protocol runs."""

# Enthought library imports.
from traits.api import (
    Bool,
    Dict,
    Enum,
    Float,
    HasTraits,
    Instance,
    Int,
    List,
    Property,
    Str,
    Tuple,
)

# Local imports.
from .consts import CATEGORIES, MUTE_ALWAYS, MUTE_RUN, STATUSES, run_mute_key


class PreflightContext(HasTraits):
    """A snapshot of the protocol facts the built-in checks read, for one
    run scope. Hardware is not in it: each column reads its own.

    Fails closed: every default is the unhealthy reading (no steps in the
    run, no device, no folder, no disk), so a field the host forgot to fill
    shows up as a problem, never as a pass.
    """

    #: Every protocol step, in order: dicts of a value per column id, then
    #: path, electrodes, routes (a list of electrode-id lists), duration_s,
    #: repeats (the step's frame count in this run) and set_columns (ids of
    #: the columns it sets away from their defaults).
    steps = List(Dict)

    #: The paths of the steps this run covers; empty runs nothing.
    run_paths = List(Tuple)

    #: Whether the run is a preview, which drives no hardware.
    preview_mode = Bool(False)

    #: The hooked columns: id -> display name.
    columns = Dict(Str, Str)

    #: Ids of the hooked columns no step of this run uses
    #: (``RowManager.unused_column_ids(run_paths)``).
    unused_column_ids = List(Str)

    #: The ack wait (s) of each wait-capable column a step of this run
    #: uses, by id (0: no wait, ``ACK_WAIT_FOREVER``: no limit), and the
    #: columns' display names.
    ack_times = Dict(Str, Float)
    ack_column_names = Dict(Str, Str)

    #: Ids of the electrodes on the loaded device, each one's channel, and
    #: each one's neighbours.
    device_electrodes = List(Str)
    electrode_channels = Dict(Str, Int)
    electrode_neighbours = Dict(Str, List(Str))

    #: The channels the user disabled in the device viewer; a run drops them.
    disabled_channels = List(Int)

    #: The experiment folder, whether it is writable, and its free space, GB.
    experiment_folder = Str
    folder_writable = Bool(False)
    free_disk_gb = Float(0.0)

    def run_steps(self):
        """The steps this run covers, in protocol order."""
        scope = set(self.run_paths)

        return [step for step in self.steps if step["path"] in scope]


class RunInfo(HasTraits):
    """The protocol run in progress, shown in place of the checks."""

    #: Whether a protocol is running, and whether that run is paused.
    active = Bool(False)
    paused = Bool(False)

    #: The current step (1-based) and the step count of the run.
    step = Int
    step_total = Int

    #: Time since the run started, s.
    elapsed_s = Int

    #: e.g. "3/8 · 01:24".
    progress_line = Property(observe="step, step_total, elapsed_s")

    def _get_progress_line(self):
        minutes, seconds = divmod(self.elapsed_s, 60)

        return f"{self.step}/{self.step_total} · {minutes:02d}:{seconds:02d}"


class PreflightCheck(HasTraits):
    """One check's row: what it checks and how it came out."""

    #: Stable identifier, e.g. "no_empty_steps" or "unused_column:video".
    id = Str

    #: The group it is listed under in the expanded view.
    category = Enum(*CATEGORIES)

    #: Short neutral noun, e.g. "DropBot", "Voltage".
    label = Str

    #: How it came out.
    status = Enum(*STATUSES)

    #: Short problem phrase for a warn/fail, two or three words, e.g.
    #: "Voltage too high"; empty otherwise.
    problem = Str

    #: Muted right-hand detail, three words at most, e.g. "Step 4".
    detail = Str

    #: The full story, shown as the row's tooltip.
    tooltip = Str

    #: Whether its warning can be allowed for good, not just for one run.
    mutable_always = Bool(False)


class PreflightReport(HasTraits):
    """Every check of the last evaluation, the mutes, and their sum."""

    #: The checks, in display order, with their final statuses.
    checks = List(Instance(PreflightCheck))

    #: "This run" mutes, by ``run_mute_key(check id, detail)``.
    run_mutes = List(Str)

    #: Check ids allowed for good: a copy of the persisted preference.
    always_mutes = List(Str)

    #: What the evaluated run covers, e.g. "Preview · 8 steps".
    scope_line = Str

    #: Protocol statistics for the pill's tooltip.
    step_count = Int
    duration_s = Int
    electrode_count = Int

    #: "pass", "warn" or "fail"; muted warnings count as pass.
    overall = Property(
        observe="checks.items.status, run_mutes.items, always_mutes.items"
    )

    #: Checks that warn (unmuted) / block.
    warning_count = Property(
        observe="checks.items.status, run_mutes.items, always_mutes.items"
    )
    blocking_count = Property(observe="checks.items.status")

    #: The card's one-line header.
    summary = Property(observe="overall, warning_count")

    #: steps · duration · electrodes.
    stats_line = Property(observe="step_count, duration_s, electrode_count")

    #: The first blocking check's reason, for the disabled Run's tooltip.
    first_blocking_reason = Property(observe="checks.items.[status, tooltip]")

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

    def _get_overall(self):
        if self.blocking_count:
            return "fail"

        if self.warning_count:
            return "warn"

        return "pass"

    def _get_warning_count(self):
        return sum(
            check.status == "warn" and not self.is_muted(check) for check in self.checks
        )

    def _get_blocking_count(self):
        return sum(check.status == "fail" for check in self.checks)

    def _get_summary(self):
        if self.overall == "fail":
            return "Can't run yet"

        if self.overall == "warn":
            count = self.warning_count

            return f"{count} thing{'s' if count != 1 else ''} to look at"

        return "Ready to run"

    def _get_stats_line(self):
        minutes, seconds = divmod(self.duration_s, 60)

        return (
            f"{self.step_count} steps · ~{minutes}m {seconds:02d}s · "
            f"{self.electrode_count} electrodes"
        )

    def _get_first_blocking_reason(self):
        for check in self.checks:
            if check.status == "fail":
                return (
                    check.tooltip or f"{check.problem or check.label}: {check.detail}"
                )

        return ""

    # ------------------------------------------------------------------
    # Views onto the checks
    # ------------------------------------------------------------------

    def mute_scope(self, check):
        """``MUTE_ALWAYS`` or ``MUTE_RUN`` if ``check`` is a muted warning,
        else empty."""
        if check.status != "warn":
            return ""

        if check.mutable_always and check.id in self.always_mutes:
            return MUTE_ALWAYS

        if run_mute_key(check.id, check.detail) in self.run_mutes:
            return MUTE_RUN

        return ""

    def is_muted(self, check):
        """Whether ``check`` is a warning the operator muted."""
        return bool(self.mute_scope(check))

    def problems(self):
        """Blocking checks, then unmuted warnings."""
        failing = [check for check in self.checks if check.status == "fail"]
        warning = [
            check
            for check in self.checks
            if check.status == "warn" and not self.is_muted(check)
        ]

        return failing + warning

    def quiet_checks(self, category):
        """Passed, skipped and muted checks under ``category``."""
        return [
            check
            for check in self.checks
            if check.category == category
            and (check.status in ("pass", "skip") or self.is_muted(check))
        ]

    def quiet_counts(self):
        """How many checks passed, were not checked (skipped) and are
        muted."""
        passed = sum(check.status == "pass" for check in self.checks)
        not_checked = sum(check.status == "skip" for check in self.checks)
        muted = sum(self.is_muted(check) for check in self.checks)

        return passed, not_checked, muted
