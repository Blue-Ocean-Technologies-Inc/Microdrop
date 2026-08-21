"""Demo columns — a traits-free mirror of the real IColumn model/handler split.

The real app's contract (``pluggable_protocol_tree/interfaces/i_column.py``)
is a model (typed value + col_id), a view (cell editor), and a handler with
priority-ordered execution hooks. Here the "view" collapses into a ``kind``
tag on the model (the demo table builds editors from it), and handlers gain
one new capability under test:

  * ``decision_specs()`` — the Decision objects this provider contributes,
    each with outcomes and default routes, and
  * ``ctx.request_decision(spec, message)`` — called from a hook when the
    step's outcome needs a user decision. The executor resolves it after
    ``on_post_step`` (prompt or auto) and routes execution accordingly.

Hook names, signatures, and the priority semantics match the real
BaseColumnHandler so these would port straight back into an IColumn.
"""

import random

from .model import ABORT, NEXT, SELF, DecisionSpec, Outcome


class ColumnModel:
    """col_id + display name + default + editor kind (float/int/bool)."""

    def __init__(
        self,
        col_id,
        col_name,
        default_value,
        kind="float",
        minimum=0.0,
        maximum=1e6,
        decimals=1,
        suffix="",
    ):
        self.col_id = col_id
        self.col_name = col_name
        self.default_value = default_value
        self.kind = kind
        self.minimum = minimum
        self.maximum = maximum
        self.decimals = decimals
        self.suffix = suffix

    def get_value(self, step):
        return step.values.get(self.col_id, self.default_value)

    def set_value(self, step, value):
        step.values[self.col_id] = value

    def format_display(self, step) -> str:
        v = self.get_value(step)
        if self.kind == "bool":
            return "yes" if v else "no"
        if self.kind == "float":
            return f"{float(v):.{self.decimals}f}{self.suffix}"
        return f"{v}{self.suffix}"


class ColumnHandler:
    """Execution hooks, mirroring BaseColumnHandler (all no-ops here)."""

    priority = 50
    model: ColumnModel = None  # wired by Column

    def decision_specs(self):
        return []

    def is_decision_active(self, spec, step) -> bool:
        """Whether this decision can fire for this step with its current
        values — lets the canvas grey out dormant decision strips."""
        return True

    # -- lifecycle hooks (same set as the real handler) -----------------
    def on_pre_protocol_start(self, ctx):
        pass

    def on_protocol_start(self, ctx):
        pass

    def on_pre_step(self, step, ctx):
        pass

    def on_step(self, step, ctx):
        pass

    def on_post_step(self, step, ctx):
        pass

    def on_protocol_end(self, ctx):
        pass

    def on_post_protocol_end(self, ctx):
        pass

    # -- group hooks (proposed addition) --------------------------------
    # Fired only on a FORMAL group entry/exit: sequential fall-through
    # into the group, or a route targeting the group node itself. A route
    # into one of the group's steps skips these (and the group repeats) —
    # that is the practical difference between wiring an outcome to a
    # group vs. to its first step.
    def on_group_enter(self, group, ctx):
        pass

    def on_group_exit(self, group, ctx):
        pass


class Column:
    """Composite: wires handler.model like the real Column.traits_init."""

    def __init__(self, model, handler):
        self.model = model
        self.handler = handler
        handler.model = model


# ---------------------------------------------------------------------------
# Demo columns
# ---------------------------------------------------------------------------


class VoltageHandler(ColumnHandler):
    priority = 10  # actuation setup runs before dwells/checks

    def on_step(self, step, ctx):
        v = self.model.get_value(step)
        ctx.log(f"Applying {v:.0f} V")
        ctx.sleep(0.15)

    def on_group_enter(self, group, ctx):
        # Demo of a group-scoped hook: something a provider does once per
        # formal group entry (per pass budget), not per step.
        ctx.log(f"Pre-charging electrodes for group {group.name!r}")


class DurationHandler(ColumnHandler):
    priority = 20

    def on_step(self, step, ctx):
        d = float(self.model.get_value(step))
        if d > 0:
            ctx.log(f"Dwelling {d:.1f} s")
            ctx.sleep(d)


VOLUME_CHECK = DecisionSpec(
    id="volume_check",
    title="Volume check",
    question="Dispensed volume is below target. What should happen?",
    outcomes=(
        Outcome("retry", "Retry", kind="negative"),
        Outcome("continue", "Continue", kind="positive"),
        Outcome("abort", "Abort", kind="danger"),
    ),
    default_routes={"retry": SELF, "continue": NEXT, "abort": ABORT},
    # When the prompt is suppressed (auto / auto-after-N) the safe default
    # is to move on rather than silently retry forever.
    default_outcome="continue",
    provider_col_id="fail_pct",
)


