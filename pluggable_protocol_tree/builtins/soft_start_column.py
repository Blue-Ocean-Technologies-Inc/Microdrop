"""Hidden soft-start column. When True, prepend ramp-up phases that
grow from 1 electrode to trail_length."""

from traits.api import Bool

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns._hidden_view_mixins import (
    HiddenCheckboxColumnView,
)


class SoftStartColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(bool(self.default_value or False),
                    desc="Prepend ramp-up phases (1 electrode → trail_length).")


def make_soft_start_column():
    return Column(
        model=SoftStartColumnModel(
            col_id="soft_start", col_name="Soft Start", default_value=False,
        ),
        view=HiddenCheckboxColumnView(),
    )
