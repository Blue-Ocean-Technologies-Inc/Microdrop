# Protocol-load Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate a loaded protocol against the current device at load time, surfacing electrode-ID, stale-channel, and orphan-column problems as a GUI dialog (File > Open) or printed logger output (headless load).

**Architecture:** A pure, side-effect-free `validate_protocol(data, columns, device_map) -> ValidationReport` reads the raw serialized JSON. Two interchangeable presenters render the same report: `confirm_report` (a two-tier `pyface_wrapper` dialog that can abort the load) and `log_report` (logger output that never blocks). Headless `RowManager.from_json` / `set_state_from_json` call the validator + `log_report`; the GUI `load_from_dialog` runs the validator + `confirm_report` and only mutates on Proceed.

**Tech Stack:** Python, Traits (`RowManager`), PySide6/Pyface dialogs (`microdrop_application.dialogs.pyface_wrapper`), pytest. Run tests with:
`pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest`

---

## File structure

- **Create** `pluggable_protocol_tree/services/protocol_validator.py` — `Finding`, `ValidationReport`, `validate_protocol`, helpers (`_row_dotted_ids`, `_value_index`, `_electrodes_in_row`), and the two presenters (`log_report`, `confirm_report`) + `_format_html` / `_format_detail`. Constants: `PROCEED`, `CANCEL`, `SEVERITY_WARNING`, `SEVERITY_ERROR`, `ROUTES_COL_ID`, `ELECTRODES_COL_ID`.
- **Create** `pluggable_protocol_tree/tests/test_protocol_validator.py` — unit tests for the validator + presenters.
- **Modify** `pluggable_protocol_tree/models/row_manager.py` — add `device_electrode_to_channel=None, report_findings=True` to `from_json` and `set_state_from_json`; validate + `log_report` before applying state.
- **Modify** `pluggable_protocol_tree/views/protocol_tree_pane.py` — `load_from_dialog` runs `validate_protocol` + `confirm_report`, aborts on Cancel, calls `set_state_from_json(..., report_findings=False)` on Proceed.

The validator's serialized-JSON contract (from `services/persistence.py`):
`data["fields"] == ["depth","uuid","type","name", *col_ids]`; each `data["rows"]` entry is `[depth, uuid, type, name, *values]`; the `routes` value is `list[list[str]]`, the `electrodes` value is `list[str]`; `data["columns"]` is a list of `{"id": col_id, ...}`; `data["protocol_metadata"]["electrode_to_channel"]` is `{electrode_id: channel_int}`.

---

## Task 1: Validator data types + orphan-column check

**Files:**
- Create: `pluggable_protocol_tree/services/protocol_validator.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# pluggable_protocol_tree/tests/test_protocol_validator.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pluggable_protocol_tree.services.protocol_validator'`

- [ ] **Step 3: Write minimal implementation**

```python
# pluggable_protocol_tree/services/protocol_validator.py
"""Pure protocol-load validation + presenters (issue #423, PPT-17).

``validate_protocol`` reads the raw serialized protocol JSON (output of
``services.persistence.serialize_tree``) and returns a structured
``ValidationReport``. It performs three checks:

  * orphan column   (error)   - a saved col_id has no live column; its
                                 values are silently dropped by
                                 ``deserialize_tree``.
  * electrode id    (warning) - an electrode referenced by a step's
                                 routes/electrodes doesn't exist on the
                                 current device.
  * stale channel   (warning) - the protocol's stored electrode->channel
                                 disagrees with the device's current map.

The function is side-effect free (no Qt, no RowManager, no I/O) so it is
trivially unit-testable. Two presenters render a report: ``log_report``
(headless, logger output) and ``confirm_report`` (GUI dialog).
"""

from dataclasses import dataclass, field
from typing import List

from logger.logger_service import get_logger

logger = get_logger(__name__)

# Presenter decisions.
PROCEED = "proceed"
CANCEL = "cancel"

SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

# Builtin column ids whose values carry electrode references.
ROUTES_COL_ID = "routes"
ELECTRODES_COL_ID = "electrodes"


@dataclass
class Finding:
    severity: str          # SEVERITY_WARNING | SEVERITY_ERROR
    category: str          # "orphan_column" | "electrode_id" | "stale_channel"
    title: str             # short human summary
    items: List[str] = field(default_factory=list)  # detail lines


@dataclass
class ValidationReport:
    findings: List[Finding] = field(default_factory=list)

    @property
    def errors(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    @property
    def is_empty(self) -> bool:
        return not self.findings


def validate_protocol(data, columns, device_electrode_to_channel) -> ValidationReport:
    """Validate raw serialized protocol ``data`` against the live ``columns``
    and the device's ``device_electrode_to_channel`` map. Never raises on
    malformed input - returns an empty/partial report instead."""
    findings: List[Finding] = []
    if not isinstance(data, dict):
        return ValidationReport(findings=findings)

    col_specs = data.get("columns") or []

    # --- orphan columns (device-independent) ---
    live_ids = {c.model.col_id for c in (columns or [])}
    orphan_ids = [
        spec.get("id") for spec in col_specs
        if isinstance(spec, dict) and spec.get("id") and spec.get("id") not in live_ids
    ]
    if orphan_ids:
        findings.append(Finding(
            severity=SEVERITY_ERROR,
            category="orphan_column",
            title=(f"{len(orphan_ids)} column(s) in this protocol have no "
                   f"matching plugin; their values will be dropped on load"),
            items=[str(cid) for cid in orphan_ids],
        ))

    return ValidationReport(findings=findings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/protocol_validator.py pluggable_protocol_tree/tests/test_protocol_validator.py
git commit -m "[PPT-17] Pure validator: ValidationReport + orphan-column check"
```

