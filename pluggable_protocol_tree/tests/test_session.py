"""Unit tests for ProtocolSession's column resolver + round-trip load.

Doesn't require Redis -- exercises only the JSON shape + dynamic-import
path. End-to-end execution with a real broker is covered separately
by the Redis integration tests.
"""

import json
from pathlib import Path

import pytest

from pluggable_protocol_tree.builtins.duration_column import (
    make_duration_column,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import (
    make_linear_repeats_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import (
    make_repeat_duration_column,
)
from pluggable_protocol_tree.builtins.repetitions_column import (
    make_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import (
    make_soft_start_column,
)
from pluggable_protocol_tree.builtins.trail_length_column import (
    make_trail_length_column,
)
from pluggable_protocol_tree.builtins.trail_overlay_column import (
    make_trail_overlay_column,
)
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.session import (
    ColumnResolutionError, ProtocolSession, resolve_columns,
)


def _all_ppt3_columns():
    return [
        make_type_column(), make_id_column(), make_name_column(),
        make_repetitions_column(), make_duration_column(),
        make_electrodes_column(), make_routes_column(),
        make_trail_length_column(), make_trail_overlay_column(),
        make_soft_start_column(), make_soft_end_column(),
        make_repeat_duration_column(), make_linear_repeats_column(),
    ]


def _build_sample_manager():
    rm = RowManager(columns=_all_ppt3_columns())
    rm.protocol_metadata["electrode_to_channel"] = {
        f"e{i:02d}": i for i in range(25)
    }
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.1,
        "electrodes": ["e00", "e01"],
    })
    rm.add_step(values={
        "name": "S2",
        "duration_s": 0.1,
        "routes": [["e02", "e03", "e04"]],
        "trail_length": 1,
    })
    return rm


# --- resolve_columns ---


def test_resolve_columns_round_trips_all_ppt3_builtins():
    """Every column factory in the canonical PPT-3 set must round-trip
    through to_json -> resolve_columns with the same col_ids in the
    same order."""
    rm = _build_sample_manager()
    payload = rm.to_json()
    cols = resolve_columns(payload)
    expected_ids = [c.model.col_id for c in _all_ppt3_columns()]
    assert [c.model.col_id for c in cols] == expected_ids


def test_resolve_columns_unknown_module_raises():
    payload = {"columns": [{
        "id": "ghost",
        "cls": "nonexistent.module.GhostModel",
    }]}
    with pytest.raises(ColumnResolutionError, match="can't import"):
        resolve_columns(payload)


def test_resolve_columns_known_module_unknown_class_raises():
    payload = {"columns": [{
        "id": "ghost",
        "cls": "pluggable_protocol_tree.builtins.routes_column.NoSuchClass",
    }]}
    with pytest.raises(ColumnResolutionError, match="no class"):
        resolve_columns(payload)


def test_resolve_columns_module_with_no_matching_factory_raises(tmp_path):
    """A model class with no make_*_column factory in its module
    should raise (not fall back silently)."""
    # Drop a temporary module on the path that defines a model class
    # but no factory.
    pkg_dir = tmp_path / "_ppt_test_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "stray_column.py").write_text(
        "class StrayModel:\n    col_id = 'stray'\n    col_name = 'stray'\n"
    )
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        payload = {"columns": [{
            "id": "stray",
            "cls": "_ppt_test_pkg.stray_column.StrayModel",
        }]}
        with pytest.raises(ColumnResolutionError, match="no make_.*factory"):
            resolve_columns(payload)
    finally:
        sys.path.remove(str(tmp_path))


def test_resolve_columns_missing_cls_field_raises():
    payload = {"columns": [{"id": "no_cls"}]}
    with pytest.raises(ColumnResolutionError, match="no 'cls' qualname"):
        resolve_columns(payload)


# --- ProtocolSession.from_file ---


def test_from_file_loads_manager_with_resolved_columns(tmp_path: Path):
    rm = _build_sample_manager()
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(rm.to_json()))

    session = ProtocolSession.from_file(str(path), with_demo_hardware=False)
    assert len(session.manager.columns) == len(_all_ppt3_columns())
    assert len(session.manager.root.children) == 2
    assert session.manager.root.children[0].name == "S1"
    assert session.manager.root.children[1].name == "S2"


def test_from_file_restores_protocol_metadata(tmp_path: Path):
    rm = _build_sample_manager()
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(rm.to_json()))

    session = ProtocolSession.from_file(str(path), with_demo_hardware=False)
    mapping = session.manager.protocol_metadata["electrode_to_channel"]
    assert mapping["e00"] == 0
    assert mapping["e24"] == 24


def test_from_file_with_explicit_columns_skips_resolver(tmp_path: Path):
    """When columns= is passed explicitly, the resolver is not called
    (so a payload with garbage cls qualnames still loads)."""
    rm = _build_sample_manager()
    payload = rm.to_json()
    # Stomp the recorded class name -- resolver would now fail.
    for entry in payload["columns"]:
        entry["cls"] = "definitely.not.a.module.Class"
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload))

    session = ProtocolSession.from_file(
        str(path), columns=_all_ppt3_columns(), with_demo_hardware=False,
    )
    assert len(session.manager.root.children) == 2


def test_session_context_manager_closes_cleanly():
    """A session built without a worker should exit the context
    manager without raising."""
    rm = _build_sample_manager()
    from pluggable_protocol_tree.execution.executor import ProtocolExecutor
    executor = ProtocolExecutor(row_manager=rm)
    with ProtocolSession(rm, executor) as session:
        assert session.manager is rm
    # close() is idempotent.
    session.close()
