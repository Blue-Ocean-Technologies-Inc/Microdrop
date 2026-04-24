"""Hidden trail-overlay column. How many electrodes the current and
next windows share — controls the effective step size."""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenIntSpinBoxColumnView,
)


class TrailOverlayColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(int(self.default_value or 0),
                   desc="Electrodes shared between the current and "
                        "next windows. step_size = max(1, length - overlay).")


def make_trail_overlay_column():
    return Column(
        model=TrailOverlayColumnModel(
            col_id="trail_overlay", col_name="Trail Overlay", default_value=0,
        ),
        view=HiddenIntSpinBoxColumnView(low=0, high=63),
    )
