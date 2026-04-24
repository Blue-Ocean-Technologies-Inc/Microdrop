"""Hidden repeat-duration column. When > 0, caps loop cycles to fit
within this many seconds of step time."""

from traits.api import Float

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenDoubleSpinBoxColumnView,
)


class RepeatDurationColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Float(float(self.default_value or 0.0),
                     desc="Loop cycles capped to fit within this many "
                          "seconds. 0 disables (use linear n_repeats).")


def make_repeat_duration_column():
    return Column(
        model=RepeatDurationColumnModel(
            col_id="repeat_duration", col_name="Repeat (s)", default_value=0.0,
        ),
        view=HiddenDoubleSpinBoxColumnView(low=0.0, high=3600.0,
                                           decimals=2, single_step=0.1),
    )
