"""Step duration in seconds.

Stored as a Float trait on each row. Not meaningful on groups; the
double-spinbox view already marks group cells non-editable."""

from traits.api import Float

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import DoubleSpinBoxColumnView


class DurationColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Float(1.0, desc="Dwell time for this step in seconds")


def make_duration_column():
    return Column(
        model=DurationColumnModel(
            col_id="duration_s", col_name="Duration (s)", default_value=1.0,
        ),
        view=DoubleSpinBoxColumnView(
            low=0.0, high=3600.0, decimals=2, single_step=0.1,
        ),
    )
