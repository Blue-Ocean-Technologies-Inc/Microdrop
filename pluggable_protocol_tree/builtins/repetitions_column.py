"""Repetitions column — number of times each row executes.

Steps repeat their on_step N times. Groups expand their child subtree
N times. Default 1.

iter_execution_steps in RowManager already reads ``getattr(row,
"repetitions", 1)`` (PPT-1 left the contract in place); this column
populates the trait so that getattr fallback becomes vestigial for
new protocols. The fallback is kept for safety against persisted
protocols that pre-date the column.
"""

from pyface.qt.QtCore import Qt
from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this row executes (groups "
                            "expand subtree N×)")


class RepsSpinBoxColumnView(IntSpinBoxColumnView):
    """IntSpinBoxColumnView variant that stays editable on group rows.

    The base IntSpinBoxColumnView strips ItemIsEditable on GroupRow
    cells (numbers don't apply to most group columns). Repetitions IS
    meaningful on groups — it multiplies the child subtree — so groups
    must be editable here too.
    """

    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable


def make_repetitions_column():
    return Column(
        model=RepetitionsColumnModel(
            col_id="repetitions", col_name="Reps", default_value=1,
        ),
        view=RepsSpinBoxColumnView(low=1, high=1000),
    )
