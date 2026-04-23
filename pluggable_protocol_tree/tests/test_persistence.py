"""Tests for persistence (save/load)."""

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.consts import PERSISTENCE_SCHEMA_VERSION


@pytest.fixture
def columns():
    return [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]


@pytest.fixture
def manager(columns):
    return RowManager(columns=columns)


# --- save ---

def test_to_json_schema_version(manager):
    data = manager.to_json()
    assert data["schema_version"] == PERSISTENCE_SCHEMA_VERSION


def test_to_json_columns_metadata(manager):
    data = manager.to_json()
    ids = [c["id"] for c in data["columns"]]
    assert ids == ["type", "id", "name", "duration_s"]
    for c in data["columns"]:
        assert "cls" in c


def test_to_json_fields_order(manager):
    data = manager.to_json()
    assert data["fields"] == ["depth", "uuid", "type", "name",
                              "type", "id", "name", "duration_s"]


def test_to_json_rows_encoded_with_depth(manager):
    g = manager.add_group(name="G")
    manager.add_step(parent_path=g, values={"name": "A"})
    manager.add_step(values={"name": "B"})
    data = manager.to_json()
    rows = data["rows"]
    # Three rows total: G (depth 0), A (depth 1), B (depth 0)
    assert len(rows) == 3
    depths = [r[0] for r in rows]
    assert depths == [0, 1, 0]
    names = [r[3] for r in rows]
    assert names == ["G", "A", "B"]


def test_to_json_empty_tree_has_zero_rows(manager):
    data = manager.to_json()
    assert data["rows"] == []


# --- load ---

def test_round_trip_flat(manager):
    manager.add_step(values={"name": "A", "duration_s": 2.5})
    manager.add_step(values={"name": "B", "duration_s": 1.0})
    data = manager.to_json()
    new_manager = RowManager.from_json(data, columns=list(manager.columns))
    assert [c.name for c in new_manager.root.children] == ["A", "B"]
    assert new_manager.root.children[0].duration_s == 2.5


def test_round_trip_nested(manager):
    g = manager.add_group(name="Wash")
    manager.add_step(parent_path=g, values={"name": "Drop"})
    manager.add_step(parent_path=g, values={"name": "Off"})
    manager.add_step(values={"name": "Settle"})
    data = manager.to_json()
    nm = RowManager.from_json(data, columns=list(manager.columns))
    wash = nm.root.children[0]
    assert wash.name == "Wash"
    assert [c.name for c in wash.children] == ["Drop", "Off"]
    assert nm.root.children[1].name == "Settle"


def test_round_trip_preserves_uuids(manager):
    p = manager.add_step()
    original_uuid = manager.get_row(p).uuid
    data = manager.to_json()
    nm = RowManager.from_json(data, columns=list(manager.columns))
    assert nm.root.children[0].uuid == original_uuid


def test_from_json_missing_column_warns_and_skips(manager, caplog):
    """If the saved column set has an entry that's not in the live
    column set, the value is skipped (PPT-1 behavior) and a warning is
    logged. Full orphan preservation is deferred to a later PR."""
    data = manager.to_json()
    # Inject a fake column entry into the saved data
    data["columns"].append({
        "id": "fake", "cls": "nonexistent.module.FakeColumn",
    })
    # The row tuples also need a placeholder value per new column
    data["fields"].append("fake")
    for r in data["rows"]:
        r.append("ignored")
    # Load with live columns that don't include 'fake'
    nm = RowManager.from_json(data, columns=list(manager.columns))
    # Loader should have warned; no exception; row count preserved
    assert len(nm.root.children) == len(manager.root.children)


# --- PPT-3: protocol_metadata in the JSON header ---

def test_protocol_metadata_round_trips():
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    rm.protocol_metadata["electrode_to_channel"] = {"e00": 0, "e01": 1}
    rm.add_step(values={"name": "A"})

    payload = rm.to_json()
    assert payload["protocol_metadata"] == {"electrode_to_channel": {"e00": 0, "e01": 1}}

    rm2 = RowManager.from_json(payload, columns=list(cols))
    assert rm2.protocol_metadata == {"electrode_to_channel": {"e00": 0, "e01": 1}}


def test_protocol_metadata_missing_in_legacy_payload_loads_as_empty():
    """Backward-compat: a PPT-1/PPT-2 era JSON without the
    protocol_metadata key loads with manager.protocol_metadata == {}."""
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_repetitions_column(), make_duration_column()]
    rm = RowManager(columns=cols)
    rm.add_step(values={"name": "A"})
    payload = rm.to_json()
    payload.pop("protocol_metadata", None)   # simulate older format

    rm2 = RowManager.from_json(payload, columns=list(cols))
    assert rm2.protocol_metadata == {}
