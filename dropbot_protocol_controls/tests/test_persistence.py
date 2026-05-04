"""JSON persistence round-trip for Int voltage/frequency columns and the
derived Force column (computed, never persisted)."""

import json
from unittest.mock import patch

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column

from dropbot_protocol_controls.protocol_columns.voltage_column import (
    make_voltage_column,
)
from dropbot_protocol_controls.protocol_columns.frequency_column import (
    make_frequency_column,
)
from dropbot_protocol_controls.protocol_columns.force_column import (
    make_force_column,
)
from dropbot_protocol_controls.services.calibration_cache import cache
from dropbot_protocol_controls.services.force_math import force_for_step


def _build_columns():
    """Patch DropbotPreferences so column factories don't need an envisage app."""
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_voltage_column(), make_frequency_column(),
        ]


def test_voltage_frequency_int_round_trip_through_json():
    cols = _build_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "voltage": 120, "frequency": 5000})

    payload = rm.to_json()
    json_str = json.dumps(payload)  # Confirms it's JSON-serializable
    parsed = json.loads(json_str)

    rm2 = RowManager.from_json(parsed, columns=_build_columns())
    step = rm2.root.children[0]
    assert step.voltage == 120
    assert step.frequency == 5000
    assert isinstance(step.voltage, int)
    assert isinstance(step.frequency, int)


# ---------------------------------------------------------------------------
# Force column persistence — derived, never stored on rows or in JSON.
# ---------------------------------------------------------------------------

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


def _build_seven_columns():
    """7-column set: PPT-3 builtins (type/id/name/duration_s) + voltage +
    frequency + force. Patches DropbotPreferences for the same reason as
    _build_columns()."""
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(),
            make_voltage_column(), make_frequency_column(),
            make_force_column(),
        ]


def _make_seven_col_rm_with_steps():
    cols = _build_seven_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "voltage": 80, "frequency": 10000})
    rm.add_step(values={"name": "S2", "voltage": 100, "frequency": 10000})
    rm.add_step(values={"name": "S3", "voltage": 120, "frequency": 10000})
    return rm


def test_force_column_metadata_in_json_payload():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    rm = _make_seven_col_rm_with_steps()

    payload = rm.to_json()

    force_entries = [c for c in payload["columns"] if c["id"] == "force"]
    assert len(force_entries) == 1, (
        f"Expected exactly one 'force' column entry, got {force_entries!r}"
    )
    assert force_entries[0]["cls"] == (
        "dropbot_protocol_controls.protocol_columns.force_column.ForceColumnModel"
    )


def test_per_row_force_values_are_none_in_json_payload():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    rm = _make_seven_col_rm_with_steps()

    payload = rm.to_json()

    force_field_idx = payload["fields"].index("force")
    rows = payload["rows"]
    assert len(rows) == 3
    for row_tuple in rows:
        assert row_tuple[force_field_idx] is None, (
            f"Force value should be None in serialized row tuple "
            f"(field idx {force_field_idx}); got {row_tuple[force_field_idx]!r} "
            f"in row {row_tuple!r}"
        )


def test_calibration_values_not_in_json_anywhere():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    rm = _make_seven_col_rm_with_steps()

    payload = rm.to_json()
    serialized = json.dumps(payload)

    assert "liquid_capacitance_over_area" not in serialized, (
        "Calibration must not be persisted on the protocol tree — diverges "
        "deliberately from legacy protocol_state.py:169-170."
    )
    assert "filler_capacitance_over_area" not in serialized


def test_force_round_trip_recomputes_from_voltage_and_cache():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    rm = _make_seven_col_rm_with_steps()

    payload = rm.to_json()
    parsed = json.loads(json.dumps(payload))

    rm2 = RowManager.from_json(parsed, columns=_build_seven_columns())
    steps = rm2.root.children
    assert [s.voltage for s in steps] == [80, 100, 120]

    force_col = next(c for c in rm2.columns if c.model.col_id == "force")
    c_per_a = cache.capacitance_per_unit_area()
    for step in steps:
        expected = force_for_step(float(step.voltage), c_per_a)
        actual = force_col.model.get_value(step)
        assert actual == expected, (
            f"Recomputed force mismatch for V={step.voltage}: "
            f"expected {expected!r}, got {actual!r}"
        )


