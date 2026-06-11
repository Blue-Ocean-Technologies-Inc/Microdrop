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


def test_stale_channel_mapping_flagged():
    fields = ["depth", "uuid", "type", "name", "electrodes"]
    rows = [[0, "u0", "step", "A", ["E1"]]]
    metadata = {"electrode_to_channel": {"E1": 5}}   # protocol thinks E1 -> ch 5
    device_map = {"E1": 7}                           # device now maps E1 -> ch 7
    report = validate_protocol(make_data(fields=fields, rows=rows, metadata=metadata),
                               fake_columns("electrodes"), device_map)
    stale = [f for f in report.warnings if f.category == "stale_channel"]
    assert len(stale) == 1
    assert stale[0].items == ["E1: protocol ch 5 -> device ch 7"]


def test_matching_channel_not_flagged():
    fields = ["depth", "uuid", "type", "name", "electrodes"]
    rows = [[0, "u0", "step", "A", ["E1"]]]
    metadata = {"electrode_to_channel": {"E1": 7}}
    device_map = {"E1": 7}
    report = validate_protocol(make_data(fields=fields, rows=rows, metadata=metadata),
                               fake_columns("electrodes"), device_map)
    assert report.is_empty


def test_no_device_map_skips_device_checks_but_reports_orphan():
    fields = ["depth", "uuid", "type", "name", "electrodes"]
    rows = [[0, "u0", "step", "A", ["E_DOES_NOT_EXIST"]]]
    data = make_data(fields=fields, rows=rows,
                     columns=[{"id": "electrodes"}, {"id": "ghost"}],
                     metadata={"electrode_to_channel": {"E1": 1}})
    report = validate_protocol(data, fake_columns("electrodes"), {})  # no device
    # device checks skipped -> only the orphan-column error remains
    assert [f.category for f in report.findings] == ["orphan_column"]


def test_malformed_data_no_exception():
    assert validate_protocol(None, fake_columns("x"), {"E1": 1}).is_empty
    assert validate_protocol({}, fake_columns("x"), {"E1": 1}).is_empty
    # rows missing value slots / wrong types must not raise
    bad = {"columns": [{"id": "electrodes"}], "fields": ["depth", "uuid", "type", "name", "electrodes"],
           "rows": [[0, "u", "step", "A"], [0, "u2", "step", "B", "notalist"]]}
    report = validate_protocol(bad, fake_columns("electrodes"), {"E1": 1})
    assert isinstance(report, ValidationReport)


import logging

from pluggable_protocol_tree.services import protocol_validator as pv
from pluggable_protocol_tree.services.protocol_validator import (
    log_report, confirm_report, PROCEED, CANCEL,
)


def _report_with_error_and_warning():
    return ValidationReport(findings=[
        Finding(severity=SEVERITY_ERROR, category="orphan_column",
                title="1 orphan column", items=["magnet"]),
        Finding(severity=SEVERITY_WARNING, category="electrode_id",
                title="1 unknown electrode", items=["E99  (steps 1)"]),
    ])


def test_log_report_levels(caplog):
    with caplog.at_level(logging.WARNING):
        log_report(_report_with_error_and_warning())
    levels = {r.levelno for r in caplog.records}
    assert logging.ERROR in levels      # orphan finding logged at ERROR
    assert logging.WARNING in levels    # electrode finding logged at WARNING
    text = caplog.text
    assert "magnet" in text and "E99" in text


def test_confirm_report_proceed(monkeypatch):
    captured = {}

    def fake_confirm(parent=None, message="", title="", **kwargs):
        captured.update(title=title, kwargs=kwargs)
        return pv.YES   # user clicked the proceed button

    monkeypatch.setattr(pv, "confirm", fake_confirm, raising=False)
    decision = confirm_report(_report_with_error_and_warning(), parent=None)
    assert decision == PROCEED
    # errors present -> the override-labelled proceed button + error title
    assert captured["title"] == "Protocol has errors"
    assert captured["kwargs"]["yes_label"] == "Load anyway (drop columns)"
    assert captured["kwargs"]["no_label"] == ""
    assert captured["kwargs"]["cancel"] is True


def test_confirm_report_cancel(monkeypatch):
    monkeypatch.setattr(pv, "confirm", lambda *a, **k: pv.CANCEL, raising=False)
    report = ValidationReport(findings=[
        Finding(severity=SEVERITY_WARNING, category="electrode_id",
                title="1 unknown electrode", items=["E99  (steps 1)"]),
    ])
    assert confirm_report(report, parent=None) == CANCEL


import logging as _logging

from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.duration_column import make_duration_column


def _basic_columns():
    return [make_type_column(), make_name_column(), make_duration_column()]


def test_set_state_from_json_logs_orphan_and_still_loads(caplog):
    mgr = RowManager(columns=_basic_columns())
    # A save that references a "magnet" column we don't have loaded.
    data = {
        "schema_version": 1,
        "protocol_metadata": {},
        "columns": [
            {"id": "duration_s",
             "cls": "pluggable_protocol_tree.builtins.duration_column.DurationColumnModel"},
            {"id": "magnet", "cls": "x.Y"},
        ],
        "fields": ["depth", "uuid", "type", "name", "duration_s", "magnet"],
        "rows": [[0, "u0", "step", "A", 2.0, "ignored"]],
    }
    with caplog.at_level(_logging.ERROR):
        mgr.set_state_from_json(data, columns=_basic_columns())
    assert "magnet" in caplog.text                 # orphan finding printed
    assert len(mgr.root.children) == 1             # load still happened


def test_report_findings_false_suppresses_logging(caplog):
    mgr = RowManager(columns=_basic_columns())
    data = {
        "schema_version": 1, "protocol_metadata": {},
        "columns": [{"id": "magnet", "cls": "x.Y"}],
        "fields": ["depth", "uuid", "type", "name", "magnet"],
        "rows": [[0, "u0", "step", "A", "ignored"]],
    }
    with caplog.at_level(_logging.WARNING):
        mgr.set_state_from_json(data, columns=_basic_columns(), report_findings=False)
    # The validator's log_report prefix must be absent — persistence.py may
    # still log its own column-import warning, but the validator findings
    # ("Protocol load: ...") are suppressed when report_findings=False.
    assert "Protocol load:" not in caplog.text
