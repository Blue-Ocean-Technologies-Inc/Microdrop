# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pre-flight checks: pure functions over a ``PreflightContext``.

Two sources:

- **ppt built-ins** (protocol structure, data, unused columns, ack waits
  turned off), registered
  here with ``@preflight_check(id, category, label)``; each is
  ``check(context) -> Result`` or a list of them, one per finding.
- **Column checks**: every column handler may override
  ``BaseColumnHandler.preflight_checks(context) -> [ColumnCheck, ...]``
  (default: none), so a column checks the hardware it drives, reading it
  itself. ``column_checks()`` collects them.

A check that raises, or a row that is not a ``ColumnCheck`` with a
``Result``, is logged and skipped, never stopping the rest.
"""

# Enthought library imports.
from traits.api import Bool, Callable, Enum, HasTraits, Instance, Str

# Local imports.
from .consts import (
    CATEGORIES,
    CHECK_DISABLED_CHANNELS,
    CHECK_DISK_SPACE,
    CHECK_ELECTRODES_EXIST,
    CHECK_FOLDER_WRITABLE,
    CHECK_NO_EMPTY_STEPS,
    CHECK_ROUTES_VALID,
    MIN_FREE_GB,
    STATUSES,
    ack_wait_off_check_id,
    run_mute_key,
    unused_column_check_id,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class Result(HasTraits):
    """One finding of a check, built by keyword, e.g.
    ``Result(status="warn", detail="Step 4", problem="Empty step")``."""

    #: How the check came out: "pass", "warn", "fail" or "skip".
    status = Enum(*STATUSES)

    #: What the finding points at, three words at most, e.g. "Step 4"; a
    #: skip's says why in a word or two, e.g. "Preview", "No device".
    detail = Str

    #: Names a warn/fail in two or three words, e.g. "Voltage too high".
    problem = Str

    #: The full story, shown on hover.
    tooltip = Str


class ColumnCheck(HasTraits):
    """A row to show: what ``evaluate_checks`` returns, and what a column
    handler's ``preflight_checks`` returns, built by keyword."""

    #: Stable id, e.g. "voltage:dropbot"; every finding of a check shares it.
    id = Str

    #: Short neutral noun, e.g. "DropBot".
    label = Str

    #: How it came out.
    result = Instance(Result)

    #: The group it is listed under.
    category = Enum("Peripherals", CATEGORIES)

    #: Whether its warning can be allowed for good, not just for one run;
    #: only for structural, intentional warnings (an unused column).
    mutable_always = Bool(False)


class CheckSpec(HasTraits):
    """A registered built-in check."""

    #: The id, group and neutral label its rows carry.
    id = Str
    category = Enum(*CATEGORIES)
    label = Str

    #: ``function(context)``: a ``Result``, or a list of them.
    function = Callable


#: The built-in checks, in display order within their category.
BUILTIN_CHECKS = []

#: Why a device check cannot judge the protocol: no device loaded.
NO_DEVICE_SKIP = Result(
    status="skip",
    detail="No device",
    tooltip="No device geometry has arrived from the device viewer yet.",
)


def preflight_check(check_id, category, label):
    """Register the decorated function as a built-in check."""

    def register(function):
        BUILTIN_CHECKS.append(
            CheckSpec(id=check_id, category=category, label=label, function=function)
        )

        return function

    return register


def column_checks(handlers, context):
    """The checks every column handler contributes, in column order. A
    handler whose checks raise contributes none, never stopping the rest."""
    rows = []

    for handler in handlers:
        try:
            checks = list(handler.preflight_checks(context))

        except Exception:
            logger.exception(f"Pre-flight checks of {handler!r} failed; skipped")

            continue

        rows.extend(_valid_rows(checks, handler))

    return rows


def evaluate_checks(context, handlers=()):
    """Run every check: built-ins, then the unused-column warnings, then the
    columns' own checks, as ``ColumnCheck`` rows (one per finding). A finding
    contributed twice (two cells of one compound column) is shown once."""
    rows = []

    for spec in BUILTIN_CHECKS:
        try:
            results = spec.function(context)

        except Exception:
            logger.exception(f"Pre-flight check {spec.id} failed; skipped")

            continue

        if isinstance(results, Result):
            results = [results]

        rows.extend(
            ColumnCheck(
                id=spec.id, label=spec.label, result=result, category=spec.category
            )
            for result in results
        )

    rows.extend(unused_column_checks(context))
    rows.extend(ack_wait_checks(context))
    rows.extend(column_checks(handlers, context))

    unique = {}

    for row in rows:
        unique.setdefault(run_mute_key(row.id, row.result.detail), row)

    return list(unique.values())


