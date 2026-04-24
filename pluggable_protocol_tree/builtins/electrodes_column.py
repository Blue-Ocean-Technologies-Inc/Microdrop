"""Electrodes column — list of electrode IDs held active for the step.

Read-only summary cell ('3 electrodes'). Mutated only via the demo's
SimpleDeviceViewer or programmatic / JSON-load path. Production
device-viewer integration is deferred to a later sub-issue.
"""

from pyface.qt.QtCore import Qt
from traits.api import List, Str

from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.views.columns.base import BaseColumnView


class ElectrodesColumnModel(BaseColumnModel):
    """List[str] trait. Default = empty list."""
    def trait_for_row(self):
        return List(Str, value=list(self.default_value or []),
                    desc="Electrode IDs held active for the entire step.")


class ElectrodesSummaryView(BaseColumnView):
    """Read-only cell. Shows '0 electrodes' / '1 electrode' / 'N electrodes'."""

    def format_display(self, value, row):
        n = len(value or [])
        return f"{n} electrode" + ("" if n == 1 else "s")

    def get_flags(self, row):
        # NOT editable — no ItemIsEditable flag.
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def create_editor(self, parent, context):
        return None


def make_electrodes_column():
    return Column(
        model=ElectrodesColumnModel(
            col_id="electrodes", col_name="Electrodes", default_value=[],
        ),
        view=ElectrodesSummaryView(),
    )
