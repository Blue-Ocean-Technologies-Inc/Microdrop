"""Hidden soft-end column. When True, append ramp-down phases that
shrink from trail_length back to 1 electrode."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class SoftEndColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Append ramp-down phases (trail_length → 1).")


def make_soft_end_column():
    return Column(
        model=SoftEndColumnModel(
            col_id="soft_end", col_name="Soft End", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