def protocol_stats(context):
    """Steps, duration (s) and distinct electrodes of the run."""
    steps = context.run_steps()
    duration = sum(step["duration_s"] * step["repeats"] for step in steps)

    return len(steps), int(duration), len(_all_electrodes(steps))


def run_actuates_electrodes(context):
    """Whether a run step names electrodes or routes: what a run with no
    device or no chip would fail to actuate."""
    return bool(_all_electrodes(context.run_steps()))


def step_name(step):
    """ "Step 4", or "Step 2.3" for a step inside a group."""
    return "Step " + ".".join(str(index + 1) for index in step["path"])


def _valid_rows(rows, source):
    """The ``ColumnCheck`` rows of ``rows`` that carry a ``Result``; any
    other is logged and skipped."""
    valid = []

    for row in rows:
        if isinstance(row, ColumnCheck) and isinstance(row.result, Result):
            valid.append(row)

        else:
            logger.error(f"Pre-flight row {row!r} of {source!r} is malformed; skipped")

    return valid


def _all_electrodes(steps):
    """Every electrode ``steps`` actuate or route through."""
    electrodes = set()

    for step in steps:
        electrodes.update(step["electrodes"])

        for route in step["routes"]:
            electrodes.update(route)

    return electrodes


def _per_step(context, finding):
    """One result per run step ``finding(step)`` flags, or a single pass."""
    results = [finding(step) for step in context.run_steps()]
    results = [result for result in results if result is not None]

    return results or [Result(status="pass")]


