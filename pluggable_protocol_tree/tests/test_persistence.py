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
    # After the dedup fix the builtin type/name columns are filtered out of
    # col_specs (they are already encoded in the fixed row-metadata fields).
    # Only the non-reserved ordinary columns remain.
    data = manager.to_json()
    ids = [c["id"] for c in data["columns"]]
    assert ids == ["id", "duration_s"]
    for c in data["columns"]:
        assert "cls" in c


def test_to_json_fields_order(manager):
    # After the dedup fix the builtin type/name columns are filtered out of
    # col_specs, so "type" and "name" each appear exactly once (in the fixed
    # row-metadata prefix).  The "id" and "duration_s" ordinary columns remain.
    data = manager.to_json()
    assert data["fields"] == ["depth", "uuid", "type", "name",
                              "id", "duration_s"]


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


# --- repeat_duration_controls round-trip via row_flags (route-reps split) ---

def test_row_flags_serialized_only_for_true_rows(manager):
    p = manager.add_step(values={"name": "A"})
    row = manager.get_row(p)
    row.repeat_duration_controls = True
    manager.add_step(values={"name": "B"})  # stays False
    data = manager.to_json()
    flags = data["row_flags"]
    assert row.uuid in flags
    assert flags[row.uuid]["repeat_duration_controls"] is True
    # The False row is omitted to keep saves compact.
    assert len(flags) == 1


def test_row_flags_round_trip(manager):
    p = manager.add_step(values={"name": "A"})
    manager.get_row(p).repeat_duration_controls = True
    data = manager.to_json()
    new_mgr = RowManager.from_json(data, columns=list(manager.columns))
    assert new_mgr.root.children[0].repeat_duration_controls is True


def test_row_flags_round_trip_nested_step(manager):
    g = manager.add_group(name="G")
    p = manager.add_step(parent_path=g, values={"name": "Inner"})
    manager.get_row(p).repeat_duration_controls = True
    data = manager.to_json()
    new_mgr = RowManager.from_json(data, columns=list(manager.columns))
    assert new_mgr.root.children[0].children[0].repeat_duration_controls is True


def test_load_old_payload_without_row_flags_defaults_false(manager):
    manager.add_step(values={"name": "A"})
    data = manager.to_json()
    del data["row_flags"]            # simulate a pre-split save
    new_mgr = RowManager.from_json(data, columns=list(manager.columns))
    assert new_mgr.root.children[0].repeat_duration_controls is False


def test_column_locks_are_never_serialized(manager):
    """Locks are runtime-derived; persisting one would strand a
    protocol opened without the owning plugin (issue #541)."""
    import json
    p = manager.add_step(values={"name": "A"})
    row = manager.get_row(p)
    row.lock_column("route_repetitions", owner="repeat_duration",
                     reason="Route Reps Dur is in control")
    data = manager.to_json()
    assert "column_locks" not in json.dumps(data)


def test_loading_row_flags_rebuilds_route_reps_lock(manager):
    """persistence writes repeat_duration_controls directly onto the
    row; the BaseRow observer must rebuild the lock from it."""
    p = manager.add_step(values={"name": "A"})
    manager.get_row(p).repeat_duration_controls = True
    data = manager.to_json()
    new_mgr = RowManager.from_json(data, columns=list(manager.columns))
    loaded_step = new_mgr.root.children[0]
    assert loaded_step.repeat_duration_controls is True
    assert loaded_step.is_column_locked("route_repetitions") is True


# --- Issue-1 dedup fix ---

def test_serialize_no_duplicate_type_or_name_in_fields():
    """The builtin type/name columns must NOT be serialized in
    addition to the fixed row metadata — fields are unique."""
    cols = [make_type_column(), make_id_column(), make_name_column()]
    m = RowManager(columns=cols)
    m.add_step()
    m.add_group(name="G")
    data = m.to_json()
    assert data["fields"].count("type") == 1
    assert data["fields"].count("name") == 1
    # Per-row width matches fields width — no orphan values.
    for row in data["rows"]:
        assert len(row) == len(data["fields"])


def test_roundtrip_after_dedup_preserves_step_type_and_name():
    """After the dedup fix, save -> load -> save preserves every
    row's type and name."""
    cols = [make_type_column(), make_name_column()]
    m = RowManager(columns=cols)
    m.add_step()
    g = m.add_group(name="MyGroup")
    m.add_step(parent_path=g)

    data = m.to_json()
    m2 = RowManager(columns=cols)
    m2.set_state_from_json(data, columns=cols)

    assert m2.root.children[0].row_type == "step"
    assert m2.root.children[1].row_type == "group"
    assert m2.root.children[1].name == "MyGroup"
    assert m2.root.children[1].children[0].row_type == "step"


def test_load_old_duplicate_fields_payload_still_loads():
    """Backward compat: a pre-fix save that has duplicate 'type'/'name'
    in col_specs still loads without error. The setattr calls for the
    orphan attributes are harmless because the row constructor already
    set name/row_type from the fixed metadata fields."""
    cols = [make_type_column(), make_id_column(), make_name_column(),
            make_duration_column()]
    m = RowManager(columns=cols)
    m.add_step(values={"name": "OldStep", "duration_s": 3.0})
    g = m.add_group(name="OldGroup")
    m.add_step(parent_path=g, values={"name": "Nested"})

    # Simulate the OLD (buggy) format: inject duplicate type/name into
    # col_specs and duplicate values into every row.
    data = m.to_json()
    # Insert fake type/name col_specs at the front (as old saves did)
    data["columns"] = (
        [{"id": "type", "cls": "pluggable_protocol_tree.builtins.type_column.TypeColumnModel"},
         {"id": "name", "cls": "pluggable_protocol_tree.builtins.name_column.NameColumnModel"}]
        + data["columns"]
    )
    # fields = ["depth", "uuid", "type", "name", "type", "name", "id", "duration_s"]
    # Insert the duplicated fields after the fixed prefix.
    data["fields"] = (
        data["fields"][:4]                     # depth, uuid, type, name
        + ["type", "name"]                     # duplicates (old format)
        + data["fields"][4:]                   # remaining ordinary columns
    )
    # Inject duplicate values into each row at the right position.
    new_rows = []
    for row in data["rows"]:
        # row[:4] = depth, uuid, type, name; row[4:] = ordinary col values
        new_row = list(row[:4]) + [row[2], row[3]] + list(row[4:])
        new_rows.append(new_row)
    data["rows"] = new_rows

    # Load with current column set — must not raise.
    nm = RowManager.from_json(data, columns=list(cols))
    assert nm.root.children[0].name == "OldStep"
    assert nm.root.children[0].row_type == "step"
    assert nm.root.children[0].duration_s == 3.0
    assert nm.root.children[1].name == "OldGroup"
    assert nm.root.children[1].row_type == "group"
    assert nm.root.children[1].children[0].name == "Nested"