class VolumeCheckHandler(ColumnHandler):
    """Simulates a post-step volume measurement. The ``fail_pct`` cell is
    the chance (0-100) that the measurement misses target and the decision
    fires. 0 disables the check for that step."""

    priority = 40  # after the dwell

    def decision_specs(self):
        return [VOLUME_CHECK]

    def is_decision_active(self, spec, step) -> bool:
        return int(self.model.get_value(step) or 0) > 0

    def on_post_step(self, step, ctx):
        fail_pct = int(self.model.get_value(step) or 0)
        if fail_pct <= 0:
            return
        measured = random.uniform(40.0, 110.0)
        if random.random() * 100.0 < fail_pct:
            ctx.log(f"Volume check FAILED (measured {measured:.0f}% of target)")
            ctx.request_decision(
                VOLUME_CHECK,
                message=f"Measured {measured:.0f}% of target volume " f"(needs ≥ 95%).",
            )
        else:
            ctx.log(f"Volume check passed ({measured:.0f}% of target)")


DROPLET_DETECT = DecisionSpec(
    id="droplet_detect",
    title="Droplet detect",
    question="No droplet detected at the sensor. What should happen?",
    outcomes=(
        Outcome("restart", "Restart", kind="negative"),
        Outcome("continue", "Continue", kind="positive"),
        Outcome("abort", "Abort", kind="danger"),
    ),
    # Route 'Restart' to a GROUP node to replay the whole group (entry
    # hooks + repeats); to the group's first STEP to just re-run the
    # sequence without the group ceremony.
    default_routes={"restart": SELF, "continue": NEXT, "abort": ABORT},
    default_outcome="continue",
    provider_col_id="detect_fail",
)


class DropletDetectHandler(ColumnHandler):
    """Simulates an end-of-sequence droplet-presence sensor. The
    ``detect_fail`` cell is the chance (0-100) the droplet is missing and
    the decision fires. 0 disables the check for that step."""

    priority = 50  # after the volume check

    def decision_specs(self):
        return [DROPLET_DETECT]

    def is_decision_active(self, spec, step) -> bool:
        return int(self.model.get_value(step) or 0) > 0

    def on_post_step(self, step, ctx):
        fail_pct = int(self.model.get_value(step) or 0)
        if fail_pct <= 0:
            return
        if random.random() * 100.0 < fail_pct:
            ctx.log("Droplet detect FAILED (no droplet at sensor)")
            ctx.request_decision(
                DROPLET_DETECT,
                message="The capacitance sensor saw no droplet where one "
                "was expected.",
            )
        else:
            ctx.log("Droplet detected")


OPERATOR_CHECK = DecisionSpec(
    id="operator_check",
    title="Operator check",
    question="Visual check: is the droplet where you expect it?",
    outcomes=(
        Outcome("yes", "Yes", kind="positive"),
        Outcome("no", "No", kind="negative"),
        Outcome("abort", "Abort", kind="danger"),
    ),
    default_routes={"yes": NEXT, "no": SELF, "abort": ABORT},
    default_outcome="yes",
    provider_col_id="op_check",
)


class OperatorCheckHandler(ColumnHandler):
    """When the ``op_check`` cell is ticked, always pauses the run for a
    human yes/no after the step — the 'prompt with buttons' case."""

    priority = 60  # last, after everything else settled

    def decision_specs(self):
        return [OPERATOR_CHECK]

    def is_decision_active(self, spec, step) -> bool:
        return bool(self.model.get_value(step))

    def on_post_step(self, step, ctx):
        if self.model.get_value(step):
            ctx.request_decision(OPERATOR_CHECK)


def make_demo_columns():
    return [
        Column(
            ColumnModel(
                "voltage",
                "Voltage",
                100.0,
                kind="float",
                minimum=0,
                maximum=300,
                decimals=0,
                suffix=" V",
            ),
            VoltageHandler(),
        ),
        Column(
            ColumnModel(
                "duration_s",
                "Duration",
                1.0,
                kind="float",
                minimum=0,
                maximum=3600,
                decimals=1,
                suffix=" s",
            ),
            DurationHandler(),
        ),
        Column(
            ColumnModel(
                "fail_pct",
                "Fail chance",
                0,
                kind="int",
                minimum=0,
                maximum=100,
                suffix=" %",
            ),
            VolumeCheckHandler(),
        ),
        Column(
            ColumnModel(
                "detect_fail",
                "Detect fail",
                0,
                kind="int",
                minimum=0,
                maximum=100,
                suffix=" %",
            ),
            DropletDetectHandler(),
        ),
        Column(
            ColumnModel("op_check", "Operator check", False, kind="bool"),
            OperatorCheckHandler(),
        ),
    ]
