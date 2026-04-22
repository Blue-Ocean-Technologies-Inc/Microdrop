"""Tests for persistence (save/load)."""

import pytest

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
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
