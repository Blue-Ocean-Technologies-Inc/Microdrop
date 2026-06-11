"""Tests for the pure protocol-load validator and its presenters."""

from types import SimpleNamespace

from pluggable_protocol_tree.services.protocol_validator import (
    validate_protocol, ValidationReport, Finding,
    SEVERITY_ERROR, SEVERITY_WARNING,
    _row_dotted_ids,
)


def fake_columns(*col_ids):
    """Minimal stand-ins for live IColumn objects: only .model.col_id is read."""
    return [SimpleNamespace(model=SimpleNamespace(col_id=cid)) for cid in col_ids]


def make_data(fields=None, rows=None, columns=None, metadata=None):
    return {
        "schema_version": 1,
        "protocol_metadata": metadata or {},
        "columns": columns or [],
        "fields": fields or ["depth", "uuid", "type", "name"],
        "rows": rows or [],
    }


def test_clean_protocol_is_empty():
    data = make_data(columns=[{"id": "duration_s"}])
    report = validate_protocol(data, fake_columns("duration_s"), {})
    assert report.is_empty
    assert report.errors == []
    assert report.warnings == []


def test_orphan_column_is_error():
    # Saved protocol references a "magnet" column whose plugin isn't loaded.
    data = make_data(columns=[{"id": "duration_s"}, {"id": "magnet"}])
    report = validate_protocol(data, fake_columns("duration_s"), {})
    assert len(report.errors) == 1
    finding = report.errors[0]
    assert finding.severity == SEVERITY_ERROR
    assert finding.category == "orphan_column"
    assert finding.items == ["magnet"]
    assert not report.is_empty


def test_non_list_columns_does_not_raise():
    data = make_data()
    data["columns"] = "corrupted"   # not a list
    report = validate_protocol(data, fake_columns("x"), {})
    assert report.is_empty


def test_non_dict_column_spec_is_skipped():
    data = make_data(columns=[42, {"id": "magnet"}])  # 42 is not a spec dict
    report = validate_protocol(data, fake_columns("duration_s"), {})
    assert [f.category for f in report.errors] == ["orphan_column"]
    assert report.errors[0].items == ["magnet"]


def test_none_columns_arg_treated_as_empty():
    data = make_data(columns=[{"id": "magnet"}])
    report = validate_protocol(data, None, {})  # no live columns
    assert report.errors[0].items == ["magnet"]


def test_multiple_orphans_one_finding():
    data = make_data(columns=[{"id": "a"}, {"id": "b"}, {"id": "duration_s"}])
    report = validate_protocol(data, fake_columns("duration_s"), {})
    assert len(report.errors) == 1
    assert sorted(report.errors[0].items) == ["a", "b"]


def test_dotted_ids_nested():
    # depths [0,1,1,0] -> ["1","1.1","1.2","2"]
    rows = [
        [0, "u0", "group", "G"],
        [1, "u1", "step", "A"],
        [1, "u2", "step", "B"],
        [0, "u3", "step", "C"],
    ]
    assert _row_dotted_ids(rows) == ["1", "1.1", "1.2", "2"]


def test_unknown_electrode_in_electrodes_column():
    fields = ["depth", "uuid", "type", "name", "electrodes"]
    rows = [
        [0, "u0", "step", "A", ["E1", "E99"]],
        [0, "u1", "step", "B", ["E1"]],
    ]
    device_map = {"E1": 1}   # E99 is unknown
    report = validate_protocol(make_data(fields=fields, rows=rows),
                               fake_columns("electrodes"), device_map)
    warns = report.warnings
    assert len(warns) == 1
    assert warns[0].category == "electrode_id"
    assert warns[0].items == ["E99  (steps 1)"]


def test_unknown_electrode_in_routes_column():
    fields = ["depth", "uuid", "type", "name", "routes"]
    rows = [
        [0, "u0", "step", "A", [["E1", "E2"], ["E2", "EX"]]],
    ]
    device_map = {"E1": 1, "E2": 2}   # EX unknown
    report = validate_protocol(make_data(fields=fields, rows=rows),
                               fake_columns("routes"), device_map)
    assert [f.category for f in report.warnings] == ["electrode_id"]
    assert report.warnings[0].items == ["EX  (steps 1)"]


def test_known_electrodes_no_findings():
    fields = ["depth", "uuid", "type", "name", "electrodes"]
    rows = [[0, "u0", "step", "A", ["E1", "E2"]]]
    device_map = {"E1": 1, "E2": 2}
    report = validate_protocol(make_data(fields=fields, rows=rows),
                               fake_columns("electrodes"), device_map)
    assert report.is_empty
