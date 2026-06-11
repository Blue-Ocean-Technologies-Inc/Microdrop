"""Pure protocol-load validation (issue #423, PPT-17).

``validate_protocol`` reads the raw serialized protocol JSON (output of
``services.persistence.serialize_tree``) and returns a structured
``ValidationReport`` covering three checks (orphan column / electrode id /
stale channel). ``log_report`` is the headless presenter (module logger);
the GUI dialog presenter ``confirm_report`` lives in
``views.protocol_validator_presenter`` so this service stays Qt-free.

The function is side-effect free (no Qt, no RowManager, no I/O) so it is
trivially unit-testable.
"""

from traits.api import Bool, Enum, HasTraits, Instance, List, Property, Str

from logger.logger_service import get_logger
from pluggable_protocol_tree.consts import ELECTRODE_TO_CHANNEL_KEY

logger = get_logger(__name__)

SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

# Builtin column ids whose values carry electrode references.
ROUTES_COL_ID = "routes"
ELECTRODES_COL_ID = "electrodes"


class Finding(HasTraits):
    severity = Enum(SEVERITY_WARNING, SEVERITY_ERROR)
    category = Enum("orphan_column", "electrode_id", "stale_channel")
    title = Str()
    items = List(Str, desc="detail lines")


class ValidationReport(HasTraits):
    findings = List(Instance(Finding))

    errors = Property(List(Instance(Finding)), observe="findings")
    warnings = Property(List(Instance(Finding)), observe="findings")
    is_empty = Property(Bool, observe="findings")

    def _get_errors(self):
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    def _get_warnings(self):
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    def _get_is_empty(self):
        return not self.findings


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


def _value_slice_index(fields, col_id):
    """Index into a row's value slice (row[4:]) for ``col_id``, or None.
    The first four fields are fixed row metadata (depth/uuid/type/name) -
    hence the -4 shift from the position in the full ``fields`` list."""
    try:
        field_list_pos = fields.index(col_id)
    except ValueError:
        return None
    return field_list_pos - 4 if field_list_pos >= 4 else None


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


def validate_protocol(data, columns, device_electrode_to_channel) -> ValidationReport:
    """Validate raw serialized protocol ``data`` against the live ``columns``
    and the device's ``device_electrode_to_channel`` map. Never raises on
    malformed input - returns an empty/partial report instead."""
    findings = []
    if not isinstance(data, dict):
        return ValidationReport(findings=findings)

    col_specs = data.get("columns")
    if not isinstance(col_specs, list):
        col_specs = []

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

    # --- electrode ID validity (device-dependent) ---
    device_map = device_electrode_to_channel or {}
    if device_map:
        fields = data.get("fields") or []
        rows = data.get("rows") or []
        dotted = _row_dotted_ids(rows)
        routes_idx = _value_slice_index(fields, ROUTES_COL_ID)
        electrodes_idx = _value_slice_index(fields, ELECTRODES_COL_ID)

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

        proto_map = (data.get("protocol_metadata") or {}).get(ELECTRODE_TO_CHANNEL_KEY) or {}
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

    return ValidationReport(findings=findings)


def log_report(report) -> None:
    """Headless presenter: emit each finding via the module logger. Errors at
    ERROR level, warnings at WARNING level. Never blocks."""
    for f in report.errors:
        logger.error(f"Protocol load: {f.title}")
        for item in f.items:
            logger.error(f"    - {item}")
    for f in report.warnings:
        logger.warning(f"Protocol load: {f.title}")
        for item in f.items:
            logger.warning(f"    - {item}")

