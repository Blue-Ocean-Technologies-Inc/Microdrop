"""Tests for the force column — model, factory, view dependency
declarations, and the calibration-driven repaint handler."""

import pytest
from pyface.qt.QtCore import QObject, Signal
from traits.api import HasTraits, Int

from pluggable_protocol_tree.models.column import Column

from dropbot_protocol_controls.protocol_columns import force_column
from dropbot_protocol_controls.protocol_columns.force_column import (
    ForceColumnHandler,
    ForceColumnModel,
    ForceColumnView,
    make_force_column,
)
from dropbot_protocol_controls.services.force_math import force_for_step


class _FakeRow(HasTraits):
    voltage = Int(100)


class _Emitter(QObject):
    """Owns a real bound Qt signal for wiring into a handler."""

    sig = Signal()


@pytest.fixture
def patch_c_per_a(monkeypatch):
    """Patch the calibration lookup the model calls so get_value is
    isolated from app globals / Redis."""

    def _set(value):
        monkeypatch.setattr(
            force_column, "current_capacitance_per_unit_area",
            lambda: value,
        )

    return _set


def test_make_force_column_returns_column_with_force_id():
    col = make_force_column()
    assert isinstance(col, Column)
    assert col.model.col_id == "force"
    assert col.model.col_name == "Force (mN/m)"
    assert col.view is not None
    assert isinstance(col.handler, ForceColumnHandler)


def test_get_value_happy_path_matches_force_for_step(patch_c_per_a):
    patch_c_per_a(1.5)
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    row = _FakeRow(voltage=100)

    expected = force_for_step(100.0, 1.5)
    assert expected is not None
    assert model.get_value(row) == pytest.approx(expected)


def test_get_value_no_calibration_returns_none(patch_c_per_a):
    patch_c_per_a(None)
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    row = _FakeRow(voltage=100)
    assert model.get_value(row) is None


def test_get_value_voltage_zero_returns_none(patch_c_per_a):
    patch_c_per_a(1.5)
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    row = _FakeRow(voltage=0)
    assert model.get_value(row) is None


def test_format_display_with_value_renders_two_decimals():
    view = ForceColumnView()
    row = _FakeRow(voltage=100)
    assert view.format_display(5.4321, row) == "5.43"


def test_format_display_with_none_returns_empty_string():
    view = ForceColumnView()
    row = _FakeRow(voltage=100)
    assert view.format_display(None, row) == ""


def test_view_class_attributes_are_set():
    view = ForceColumnView()
    assert view.renders_on_group is False
    assert view.hidden_by_default is False


def test_serialize_drops_value_to_none_and_deserialize_returns_float_placeholder():
    model = ForceColumnModel(
        col_id="force", col_name="Force (mN/m)", default_value=0.0,
    )
    assert model.serialize(123.4) is None
    assert model.serialize(None) is None
    assert model.deserialize("anything") == 0.0
    assert model.deserialize(None) == 0.0


def test_view_dependency_declarations_are_present():
    view = ForceColumnView()
    assert list(view.depends_on_row_traits) == ["voltage"]


# ---------------------------------------------------------------------------
# ForceColumnHandler — calibration-driven column repaint.
# ---------------------------------------------------------------------------

def test_calibration_trigger_emits_signal_when_wired():
    handler = ForceColumnHandler()
    emitter = _Emitter()
    fired = []
    emitter.sig.connect(lambda: fired.append(True))
    handler.column_changed_signal = emitter.sig

    handler._on_calibration_data_triggered(message="ignored")

    assert fired == [True]


def test_calibration_trigger_defers_when_signal_not_wired():
    handler = ForceColumnHandler()
    assert handler.column_changed_signal is None

    handler._on_calibration_data_triggered(message="ignored")

    assert handler.trigger_column_change_when_wired is True


def test_deferred_trigger_replays_when_signal_is_wired_later():
    handler = ForceColumnHandler()
    handler._on_calibration_data_triggered(message="ignored")  # before wiring

    emitter = _Emitter()
    fired = []
    emitter.sig.connect(lambda: fired.append(True))

    handler.column_changed_signal = emitter.sig  # wiring replays the repaint

    assert fired == [True]