---

## Task 2: Step dotted-id reconstruction + electrode-ID validity check

**Files:**
- Modify: `pluggable_protocol_tree/services/protocol_validator.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# append to test_protocol_validator.py
from pluggable_protocol_tree.services.protocol_validator import _row_dotted_ids


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: FAIL (`ImportError: cannot import name '_row_dotted_ids'` and electrode-validity assertions)

- [ ] **Step 3: Write minimal implementation**

Add the helpers above `validate_protocol`, and the electrode-validity block inside it (after the orphan block, before `return`):

```python
def _row_dotted_ids(rows):
    """1-indexed dotted ids (e.g. '1.2') for each row, derived from the
    ``depth`` sequence. Matches the dotted-id convention used by
    device_viewer_sync._publish_for_row."""
    stack = []  # stack[d] = running sibling count at depth d under current parent
    out = []
    for row in rows:
        depth = int(row[0])
        if len(stack) < depth + 1:
            stack.extend([0] * (depth + 1 - len(stack)))
        else:
            del stack[depth + 1:]   # leaving a deeper level resets its counters
        stack[depth] += 1
        out.append(".".join(str(stack[i]) for i in range(depth + 1)))
    return out


def _value_index(fields, col_id):
    """Index into a row's value slice (row[4:]) for ``col_id``, or None.
    The first four fields are fixed row metadata (depth/uuid/type/name)."""
    try:
        field_pos = fields.index(col_id)
    except ValueError:
        return None
    return field_pos - 4 if field_pos >= 4 else None


def _electrodes_in_row(values, routes_idx, electrodes_idx):
    """All electrode IDs referenced by one row's electrodes + routes values."""
    out = set()
    if electrodes_idx is not None and electrodes_idx < len(values):
        val = values[electrodes_idx]
        if isinstance(val, list):
            out.update(str(e) for e in val)
    if routes_idx is not None and routes_idx < len(values):
        val = values[routes_idx]
        if isinstance(val, list):
            for route in val:
                if isinstance(route, list):
                    out.update(str(e) for e in route)
    return out
