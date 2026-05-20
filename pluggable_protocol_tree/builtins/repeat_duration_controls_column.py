"""Hidden mode-flag column tracking whether Repeat Duration is the
authoritative knob for loop cycle counts (True) or whether Repetitions
controls and Repeat Duration is auto-recalculated (False — default).

Mirrors the legacy protocol_grid REPEAT_DURATION_CONTROLS_ROLE on the
Description item. Lives as a column so it serializes with the rest of
the row state and rides the same trait-change plumbing as other
per-row config.
"""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class RepeatDurationControlsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="True when Repeat (s) is the authoritative "
                         "loop-budget knob; False when Reps controls.")


def make_repeat_duration_controls_column():
    return Column(
        model=RepeatDurationControlsColumnModel(
            col_id="repeat_duration_controls",
            col_name="Dur Controls",
            default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
