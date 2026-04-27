"""Tests for the frequency column — model, factory, view, handler."""

from unittest.mock import MagicMock, patch

import pytest
from traits.api import HasTraits

from dropbot_protocol_controls.protocol_columns.frequency_column import (
    FrequencyColumnModel, make_frequency_column,
)


def test_frequency_column_model_id_and_name():
    m = FrequencyColumnModel(col_id="frequency", col_name="Frequency (Hz)",
                             default_value=10000)
    assert m.col_id == "frequency"
    assert m.col_name == "Frequency (Hz)"
    assert m.default_value == 10000


def test_frequency_column_trait_for_row_is_int():
    m = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                             default_value=10000)
    trait = m.trait_for_row()
    class Row(HasTraits):
        frequency = trait
    r = Row()
    assert r.frequency == 10000
    r.frequency = 5000
    assert r.frequency == 5000
    assert isinstance(r.frequency, int)


def test_frequency_column_serialize_identity():
    m = FrequencyColumnModel(col_id="frequency", col_name="Hz",
                             default_value=10000)
    assert m.serialize(10000) == 10000
    assert m.deserialize(10000) == 10000


def test_make_frequency_column_returns_column_with_frequency_id():
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_frequency = 10000
        col = make_frequency_column()
    assert col.model.col_id == "frequency"


def test_make_frequency_column_default_reads_from_prefs():
    with patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockPrefs:
        MockPrefs.return_value.last_frequency = 5000
        col = make_frequency_column()
    assert col.model.default_value == 5000
