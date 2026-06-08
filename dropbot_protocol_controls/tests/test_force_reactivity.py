"""Integration test for the Force column reactive wiring.

Wires the real make_force_column() + make_voltage_column() into a
RowManager, then exercises both reactive paths end-to-end:
- mutating row.voltage repaints the Force cell on that row (per-row
  dataChanged, driven by the view's depends_on_row_traits).
- a CALIBRATION_DATA event reaching the Force column handler repaints
  the entire Force column (column-wide layoutChanged, driven by the
  handler's column_changed_signal).
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
from dropbot_protocol_controls.services import force_math


class _FakeGlobals:
    def __init__(self):
        self._values = {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set_calibration(self, liquid, filler):
        self._values["liquid_capacitance_over_area"] = liquid
        self._values["filler_capacitance_over_area"] = filler


@pytest.fixture(autouse=True)
def fake_app_globals(monkeypatch):
    fake = _FakeGlobals()
    monkeypatch.setattr(force_math, "app_globals", fake)
    return fake


def _build_columns():
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV:
        MockV.return_value.last_voltage = 100
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_voltage_column(), make_force_column(),
        ]


def test_voltage_change_repaints_force_cell_on_that_row(fake_app_globals):
    cols = _build_columns()
    manager = RowManager(columns=cols)
    fake_app_globals.set_calibration(2.0, 0.5)
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


def test_calibration_event_repaints_force_column(fake_app_globals):
    cols = _build_columns()
    manager = RowManager(columns=cols)
    fake_app_globals.set_calibration(2.0, 0.5)
    manager.add_step(values={"voltage": 100})
    manager.add_step(values={"voltage": 110})

    qm = MvcTreeModel(manager)
    force_col = next(c for c in manager.columns if c.model.col_id == "force")

    layout_count = {"n": 0}
    qm.layoutChanged.connect(
        lambda: layout_count.__setitem__("n", layout_count["n"] + 1),
    )

    before = layout_count["n"]
    # Simulate the dramatiq listener delivering a CALIBRATION_DATA message
    # to the force column handler; the model is already wired to its signal.
    force_col.handler._on_calibration_data_triggered(message="{}")

    assert layout_count["n"] > before, (
        "Expected a calibration event to repaint the force column "
        f"(layout fires={layout_count['n'] - before})"
    )
