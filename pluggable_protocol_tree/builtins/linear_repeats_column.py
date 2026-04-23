"""Hidden linear-repeats column. When True, replay open routes
n_repeats times (n_repeats comes from the row's repetitions column)."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class LinearRepeatsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Replay open routes n_repeats times.")


def make_linear_repeats_column():
    return Column(
        model=LinearRepeatsColumnModel(
            col_id="linear_repeats", col_name="Lin Reps", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