def test_force_recomputes_when_cache_set_after_load():
    cache.trait_set(
        liquid_capacitance_over_area=2.0,
        filler_capacitance_over_area=0.5,
    )
    rm = _make_seven_col_rm_with_steps()
    payload = rm.to_json()
    parsed = json.loads(json.dumps(payload))

    cache.trait_set(
        liquid_capacitance_over_area=0.0,
        filler_capacitance_over_area=0.0,
    )

    rm2 = RowManager.from_json(parsed, columns=_build_seven_columns())
    force_col = next(c for c in rm2.columns if c.model.col_id == "force")

    first_step = rm2.root.children[0]
    assert force_col.model.get_value(first_step) is None

    cache.trait_set(
        liquid_capacitance_over_area=3.0,
        filler_capacitance_over_area=1.0,
    )

    expected = force_for_step(float(first_step.voltage),
                              cache.capacitance_per_unit_area())
    assert force_col.model.get_value(first_step) == expected
    assert expected is not None


# ---------------------------------------------------------------------------
# PPT-8 — check_droplets Bool column persistence (added in Task 3)
# ---------------------------------------------------------------------------

def _build_eight_columns():
    """7-column set from PPT-7 + check_droplets."""
    from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
        make_droplet_check_column,
    )
    with patch(
        "dropbot_protocol_controls.protocol_columns.voltage_column.DropbotPreferences"
    ) as MockV, patch(
        "dropbot_protocol_controls.protocol_columns.frequency_column.DropbotPreferences"
    ) as MockF:
        MockV.return_value.last_voltage = 100
        MockF.return_value.last_frequency = 10000
        return [
            make_type_column(), make_id_column(), make_name_column(),
            make_duration_column(),
            make_voltage_column(), make_frequency_column(),
            make_force_column(),
            make_droplet_check_column(),
        ]


def test_check_droplets_per_row_round_trip_through_json():
    cols = _build_eight_columns()
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "S1", "check_droplets": True})
    rm.add_step(values={"name": "S2", "check_droplets": False})
    rm.add_step(values={"name": "S3"})  # default → True

    payload = rm.to_json()
    parsed = json.loads(json.dumps(payload))

    rm2 = RowManager.from_json(parsed, columns=_build_eight_columns())
    steps = rm2.root.children
    assert [s.check_droplets for s in steps] == [True, False, True]
    assert all(isinstance(s.check_droplets, bool) for s in steps)


def test_check_droplets_column_metadata_in_json_payload():
    rm = RowManager(columns=_build_eight_columns())
    rm.add_step(values={"name": "S1"})
    payload = rm.to_json()

    entries = [c for c in payload["columns"] if c["id"] == "check_droplets"]
    assert len(entries) == 1
    assert entries[0]["cls"] == (
        "dropbot_protocol_controls.protocol_columns.droplet_check_column.DropletCheckColumnModel"
    )


def test_legacy_load_without_check_droplets_field_defaults_to_true():
    # Build a JSON payload as if check_droplets had never existed (i.e.
    # a protocol saved before PPT-8). After load, all rows should have
    # check_droplets=True (the column default).
    cols_no_check = [c for c in _build_eight_columns()
                     if c.model.col_id != "check_droplets"]
    rm = RowManager(columns=cols_no_check)
    rm.add_step(values={"name": "S1"})
    rm.add_step(values={"name": "S2"})
    payload = rm.to_json()                # no check_droplets in payload

    rm2 = RowManager.from_json(json.loads(json.dumps(payload)),
                                columns=_build_eight_columns())
    for step in rm2.root.children:
        assert step.check_droplets is True
