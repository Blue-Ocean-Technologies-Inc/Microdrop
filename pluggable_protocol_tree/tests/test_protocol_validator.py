"""Tests for the pure protocol-load validator and its presenters."""

from types import SimpleNamespace

from pluggable_protocol_tree.services.protocol_validator import (
    validate_protocol, ValidationReport, Finding,
    SEVERITY_ERROR, SEVERITY_WARNING,
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
