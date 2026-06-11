# Protocol-load validation (issue #423, PPT-17) — design

**Issue:** [#423](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/issues/423)
**Date:** 2026-06-11
**Scope (this pass):** core device-compatibility checks — electrode-ID validity,
stale channel mappings, and orphan-column detection. Loop-route
well-formedness and structural-sanity checks are deferred to follow-ups.

## Problem

When a protocol is loaded into the pluggable protocol tree (File > Open, or the
headless `RowManager.from_json` / `set_state_from_json` paths) there is currently
**no validation** that it is compatible with the device currently loaded in the
device viewer. A protocol authored on a different device (or hand-edited) can
reference electrode IDs that don't exist, or that now map to a different channel.
Today this only surfaces at run time as a silent per-phase skip
(`RoutesHandler` logs `"electrode {e!r} has no channel mapping; actuation channel
skipped"`), so a step appears to "do nothing" with no up-front warning. Columns
whose contributing plugin is absent are likewise dropped silently during
`deserialize_tree`.

We want to catch these at **load time** and surface them — as a dialog in the
GUI, and as printed log output in headless mode.

## Scope

Three checks this pass:

| # | Check | Comparison | Severity |
|---|-------|------------|----------|
| 1 | **Electrode-ID validity** | every electrode ID referenced by any step's `routes` or `electrodes` column exists in the device's electrode set | warning |
| 2 | **Stale channel mapping** | the protocol's stored `protocol_metadata["electrode_to_channel"][E]` equals the device's current channel for `E` | warning |
| 4 | **Orphan column** | every saved `col_id` resolves to a live column (its plugin is loaded); otherwise its values are silently dropped on load | error |

Out of scope (deferred): loop-route well-formedness (issue check 3) and
structural sanity — reps/duration/trail ranges, empty steps, empty protocol
(issue check 5).

## Architecture

Three isolated pieces. The validator is a pure function; presentation is split
into two interchangeable presenters so the same report drives both GUI and
headless flows.

### 1. Pure validator — `pluggable_protocol_tree/services/protocol_validator.py`

```python
@dataclass(frozen=True)
class Finding:
    severity: str          # "warning" | "error"
    category: str          # "electrode_id" | "stale_channel" | "orphan_column"
    title: str             # short human summary
    items: list[str]       # detail lines (e.g. "E12  (steps 1.2, 3)")

@dataclass(frozen=True)
class ValidationReport:
    findings: list[Finding]
    @property
    def errors(self) -> list[Finding]: ...
    @property
    def warnings(self) -> list[Finding]: ...
    @property
    def is_empty(self) -> bool: ...

def validate_protocol(
    data: dict,
    columns: list,
    device_electrode_to_channel: dict | None,
) -> ValidationReport:
    ...
```

- **Pure**: no Qt, no `RowManager`, no I/O. Operates only on the raw serialized
  JSON `data` (output of `serialize_tree`), the live column list, and the
  device's electrode→channel map. Fully unit-testable with crafted dicts.
- **Inputs it reads from `data`:**
  - `data["columns"]` — list of `{"id": col_id, ...}` → orphan detection vs
    `{c.model.col_id for c in columns}`.
  - `data["fields"]` — to find the column index of `"routes"` and
    `"electrodes"`.
  - `data["rows"]` — `[depth, uuid, type, name, *values]`; the `routes` value is
    `list[list[str]]`, the `electrodes` value is `list[str]`.
  - `data["protocol_metadata"]["electrode_to_channel"]` — protocol's stored map
    for the stale-mapping check.
- **Step labels:** referenced-electrode findings name *which steps* reference an
  ID. A 1-indexed dotted id (e.g. `1.2`) is reconstructed from the rows' `depth`
  sequence using a per-depth counter stack, matching the existing `dotted_id`
  convention in `device_viewer_sync._publish_for_row`
  (`".".join(str(i + 1) for i in row.path)`).
- **No-device behavior:** if `device_electrode_to_channel` is `None` or empty,
  checks 1 and 2 are skipped (validity is undeterminable without a device). The
  device-independent orphan-column check (4) always runs.

#### Check details

1. **Electrode-ID validity** — collect every electrode ID appearing in any
   step's `routes` (flattened) or `electrodes`. Any not present as a key in
   `device_electrode_to_channel` → one warning Finding listing each unknown ID
   and the dotted ids of the steps referencing it.
2. **Stale channel mapping** — for each electrode `E` in the protocol's
   `electrode_to_channel` that is also a key in the device map: if
   `protocol_map[E] != device_map[E]` → a warning Finding listing
   `E: protocol ch X → device ch Y`. (Electrodes referenced by steps but absent
   from the device map are already covered by check 1.)
3. **Orphan column** — any `col_id` in `data["columns"]` not present in the live
   column set → an error Finding. These values are dropped by `deserialize_tree`
   today; the finding makes that data loss explicit.

### 2. Presenters — same module

```python
PROCEED = "proceed"
CANCEL  = "cancel"

def confirm_report(report: ValidationReport, parent=None) -> str:
    """GUI: one summary dialog via microdrop_application.dialogs.pyface_wrapper.
    Returns PROCEED or CANCEL."""

def log_report(report: ValidationReport) -> None:
    """Headless: emit findings via get_logger(__name__) — logger.error() for
    error findings, logger.warning() for warnings. Never blocks."""
```

- **`confirm_report`** builds a single two-tier summary dialog with
  `pyface_wrapper.confirm` (no raw `QMessageBox`):
  - **Errors present (orphan columns):** default action is Cancel; an explicit
    `Load anyway (drop columns)` button maps to PROCEED. Errors and warnings are
    listed in separate sections (HTML `informative`, full lists in the
    collapsible `detail` pane).
  - **Warnings only:** `Proceed anyway` / `Cancel`.
- **`log_report`** formats each finding to a log line at the matching level.
  Consistent with the rest of the codebase (every module uses
  `logger.logger_service.get_logger`); console-visible and captured by handlers.

### 3. Wiring

**Headless** — `RowManager.from_json` and `set_state_from_json` gain:
```python
def set_state_from_json(self, data, columns,
                        device_electrode_to_channel=None,
                        report_findings=True): ...
```
When `report_findings` is true they call `validate_protocol(...)` +
`log_report(...)` before applying state, then proceed regardless (headless
cannot prompt; orphan columns still drop, exactly as today, but now printed).
Every headless caller (tests, scripts, executor) thus gets findings printed for
free. With no device map passed, checks 1 and 2 skip and orphan-column findings
still print.

**GUI** — `protocol_tree_pane.load_from_dialog` does the presentation itself so
it can abort before mutating:
```python
data = json.load(f)
columns = columns_factory()
device_map = (self.device_viewer_sync.electrode_ids_channels_map
              if self.device_viewer_sync is not None else None)
report = validate_protocol(data, columns, device_map)
if not report.is_empty and confirm_report(report, parent=self) == CANCEL:
    return None
self.manager.set_state_from_json(
    data, columns=columns, report_findings=False,   # dialog already showed them
)
```
`report_findings=False` prevents the dialog's findings from being *re-printed* by
`set_state_from_json`.

**Device truth** is `device_viewer_sync.electrode_ids_channels_map`, populated
authoritatively from `DEVICE_VIEWER_GEOMETRY_CHANGED` (the loaded SVG's
electrode→channel map). It is independent of the protocol's stored
`electrode_to_channel`, which is exactly what makes the stale-mapping comparison
meaningful.

## Error handling

- Malformed `data` (missing `columns`/`fields`/`rows` keys, non-list rows) — the
  validator guards with `.get(...)` and defensive type checks and returns an
  empty/partial report rather than raising; load proceeds to the existing
  `set_state_from_json` try/except which already shows a `Load error` dialog for
  truly broken files. The validator must never be the thing that breaks a load.
- A `None` device-sync controller (demo windows that don't wire one) → device
  map treated as absent → checks 1 & 2 skipped.

## Testing

- **Validator (primary):** unit tests with hand-built `data` dicts and fake
  column lists / device maps.
  - unknown electrode ID in `electrodes` and in `routes` → check-1 warning with
    correct step dotted-ids.
  - stale mapping (protocol ch ≠ device ch) → check-2 warning; matching mapping →
    no finding.
  - orphan `col_id` → check-4 error.
  - empty/None device map → checks 1 & 2 skipped, orphan still reported.
  - clean protocol → `is_empty` report.
  - malformed `data` → no exception, empty/partial report.
  - dotted-id reconstruction from nested `depth` sequence.
- **Presenters:** `log_report` emits at the right levels (caplog);
  `confirm_report` decision mapping with `pyface_wrapper.confirm` monkeypatched
  (errors → default Cancel + override → PROCEED; warnings-only → Proceed/Cancel).
- GUI `load_from_dialog` wiring is kept thin; not directly unit-tested (Qt file
  dialog).

## Likely touch points

- New: `pluggable_protocol_tree/services/protocol_validator.py`
- New: `pluggable_protocol_tree/tests/test_protocol_validator.py`
- Edit: `pluggable_protocol_tree/models/row_manager.py`
  (`from_json`, `set_state_from_json` signatures + validate/log call)
- Edit: `pluggable_protocol_tree/views/protocol_tree_pane.py` (`load_from_dialog`)
