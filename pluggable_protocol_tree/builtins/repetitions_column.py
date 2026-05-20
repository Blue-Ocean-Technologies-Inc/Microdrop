"""Repetitions column — number of times each row executes as a whole.

Steps re-run their on_step N times; groups expand their child subtree N
times. Default 1. Consumed only by row_manager._expand_frames.

NOTE: Reps no longer affects route looping — that is the separate
``route_repetitions`` ("Route Reps") column. A plain spinbox: editing
Reps never prompts and never touches repeat_duration_controls.

``iter_execution_frames`` in RowManager reads ``getattr(row,
"repetitions", 1)``; this column populates the trait. The getattr
fallback is kept for safety against persisted protocols predating the
column.
"""

from pyface.qt.QtCore import Qt
from traits.api import Int

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class RepetitionsColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Int(1, desc="Number of times this row executes as a whole "
                            "(groups expand subtree Nx)")


class RepsSpinBoxColumnView(IntSpinBoxColumnView):
    """IntSpinBoxColumnView variant that stays editable on group rows.

    Repetitions IS meaningful on groups — it multiplies the child
    subtree — so groups must be editable here too.
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