```

Insert this block in `validate_protocol` just before `return`:

```python
    device_map = device_electrode_to_channel or {}
    if device_map:
        fields = data.get("fields") or []
        rows = data.get("rows") or []
        dotted = _row_dotted_ids(rows)
        routes_idx = _value_index(fields, ROUTES_COL_ID)
        electrodes_idx = _value_index(fields, ELECTRODES_COL_ID)

        refs = {}   # electrode_id -> set of step dotted-ids
        for i, row in enumerate(rows):
            values = list(row[4:])
            step_id = dotted[i] if i < len(dotted) else str(i + 1)
            for eid in _electrodes_in_row(values, routes_idx, electrodes_idx):
                refs.setdefault(eid, set()).add(step_id)

        unknown = sorted(eid for eid in refs if eid not in device_map)
        if unknown:
            items = [f"{eid}  (steps {', '.join(sorted(refs[eid]))})"
                     for eid in unknown]
            findings.append(Finding(
                severity=SEVERITY_WARNING,
                category="electrode_id",
                title=(f"{len(unknown)} electrode(s) referenced by this protocol "
                       f"do not exist on the current device"),
                items=items,
            ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: PASS (all Task 1 + Task 2 tests)

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/protocol_validator.py pluggable_protocol_tree/tests/test_protocol_validator.py
git commit -m "[PPT-17] Validator: electrode-ID validity check + dotted step ids"
```

---

## Task 3: Stale-channel-mapping check + no-device / malformed-input behavior

**Files:**
- Modify: `pluggable_protocol_tree/services/protocol_validator.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# append to test_protocol_validator.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: FAIL on `test_stale_channel_mapping_flagged` (no stale findings produced)

- [ ] **Step 3: Write minimal implementation**

Inside the `if device_map:` block in `validate_protocol`, after the electrode-validity `if unknown:` block, add:

```python
        proto_map = (data.get("protocol_metadata") or {}).get("electrode_to_channel") or {}
        stale = [
            f"{eid}: protocol ch {proto_ch} -> device ch {device_map[eid]}"
            for eid, proto_ch in sorted(proto_map.items())
            if eid in device_map and device_map[eid] != proto_ch
        ]
        if stale:
            findings.append(Finding(
                severity=SEVERITY_WARNING,
                category="stale_channel",
                title=(f"{len(stale)} electrode(s) map to a different channel on "
                       f"the current device than the protocol expects"),
                items=stale,
            ))
```

(The no-device skip and malformed-input safety are already covered by the
`if not isinstance(data, dict)` guard, the `if device_map:` gate, and the
`isinstance(val, list)` checks in `_electrodes_in_row`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: PASS (all validator tests)

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/protocol_validator.py pluggable_protocol_tree/tests/test_protocol_validator.py
git commit -m "[PPT-17] Validator: stale channel-mapping check"
```

---

## Task 4: Presenters — `log_report` and `confirm_report`

**Files:**
- Modify: `pluggable_protocol_tree/services/protocol_validator.py`
- Test: `pluggable_protocol_tree/tests/test_protocol_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# append to test_protocol_validator.py
import logging

from pluggable_protocol_tree.services import protocol_validator as pv
from pluggable_protocol_tree.services.protocol_validator import (
    log_report, confirm_report, PROCEED, CANCEL,
)


def _report_with_error_and_warning():
    return ValidationReport(findings=[
        Finding(SEVERITY_ERROR, "orphan_column", "1 orphan column", ["magnet"]),
        Finding(SEVERITY_WARNING, "electrode_id", "1 unknown electrode", ["E99  (steps 1)"]),
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
        Finding(SEVERITY_WARNING, "electrode_id", "1 unknown electrode", ["E99  (steps 1)"]),
    ])
    assert confirm_report(report, parent=None) == CANCEL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: FAIL (`ImportError: cannot import name 'log_report'`)

- [ ] **Step 3: Write minimal implementation**

Append to `protocol_validator.py`. Import the dialog primitives at module top
so tests can monkeypatch `pv.confirm` / read `pv.YES`:

```python
# add near the top imports
from microdrop_application.dialogs.pyface_wrapper import confirm, YES
```

```python
# append at end of protocol_validator.py
def log_report(report) -> None:
    """Headless presenter: emit each finding via the module logger. Errors at
    ERROR level, warnings at WARNING level. Never blocks."""
    for f in report.errors:
        logger.error("Protocol load: %s", f.title)
        for item in f.items:
            logger.error("    - %s", item)
    for f in report.warnings:
        logger.warning("Protocol load: %s", f.title)
        for item in f.items:
            logger.warning("    - %s", item)


def _format_html(report) -> str:
    parts = []
    if report.errors:
        parts.append("<b>Errors</b><br>")
        parts.extend(f"&bull; {f.title}<br>" for f in report.errors)
    if report.warnings:
        parts.append("<b>Warnings</b><br>")
        parts.extend(f"&bull; {f.title}<br>" for f in report.warnings)
    return "".join(parts)


def _format_detail(report) -> str:
    lines = []
    for f in report.errors + report.warnings:
        lines.append(f"[{f.severity.upper()}] {f.title}")
        lines.extend(f"    - {item}" for item in f.items)
        lines.append("")
    return "\n".join(lines).rstrip()


def confirm_report(report, parent=None) -> str:
    """GUI presenter: one two-tier summary dialog. Returns PROCEED or CANCEL.

    Uses exactly two buttons - a proceed button (yes_label) and Cancel - by
    passing no_label="" to suppress confirm()'s default No button. When errors
    are present the proceed button is the explicit drop-columns override."""
    if report.errors:
        title = "Protocol has errors"
        proceed_label = "Load anyway (drop columns)"
    else:
        title = "Protocol warnings"
        proceed_label = "Proceed anyway"
    result = confirm(
        parent,
        message="",
        title=title,
        cancel=True,
        yes_label=proceed_label,
        no_label="",
        cancel_label="Cancel",
        informative=_format_html(report),
        detail=_format_detail(report),
    )
    return PROCEED if result == YES else CANCEL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: PASS (all validator + presenter tests)

- [ ] **Step 5: Commit**

```bash
git add pluggable_protocol_tree/services/protocol_validator.py pluggable_protocol_tree/tests/test_protocol_validator.py
git commit -m "[PPT-17] Presenters: log_report (headless) + confirm_report (dialog)"
```

---

## Task 5: Headless wiring — `RowManager.from_json` / `set_state_from_json`

**Files:**
- Modify: `pluggable_protocol_tree/models/row_manager.py:508-544`
- Test: `pluggable_protocol_tree/tests/test_protocol_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# append to test_protocol_validator.py
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
        "columns": [{"id": "duration_s"}, {"id": "magnet", "cls": "x.Y"}],
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
    assert "magnet" not in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -k "set_state_from_json or report_findings_false" -v`
Expected: FAIL (`TypeError: set_state_from_json() got an unexpected keyword argument 'report_findings'`)

- [ ] **Step 3: Write minimal implementation**

In `row_manager.py`, replace `from_json` (lines 508-519) and
`set_state_from_json` (lines 521-544) with the versions below. Only the
signatures and the new validate/log block are added; the existing body is
unchanged.

```python
    @classmethod
    def from_json(cls, data: dict, columns: list,
                  device_electrode_to_channel=None,
                  report_findings: bool = True) -> "RowManager":
        """Reconstruct a RowManager from a serialized payload.

        When ``report_findings`` is True (headless default) the payload is
        validated against ``columns`` + ``device_electrode_to_channel`` and any
        findings are printed via the module logger before loading. The load
        proceeds regardless - headless cannot prompt."""
        from pluggable_protocol_tree.services.persistence import deserialize_tree
        from pluggable_protocol_tree.services.protocol_validator import (
            validate_protocol, log_report,
        )
        if report_findings:
            report = validate_protocol(data, columns, device_electrode_to_channel)
            if not report.is_empty:
                log_report(report)
        manager = cls(columns=list(columns))
        root, metadata = deserialize_tree(
            data, columns,
            step_type=manager.step_type, group_type=manager.group_type,
        )
        manager.root = root
        manager.protocol_metadata = metadata
        return manager

    def set_state_from_json(self, data: dict, columns: list,
                            device_electrode_to_channel=None,
                            report_findings: bool = True) -> None:
        """Reconstruct tree state in-place from a serialized payload dynamically.

        When ``report_findings`` is True (headless default) findings are
        validated and printed via the module logger before applying state. The
        GUI load path passes ``report_findings=False`` because it has already
        shown them in a dialog."""
        from pluggable_protocol_tree.services.persistence import deserialize_tree
        from pluggable_protocol_tree.services.protocol_validator import (
            validate_protocol, log_report,
        )

        if report_findings:
            report = validate_protocol(data, columns, device_electrode_to_channel)
            if not report.is_empty:
                log_report(report)

        # 1. Update columns. This triggers _on_columns_change via Traits,
        #    which automatically rebuilds self.step_type and self.group_type.
        self.columns = list(columns)

        # 2. Deserialize the payload into a new root and metadata dict
        root, metadata = deserialize_tree(
            data, self.columns,
            step_type=self.step_type,
            group_type=self.group_type,
        )

        # 3. Apply the new state
        self.root = root
        self.protocol_metadata = metadata

        # 4. Clear any dangling selection paths, as the old tree structure is gone
        self.selection = []

        # 5. Notify the UI/observers that the structure has completely changed
        self.rows_changed = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_validator.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the existing row-manager + persistence suites for regressions**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_row_manager.py pluggable_protocol_tree/tests/test_persistence.py -v`
Expected: PASS (no regressions — new params default to backward-compatible behavior)

- [ ] **Step 6: Commit**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_protocol_validator.py
git commit -m "[PPT-17] Headless wiring: validate + log findings in from_json/set_state_from_json"
```

---

## Task 6: GUI wiring — `load_from_dialog` runs the validator + dialog

**Files:**
- Modify: `pluggable_protocol_tree/views/protocol_tree_pane.py:1114-1136`

- [ ] **Step 1: Add the import**

At the top of `protocol_tree_pane.py` (with the other `pluggable_protocol_tree` imports), add:

```python
from pluggable_protocol_tree.services.protocol_validator import (
    validate_protocol, confirm_report, CANCEL,
)
```

- [ ] **Step 2: Replace the body of `load_from_dialog`**

Replace lines 1128-1135 (the `try`/`except` block that parses + applies the
JSON) with the validating version. The device map comes from the sync
controller when present (authoritative device electrode->channel map); when
absent, the validator skips the device-dependent checks.

```python
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            columns = columns_factory()
            device_map = None
            if self.device_viewer_sync is not None:
                device_map = dict(self.device_viewer_sync.electrode_ids_channels_map)
            report = validate_protocol(data, columns, device_map)
            if not report.is_empty:
                if confirm_report(report, parent=parent or self) == CANCEL:
                    return None
            # report already shown in the dialog -> don't re-log it
            self.manager.set_state_from_json(
                data, columns=columns, report_findings=False,
            )
        except Exception as e:
            error_dialog(parent=parent or self,
                         title="Load error", message=str(e))
            return None
        return path
```

- [ ] **Step 3: Run the pane / file-menu suites**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/test_protocol_tree_pane.py pluggable_protocol_tree/tests/test_protocol_tree_pane_file_menu.py -v`
Expected: PASS — a clean protocol produces an empty report, so the dialog never opens and the existing load behavior is unchanged.

- [ ] **Step 4: Commit**

```bash
git add pluggable_protocol_tree/views/protocol_tree_pane.py
git commit -m "[PPT-17] GUI wiring: validate + confirm dialog in load_from_dialog"
```

---

## Task 7: Full-suite regression check + close-out

- [ ] **Step 1: Run the whole pluggable_protocol_tree suite**

Run: `pixi run --manifest-path ..\pixi-microdrop\microdrop-py\pyproject.toml python -m pytest pluggable_protocol_tree/tests/ -q`
Expected: PASS (no regressions).

- [ ] **Step 2: Push the branch and open a PR**

```bash
git push -u origin issue-423-protocol-load-validation
gh pr create --repo Blue-Ocean-Technologies-Inc/Microdrop --base main \
  --title "[PPT-17] Validate loaded protocol against current device (#423)" \
  --body "Implements issue #423 core checks: electrode-ID validity, stale channel mappings, and orphan columns. Pure validator + GUI dialog / headless logger presenters. See docs/superpowers/specs/2026-06-11-issue-423-protocol-load-validation-design.md."
```

---

## Self-review notes

- **Spec coverage:** check 1 (electrode-ID validity) → Task 2; check 2 (stale channel) → Task 3; check 4 (orphan column) → Task 1; GUI two-tier dialog with drop-columns override → Task 4 + Task 6; headless logger output → Task 4 + Task 5; no-device skip + malformed-input safety → Task 3; device-truth source (`device_viewer_sync.electrode_ids_channels_map`) → Task 6. Deferred (loop well-formedness, structural sanity) are explicitly out of scope per the spec.
- **Type consistency:** `Finding(severity, category, title, items)`, `ValidationReport.findings/errors/warnings/is_empty`, `validate_protocol(data, columns, device_electrode_to_channel)`, `log_report(report)`, `confirm_report(report, parent)`, constants `PROCEED`/`CANCEL`/`SEVERITY_ERROR`/`SEVERITY_WARNING` are used identically across all tasks.
- **No placeholders:** every code step shows complete code; every run step shows the exact command + expected outcome.