def _aggregated(status, problem, findings):
    """One result for every flagged run step: ``findings`` maps a step's
    name to its line, all listed in the tooltip. A single pass if empty."""
    if not findings:
        return Result(status="pass")

    names = list(findings)
    detail = names[0] if len(names) == 1 else f"{len(names)} steps"

    return Result(
        status=status,
        detail=detail,
        tooltip="\n".join(findings.values()),
        problem=problem,
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@preflight_check(CHECK_NO_EMPTY_STEPS, "Protocol", "Steps")
def check_no_empty_steps(context):
    steps = context.run_steps()

    if not steps:
        return Result(
            status="fail",
            detail="No steps",
            tooltip="This run covers no steps.",
            problem="Nothing to run",
        )

    # A step setting nothing (no electrodes, routes or other column changed
    # from its default) only waits out its duration.
    findings = {
        step_name(step): f"{step_name(step)} actuates and sets nothing"
        for step in steps
        if not _all_electrodes([step]) and not step["set_columns"]
    }

    return _aggregated("warn", "Empty step", findings)


@preflight_check(CHECK_ELECTRODES_EXIST, "Protocol", "Electrodes")
def check_electrodes_exist(context):
    if not context.device_electrodes:
        return _no_device_result(context)

    on_device = set(context.device_electrodes)

    def finding(step):
        missing = sorted(_all_electrodes([step]) - on_device)

        if not missing:
            return None

        name = step_name(step)
        tooltip = f"{name}: {', '.join(missing)} not on the loaded device"

        return Result(
            status="fail",
            detail=name,
            tooltip=tooltip,
            problem="Electrode not on device",
        )

    return _per_step(context, finding)


def _no_device_result(context):
    """Without a device a run has no channel map and actuates nothing: a
    failure when a run step names electrodes, else nothing to judge."""
    if context.preview_mode:
        return Result(
            status="skip",
            detail="Preview",
            tooltip="No device is loaded; a preview drives no hardware.",
        )

    if not run_actuates_electrodes(context):
        return NO_DEVICE_SKIP

    tooltip = (
        "No device is loaded, so the run has no channel map and its steps "
        "actuate no electrodes."
    )

    return Result(
        status="fail", detail="Not loaded", tooltip=tooltip, problem="No device"
    )


@preflight_check(CHECK_ROUTES_VALID, "Protocol", "Routes")
def check_routes_valid(context):
    neighbours = context.electrode_neighbours

    # The electrodes check reports a missing device.
    if not context.device_electrodes or not neighbours:
        return NO_DEVICE_SKIP

    def finding(step):
        for route in step["routes"]:
            # Electrodes off the device are the electrodes check's finding.
            route = [electrode for electrode in route if electrode in neighbours]

            for here, there in zip(route, route[1:]):
                if there not in neighbours[here]:
                    name = step_name(step)
                    tooltip = f"{name}: route jumps {here} → {there}, not neighbours"

                    return Result(
                        status="warn",
                        detail=name,
                        tooltip=tooltip,
                        problem="Route not contiguous",
                    )

        return None

    return _per_step(context, finding)


@preflight_check(CHECK_DISABLED_CHANNELS, "Protocol", "Channels")
def check_disabled_channels(context):
    channels = context.electrode_channels

    if not channels:
        return NO_DEVICE_SKIP

    disabled = set(context.disabled_channels)
    findings = {}

    for step in context.run_steps():
        hit = sorted(
            electrode
            for electrode in _all_electrodes([step])
            if channels.get(electrode) in disabled
        )

        if not hit:
            continue

        name = step_name(step)
        listed = ", ".join(
            f"{electrode} (ch {channels[electrode]})" for electrode in hit
        )
        findings[name] = f"{name}: {listed} disabled, so not actuated"

    return _aggregated("warn", "Disabled electrode", findings)


def unused_column_checks(context):
    """One warning per hooked column no step of the run uses: the run skips
    its protocol start/end hooks. Allowing one "Always" keeps it quiet for
    good; ``suppress_unused_column_hooks_information`` hides them all."""
    rows = []

    for column_id in context.unused_column_ids:
        name = context.columns.get(column_id, column_id)
        tooltip = (
            f"No step of this run uses the {name} column, so its protocol "
            f"start/end hooks will be skipped."
        )
        result = Result(status="warn", tooltip=tooltip, problem=f"{name} column unused")

        rows.append(
            ColumnCheck(
                id=unused_column_check_id(column_id),
                label=name,
                result=result,
                category="Protocol",
                mutable_always=True,
            )
        )

    return rows


def ack_wait_checks(context):
    """One warning per column the run uses whose ack wait is 0: the run
    would not notice a hardware command that never lands. Skipped in a
    preview, which drives no hardware; an endless wait is never flagged."""
    rows = []

    for column_id, seconds in context.ack_times.items():
        if seconds != 0:
            continue

        name = context.ack_column_names.get(column_id, column_id)

        if context.preview_mode:
            result = Result(
                status="skip", detail="Preview", tooltip="Preview drives no hardware."
            )

        else:
            tooltip = (
                f"The {name} column does not wait for the hardware to "
                f"acknowledge its commands, so this run would not notice one "
                f"that never lands. Set its ack wait under the card's settings."
            )
            result = Result(
                status="warn", tooltip=tooltip, problem=f"{name} ack wait off"
            )

        rows.append(
            ColumnCheck(
                id=ack_wait_off_check_id(column_id),
                label=name,
                result=result,
                category="Protocol",
                mutable_always=True,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@preflight_check(CHECK_FOLDER_WRITABLE, "Data", "Folder")
def check_folder_writable(context):
    if not context.experiment_folder:
        return Result(
            status="fail",
            detail="None set",
            tooltip="No experiment folder is set.",
            problem="No folder",
        )

    if not context.folder_writable:
        tooltip = f"{context.experiment_folder} is read-only."

        return Result(
            status="fail",
            detail="Read-only",
            tooltip=tooltip,
            problem="Folder read-only",
        )

    return Result(status="pass")


@preflight_check(CHECK_DISK_SPACE, "Data", "Disk space")
def check_disk_space(context):
    if context.free_disk_gb >= MIN_FREE_GB:
        return Result(status="pass")

    free = f"{context.free_disk_gb:.1f} GB free"
    tooltip = f"{free} for the experiment folder; under {MIN_FREE_GB:.0f} GB."

    return Result(status="warn", detail=free, tooltip=tooltip, problem="Low disk space")
