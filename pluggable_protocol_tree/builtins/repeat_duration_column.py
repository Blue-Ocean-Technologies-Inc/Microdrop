"""Route Reps Dur column. When > 0, caps route loop cycles to fit
within this many seconds of step time.

Edits prompt the user to hand loop-budget control over to Route Reps Dur
(matches the legacy protocol_grid dialog flow) when the new value
diverges from what the auto-estimate would compute given the current
Route Reps + Duration + trail config. On confirm, the row's
``repeat_duration_controls`` flag flips to True; on cancel, the edit
is rejected and the column reverts to its previous value.
"""

from traits.api import Float

from microdrop_application.dialogs.pyface_wrapper import YES, confirm

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler, BaseColumnModel, Column,
)
from pluggable_protocol_tree.services.phase_math import (
    estimate_repeat_duration_s,
)
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView,
)


class RepeatDurationColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Float(float(self.default_value or 0.0),
                     desc="Loop cycles capped to fit within this many "
                          "seconds. 0 disables (use linear n_repeats).")


class RepeatDurationHandler(BaseColumnHandler):
    """Intercepts edits to prompt for the Route Reps --> Route Reps Dur
    mode handoff. Read-through writes (no prompt) when:
      * the row is already in Route Reps Dur-controls mode, or
      * the new value matches the auto-estimate (rounding to the
        column's display precision), or
      * the row has no routes (Route Reps Dur has no semantic effect, so
        treat as a plain write).
    """

    def on_interact(self, row, model, value):
        new_value = float(value or 0.0)
        already_controls = bool(getattr(row, "repeat_duration_controls", False))
        if already_controls:
            return model.set_value(row, new_value)

        routes = list(getattr(row, "routes", []) or [])
        if not routes:
            return model.set_value(row, new_value)

        estimated = estimate_repeat_duration_s(
            routes=routes,
            trail_length=int(getattr(row, "trail_length", 1) or 1),
            trail_overlay=int(getattr(row, "trail_overlay", 0) or 0),
            n_repeats=int(getattr(row, "route_repetitions", 1) or 1),
            step_duration_s=float(getattr(row, "duration_s", 1.0) or 0.0),
            linear_repeats=bool(getattr(row, "linear_repeats", False)),
            soft_start=bool(getattr(row, "soft_start", False)),
            soft_end=bool(getattr(row, "soft_end", False)),
        )
        # Compare at 0.01s resolution — matches the column's two-decimal
        # display so a user-typed value identical to what's shown does
        # not falsely trigger the dialog.
        if abs(new_value - round(estimated, 2)) < 0.01:
            return model.set_value(row, new_value)

        choice = confirm(
            None,
            title="Switch to Repeat Duration Control",
            message=(
                "Using Repeat Duration will calculate the maximum number of "
                "complete loops that fit within the specified time. Any "
                "remaining time will be spent idling.<br><br>"
                "Route Reps will become read-only while Route Reps Dur "
                "is in control."
            ),
            yes_label="Switch",
            no_label="Cancel",
        )
        if choice != YES:
            return False
        row.repeat_duration_controls = True
        return model.set_value(row, new_value)


def make_repeat_duration_column():
    return Column(
        model=RepeatDurationColumnModel(
            col_id="repeat_duration", col_name="Route Reps Dur",
            default_value=0.0,
        ),
        view=DoubleSpinBoxColumnView(low=0.0, high=float("inf"),
                                     decimals=2, single_step=10),
        handler=RepeatDurationHandler(),
    )
