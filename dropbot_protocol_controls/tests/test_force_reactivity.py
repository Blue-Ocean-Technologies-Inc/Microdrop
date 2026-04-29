"""Integration test for the Force column reactive wiring.

Wires the real make_force_column() + make_voltage_column() into a
RowManager, then exercises both reactive paths end-to-end:
- mutating row.voltage repaints the Force cell on that row.
- firing cache.cache_changed repaints the entire Force column.

Treats the production view's depends_on_row_traits / depends_on_event_*
declarations as the contract that MvcTreeModel must honour.
"""

from unittest.mock import patch

import pytest

from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel

from dropbot_protocol_controls.protocol_columns.force_column import (
    make_force_column,
)
from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.services.calibration_cache import cache


@pytest.fixture(autouse=True)
def _reset_calibration_cache():
    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )
    yield
    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )


def _build_columns():
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV:
        MockV.return_value.last_voltage = 100
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_voltage_column(), make_force_column(),
        ]


def test_voltage_change_repaints_force_cell_on_that_row():
    cols = _build_columns()
    manager = RowManager(columns=cols)
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    manager.add_step(values={"voltage": 100})

    qm = MvcTreeModel(manager)
    force_idx = [c.model.col_id for c in manager.columns].index("force")

    received: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top.row(), top.column())),
    )

    row = manager.root.children[0]
    row.voltage = 120

    assert (0, force_idx) in received, (
        f"Expected force-cell dataChanged at (row=0, col={force_idx}); "
        f"got {received}"
    )


def test_cache_changed_repaints_force_column():
    cols = _build_columns()
    manager = RowManager(columns=cols)
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    manager.add_step(values={"voltage": 100})
    manager.add_step(values={"voltage": 110})

    qm = MvcTreeModel(manager)
    force_idx = [c.model.col_id for c in manager.columns].index("force")

    layout_count = {"n": 0}
    qm.layoutChanged.connect(
        lambda: layout_count.__setitem__("n", layout_count["n"] + 1),
    )
    data_changes: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: data_changes.append(
            (top.column(), bottom.column()),
        ),
    )

    before = layout_count["n"]
    cache.cache_changed = True

    fired_layout = layout_count["n"] > before
    fired_force_data = any(
        top == force_idx and bottom == force_idx
        for top, bottom in data_changes
    )
    assert fired_layout or fired_force_data, (
        "Expected cache_changed to repaint the force column "
        f"(layout fires={layout_count['n'] - before}, "
        f"data-changed cols={data_changes}, force_idx={force_idx})"
    )
