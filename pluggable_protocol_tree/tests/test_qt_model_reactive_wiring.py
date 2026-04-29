"""Reactive wiring tests for MvcTreeModel.

Covers two paths added in PPT-7 Task 5:
- per-row trait dependency: a column view declaring depends_on_row_traits
  should cause the model to emit dataChanged for that column's cell on
  the row whose trait fired.
- column-wide event dependency: a column view declaring
  depends_on_event_source + depends_on_event_trait_name should cause
  the model to emit a column-wide repaint when the event fires.
"""

import pytest
from traits.api import Bool, Float, HasTraits, Int, List as TraitList, Str

from pluggable_protocol_tree.models.column import (
    BaseColumnHandler,
    BaseColumnModel,
    Column,
)
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.columns.readonly_label import (
    ReadOnlyLabelColumnView,
)
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column


class _RowTraitEventSource(HasTraits):
    test_event = Bool(False)


class _DerivedColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Float(0.0)

    def get_value(self, row):
        return float(getattr(row, "voltage", 0.0))


class _RowTraitDependentView(ReadOnlyLabelColumnView):
    depends_on_row_traits = TraitList(Str, value=["voltage"])

    def format_display(self, value, row):
        return f"{value:.1f}"


class _EventDependentView(ReadOnlyLabelColumnView):
    def format_display(self, value, row):
        return f"{value:.1f}"


class _PlainVoltageColumnModel(BaseColumnModel):
    """Stand-in for the real VoltageColumnModel; avoids preferences /
    Redis side effects that the production make_voltage_column has."""

    def trait_for_row(self):
        return Int(int(self.default_value or 0))


def _make_plain_voltage_column():
    return Column(
        model=_PlainVoltageColumnModel(
            col_id="voltage", col_name="Voltage (V)", default_value=100,
        ),
        view=ReadOnlyLabelColumnView(),
        handler=BaseColumnHandler(),
    )


def _make_derived_column_with_row_dep():
    return Column(
        model=_DerivedColumnModel(
            col_id="derived", col_name="Derived", default_value=0.0,
        ),
        view=_RowTraitDependentView(),
        handler=BaseColumnHandler(),
    )


def _make_derived_column_with_event_dep(source, trait_name):
    view = _EventDependentView()
    view.depends_on_event_source = source
    view.depends_on_event_trait_name = trait_name
    return Column(
        model=_DerivedColumnModel(
            col_id="derived", col_name="Derived", default_value=0.0,
        ),
        view=view,
        handler=BaseColumnHandler(),
    )


# -----------------------------------------------------------------------------
# Per-row trait dependency
# -----------------------------------------------------------------------------

def test_row_trait_change_emits_datachanged_for_derived_column_only():
    derived_col = _make_derived_column_with_row_dep()
    voltage_col = _make_plain_voltage_column()
    cols = [
        make_type_column(), make_id_column(), make_name_column(),
        voltage_col, derived_col,
    ]
    manager = RowManager(columns=cols)
    manager.add_step(values={"voltage": 100})

    qm = MvcTreeModel(manager)

    derived_idx = [c.model.col_id for c in manager.columns].index("derived")
    voltage_idx = [c.model.col_id for c in manager.columns].index("voltage")

    received: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top, bottom)),
    )

    row = manager.root.children[0]
    row.voltage = 200

    assert any(
        top.column() == derived_idx and bottom.column() == derived_idx
        and top.row() == 0 and bottom.row() == 0
        for top, bottom in received
    ), (
        f"Expected dataChanged for derived column index {derived_idx} on row 0, "
        f"got {[(t.row(), t.column()) for t, _ in received]}"
    )
    assert all(
        not (top.column() == voltage_idx and bottom.column() == voltage_idx)
        for top, bottom in received
    ), "Voltage cell should not have been re-emitted by the derived-column wiring"


def test_row_trait_change_targets_correct_row_index_among_many():
    derived_col = _make_derived_column_with_row_dep()
    voltage_col = _make_plain_voltage_column()
    cols = [make_type_column(), make_name_column(), voltage_col, derived_col]
    manager = RowManager(columns=cols)
    manager.add_step(values={"voltage": 100})
    manager.add_step(values={"voltage": 110})
    manager.add_step(values={"voltage": 120})

    qm = MvcTreeModel(manager)
    derived_idx = [c.model.col_id for c in manager.columns].index("derived")

    received: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top.row(), top.column())),
    )

    middle_row = manager.root.children[1]
    middle_row.voltage = 999

    assert (1, derived_idx) in received
    assert (0, derived_idx) not in received
    assert (2, derived_idx) not in received


def test_row_observers_rewire_after_add_step():
    derived_col = _make_derived_column_with_row_dep()
    voltage_col = _make_plain_voltage_column()
    cols = [make_type_column(), make_name_column(), voltage_col, derived_col]
    manager = RowManager(columns=cols)
    manager.add_step(values={"voltage": 100})

    qm = MvcTreeModel(manager)
    derived_idx = [c.model.col_id for c in manager.columns].index("derived")

    # Add a second step AFTER the model was created.
    manager.add_step(values={"voltage": 110})

    received: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top.row(), top.column())),
    )

    new_row = manager.root.children[1]
    new_row.voltage = 200

    assert (1, derived_idx) in received


# -----------------------------------------------------------------------------
# Column-wide event dependency
# -----------------------------------------------------------------------------

def test_event_dependency_triggers_column_wide_repaint():
    source = _RowTraitEventSource()
    derived_col = _make_derived_column_with_event_dep(source, "test_event")
    cols = [
        make_type_column(), make_id_column(), make_name_column(), derived_col,
    ]
    manager = RowManager(columns=cols)
    manager.add_step()
    manager.add_step()

    qm = MvcTreeModel(manager)
    derived_idx = [c.model.col_id for c in manager.columns].index("derived")

    layout_changed_count = {"n": 0}
    qm.layoutChanged.connect(lambda: layout_changed_count.__setitem__(
        "n", layout_changed_count["n"] + 1,
    ))
    data_changed: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: data_changed.append(
            (top.column(), bottom.column()),
        ),
    )

    before = layout_changed_count["n"]
    source.test_event = True

    fired_layout = layout_changed_count["n"] > before
    fired_data_for_col = any(
        top == derived_idx and bottom == derived_idx
        for top, bottom in data_changed
    )
    assert fired_layout or fired_data_for_col, (
        "Expected event-dependency to repaint the derived column "
        f"(layout fires={layout_changed_count['n'] - before}, "
        f"data-changed cols={data_changed})"
    )


def test_event_dependency_no_crash_with_zero_rows():
    source = _RowTraitEventSource()
    derived_col = _make_derived_column_with_event_dep(source, "test_event")
    cols = [
        make_type_column(), make_id_column(), make_name_column(), derived_col,
    ]
    manager = RowManager(columns=cols)

    MvcTreeModel(manager)
    source.test_event = True   # must not raise


# -----------------------------------------------------------------------------
# Regression — model with no derived columns
# -----------------------------------------------------------------------------

def test_no_derived_columns_no_extra_signals():
    cols = [make_type_column(), make_id_column(), make_name_column()]
    manager = RowManager(columns=cols)
    manager.add_step()

    qm = MvcTreeModel(manager)

    received: list = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top, bottom)),
    )

    row = manager.root.children[0]
    row.name = "renamed"

    assert received == []
