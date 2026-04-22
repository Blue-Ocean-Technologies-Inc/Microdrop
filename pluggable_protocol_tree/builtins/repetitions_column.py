"""Repetitions column — number of times each row executes.

Steps repeat their on_step N times. Groups expand their child subtree
N times. Default 1.

iter_execution_steps in RowManager already reads ``getattr(row,
"repetitions", 1)`` (PPT-1 left the contract in place); this column
populates the trait so that getattr fallback becomes vestigial for
new protocols. The fallback is kept for safety against persisted
protocols that pre-date the column.
"""

from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this row executes (groups "
                            "expand subtree N×)")


def make_repetitions_column():
    return Column(
        model=RepetitionsColumnModel(
            col_id="repetitions", col_name="Reps", default_value=1,
        ),
        view=IntSpinBoxColumnView(low=1, high=1000),
    )
