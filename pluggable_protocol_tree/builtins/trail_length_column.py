"""Hidden trail-length column. How many electrodes are simultaneously
active in a route's sliding window."""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenIntSpinBoxColumnView,
)


class TrailLengthColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(int(self.default_value or 1),
                   desc="Number of electrodes simultaneously active in "
                        "a route's sliding window.")


def make_trail_length_column():
    return Column(
        model=TrailLengthColumnModel(
            col_id="trail_length", col_name="Trail Len", default_value=1,
        ),
        view=HiddenIntSpinBoxColumnView(low=1, high=64),
    )
