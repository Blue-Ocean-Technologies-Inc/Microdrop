"""Tests for the voltage column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

import pytest
from traits.api import HasTraits

from dropbot_protocol_controls.protocol_columns.voltage_column import (
    VoltageColumnModel, make_voltage_column,
)


def test_voltage_column_model_id_and_name():
    m = VoltageColumnModel(col_id="voltage", col_name="Voltage (V)",
                           default_value=100)
    assert m.col_id == "voltage"
    assert m.col_name == "Voltage (V)"
    assert m.default_value == 100


def test_voltage_column_trait_for_row_is_int():
    """Row trait stores Int — never Float."""
    m = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    trait = m.trait_for_row()
    class Row(HasTraits):
        voltage = trait
    r = Row()
    assert r.voltage == 100
    r.voltage = 75
    assert r.voltage == 75
    assert isinstance(r.voltage, int)


def test_voltage_column_serialize_identity():
    m = VoltageColumnModel(col_id="voltage", col_name="V", default_value=100)
    assert m.serialize(100) == 100
    assert m.deserialize(100) == 100


def test_make_voltage_column_returns_column_with_voltage_id():
    """Factory yields a Column whose model.col_id is 'voltage'."""
    # Patch DropbotPreferences so test doesn't need a real envisage app.
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_voltage = 100
        col = make_voltage_column()
    assert col.model.col_id == "voltage"
    assert col.view is not None
    assert col.handler is not None


def test_make_voltage_column_default_reads_from_prefs():
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_voltage = 75
        col = make_voltage_column()
    assert col.model.default_value == 75
