"""Route Reps Dur column. When > 0, caps route loop cycles to fit
within this many seconds of step time.

Edits prompt the user to hand loop-budget control over to Route Reps Dur
(matches the legacy protocol_grid dialog flow) when the new value
diverges from what the auto-estimate would compute given the current
Route Reps + Duration + trail config. On confirm, the row's
``repeat_duration_controls`` flag flips to True; on cancel, the edit
is rejected and the column reverts to its previous value.

Flipping the flag to True locks the ``route_repetitions`` cell (via the
BaseRow observer in models/row.py — issue #541), so once duration
control is active Route Reps is genuinely read-only. Editing Route Reps
Dur back to 0 is therefore the only way back to count mode: it prompts
with the same handoff dialog and, on confirm, flips the flag back to
False, which unlocks Route Reps again.
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
    """Intercepts edits to prompt for the Route Reps <--> Route Reps Dur
    mode handoffs: entering duration mode on a diverging non-zero edit,
    and handing control back on a 0 edit while in duration mode.
    Read-through writes (no prompt) when:
      * the row is already in Route Reps Dur-controls mode and the new
        value is non-zero, or
      * the new value matches the auto-estimate (rounding to the
        column's display precision), or
      * the row has no routes (Route Reps Dur has no semantic effect, so
        treat as a plain write).
    """

    def on_interact(self, row, model, value):
        new_value = float(value or 0.0)
        already_controls = bool(getattr(row, "repeat_duration_controls", False))
        if already_controls:
            if new_value == 0.0:
                # 0 disables duration control (matches the DV sidebar,
                # which derives the flag from repeat_duration > 0) —
                # and it is the only way back now that the lock makes
                # Route Reps genuinely read-only in duration mode.
                choice = confirm(
                    None,
                    title="Switch to Route Reps Control",
                    message=(
                        "Setting Route Reps Dur to 0 hands loop control "
                        "back to Route Reps: routes loop until the largest "
                        "loop has completed all repetitions.<br><br>"
                        "Route Reps will become editable again."
                    ),
                    yes_label="Switch",
                    no_label="Cancel",
                )
                if choice != YES:
                    return False
                row.repeat_duration_controls = False
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
        # Bounds mirror the DV sidebar's RouteLayerManager.repeat_duration.
        view=DoubleSpinBoxColumnView(low=0.0, high=10000.0,
                                     decimals=2, single_step=10),
        handler=RepeatDurationHandler(),
    )
